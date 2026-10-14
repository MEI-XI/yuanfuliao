from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="user")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Ledger(Base):
    __tablename__ = "ledgers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(31), unique=True)
    name_key: Mapped[str] = mapped_column(String(100), unique=True)


class Record(Base):
    __tablename__ = "records"
    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id"), index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    fields: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    checker_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    material_id: Mapped[int | None] = mapped_column(ForeignKey("materials.id"), nullable=True)
    scheme_name: Mapped[str] = mapped_column(String(120), default="")
    items: Mapped[list] = mapped_column(JSON, default=list)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    image_ids: Mapped[list] = mapped_column(JSON, default=list)
    recognition_job_id: Mapped[int | None] = mapped_column(ForeignKey('recognition_jobs.id'), nullable=True)


class History(Base):
    __tablename__ = "history"
    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("records.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(24))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    snapshot: Mapped[dict] = mapped_column(JSON)


class Material(Base):
    __tablename__ = "materials"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    model: Mapped[str] = mapped_column(String(200), default="")
    aliases: Mapped[str] = mapped_column(String(500), default="")


class Scheme(Base):
    __tablename__ = "schemes"
    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int | None] = mapped_column(ForeignKey("materials.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    items: Mapped[list] = mapped_column(JSON)


class Partner(Base):
    __tablename__ = "partners"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(24))
    address: Mapped[str] = mapped_column(String(1000), default="")
    contact: Mapped[str] = mapped_column(String(500), default="")


class Photo(Base):
    __tablename__ = "photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id"))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    path: Mapped[str] = mapped_column(String(500))
    filename: Mapped[str] = mapped_column(String(250))
    media_type: Mapped[str] = mapped_column(String(40))


class RecognitionJob(Base):
    __tablename__ = "recognition_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id"))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    image_ids: Mapped[list] = mapped_column(JSON)
    cloud_enabled: Mapped[bool] = mapped_column(Boolean)
    local_status: Mapped[str] = mapped_column(String(20), default="queued")
    cloud_status: Mapped[str] = mapped_column(String(20), default="disabled")
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    cloud_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    conflicts: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(500), default="")
    cloud_error: Mapped[str] = mapped_column(String(500), default="")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(2000))
