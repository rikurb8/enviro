"""Database engine and models for the local Enviro dashboard."""
from pathlib import Path
from typing import Optional

from sqlmodel import JSON, Column, Field, SQLModel, create_engine

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data.db"
LEGACY_STORE = BASE_DIR / "data.json"
KINDS = ("provisioning", "readings")


class WateringCommand(SQLModel, table=True):
    """One idempotent remote watering request for an Enviro Grow."""

    id: str = Field(primary_key=True)
    device_uid: str = Field(index=True)
    amounts: dict = Field(sa_column=Column(JSON))
    status: str = Field(index=True)
    created_at: str = Field(index=True)
    expires_at: str = Field(index=True)
    delivered_at: Optional[str] = Field(default=None, index=True)
    acknowledged_at: Optional[str] = Field(default=None, index=True)
    result: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))


class Event(SQLModel, table=True):
    """One received event; the raw JSON payload is kept verbatim in `payload`."""

    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = Field(index=True)
    received_at: str = Field(index=True)
    payload: dict = Field(sa_column=Column(JSON))


engine = create_engine(
    f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}
)
