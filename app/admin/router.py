from __future__ import annotations

from datetime import datetime, time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.api_auth import clear_admin_cookie, require_admin, set_admin_cookie
from app.api.deps import get_session
from app.config import Settings, get_settings
from app.db.models import Appointment, Master, WorkingHours
from app.services import booking
from app.services.media import build_public_url, compress_and_save_image, delete_media_file

router = APIRouter(prefix="/admin", tags=["admin"]) 


class LoginIn(BaseModel):
    password: str


class MasterIn(BaseModel):
    name: str
    description: str | None = None
    experience_years: int | None = Field(default=None, ge=0, le=80)
    is_active: bool = True


class MasterOut(BaseModel):
    id: int
    name: str
    description: str | None
    experience_years: int | None
    is_active: bool
    photo_url: str | None = None


def _master_out(m: Master, *, settings: Settings) -> MasterOut:
    return MasterOut(
        id=m.id,
        name=m.name,
        description=m.description,
        experience_years=m.experience_years,
        is_active=m.is_active,
        photo_url=(build_public_url(settings, relative_path=m.photo_path) if m.photo_path else None),
    )


class WorkingHoursIn(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: str
    end_time: str


class AppointmentOut(BaseModel):
    id: int
    master_id: int
    customer_telegram_id: int
    start_at: datetime
    end_at: datetime
    status: str


@router.post("/auth/login")
async def login(body: LoginIn, response: Response, settings: Settings = Depends(get_settings)) -> dict:
    if not settings.admin_panel_password:
        raise HTTPException(status_code=500, detail="ADMIN_PANEL_PASSWORD is not configured")

    if body.password != settings.admin_panel_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")

    set_admin_cookie(response, settings=settings)
    return {"ok": True}


@router.post("/auth/logout")
async def logout(response: Response, settings: Settings = Depends(get_settings)) -> dict:
    clear_admin_cookie(response, settings=settings)
    return {"ok": True}


@router.get("/me", dependencies=[Depends(require_admin)])
async def me() -> dict:
    return {"ok": True}


@router.get("/masters", dependencies=[Depends(require_admin)], response_model=list[MasterOut])
async def list_masters(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[MasterOut]:
    rows = (await session.execute(select(Master).order_by(Master.id))).scalars().all()
    return [_master_out(m, settings=settings) for m in rows]


@router.post("/masters", dependencies=[Depends(require_admin)], response_model=MasterOut, status_code=201)
async def create_master(
    name: str = Form(...),
    description: str | None = Form(None),
    experience_years: int | None = Form(None),
    is_active: bool = Form(True),
    file: UploadFile | None = File(None),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MasterOut:
    m = Master(
        name=name,
        description=description,
        experience_years=experience_years,
        is_active=is_active,
    )
    session.add(m)
    await session.commit()
    await session.refresh(m)

    if file is not None:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty file")
        if len(raw) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File is too large")

        saved = compress_and_save_image(
            settings,
            master_id=m.id,
            content_type=file.content_type,
            raw=raw,
        )
        m.photo_path = saved.relative_path
        await session.commit()
        await session.refresh(m)

    return _master_out(m, settings=settings)


@router.patch("/masters/{master_id}", dependencies=[Depends(require_admin)], response_model=MasterOut)
async def update_master(
    master_id: int,
    body: MasterIn,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MasterOut:
    m = await session.get(Master, master_id)
    if not m:
        raise HTTPException(status_code=404, detail="Master not found")

    m.name = body.name
    m.description = body.description
    m.experience_years = body.experience_years
    m.is_active = body.is_active

    await session.commit()
    await session.refresh(m)
    return _master_out(m, settings=settings)


@router.delete("/masters/{master_id}", dependencies=[Depends(require_admin)])
async def delete_master(
    master_id: int,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    m = await session.get(Master, master_id)
    if not m:
        raise HTTPException(status_code=404, detail="Master not found")

    # best-effort delete photo file
    if m.photo_path:
        delete_media_file(settings, relative_path=m.photo_path)

    await session.delete(m)
    await session.commit()
    return {"ok": True}


@router.put(
    "/masters/{master_id}/photo",
    dependencies=[Depends(require_admin)],
    response_model=MasterOut,
)
async def upload_master_photo(
    master_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MasterOut:
    m = await session.get(Master, master_id)
    if not m:
        raise HTTPException(status_code=404, detail="Master not found")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    # 10MB hard limit for upload (before compression)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File is too large")

    saved = compress_and_save_image(
        settings,
        master_id=master_id,
        content_type=file.content_type,
        raw=raw,
    )

    # If there was a previous photo under another path, delete it
    if m.photo_path and m.photo_path != saved.relative_path:
        delete_media_file(settings, relative_path=m.photo_path)

    m.photo_path = saved.relative_path
    await session.commit()
    await session.refresh(m)
    return _master_out(m, settings=settings)


@router.delete(
    "/masters/{master_id}/photo",
    dependencies=[Depends(require_admin)],
)
async def delete_master_photo(
    master_id: int,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    m = await session.get(Master, master_id)
    if not m:
        raise HTTPException(status_code=404, detail="Master not found")

    if m.photo_path:
        delete_media_file(settings, relative_path=m.photo_path)
        m.photo_path = None
        await session.commit()

    return {"ok": True}


@router.get(
    "/masters/{master_id}/working-hours",
    dependencies=[Depends(require_admin)],
    response_model=list[WorkingHoursIn],
)
async def get_working_hours(master_id: int, session: AsyncSession = Depends(get_session)) -> list[WorkingHoursIn]:
    rows = (
        (await session.execute(select(WorkingHours).where(WorkingHours.master_id == master_id)))
        .scalars()
        .all()
    )
    return [
        WorkingHoursIn(
            day_of_week=r.day_of_week,
            start_time=r.start_time.strftime("%H:%M"),
            end_time=r.end_time.strftime("%H:%M"),
        )
        for r in rows
    ]


@router.put("/masters/{master_id}/working-hours", dependencies=[Depends(require_admin)])
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


@router.get("/appointments", dependencies=[Depends(require_admin)], response_model=list[AppointmentOut])
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


@router.post(
    "/appointments/{appointment_id}/cancel",
    dependencies=[Depends(require_admin)],
    response_model=AppointmentOut,
)
async def cancel_appt(appointment_id: int, session: AsyncSession = Depends(get_session)) -> AppointmentOut:
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
