from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Appointment, AppointmentStatus, WorkingHours


class BookingError(Exception):
    pass


class OutsideWorkingHours(BookingError):
    pass


class MasterBusy(BookingError):
    pass


class AppointmentNotFound(BookingError):
    pass


@dataclass(frozen=True)
class CreateAppointment:
    master_id: int
    customer_telegram_id: int
    start_at: datetime
    end_at: datetime


async def assert_within_working_hours(
    session: AsyncSession, *, master_id: int, start_at: datetime, end_at: datetime
) -> None:
    dow = start_at.weekday()  # 0..6
    stmt = select(WorkingHours).where(
        and_(WorkingHours.master_id == master_id, WorkingHours.day_of_week == dow)
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        raise OutsideWorkingHours("No working hours configured for this day")

    start_t = start_at.timetz().replace(tzinfo=None)
    end_t = end_at.timetz().replace(tzinfo=None)

    ok = any((wh.start_time <= start_t and end_t <= wh.end_time) for wh in rows)
    if not ok:
        raise OutsideWorkingHours("Outside working hours")


async def assert_no_overlap(
    session: AsyncSession,
    *,
    master_id: int,
    start_at: datetime,
    end_at: datetime,
    exclude_id: int | None = None,
) -> None:
    # overlap if existing.start < new.end and new.start < existing.end
    stmt = select(Appointment.id).where(
        and_(
            Appointment.master_id == master_id,
            Appointment.status == AppointmentStatus.booked,
            Appointment.start_at < end_at,
            start_at < Appointment.end_at,
        )
    )
    if exclude_id is not None:
        stmt = stmt.where(Appointment.id != exclude_id)

    existing = (await session.execute(stmt)).scalars().first()
    if existing is not None:
        raise MasterBusy("Master is busy for this time range")


async def create_appointment(session: AsyncSession, cmd: CreateAppointment) -> Appointment:
    if cmd.end_at <= cmd.start_at:
        raise ValueError("end_at must be after start_at")

    await assert_within_working_hours(
        session, master_id=cmd.master_id, start_at=cmd.start_at, end_at=cmd.end_at
    )
    await assert_no_overlap(
        session, master_id=cmd.master_id, start_at=cmd.start_at, end_at=cmd.end_at
    )

    appt = Appointment(
        master_id=cmd.master_id,
        customer_telegram_id=cmd.customer_telegram_id,
        start_at=cmd.start_at,
        end_at=cmd.end_at,
        status=AppointmentStatus.booked,
    )
    session.add(appt)
    await session.flush()
    return appt


async def reschedule_appointment(
    session: AsyncSession, *, appointment_id: int, start_at: datetime, end_at: datetime
) -> Appointment:
    appt = await session.get(Appointment, appointment_id)
    if not appt or appt.status != AppointmentStatus.booked:
        raise AppointmentNotFound("Appointment not found")

    await assert_within_working_hours(session, master_id=appt.master_id, start_at=start_at, end_at=end_at)
    await assert_no_overlap(
        session,
        master_id=appt.master_id,
        start_at=start_at,
        end_at=end_at,
        exclude_id=appointment_id,
    )

    appt.start_at = start_at
    appt.end_at = end_at
    await session.flush()
    return appt


async def cancel_appointment(session: AsyncSession, *, appointment_id: int) -> Appointment:
    appt = await session.get(Appointment, appointment_id)
    if not appt or appt.status != AppointmentStatus.booked:
        raise AppointmentNotFound("Appointment not found")

    appt.status = AppointmentStatus.cancelled
    appt.cancelled_at = datetime.utcnow()
    await session.flush()
    return appt
