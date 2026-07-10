"""Tiny local Enviro receiver and dashboard."""
from datetime import datetime, timezone
import json
from pathlib import Path

from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).parent
app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))
STORE = BASE_DIR / "data.json"


def load_data():
    if not STORE.exists():
        return {"provisioning": [], "readings": []}
    try:
        return json.loads(STORE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"provisioning": [], "readings": []}


def save_data(data):
    temporary = STORE.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2))
    temporary.replace(STORE)


def record(kind, payload):
    data = load_data()
    event = {"received_at": datetime.now(timezone.utc).isoformat(), **payload}
    data[kind].append(event)
    save_data(data)
    return event


def dashboard_summary(data):
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
    summary = dashboard_summary(data)
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
    return jsonify(record("readings", payload)), 201


@app.get("/api/data")
def data():
    return jsonify(load_data())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
