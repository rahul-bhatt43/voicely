import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Voice(Base):
    """A voice model plus the consent record that allows it to exist."""

    __tablename__ = "voices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")

    # draft -> validating | training -> ready | failed
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    status_detail: Mapped[str] = mapped_column(Text, default="")
    visibility: Mapped[str] = mapped_column(String(10), default="private", index=True)  # private | public
    source: Mapped[str | None] = mapped_column(String(10))  # upload | trained

    # Consent: whose voice this is and who vouched for the right to clone it.
    consent_type: Mapped[str] = mapped_column(String(12))  # self | permission
    consent_name: Mapped[str] = mapped_column(String(120))
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    consent_ip: Mapped[str] = mapped_column(String(64), default="")
    consent_audio: Mapped[str | None] = mapped_column(String(255))

    model_path: Mapped[str | None] = mapped_column(String(255))
    index_path: Mapped[str | None] = mapped_column(String(255))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # sample_rate, version, f0, epochs...

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    owner: Mapped[User] = relationship()
    dataset: Mapped[list["DatasetFile"]] = relationship(
        back_populates="voice", cascade="all, delete-orphan", order_by="DatasetFile.created_at")


class DatasetFile(Base):
    """One training recording, with the quality measurements taken on upload."""

    __tablename__ = "dataset_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    voice_id: Mapped[str] = mapped_column(ForeignKey("voices.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(255))
    duration: Mapped[float] = mapped_column(Float, default=0)
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    voice: Mapped[Voice] = relationship(back_populates="dataset")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    voice_id: Mapped[str | None] = mapped_column(ForeignKey("voices.id", ondelete="SET NULL"))
    voice_name: Mapped[str] = mapped_column(String(80), default="")

    type: Mapped[str] = mapped_column(String(10))  # convert | cover | tts | train | inspect
    title: Mapped[str] = mapped_column(String(200), default="")
    # queued -> running -> succeeded | failed | canceled
    status: Mapped[str] = mapped_column(String(12), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0)
    stage: Mapped[str] = mapped_column(String(120), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    log: Mapped[str] = mapped_column(Text, default="")

    params: Mapped[dict] = mapped_column(JSON, default=dict)
    input_path: Mapped[str | None] = mapped_column(String(255))
    outputs: Mapped[dict] = mapped_column(JSON, default=dict)  # name -> path under the data dir
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)  # internal jobs (inspect)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seconds: Mapped[float | None] = mapped_column(Float)


class Report(Base):
    """An abuse report against a shared voice."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    voice_id: Mapped[str] = mapped_column(ForeignKey("voices.id", ondelete="CASCADE"), index=True)
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
