from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.admin.router import router as admin_router
from app.api.routers.make import router as make_router
from app.bot.manager import BotManager
from app.config import get_settings
from app.db.models import Admin, Base
from app.db.session import create_engine, create_session_factory


def create_app() -> FastAPI:
    settings = get_settings()

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    app = FastAPI(title="Barbershop Telegram Backend")
    app.state.settings = settings

    cors_origins = [o.strip() for o in settings.admin_cors_origins.split(",") if o.strip()]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.state.engine = engine
    app.state.session_factory = session_factory

    # Create BotManager
    bot_manager = BotManager(
        settings=settings,
        session_factory=session_factory,
    )
    app.state.bot_manager = bot_manager

    # Public media (master photos)
    app.mount(
        settings.media_url_prefix,
        StaticFiles(directory=settings.media_root),
        name="media",
    )

    app.include_router(make_router)
    app.include_router(admin_router)

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True}

    @app.on_event("startup")
    async def on_startup() -> None:
        # Ensure media directories exist
        os.makedirs(settings.media_root, exist_ok=True)
        os.makedirs(os.path.join(settings.media_root, "masters"), exist_ok=True)

        # For local/dev convenience. In prod prefer alembic migrations.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Bootstrap admins
        async with session_factory() as session:
            for tg_id in settings.admin_ids:
                exists = await session.scalar(select(Admin.id).where(Admin.telegram_id == tg_id).limit(1))
                if not exists:
                    session.add(Admin(telegram_id=tg_id))
            await session.commit()

        # Start bot if enabled
        if settings.enable_bot:
            await bot_manager.start()

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        await bot_manager.shutdown()
        await engine.dispose()

    return app
