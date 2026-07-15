"""Async fleet daemon and loopback control API."""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sqlite3
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import NAMESPACE_URL, uuid4, uuid5

from aiohttp import ClientError, ClientSession, ClientTimeout, web

from . import model
from .settings import DB_PATH, DEFAULT_PROFILE, HOST, PORT
from .storage import Store, utcnow

LOG = logging.getLogger("enviro-simulator")


def deep_merge(base, changes):
    result = deepcopy(base)
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def validate_profile(profile):
    if profile.get("model") != "grow":
        raise ValueError("v1 supports only the grow model")
    for key in ("reading_frequency", "upload_frequency", "time_scale"):
        if not isinstance(profile.get(key), (int, float)) or profile[key] <= 0:
            raise ValueError(f"{key} must be greater than zero")
    if not str(profile.get("dashboard_url", "")).startswith(("http://", "https://")):
        raise ValueError("dashboard_url must be an http(s) URL")


class SimulatorDaemon:
    def __init__(self, db_path: Path = DB_PATH):
        self.store = Store(db_path)
        self.session: Optional[ClientSession] = None
        self.stop_event = asyncio.Event()

    async def start(self):
        self.session = ClientSession(timeout=ClientTimeout(total=10))

    async def close(self):
        if self.session:
            await self.session.close()
        self.store.close()

    @staticmethod
    def simulated_now(device):
        profile = device["profile"]
        wall_anchor = datetime.fromisoformat(profile["clock_wall_anchor"])
        sim_anchor = datetime.fromisoformat(profile["clock_sim_anchor"])
        elapsed = (datetime.now(timezone.utc) - wall_anchor).total_seconds()
        return sim_anchor + timedelta(seconds=elapsed * float(profile["time_scale"]))

    async def create_device(self, values, deterministic=False):
        nickname = str(values.get("nickname", "")).strip()
        if not nickname:
            raise ValueError("nickname is required")
        profile = deep_merge(DEFAULT_PROFILE, {k: v for k, v in values.items() if k not in {"uid", "nickname", "enabled", "online", "simulated_start"}})
        validate_profile(profile)
        now = datetime.now(timezone.utc)
        profile["clock_wall_anchor"] = now.isoformat()
        profile["clock_sim_anchor"] = values.get("simulated_start", now.isoformat())
        uid = values.get("uid")
        if not uid:
            uid = uuid5(NAMESPACE_URL, f"enviro-simulator:{nickname}").hex[:16] if deterministic else uuid4().hex[:16]
        interval = float(profile["reading_frequency"]) * 60 / float(profile["time_scale"])
        simulated_start = datetime.fromisoformat(profile["clock_sim_anchor"])
        device = self.store.create_device(uid, nickname, profile, model.initial_state(profile, simulated_start), time.time() + interval)
        if "enabled" in values or "online" in values:
            device = self.store.update_device(
                uid,
                **{key: values[key] for key in ("enabled", "online") if key in values},
            )
        await self.call_home(device)
        return self.store.get_device(uid)

    async def call_home(self, device):
        payload = {"event": "provisioned", "model": "grow", "nickname": device["nickname"], "uid": device["uid"]}
        url = device["profile"]["dashboard_url"].rstrip("/") + "/api/provisioned"
        if not device["online"]:
            self.store.event(device["uid"], "call_home_skipped", {"reason": "offline"})
            return False
        try:
            async with self.session.post(url, json=payload) as response:
                if response.status not in (200, 201, 202):
                    raise RuntimeError(f"HTTP {response.status}")
            self.store.event(device["uid"], "call_home_sent", {"url": url})
            return True
        except (ClientError, asyncio.TimeoutError, RuntimeError) as exc:
            self.store.update_device(device["uid"], last_error=f"call-home: {exc}")
            self.store.event(device["uid"], "call_home_failed", {"error": str(exc)})
            return False

    async def generate_reading(self, device, scheduled=False):
        simulated_now = self.simulated_now(device)
        reading, state, actions = model.evolve(
            device["profile"], device["state"], simulated_now, device["overrides"]
        )
        payload = {
            "nickname": device["nickname"],
            "timestamp": simulated_now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "readings": reading,
            "model": "grow",
            "uid": device["uid"],
            "capabilities": {"remote_watering": model.capabilities(device["profile"])},
        }
        values = {"state": state, "last_reading_at": utcnow(), "last_error": None}
        if scheduled:
            interval = float(device["profile"]["reading_frequency"]) * 60 / float(device["profile"]["time_scale"])
            values["next_due"] = max(time.time(), float(device["next_due"])) + interval
        self.store.update_device(device["uid"], **values)
        self.store.enqueue(device["uid"], payload)
        self.store.event(device["uid"], "reading", {"timestamp": payload["timestamp"], "automatic_watering": actions})
        for action in actions:
            self.store.event(device["uid"], "automatic_watering", action)
        await self.flush_device(self.store.get_device(device["uid"]))
        return payload

    async def flush_device(self, device):
        if not device["online"]:
            return
        minimum = int(device["profile"]["upload_frequency"])
        if self.store.outbox_count(device["uid"]) < minimum and not self.store.has_failed_outbox(device["uid"]):
            return
        now = time.time()
        url = device["profile"]["dashboard_url"].rstrip("/") + "/api/readings"
        for row in self.store.due_outbox(device["uid"], now):
            try:
                async with self.session.post(url, json=json.loads(row["payload"])) as response:
                    body = await response.json(content_type=None)
                    if response.status not in (200, 201, 202):
                        raise RuntimeError(f"HTTP {response.status}")
                self.store.delivered(row["id"])
                self.store.update_device(device["uid"], last_upload_at=utcnow(), last_error=None)
                self.store.event(device["uid"], "uploaded", {"outbox_id": row["id"]})
                command = body.get("watering_command") if isinstance(body, dict) else None
                if isinstance(command, dict):
                    await self.handle_command(device["uid"], command)
            except (ClientError, asyncio.TimeoutError, RuntimeError, ValueError) as exc:
                attempts = row["attempts"] + 1
                delay = min(300, 2 ** min(attempts, 8))
                self.store.fail_delivery(row["id"], attempts, time.time() + delay)
                self.store.update_device(device["uid"], last_error=f"upload: {exc}")
                self.store.event(device["uid"], "upload_failed", {"error": str(exc), "retry_seconds": delay})
                break

    async def handle_command(self, uid, command):
        command_id = command.get("id")
        previous = self.store.get_command(command_id) if command_id else None
        device = self.store.get_device(uid)
        if previous:
            result = previous["result"]
        else:
            result, state = model.execute_remote(device["profile"], device["state"], command)
            self.store.update_device(uid, state=state)
            self.store.save_command(uid, command, result, command.get("ack_url"))
            self.store.event(uid, "remote_watering", result)
        await self.send_ack(self.store.get_command(command_id))

    async def send_ack(self, command):
        if not command or command["acknowledged"] or not command["ack_url"]:
            return
        device = self.store.get_device(command["device_uid"])
        if not device or not device["online"]:
            return
        try:
            async with self.session.post(command["ack_url"], json={"result": command["result"]}) as response:
                if response.status not in (200, 201, 202):
                    raise RuntimeError(f"HTTP {response.status}")
            self.store.acked(command["command_id"])
            self.store.event(command["device_uid"], "command_acknowledged", {"id": command["command_id"]})
        except (ClientError, asyncio.TimeoutError, RuntimeError) as exc:
            attempts = command["attempts"] + 1
            delay = min(300, 2 ** min(attempts, 8))
            self.store.fail_ack(command["command_id"], attempts, time.time() + delay)
            self.store.event(command["device_uid"], "ack_failed", {"id": command["command_id"], "error": str(exc)})

    async def scheduler(self):
        while not self.stop_event.is_set():
            now = time.time()
            jobs = []
            for device in self.store.list_devices():
                if not device["enabled"]:
                    continue
                if float(device["next_due"]) <= now:
                    jobs.append(self.generate_reading(device, scheduled=True))
                elif device["online"] and (
                    device["queued"] >= int(device["profile"]["upload_frequency"])
                    or self.store.has_failed_outbox(device["uid"])
                ):
                    jobs.append(self.flush_device(device))
            for row in self.store.pending_acks(now):
                command = dict(row)
                command["result"] = json.loads(command["result"])
                jobs.append(self.send_ack(command))
            if jobs:
                results = await asyncio.gather(*jobs, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        LOG.error("scheduled simulator operation failed", exc_info=result)
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=0.25)
            except asyncio.TimeoutError:
                pass


