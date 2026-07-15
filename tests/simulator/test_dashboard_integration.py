"""End-to-end simulator contract test against the real Flask dashboard."""
import asyncio
import importlib
import sys
import threading
from pathlib import Path

from aiohttp import ClientSession
from sqlmodel import SQLModel, Session, create_engine, select
from werkzeug.serving import make_server

from enviro_simulator.daemon import SimulatorDaemon


# The dashboard is intentionally a standalone script rather than a package.
SERVER_DIR = str(Path(__file__).resolve().parents[2] / "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)
server_app = importlib.import_module("app")
db = importlib.import_module("db")


def test_simulator_against_real_dashboard_contract(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'dashboard.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(server_app, "engine", engine)

    httpd = make_server("127.0.0.1", 0, server_app.app, threaded=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    dashboard_url = f"http://127.0.0.1:{httpd.server_port}"

    async def scenario():
        daemon = SimulatorDaemon(tmp_path / "simulator.db")
        await daemon.start()
        device = await daemon.create_device({
            "nickname": "real-dashboard-grow",
            "dashboard_url": dashboard_url,
            "upload_frequency": 1,
            "pump_ml_per_second": 2,
        })
        await daemon.generate_reading(device)

        async with ClientSession() as session:
            async with session.post(
                f"{dashboard_url}/api/devices/{device['uid']}/watering-commands",
                json={"amounts": {"A": 20}},
            ) as response:
                assert response.status == 201
                command = await response.json()

        before = daemon.store.get_device(device["uid"])["state"]["values"]["moisture_a"]
        await daemon.generate_reading(daemon.store.get_device(device["uid"]))
        after = daemon.store.get_device(device["uid"])["state"]["values"]["moisture_a"]
        assert after > before
        assert daemon.store.get_command(command["id"])["acknowledged"] == 1
        await daemon.close()
        return device, command

    try:
        device, command = asyncio.run(scenario())
        with Session(engine) as session:
            stored = session.get(db.WateringCommand, command["id"])
            assert stored.status == "completed"
            events = session.exec(select(db.Event)).all()
            assert any(event.kind == "provisioning" and event.payload["uid"] == device["uid"] for event in events)
            assert sum(event.kind == "readings" for event in events) == 2
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
