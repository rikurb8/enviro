import importlib
import json
import sys

from sqlmodel import Session, create_engine, select


sys.path.insert(0, "server")
db = importlib.import_module("db")
migrations = importlib.import_module("migrations")


def test_initial_migration_imports_legacy_json(tmp_path, monkeypatch):
    legacy_store = tmp_path / "data.json"
    legacy_store.write_text(
        json.dumps(
            {
                "provisioning": [
                    {"received_at": "2026-01-01T00:00:00+00:00", "nickname": "fern"}
                ],
                "readings": [
                    {"received_at": "2026-01-01T00:01:00+00:00", "temperature": 21.5}
                ],
            }
        )
    )
    monkeypatch.setattr(migrations, "LEGACY_STORE", legacy_store)
    engine = create_engine(f"sqlite:///{tmp_path / 'data.db'}")

    assert migrations.migrate(engine) == len(migrations.MIGRATIONS)

    with Session(engine) as session:
        events = session.exec(select(db.Event).order_by(db.Event.id)).all()

    assert [(event.kind, event.received_at) for event in events] == [
        ("provisioning", "2026-01-01T00:00:00+00:00"),
        ("readings", "2026-01-01T00:01:00+00:00"),
    ]
    assert events[0].payload["nickname"] == "fern"
    assert events[1].payload["temperature"] == 21.5
    assert migrations.applied_version(engine) == len(migrations.MIGRATIONS)


def test_migrations_are_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(migrations, "LEGACY_STORE", tmp_path / "missing-data.json")
    engine = create_engine(f"sqlite:///{tmp_path / 'data.db'}")

    assert migrations.migrate(engine) == len(migrations.MIGRATIONS)
    assert migrations.migrate(engine) == 0

    with Session(engine) as session:
        assert session.exec(select(db.Event)).all() == []
