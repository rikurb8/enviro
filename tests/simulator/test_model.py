from copy import deepcopy
from datetime import datetime, timedelta, timezone

from enviro_simulator import model
from enviro_simulator.settings import DEFAULT_PROFILE


def profile(**changes):
    value = deepcopy(DEFAULT_PROFILE)
    value.update(changes)
    return value


def test_grow_model_is_deterministic_and_dries_moisture():
    cfg = profile(seed=42)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = model.initial_state(cfg, start)
    reading_a, state_a, _ = model.evolve(cfg, state, start + timedelta(hours=2))
    reading_b, state_b, _ = model.evolve(cfg, state, start + timedelta(hours=2))
    assert reading_a == reading_b
    assert state_a == state_b
    assert reading_a["moisture_a"] < cfg["initial"]["moisture_a"]


def test_auto_watering_changes_following_state():
    cfg = profile(auto_water=True, moisture_targets={"A": 60, "B": 50, "C": 50})
    cfg["initial"]["moisture_a"] = 20
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    reading, state, actions = model.evolve(cfg, model.initial_state(cfg, start), start)
    assert reading["moisture_a"] < 60
    assert actions[0]["channel"] == "A"
    assert state["values"]["moisture_a"] > reading["moisture_a"]


def test_remote_watering_validates_and_changes_moisture():
    cfg = profile(pump_ml_per_second=2.0)
    state = model.initial_state(cfg)
    before = state["values"]["moisture_a"]
    result, state = model.execute_remote(cfg, state, {"id": "c1", "amounts": {"A": 20}})
    assert result["status"] == "completed"
    assert result["channels"][0]["seconds"] == 10
    assert state["values"]["moisture_a"] > before


def test_remote_watering_rejects_unsafe_runtime():
    cfg = profile(pump_ml_per_second=0.1, remote_watering_max_seconds=60)
    result, _ = model.execute_remote(cfg, model.initial_state(cfg), {"id": "c1", "amounts": {"A": 20}})
    assert result["status"] == "rejected"
    assert "runtime" in result["error"]
