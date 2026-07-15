"""Paths and defaults for the repository-local simulator."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = Path(os.environ.get("ENVIRO_SIM_STATE_DIR", ROOT / ".enviro-simulator"))
DB_PATH = STATE_DIR / "simulator.db"
PID_PATH = STATE_DIR / "daemon.pid"
LOG_PATH = STATE_DIR / "daemon.log"
HOST = os.environ.get("ENVIRO_SIM_HOST", "127.0.0.1")
PORT = int(os.environ.get("ENVIRO_SIM_PORT", "8765"))
CONTROL_URL = f"http://{HOST}:{PORT}"

DEFAULT_PROFILE = {
    "model": "grow",
    "dashboard_url": "http://127.0.0.1:5001",
    "reading_frequency": 15.0,
    "upload_frequency": 1,
    "time_scale": 1.0,
    "seed": 1,
    "auto_water": False,
    "moisture_targets": {"A": 50.0, "B": 50.0, "C": 50.0},
    "pump_ml_per_second": 2.0,
    "remote_watering_max_ml": 100.0,
    "remote_watering_max_seconds": 60.0,
    "initial": {
        "temperature": 21.0,
        "humidity": 50.0,
        "pressure": 1013.0,
        "luminance": 100.0,
        "moisture_a": 55.0,
        "moisture_b": 55.0,
        "moisture_c": 55.0,
    },
}
