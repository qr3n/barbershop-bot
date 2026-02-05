from __future__ import annotations

import asyncio
import contextlib

from aiogram import Bot
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.admin.router import router as admin_router
from sqlalchemy import select

from app.api.routers.make import router as make_router
from app.bot.dispatcher import setup_dispatcher
from app.bot.make_client import MakeClient, MakeClientConfig
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
        import os

        os.makedirs(settings.media_root, exist_ok=True)
        os.makedirs(os.path.join(settings.media_root, "masters"), exist_ok=True)

        # For local/dev convenience. In prod prefer alembic migrations.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        if (not settings.enable_bot) or (not settings.bot_token):
            # Allow running API without Telegram bot (useful for admin panel / smoke tests)
            app.state.bot = None
            app.state.dp = None
            app.state.make_client = None
            app.state.polling_task = None
            return

        app.state.bot = Bot(token=settings.bot_token)

        make_client = MakeClient(
            MakeClientConfig(
                webhook_url=settings.make_webhook_url,
                bearer_token=settings.make_outgoing_bearer_token,
            )
        )
        app.state.make_client = make_client

        dp = setup_dispatcher(
            bot=app.state.bot,
            session_factory=session_factory,
            make_client=make_client,
            public_base_url=settings.public_base_url,
        )
        app.state.dp = dp

        # bootstrap admins
        async with session_factory() as session:
            for tg_id in settings.admin_ids:
                exists = await session.scalar(select(Admin.id).where(Admin.telegram_id == tg_id).limit(1))
                if not exists:
                    session.add(Admin(telegram_id=tg_id))
            await session.commit()

        app.state.polling_task = asyncio.create_task(dp.start_polling(app.state.bot))

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        task: asyncio.Task | None = getattr(app.state, "polling_task", None)
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        make_client: MakeClient | None = getattr(app.state, "make_client", None)
        if make_client:
            await make_client.aclose()

        bot: Bot | None = getattr(app.state, "bot", None)
        if bot:
            await bot.session.close()

        await engine.dispose()

    return app
