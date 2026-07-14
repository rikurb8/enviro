"""Tiny local Enviro receiver and dashboard."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, redirect, render_template, request, url_for
from sqlmodel import Session, select

import migrations
from db import KINDS, Event, WateringCommand, engine

BASE_DIR = Path(__file__).parent
app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))


def load_data():
    data = {kind: [] for kind in KINDS}
    with Session(engine) as session:
        for event in session.exec(select(Event).order_by(Event.id)).all():
            data.setdefault(event.kind, []).append(event.payload)
    return data


def load_commands():
    expire_pending_commands()
    with Session(engine) as session:
        return session.exec(select(WateringCommand).order_by(WateringCommand.created_at.desc())).all()


def command_json(command):
    return {
        "id": command.id,
        "device_uid": command.device_uid,
        "amounts": command.amounts,
        "status": command.status,
        "created_at": command.created_at,
        "expires_at": command.expires_at,
        "delivered_at": command.delivered_at,
        "acknowledged_at": command.acknowledged_at,
        "result": command.result,
    }


def expire_pending_commands():
    now = datetime.now(timezone.utc).isoformat()
    with Session(engine) as session:
        commands = session.exec(
            select(WateringCommand).where(
                WateringCommand.status == "pending",
                WateringCommand.expires_at <= now,
            )
        ).all()
        for command in commands:
            command.status = "expired"
            session.add(command)
        if commands:
            session.commit()


def remote_watering_capabilities(device_uid):
    with Session(engine) as session:
        events = session.exec(
            select(Event).where(Event.kind == "readings").order_by(Event.id.desc())
        ).all()
    for event in events:
        if event.payload.get("uid") == device_uid:
            return ((event.payload.get("capabilities") or {}).get("remote_watering") or {})
    return {}


def outstanding_command(session, device_uid):
    return session.exec(
        select(WateringCommand)
        .where(
            WateringCommand.device_uid == device_uid,
            WateringCommand.status.in_(["pending", "delivered"]),
        )
        .order_by(WateringCommand.created_at)
    ).first()


def record(kind, payload):
    event = {"received_at": datetime.now(timezone.utc).isoformat(), **payload}
    with Session(engine) as session:
        session.add(
            Event(kind=kind, received_at=event.get("received_at", ""), payload=event)
        )
        session.commit()
    return event


migrations.migrate()


def dashboard_summary(data, commands=None):
    """Build the small amount of derived data the dashboard needs."""
    provisioning = data.get("provisioning", [])
    readings = data.get("readings", [])
    devices = {}

    def device_key(event):
        return event.get("uid") or event.get("nickname") or event.get("model") or "unknown"

    def get_device(event):
        key = device_key(event)
        if key not in devices:
            devices[key] = {
                "uid": event.get("uid"),
                "nickname": event.get("nickname"),
                "model": event.get("model"),
                "registered": None,
                "latest": None,
                "latest_received_at": "",
            }
        device = devices[key]
        device["uid"] = device["uid"] or event.get("uid")
        device["nickname"] = device["nickname"] or event.get("nickname")
        device["model"] = device["model"] or event.get("model")
        return device

    for event in provisioning:
        get_device(event)["registered"] = event
    for event in readings:
        device = get_device(event)
        received_at = event.get("received_at", "")
        if device["latest"] is None or received_at >= device["latest_received_at"]:
            device["latest"] = event
            device["latest_received_at"] = received_at

    all_events = [
        {"kind": "Provisioned", "event": event} for event in provisioning
    ] + [
        {"kind": "Reading", "event": event} for event in readings
    ]
    all_events.sort(key=lambda item: item["event"].get("received_at", ""), reverse=True)

    def device_sort_key(device):
        registered_at = device["registered"].get("received_at", "") if device["registered"] else ""
        return device["latest_received_at"] or registered_at

    commands = commands or []
    latest_commands = {}
    for command in commands:
        if command.device_uid not in latest_commands:
            latest_commands[command.device_uid] = command_json(command)
    for device in devices.values():
        device["watering_command"] = latest_commands.get(device["uid"])
        capability = ((device["latest"] or {}).get("capabilities") or {}).get("remote_watering")
        device["remote_watering"] = capability or {"ready": False, "max_ml": 100, "max_seconds": 60}

    devices = sorted(devices.values(), key=device_sort_key, reverse=True)
    timestamps = [item["event"].get("received_at", "") for item in all_events]
    models = sorted({device["model"] for device in devices if device["model"]})
    return {
        "devices": devices,
        "activity": all_events,
        "stats": {
            "devices": len(devices),
            "readings": len(readings),
            "models": models,
            "last_received": max(timestamps, default=""),
        },
    }


@app.get("/")
def dashboard():
    data = load_data()
    commands = load_commands()
    summary = dashboard_summary(data, commands)
    return render_template(
        "index.html",
        provisioning=list(reversed(data.get("provisioning", []))),
        readings=list(reversed(data.get("readings", []))),
        **summary,
    )


@app.post("/api/provisioned")
def provisioned():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Expected a JSON object"), 400
    return jsonify(record("provisioning", payload)), 201


@app.post("/api/readings")
def readings():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Expected a JSON object"), 400

    response = record("readings", payload)
    uid = payload.get("uid")
    if uid and payload.get("model") == "grow":
        expire_pending_commands()
        with Session(engine) as session:
            command = outstanding_command(session, uid)
            if command:
                if command.status == "pending":
                    command.status = "delivered"
                    command.delivered_at = datetime.now(timezone.utc).isoformat()
                    session.add(command)
                    session.commit()
                    session.refresh(command)
                response["watering_command"] = {
                    "id": command.id,
                    "amounts": command.amounts,
                    "ack_url": url_for("acknowledge_watering_command", command_id=command.id, _external=True),
                }
    return jsonify(response), 201


@app.post("/api/devices/<device_uid>/watering-commands")
def create_watering_command(device_uid):
    values = request.get_json(silent=True) if request.is_json else request.form
    if values is None or not hasattr(values, "get"):
        return jsonify(error="Expected a JSON object or form fields"), 400
    source = values.get("amounts", values)
    if not hasattr(source, "get"):
        return jsonify(error="Amounts must be an object"), 400
    capabilities = remote_watering_capabilities(device_uid)
    if not capabilities.get("ready"):
        return jsonify(error="Device has not reported a valid pump calibration"), 409
    max_ml = capabilities.get("max_ml", 100)
    if not isinstance(max_ml, (int, float)) or max_ml <= 0:
        max_ml = 100

    amounts = {}
    try:
        for channel in ("A", "B", "C"):
            raw = source.get(channel)
            if raw not in (None, ""):
                amount = float(raw)
                if not amount > 0 or not amount <= max_ml:
                    raise ValueError(f"Channel {channel} must be between 0 and {max_ml:g} ml")
                amounts[channel] = amount
    except (TypeError, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    if not amounts:
        return jsonify(error="At least one channel amount is required"), 400

    expire_pending_commands()
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        if outstanding_command(session, device_uid):
            return jsonify(error="Device already has an outstanding command"), 409
        command = WateringCommand(
            id=str(uuid4()),
            device_uid=device_uid,
            amounts=amounts,
            status="pending",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(hours=24)).isoformat(),
        )
        session.add(command)
        session.commit()
        session.refresh(command)

    if request.is_json:
        return jsonify(command_json(command)), 201
    return redirect(url_for("dashboard"))


@app.delete("/api/watering-commands/<command_id>")
def cancel_watering_command(command_id):
    with Session(engine) as session:
        command = session.get(WateringCommand, command_id)
        if not command:
            return jsonify(error="Command not found"), 404
        if command.status != "pending":
            return jsonify(error="Only pending commands can be cancelled"), 409
        command.status = "cancelled"
        session.add(command)
        session.commit()
        session.refresh(command)
    return jsonify(command_json(command))


@app.post("/api/watering-commands/<command_id>/cancel")
def cancel_watering_command_form(command_id):
    response = cancel_watering_command(command_id)
    if isinstance(response, tuple):
        return response
    return redirect(url_for("dashboard"))


@app.post("/api/watering-commands/<command_id>/ack")
def acknowledge_watering_command(command_id):
    payload = request.get_json(silent=True)
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict) or result.get("status") not in ("completed", "rejected", "interrupted"):
        return jsonify(error="Expected a terminal command result"), 400
    if result.get("id") != command_id:
        return jsonify(error="Result command ID does not match the endpoint"), 400

    with Session(engine) as session:
        command = session.get(WateringCommand, command_id)
        if not command:
            return jsonify(error="Command not found"), 404
        if command.status in ("completed", "rejected", "interrupted"):
            return jsonify(command_json(command))
        if command.status != "delivered":
            return jsonify(error="Command has not been delivered"), 409
        command.status = result["status"]
        command.result = result
        command.acknowledged_at = datetime.now(timezone.utc).isoformat()
        session.add(command)
        session.commit()
        session.refresh(command)
    return jsonify(command_json(command))


@app.get("/api/data")
def data():
    result = load_data()
    result["watering_commands"] = [command_json(command) for command in load_commands()]
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
