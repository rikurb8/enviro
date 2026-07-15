"""Command-line client and daemon lifecycle commands."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .daemon import run_daemon
from .settings import CONTROL_URL, LOG_PATH, PID_PATH, STATE_DIR


def request(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        CONTROL_URL + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            message = json.load(exc).get("error", str(exc))
        except Exception:
            message = str(exc)
        raise SystemExit(f"error: {message}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"error: simulator daemon is not reachable at {CONTROL_URL}: {exc.reason}")


def output(value):
    print(json.dumps(value, indent=2, sort_keys=True))


def read_pid():
    try:
        return int(PID_PATH.read_text().strip())
    except (OSError, ValueError):
        return None


def process_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def daemon_run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()))
    try:
        asyncio.run(run_daemon())
    finally:
        try:
            if read_pid() == os.getpid():
                PID_PATH.unlink()
        except OSError:
            pass


def daemon_start():
    pid = read_pid()
    if process_alive(pid):
        raise SystemExit(f"simulator daemon is already running (pid {pid})")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_PATH.open("a")
    process = subprocess.Popen(
        [sys.executable, "-m", "enviro_simulator", "daemon", "run"],
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log.close()
    for _ in range(50):
        if process.poll() is not None:
            raise SystemExit(f"daemon failed to start; inspect {LOG_PATH}")
        try:
            request("GET", "/health")
            print(f"simulator daemon started (pid {process.pid})")
            return
        except SystemExit:
            time.sleep(0.1)
    process.terminate()
    raise SystemExit(f"daemon did not become ready; inspect {LOG_PATH}")


def daemon_stop():
    pid = read_pid()
    if not process_alive(pid):
        PID_PATH.unlink(missing_ok=True)
        raise SystemExit("simulator daemon is not running")
    try:
        request("POST", "/shutdown", {})
    except SystemExit:
        os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        if not process_alive(pid):
            print("simulator daemon stopped")
            return
        time.sleep(0.1)
    raise SystemExit(f"daemon pid {pid} did not stop")


def parse_value(raw):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def nested_values(items):
    result = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"error: expected KEY=VALUE, got {item!r}")
        path, raw = item.split("=", 1)
        target = result
        parts = path.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = parse_value(raw)
    return result


def build_parser():
    parser = argparse.ArgumentParser(prog="enviro-sim", description="Enviro Grow fleet simulator")
    commands = parser.add_subparsers(dest="command", required=True)

    daemon = commands.add_parser("daemon", help="manage the simulator daemon")
    daemon_sub = daemon.add_subparsers(dest="action", required=True)
    daemon_sub.add_parser("run", help="run in the foreground")
    daemon_sub.add_parser("start", help="start in the background")
    daemon_sub.add_parser("stop", help="stop the background daemon")
    daemon_sub.add_parser("status", help="show daemon health")
    daemon_sub.add_parser("logs", help="print the background daemon log")

    device = commands.add_parser("device", help="manage simulated devices")
    sub = device.add_subparsers(dest="action", required=True)
    create = sub.add_parser("create")
    create.add_argument("nickname")
    create.add_argument("--dashboard-url", default="http://127.0.0.1:5001")
    create.add_argument("--reading-frequency", type=float, default=15)
    create.add_argument("--upload-frequency", type=int, default=1)
    create.add_argument("--time-scale", type=float, default=1)
    create.add_argument("--seed", type=int, default=1)
    create.add_argument("--auto-water", action="store_true")
    create.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    sub.add_parser("list")
    show = sub.add_parser("show"); show.add_argument("device")
    update = sub.add_parser("update"); update.add_argument("device"); update.add_argument("--set", action="append", required=True)
    delete = sub.add_parser("delete"); delete.add_argument("device"); delete.add_argument("--force", action="store_true")
    for action in ("enable", "disable", "online", "offline", "trigger"):
        item = sub.add_parser(action); item.add_argument("device")
    override = sub.add_parser("override"); override.add_argument("device"); override.add_argument("values", nargs="+", metavar="SENSOR=VALUE")
    clear = sub.add_parser("clear-override"); clear.add_argument("device"); clear.add_argument("sensors", nargs="*")

    fleet = commands.add_parser("fleet", help="apply fleet definitions")
    fleet_sub = fleet.add_subparsers(dest="action", required=True)
    apply = fleet_sub.add_parser("apply"); apply.add_argument("file", type=Path)

    events = commands.add_parser("events", help="show recent simulator events")
    events.add_argument("--device"); events.add_argument("--limit", type=int, default=50)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "daemon":
        if args.action == "run": daemon_run()
        elif args.action == "start": daemon_start()
        elif args.action == "stop": daemon_stop()
        elif args.action == "status":
            try: output(request("GET", "/health"))
            except SystemExit: output({"status": "stopped"})
        elif args.action == "logs":
            if LOG_PATH.exists(): print(LOG_PATH.read_text(), end="")
            else: print("no daemon log")
        return

    if args.command == "device":
        if args.action == "create":
            payload = nested_values(args.set)
            payload.update(nickname=args.nickname, dashboard_url=args.dashboard_url,
                           reading_frequency=args.reading_frequency, upload_frequency=args.upload_frequency,
                           time_scale=args.time_scale, seed=args.seed, auto_water=args.auto_water)
            output(request("POST", "/devices", payload))
        elif args.action == "list": output(request("GET", "/devices"))
        elif args.action == "show": output(request("GET", f"/devices/{args.device}"))
        elif args.action == "update": output(request("PATCH", f"/devices/{args.device}", nested_values(args.set)))
        elif args.action == "delete": output(request("DELETE", f"/devices/{args.device}?force={'true' if args.force else 'false'}"))
        elif args.action in ("enable", "disable", "online", "offline"):
            output(request("POST", f"/devices/{args.device}/actions/{args.action}", {}))
        elif args.action == "trigger": output(request("POST", f"/devices/{args.device}/trigger", {}))
        elif args.action == "override":
            device = request("GET", f"/devices/{args.device}")
            overrides = dict(device.get("overrides", {})); overrides.update(nested_values(args.values))
            output(request("PATCH", f"/devices/{args.device}", {"overrides": overrides}))
        elif args.action == "clear-override":
            device = request("GET", f"/devices/{args.device}")
            overrides = dict(device.get("overrides", {}))
            if args.sensors:
                for sensor in args.sensors: overrides.pop(sensor, None)
            else: overrides = {}
            output(request("PATCH", f"/devices/{args.device}", {"overrides": overrides}))
        return

    if args.command == "fleet":
        output(request("POST", "/fleet/apply", json.loads(args.file.read_text())))
    elif args.command == "events":
        query = f"?limit={args.limit}" + (f"&uid={args.device}" if args.device else "")
        output(request("GET", "/events" + query))
