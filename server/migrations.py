"""Ordered schema migrations for the dashboard database.

How many migrations have been applied is stored in SQLite's built-in
``PRAGMA user_version``. Apply pending migrations with ``task server:migrate``
(the server also applies them on startup) and inspect the state with
``task server:migrate -- status``.

To add a migration, append a function taking the engine to MIGRATIONS. Never
reorder or remove entries: existing databases track their position by index.
"""
import json
import sys

from sqlmodel import Session, SQLModel, select

import db
from db import KINDS, LEGACY_STORE, Event


def initial_schema(engine):
    """Create the event table and import the pre-SQLite data.json store."""
    SQLModel.metadata.create_all(engine)
    if not LEGACY_STORE.exists():
        return
    with Session(engine) as session:
        if session.exec(select(Event.id).limit(1)).first() is not None:
            return
        try:
            legacy = json.loads(LEGACY_STORE.read_text())
        except (json.JSONDecodeError, OSError):
            return
        for kind in KINDS:
            for event in legacy.get(kind, []):
                session.add(
                    Event(kind=kind, received_at=event.get("received_at", ""), payload=event)
                )
        session.commit()


def watering_commands(engine):
    """Add durable command delivery and acknowledgement state."""
    SQLModel.metadata.create_all(engine)


MIGRATIONS = [
    initial_schema,
    watering_commands,
]


def applied_version(engine):
    with engine.connect() as connection:
        return connection.exec_driver_sql("PRAGMA user_version").scalar()


def migrate(engine=db.engine):
    """Apply pending migrations and return how many were applied."""
    version = applied_version(engine)
    pending = MIGRATIONS[version:]
    for step, migration in enumerate(pending, start=version + 1):
        print(f"applying migration {step}/{len(MIGRATIONS)}: {migration.__name__}")
        migration(engine)
        with engine.connect() as connection:
            connection.exec_driver_sql(f"PRAGMA user_version = {step}")
            connection.commit()
    return len(pending)


def print_status(engine=db.engine):
    version = applied_version(engine)
    print(f"database: {db.DB_PATH}")
    print(f"applied {version} of {len(MIGRATIONS)} migrations")
    for step, migration in enumerate(MIGRATIONS, start=1):
        marker = "x" if step <= version else " "
        print(f"  [{marker}] {step}: {migration.__name__}")


def main(argv):
    if argv[:1] == ["status"]:
        print_status()
    elif not argv:
        if migrate() == 0:
            print("database is up to date")
    else:
        print(f"unknown arguments: {' '.join(argv)}\nusage: migrations.py [status]")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
