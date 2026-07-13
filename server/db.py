"""Database engine and models for the local Enviro dashboard."""
from pathlib import Path
from typing import Optional

from sqlmodel import JSON, Column, Field, SQLModel, create_engine

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data.db"
LEGACY_STORE = BASE_DIR / "data.json"
KINDS = ("provisioning", "readings")


class Event(SQLModel, table=True):
    """One received event; the raw JSON payload is kept verbatim in `payload`."""

    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = Field(index=True)
    received_at: str = Field(index=True)
    payload: dict = Field(sa_column=Column(JSON))


engine = create_engine(
    f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}
)
