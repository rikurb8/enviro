from copy import deepcopy

from enviro_simulator import model
from enviro_simulator.settings import DEFAULT_PROFILE
from enviro_simulator.storage import Store


def test_outbox_and_device_state_survive_reopen(tmp_path):
    path = tmp_path / "sim.db"
    profile = deepcopy(DEFAULT_PROFILE)
    profile.update(clock_wall_anchor="2026-01-01T00:00:00+00:00", clock_sim_anchor="2026-01-01T00:00:00+00:00")
    store = Store(path)
    store.create_device("uid-1", "grow-one", profile, model.initial_state(profile), 10)
    store.enqueue("uid-1", {"uid": "uid-1", "readings": {"moisture_a": 50}})
    store.close()

    reopened = Store(path)
    assert reopened.get_device("grow-one")["queued"] == 1
    assert len(reopened.due_outbox("uid-1", 100)) == 1
    reopened.close()


def test_device_delete_cascades_outbox(tmp_path):
    store = Store(tmp_path / "sim.db")
    profile = deepcopy(DEFAULT_PROFILE)
    profile.update(clock_wall_anchor="2026-01-01T00:00:00+00:00", clock_sim_anchor="2026-01-01T00:00:00+00:00")
    store.create_device("uid-1", "grow-one", profile, model.initial_state(profile), 10)
    store.enqueue("uid-1", {"reading": 1})
    store.delete_device("uid-1")
    assert store.list_devices() == []
    assert store.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0
    store.close()
