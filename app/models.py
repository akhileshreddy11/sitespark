import uuid
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def is_expired(value: datetime) -> bool:
    # SQLite returns timezone-aware columns as naive datetimes.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= now()


class LeadState(str, Enum):
    found = "found"
    enriched = "enriched"
    demo_generating = "demo_generating"
    demo_ready = "demo_ready"
    demo_failed = "demo_failed"
    contacted = "contacted"
    replied = "replied"
    paid = "paid"
    live = "live"
    churned = "churned"
    unsubscribed = "unsubscribed"
    rejected = "rejected"
    error = "error"


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # The only durable Google Places identifier. Profile data belongs in LeadCache.
    place_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    state: Mapped[LeadState] = mapped_column(default=LeadState.found, index=True)
    lead_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    found_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    cache: Mapped["LeadCache | None"] = relationship(back_populates="lead", cascade="all, delete-orphan", uselist=False)
    demos: Mapped[list["DemoSite"]] = relationship(back_populates="lead", cascade="all, delete-orphan")


class LeadCache(Base):
    __tablename__ = "lead_caches"
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True)
    # No review/photo content: photo refs and review attribution metadata only.
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    lead: Mapped[Lead] = relationship(back_populates="cache")


class SearchRun(Base):
    __tablename__ = "lead_search_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    max_results: Mapped[int] = mapped_column(Integer, nullable=False)
    min_rating_milli: Mapped[int] = mapped_column(Integer, default=3800, nullable=False)
    min_review_count: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    pages_requested: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    places_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leads_qualified: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leads_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd_micros: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StateEvent(Base):
    __tablename__ = "lead_state_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    from_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_state: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_type: Mapped[str] = mapped_column(String(30), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class JobRun(Base):
    __tablename__ = "job_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    job_name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DemoSite(Base):
    __tablename__ = "demo_sites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="generating", nullable=False, index=True)
    content: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    template_name: Mapped[str] = mapped_column(String(30), nullable=False)
    preview_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    screenshot_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    unpublished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    lead: Mapped[Lead] = relationship(back_populates="demos")
