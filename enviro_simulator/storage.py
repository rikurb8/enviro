"""SQLite persistence for simulator profiles, state, outbox and events."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def close(self):
        self.db.close()

    def migrate(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS devices (
          uid TEXT PRIMARY KEY,
          nickname TEXT NOT NULL UNIQUE,
          enabled INTEGER NOT NULL DEFAULT 1,
          online INTEGER NOT NULL DEFAULT 1,
          profile TEXT NOT NULL,
          state TEXT NOT NULL,
          overrides TEXT NOT NULL DEFAULT '{}',
          next_due REAL NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          last_reading_at TEXT,
          last_upload_at TEXT,
          last_error TEXT
        );
        CREATE TABLE IF NOT EXISTS outbox (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          device_uid TEXT NOT NULL REFERENCES devices(uid) ON DELETE CASCADE,
          payload TEXT NOT NULL,
          created_at TEXT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0,
          next_attempt REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS outbox_device ON outbox(device_uid, id);
        CREATE TABLE IF NOT EXISTS commands (
          command_id TEXT PRIMARY KEY,
          device_uid TEXT NOT NULL REFERENCES devices(uid) ON DELETE CASCADE,
          command TEXT NOT NULL,
          result TEXT NOT NULL,
          ack_url TEXT,
          acknowledged INTEGER NOT NULL DEFAULT 0,
          attempts INTEGER NOT NULL DEFAULT 0,
          next_attempt REAL NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          device_uid TEXT,
          kind TEXT NOT NULL,
          detail TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS events_device ON events(device_uid, id DESC);
        """)
        self.db.commit()

    @staticmethod
    def _device(row):
        if row is None:
            return None
        item = dict(row)
        for key in ("profile", "state", "overrides"):
            item[key] = json.loads(item[key])
        item["enabled"] = bool(item["enabled"])
        item["online"] = bool(item["online"])
        item["queued"] = 0
        return item

    def list_devices(self):
        rows = self.db.execute("""
          SELECT d.*, COUNT(o.id) AS queued_count
          FROM devices d LEFT JOIN outbox o ON o.device_uid=d.uid
          GROUP BY d.uid ORDER BY d.nickname
        """).fetchall()
        result = []
        for row in rows:
            item = self._device(row)
            item["queued"] = item.pop("queued_count")
            result.append(item)
        return result

    def get_device(self, identifier: str):
        row = self.db.execute(
            "SELECT * FROM devices WHERE uid=? OR nickname=?", (identifier, identifier)
        ).fetchone()
        item = self._device(row)
        if item:
            item["queued"] = self.outbox_count(item["uid"])
        return item

    def create_device(self, uid: str, nickname: str, profile: dict, state: dict, next_due: float):
        now = utcnow()
        self.db.execute(
            """INSERT INTO devices
            (uid,nickname,profile,state,next_due,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?)""",
            (uid, nickname, json.dumps(profile), json.dumps(state), next_due, now, now),
        )
        self.db.commit()
        self.event(uid, "provisioned", {"nickname": nickname})
        return self.get_device(uid)

    def update_device(self, uid: str, **values):
        allowed = {"nickname", "enabled", "online", "profile", "state", "overrides", "next_due", "last_reading_at", "last_upload_at", "last_error"}
        fields, args = [], []
        for key, value in values.items():
            if key not in allowed:
                continue
            if key in {"profile", "state", "overrides"}:
                value = json.dumps(value)
            if key in {"enabled", "online"}:
                value = int(value)
            fields.append(f"{key}=?")
            args.append(value)
        if not fields:
            return self.get_device(uid)
        fields.append("updated_at=?")
        args.extend((utcnow(), uid))
        self.db.execute(f"UPDATE devices SET {', '.join(fields)} WHERE uid=?", args)
        self.db.commit()
        return self.get_device(uid)

    def delete_device(self, uid: str):
        self.db.execute("DELETE FROM devices WHERE uid=?", (uid,))
        self.db.commit()

    def enqueue(self, uid: str, payload: dict):
        self.db.execute(
            "INSERT INTO outbox(device_uid,payload,created_at) VALUES (?,?,?)",
            (uid, json.dumps(payload), utcnow()),
        )
        self.db.commit()

    def outbox_count(self, uid: str):
        return self.db.execute("SELECT COUNT(*) FROM outbox WHERE device_uid=?", (uid,)).fetchone()[0]

    def due_outbox(self, uid: str, now: float):
        return self.db.execute(
            "SELECT * FROM outbox WHERE device_uid=? AND next_attempt<=? ORDER BY id", (uid, now)
        ).fetchall()

    def has_failed_outbox(self, uid: str):
        return bool(self.db.execute(
            "SELECT 1 FROM outbox WHERE device_uid=? AND attempts>0 LIMIT 1", (uid,)
        ).fetchone())

    def delivered(self, outbox_id: int):
        self.db.execute("DELETE FROM outbox WHERE id=?", (outbox_id,))
        self.db.commit()

    def fail_delivery(self, outbox_id: int, attempts: int, next_attempt: float):
        self.db.execute(
            "UPDATE outbox SET attempts=?,next_attempt=? WHERE id=?",
            (attempts, next_attempt, outbox_id),
        )
        self.db.commit()

    def get_command(self, command_id: str):
        row = self.db.execute("SELECT * FROM commands WHERE command_id=?", (command_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["command"] = json.loads(item["command"])
        item["result"] = json.loads(item["result"])
        return item

    def save_command(self, uid: str, command: dict, result: dict, ack_url: Optional[str]):
        self.db.execute(
            """INSERT OR IGNORE INTO commands
            (command_id,device_uid,command,result,ack_url,created_at)
            VALUES (?,?,?,?,?,?)""",
            (command["id"], uid, json.dumps(command), json.dumps(result), ack_url, utcnow()),
        )
        self.db.commit()
        return self.get_command(command["id"])

    def pending_acks(self, now: float):
        return self.db.execute(
            "SELECT * FROM commands WHERE acknowledged=0 AND ack_url IS NOT NULL AND next_attempt<=?", (now,)
        ).fetchall()

    def acked(self, command_id: str):
        self.db.execute("UPDATE commands SET acknowledged=1 WHERE command_id=?", (command_id,))
        self.db.commit()

    def fail_ack(self, command_id: str, attempts: int, next_attempt: float):
        self.db.execute(
            "UPDATE commands SET attempts=?,next_attempt=? WHERE command_id=?",
            (attempts, next_attempt, command_id),
        )
        self.db.commit()

    def event(self, uid: Optional[str], kind: str, detail: dict):
        self.db.execute(
            "INSERT INTO events(device_uid,kind,detail,created_at) VALUES (?,?,?,?)",
            (uid, kind, json.dumps(detail), utcnow()),
        )
        self.db.commit()

    def recent_events(self, uid: Optional[str] = None, limit: int = 50):
        if uid:
            rows = self.db.execute(
                "SELECT * FROM events WHERE device_uid=? ORDER BY id DESC LIMIT ?", (uid, limit)
            ).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(row), "detail": json.loads(row["detail"])} for row in rows]
