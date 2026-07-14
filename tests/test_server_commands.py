import importlib
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import SQLModel, Session, create_engine


sys.path.insert(0, "server")
server_app = importlib.import_module("app")
db = importlib.import_module("db")


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'commands.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(server_app, "engine", engine)
    server_app.app.config.update(TESTING=True)
    client = server_app.app.test_client()
    client.post("/api/readings", json={
        "uid": "grow-1",
        "model": "grow",
        "readings": {},
        "capabilities": {"remote_watering": {
            "ready": True, "max_ml": 100, "max_seconds": 60, "auto_water": False,
        }},
    })
    return client, engine


def create_command(client, uid="grow-1", amounts=None):
    return client.post(
        f"/api/devices/{uid}/watering-commands",
        json={"amounts": {"A": 20, "C": 10} if amounts is None else amounts},
    )


def test_dashboard_shows_controls_for_calibrated_grow(client):
    client, _ = client
    page = client.get("/")
    assert page.status_code == 200
    assert b"Remote watering" in page.data
    assert b"Queue dose" in page.data


def test_command_is_delivered_retried_and_acknowledged(client):
    client, _ = client
    created = create_command(client)
    assert created.status_code == 201
    command = created.get_json()
    assert command["status"] == "pending"

    duplicate = create_command(client)
    assert duplicate.status_code == 409

    reading = {"uid": "grow-1", "model": "grow", "readings": {"moisture_a": 30}}
    first_delivery = client.post("/api/readings", json=reading)
    delivered = first_delivery.get_json()["watering_command"]
    assert delivered["id"] == command["id"]
    assert delivered["amounts"] == {"A": 20.0, "C": 10.0}
    assert delivered["ack_url"].endswith(f"/{command['id']}/ack")

    retry = client.post("/api/readings", json=reading)
    assert retry.get_json()["watering_command"]["id"] == command["id"]

    acknowledgement = client.post(
        f"/api/watering-commands/{command['id']}/ack",
        json={"result": {"id": command["id"], "status": "completed"}},
    )
    assert acknowledgement.status_code == 200
    assert acknowledgement.get_json()["status"] == "completed"
    assert "watering_command" not in client.post("/api/readings", json=reading).get_json()


def test_only_pending_commands_can_be_cancelled(client):
    client, _ = client
    command = create_command(client).get_json()

    cancelled = client.delete(f"/api/watering-commands/{command['id']}")
    assert cancelled.status_code == 200
    assert cancelled.get_json()["status"] == "cancelled"

    assert client.delete(f"/api/watering-commands/{command['id']}").status_code == 409


def test_expired_command_is_not_delivered(client):
    client, engine = client
    command = create_command(client).get_json()
    with Session(engine) as session:
        stored = session.get(db.WateringCommand, command["id"])
        stored.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        session.add(stored)
        session.commit()

    response = client.post(
        "/api/readings",
        json={"uid": "grow-1", "model": "grow", "readings": {}},
    )
    assert "watering_command" not in response.get_json()
    with Session(engine) as session:
        assert session.get(db.WateringCommand, command["id"]).status == "expired"


def test_command_validation_rejects_empty_and_unsafe_doses(client):
    client, _ = client
    assert create_command(client, amounts={}).status_code == 400
    response = create_command(client, amounts={"B": 101})
    assert response.status_code == 400
    assert "between 0 and 100" in response.get_json()["error"]


def test_uncalibrated_device_cannot_queue_command(client):
    client, _ = client
    response = create_command(client, uid="uncalibrated")
    assert response.status_code == 409
    assert "calibration" in response.get_json()["error"]