def json_response(data, status=200):
    return web.json_response(data, status=status)


def create_app(daemon):
    routes = web.RouteTableDef()

    @routes.get("/health")
    async def health(request):
        devices = daemon.store.list_devices()
        return json_response({"status": "running", "devices": len(devices), "active": sum(d["enabled"] for d in devices)})

    @routes.get("/devices")
    async def list_devices(request):
        return json_response(daemon.store.list_devices())

    @routes.post("/devices")
    async def create_device(request):
        try:
            return json_response(await daemon.create_device(await request.json()), 201)
        except (ValueError, sqlite3.IntegrityError) as exc:
            return json_response({"error": str(exc)}, 400)

    @routes.get("/devices/{identifier}")
    async def get_device(request):
        device = daemon.store.get_device(request.match_info["identifier"])
        return json_response(device or {"error": "not found"}, 200 if device else 404)

    @routes.patch("/devices/{identifier}")
    async def update_device(request):
        device = daemon.store.get_device(request.match_info["identifier"])
        if not device:
            return json_response({"error": "not found"}, 404)
        values = await request.json()
        profile_changes = values.pop("profile", {})
        direct_profile = {k: values.pop(k) for k in list(values) if k in DEFAULT_PROFILE}
        profile = deep_merge(device["profile"], deep_merge(profile_changes, direct_profile))
        try:
            validate_profile(profile)
        except ValueError as exc:
            return json_response({"error": str(exc)}, 400)
        allowed = {k: values[k] for k in ("nickname", "enabled", "online", "overrides") if k in values}
        if profile != device["profile"]:
            if profile["time_scale"] != device["profile"]["time_scale"]:
                profile["clock_sim_anchor"] = daemon.simulated_now(device).isoformat()
                profile["clock_wall_anchor"] = datetime.now(timezone.utc).isoformat()
            allowed["profile"] = profile
            if (
                profile["time_scale"] != device["profile"]["time_scale"]
                or profile["reading_frequency"] != device["profile"]["reading_frequency"]
            ):
                allowed["next_due"] = time.time() + float(profile["reading_frequency"]) * 60 / float(profile["time_scale"])
        return json_response(daemon.store.update_device(device["uid"], **allowed))

    @routes.delete("/devices/{identifier}")
    async def delete_device(request):
        device = daemon.store.get_device(request.match_info["identifier"])
        if not device:
            return json_response({"error": "not found"}, 404)
        if device["queued"] and request.query.get("force") != "true":
            return json_response({"error": "device has queued readings; use force=true"}, 409)
        daemon.store.delete_device(device["uid"])
        return json_response({"deleted": device["uid"]})

    @routes.post("/devices/{identifier}/trigger")
    async def trigger(request):
        device = daemon.store.get_device(request.match_info["identifier"])
        if not device:
            return json_response({"error": "not found"}, 404)
        return json_response(await daemon.generate_reading(device))

    @routes.post("/devices/{identifier}/actions/{action}")
    async def action(request):
        device = daemon.store.get_device(request.match_info["identifier"])
        if not device:
            return json_response({"error": "not found"}, 404)
        action = request.match_info["action"]
        mapping = {"enable": ("enabled", True), "disable": ("enabled", False), "online": ("online", True), "offline": ("online", False)}
        if action not in mapping:
            return json_response({"error": "unknown action"}, 400)
        key, value = mapping[action]
        return json_response(daemon.store.update_device(device["uid"], **{key: value}))

    @routes.get("/events")
    async def events(request):
        return json_response(daemon.store.recent_events(request.query.get("uid"), int(request.query.get("limit", 50))))

    @routes.post("/fleet/apply")
    async def fleet_apply(request):
        document = await request.json()
        entries = document.get("devices") if isinstance(document, dict) else None
        if not isinstance(entries, list):
            return json_response({"error": "fleet document must contain a devices array"}, 400)
        results = []
        for values in entries:
            existing = daemon.store.get_device(str(values.get("uid") or values.get("nickname", "")))
            if existing:
                changes = {k: v for k, v in values.items() if k not in {"uid", "nickname"}}
                profile = deep_merge(existing["profile"], changes)
                validate_profile(profile)
                daemon.store.update_device(existing["uid"], profile=profile)
                results.append({"uid": existing["uid"], "action": "updated"})
            else:
                created = await daemon.create_device(values, deterministic=True)
                results.append({"uid": created["uid"], "action": "created"})
        return json_response({"devices": results})

    @routes.post("/shutdown")
    async def shutdown(request):
        daemon.stop_event.set()
        return json_response({"status": "stopping"})

    app = web.Application()
    app.add_routes(routes)
    return app


async def run_daemon(host=HOST, port=PORT, db_path=DB_PATH):
    daemon = SimulatorDaemon(db_path)
    await daemon.start()
    runner = web.AppRunner(create_app(daemon))
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    LOG.info("control API listening on http://%s:%s", host, port)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, daemon.stop_event.set)
        except NotImplementedError:
            pass
    scheduler = asyncio.create_task(daemon.scheduler())
    await daemon.stop_event.wait()
    await scheduler
    await runner.cleanup()
    await daemon.close()
