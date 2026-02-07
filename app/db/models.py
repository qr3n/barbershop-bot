from __future__ import annotations

import enum
from datetime import datetime, time

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Time
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AppointmentStatus(str, enum.Enum):
    booked = "booked"
    cancelled = "cancelled"


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Master(Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Relative path in media storage, e.g. "masters/1.jpg" (one photo per master)
    photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    working_hours: Mapped[list[WorkingHours]] = relationship(back_populates="master")  # type: ignore[name-defined]


class WorkingHours(Base):
    __tablename__ = "working_hours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id", ondelete="CASCADE"), index=True)
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0=Mon .. 6=Sun
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    master: Mapped[Master] = relationship(back_populates="working_hours")

    __table_args__ = (
        Index("ix_working_hours_master_day", "master_id", "day_of_week"),
    )


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id", ondelete="RESTRICT"), index=True
    )
    customer_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus), default=AppointmentStatus.booked
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MakeRequestStatus(str, enum.Enum):
    created = "created"
    sent = "sent"
    failed = "failed"
    completed = "completed"


class MakeRequest(Base):
    __tablename__ = "make_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[MakeRequestStatus] = mapped_column(
        Enum(MakeRequestStatus), default=MakeRequestStatus.created
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)


Index("ix_appointments_master_time", Appointment.master_id, Appointment.start_at, Appointment.end_at)
Index("ix_appointments_customer_time", Appointment.customer_telegram_id, Appointment.start_at)


class BotSettings(Base):
    """Singleton table for bot configuration (always id=1)."""
    __tablename__ = "bot_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_token: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class BotLogLevel(str, enum.Enum):
    info = "info"
    warning = "warning"
    error = "error"


class BotLog(Base):
    """Logs for bot lifecycle events."""
    __tablename__ = "bot_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[BotLogLevel] = mapped_column(Enum(BotLogLevel), default=BotLogLevel.info)
    message: Mapped[str] = mapped_column(String(1000))
    details: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
