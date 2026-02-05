from __future__ import annotations

from datetime import datetime, time

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_session
from app.bot.sender import send_text
from app.db.models import Appointment, MakeRequest, MakeRequestStatus, Master, WorkingHours
from app.services import booking
from app.services.auth import admin_auth, make_auth
from app.config import Settings, get_settings
from app.services.media import build_public_url

router = APIRouter(prefix="/make", tags=["make"])


class CallbackIn(BaseModel):
    correlation_id: str = Field(min_length=8, max_length=64)
    text: str


class MasterOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    experience_years: int | None = None
    is_active: bool
    photo_url: str | None = None


class MasterCreateIn(BaseModel):
    name: str
    description: str | None = None
    experience_years: int | None = Field(default=None, ge=0, le=80)


class WorkingHoursIn(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: str  # HH:MM
    end_time: str  # HH:MM


class WorkingHoursOut(BaseModel):
    day_of_week: int
    start_time: str
    end_time: str


class AppointmentCreateIn(BaseModel):
    master_id: int
    customer_telegram_id: int
    start_at: datetime
    end_at: datetime


class AppointmentRescheduleIn(BaseModel):
    start_at: datetime
    end_at: datetime


class AppointmentOut(BaseModel):
    id: int
    master_id: int
    customer_telegram_id: int
    start_at: datetime
    end_at: datetime
    status: str


@router.post("/callback", dependencies=[Depends(make_auth)])
async def make_callback(
    body: CallbackIn,
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
) -> dict:
    req = (
        (await session.execute(select(MakeRequest).where(MakeRequest.correlation_id == body.correlation_id)))
        .scalars()
        .first()
    )
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown correlation_id")

    await send_text(bot, chat_id=req.chat_id, text=body.text)
    req.status = MakeRequestStatus.completed
    await session.commit()
    return {"ok": True}


# --- Admin-only: masters + working hours ---


@router.post("/masters", dependencies=[Depends(admin_auth)], response_model=MasterOut)
async def create_master(
    body: MasterCreateIn,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MasterOut:
    m = Master(
        name=body.name,
        description=body.description,
        experience_years=body.experience_years,
        is_active=True,
    )
    session.add(m)
    await session.commit()
    await session.refresh(m)
    return MasterOut(
        id=m.id,
        name=m.name,
        description=m.description,
        experience_years=m.experience_years,
        is_active=m.is_active,
        photo_url=(build_public_url(settings, relative_path=m.photo_path) if m.photo_path else None),
    )


@router.get("/masters", dependencies=[Depends(make_auth)], response_model=list[MasterOut])
async def list_masters(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[MasterOut]:
    ms = (await session.execute(select(Master).order_by(Master.id))).scalars().all()
    return [
        MasterOut(
            id=m.id,
            name=m.name,
            description=m.description,
            experience_years=m.experience_years,
            is_active=m.is_active,
            photo_url=(build_public_url(settings, relative_path=m.photo_path) if m.photo_path else None),
        )
        for m in ms
    ]


@router.delete("/masters/{master_id}", dependencies=[Depends(admin_auth)])
async def delete_master(master_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    m = await session.get(Master, master_id)
    if not m:
        raise HTTPException(status_code=404, detail="Master not found")
    await session.delete(m)
    await session.commit()
    return {"ok": True}


@router.put("/masters/{master_id}/working-hours", dependencies=[Depends(admin_auth)])
async def set_working_hours(
    master_id: int, body: list[WorkingHoursIn], session: AsyncSession = Depends(get_session)
) -> dict:
    m = await session.get(Master, master_id)
    if not m:
        raise HTTPException(status_code=404, detail="Master not found")

    await session.execute(delete(WorkingHours).where(WorkingHours.master_id == master_id))

    def parse_hm(s: str) -> time:
        hh, mm = s.split(":")
        return time(hour=int(hh), minute=int(mm))

    for wh in body:
        session.add(
            WorkingHours(
                master_id=master_id,
                day_of_week=wh.day_of_week,
                start_time=parse_hm(wh.start_time),
                end_time=parse_hm(wh.end_time),
            )
        )

    await session.commit()
    return {"ok": True}


@router.get(
    "/masters/{master_id}/working-hours",
    dependencies=[Depends(make_auth)],
    response_model=list[WorkingHoursOut],
)
async def get_working_hours(
    master_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[WorkingHoursOut]:
    rows = (
        (await session.execute(select(WorkingHours).where(WorkingHours.master_id == master_id)))
        .scalars()
        .all()
    )
    return [
        WorkingHoursOut(
            day_of_week=r.day_of_week,
            start_time=r.start_time.strftime("%H:%M"),
            end_time=r.end_time.strftime("%H:%M"),
        )
        for r in rows
    ]


# --- Make booking endpoints ---


@router.post(
    "/appointments",
    dependencies=[Depends(make_auth)],
    response_model=AppointmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_appointment(
    body: AppointmentCreateIn, session: AsyncSession = Depends(get_session)
) -> AppointmentOut:
    try:
        appt = await booking.create_appointment(
            session,
            booking.CreateAppointment(
                master_id=body.master_id,
                customer_telegram_id=body.customer_telegram_id,
                start_at=body.start_at,
                end_at=body.end_at,
            ),
        )
        await session.commit()
        return AppointmentOut(
            id=appt.id,
            master_id=appt.master_id,
            customer_telegram_id=appt.customer_telegram_id,
            start_at=appt.start_at,
            end_at=appt.end_at,
            status=appt.status.value,
        )
    except booking.OutsideWorkingHours as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except booking.MasterBusy as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.patch(
    "/appointments/{appointment_id}",
    dependencies=[Depends(make_auth)],
    response_model=AppointmentOut,
)
async def reschedule(
    appointment_id: int, body: AppointmentRescheduleIn, session: AsyncSession = Depends(get_session)
) -> AppointmentOut:
    try:
        appt = await booking.reschedule_appointment(
            session, appointment_id=appointment_id, start_at=body.start_at, end_at=body.end_at
        )
        await session.commit()
        return AppointmentOut(
            id=appt.id,
            master_id=appt.master_id,
            customer_telegram_id=appt.customer_telegram_id,
            start_at=appt.start_at,
            end_at=appt.end_at,
            status=appt.status.value,
        )
    except booking.OutsideWorkingHours as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except booking.MasterBusy as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except booking.AppointmentNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post(
    "/appointments/{appointment_id}/cancel",
    dependencies=[Depends(make_auth)],
    response_model=AppointmentOut,
)
async def cancel(appointment_id: int, session: AsyncSession = Depends(get_session)) -> AppointmentOut:
    try:
        appt = await booking.cancel_appointment(session, appointment_id=appointment_id)
        await session.commit()
        return AppointmentOut(
            id=appt.id,
            master_id=appt.master_id,
            customer_telegram_id=appt.customer_telegram_id,
            start_at=appt.start_at,
            end_at=appt.end_at,
            status=appt.status.value,
        )
    except booking.AppointmentNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/appointments", dependencies=[Depends(make_auth)], response_model=list[AppointmentOut])
async def list_appointments(
    master_id: int | None = None,
    customer_telegram_id: int | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[AppointmentOut]:
    stmt = select(Appointment).order_by(Appointment.start_at)
    if master_id is not None:
        stmt = stmt.where(Appointment.master_id == master_id)
    if customer_telegram_id is not None:
        stmt = stmt.where(Appointment.customer_telegram_id == customer_telegram_id)
    if from_dt is not None:
        stmt = stmt.where(Appointment.start_at >= from_dt)
    if to_dt is not None:
        stmt = stmt.where(Appointment.start_at < to_dt)

    rows = (await session.execute(stmt)).scalars().all()
    return [
        AppointmentOut(
            id=a.id,
            master_id=a.master_id,
            customer_telegram_id=a.customer_telegram_id,
            start_at=a.start_at,
            end_at=a.end_at,
            status=a.status.value,
        )
        for a in rows
    ]
