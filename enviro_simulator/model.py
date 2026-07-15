"""Deterministic, stateful Enviro Grow telemetry model."""
from __future__ import annotations

import math
import random
from copy import deepcopy
from datetime import datetime, timezone
from typing import Optional

CHANNELS = ("A", "B", "C")


def clamp(value, low, high):
    return max(low, min(high, value))


def initial_state(profile, now: Optional[datetime] = None):
    now = now or datetime.now(timezone.utc)
    values = deepcopy(profile["initial"])
    return {"values": values, "last_model_time": now.isoformat(), "cycle": 0}


def evolve(profile, state, simulated_now: datetime, overrides=None):
    """Return (reading, new state, automatic watering actions)."""
    state = deepcopy(state)
    values = state["values"]
    last = datetime.fromisoformat(state["last_model_time"])
    hours = max(0.0, (simulated_now - last).total_seconds() / 3600.0)
    cycle = int(state.get("cycle", 0)) + 1
    rng = random.Random(int(profile.get("seed", 1)) * 1_000_003 + cycle)

    phase = (simulated_now.hour + simulated_now.minute / 60.0) / 24.0 * math.tau
    target_temp = 21.0 + 2.5 * math.sin(phase - math.pi / 2)
    values["temperature"] += (target_temp - values["temperature"]) * min(1.0, hours / 4.0) + rng.uniform(-0.08, 0.08)
    target_humidity = 52.0 - (values["temperature"] - 21.0) * 1.5
    values["humidity"] += (target_humidity - values["humidity"]) * min(1.0, hours / 6.0) + rng.uniform(-0.15, 0.15)
    values["pressure"] += rng.uniform(-0.12, 0.12) * max(1.0, math.sqrt(hours))
    daylight = max(0.0, math.sin(phase - math.pi / 2))
    values["luminance"] = daylight * 900.0 + rng.uniform(0.0, 8.0)

    for channel in CHANNELS:
        key = f"moisture_{channel.lower()}"
        values[key] -= hours * (0.35 + 0.08 * CHANNELS.index(channel))
        values[key] += rng.uniform(-0.08, 0.08)
        values[key] = clamp(values[key], 0.0, 100.0)

    reading = {
        "temperature": round(clamp(values["temperature"], -20, 60), 2),
        "humidity": round(clamp(values["humidity"], 0, 100), 2),
        "pressure": round(clamp(values["pressure"], 850, 1100), 2),
        "luminance": round(max(0, values["luminance"]), 2),
        **{f"moisture_{c.lower()}": round(values[f"moisture_{c.lower()}"] , 2) for c in CHANNELS},
    }
    for key, value in (overrides or {}).items():
        if key in reading:
            reading[key] = float(value)
            values[key] = float(value)

    actions = []
    if profile.get("auto_water"):
        targets = profile.get("moisture_targets", {})
        for channel in CHANNELS:
            key = f"moisture_{channel.lower()}"
            target = float(targets.get(channel, 50))
            if reading[key] < target:
                seconds = round((target - reading[key]) / 25.0, 1)
                # A deliberately simple response model: five percentage points
                # per pump-second, capped by the physical sensor range.
                gain = seconds * 5.0
                values[key] = clamp(values[key] + gain, 0, 100)
                actions.append({"channel": channel, "seconds": seconds, "moisture_gain": round(gain, 2)})

    state.update(values=values, last_model_time=simulated_now.isoformat(), cycle=cycle)
    return reading, state, actions


def capabilities(profile):
    rate = profile.get("pump_ml_per_second")
    return {
        "ready": isinstance(rate, (int, float)) and rate > 0,
        "max_ml": profile.get("remote_watering_max_ml", 100),
        "max_seconds": profile.get("remote_watering_max_seconds", 60),
        "auto_water": bool(profile.get("auto_water")),
    }


def execute_remote(profile, state, command):
    command_id = command.get("id") if isinstance(command, dict) else None
    result = {"id": command_id, "status": "rejected"}
    if not isinstance(command_id, str) or not command_id:
        result["error"] = "missing command id"
        return result, state
    amounts = command.get("amounts")
    if not isinstance(amounts, dict):
        result["error"] = "amounts must be an object"
        return result, state
    rate = profile.get("pump_ml_per_second")
    max_ml = profile.get("remote_watering_max_ml", 100)
    max_seconds = profile.get("remote_watering_max_seconds", 60)
    if not isinstance(rate, (int, float)) or rate <= 0:
        result["error"] = "pump calibration is missing"
        return result, state

    runs = []
    try:
        unknown = set(amounts) - set(CHANNELS)
        if unknown:
            raise ValueError(f"unknown channel {sorted(unknown)[0]}")
        for channel in CHANNELS:
            if channel not in amounts:
                continue
            amount = float(amounts[channel])
            if not 0 < amount <= max_ml:
                raise ValueError(f"channel {channel} amount is outside the allowed range")
            seconds = amount / rate
            if seconds > max_seconds:
                raise ValueError(f"channel {channel} runtime exceeds the safety limit")
            runs.append((channel, amount, seconds))
        if not runs:
            raise ValueError("at least one channel amount is required")
    except (TypeError, ValueError) as exc:
        result["error"] = str(exc)
        return result, state

    state = deepcopy(state)
    completed = []
    for channel, amount, seconds in runs:
        key = f"moisture_{channel.lower()}"
        gain = amount * 0.35
        state["values"][key] = clamp(state["values"][key] + gain, 0, 100)
        completed.append({"channel": channel, "ml": amount, "seconds": seconds})
    return {"id": command_id, "status": "completed", "channels": completed}, state
