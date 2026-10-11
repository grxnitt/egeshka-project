"""python -m reviews_service public   site API on 127.0.0.1:8085 (+ hourly cleanup of drafts and stale screenshots)
python -m reviews_service admin    moderation and school partnerships on 127.0.0.1:8090 (reach it only through an SSH tunnel)
python -m reviews_service leads    requests to schools on 127.0.0.1:8081 (the global switch is in the console)"""
import asyncio
import logging
import sys

from aiohttp import web
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from . import admin_app, public_api, store
from .lead_settings import LeadSettings
from .config import Settings


async def serve(kind: str):
    settings = Settings()
    settings.check()
    # The service writes naive UTC timestamps: the database session must read them as UTC (the server runs on Moscow time).
    connect_args = {"server_settings": {"timezone": "UTC"}} if "asyncpg" in settings.database_url else {}
    engine = create_async_engine(settings.database_url, pool_size=4, max_overflow=2, pool_pre_ping=True,
                                 connect_args=connect_args)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    background = []
    if kind == "public":
        app, port = public_api.create_app(settings, sessions), settings.public_port
    elif kind == "leads":
        from egeshka_bot import leads, leads_api
        lead_settings = LeadSettings(settings)
        app, port = leads_api.create_app(lead_settings, sessions), settings.leads_port
        background.append(asyncio.create_task(lead_settings.keep_fresh(sessions)))

        async def retry_loop():
            while True:
                await asyncio.sleep(60)
                try:
                    if lead_settings.leads_enabled:
                        await leads.retry_pending(sessions, lead_settings)
                    async with sessions() as session:
                        await leads.purge_old(session)
                except Exception:  # noqa: BLE001
                    logging.getLogger("reviews").exception("leads loop failed")
        background.append(asyncio.create_task(retry_loop()))
    else:
        app, port = admin_app.create_app(settings, sessions), settings.admin_port
    runner = web.AppRunner(app, access_log=None)   # no access log: it would hold visitors' IPs
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    logging.getLogger("reviews").warning("%s on 127.0.0.1:%s", kind, port)
    try:
        while True:
            await asyncio.sleep(3600)
            if kind == "public":
                try:
                    async with sessions() as session:
                        await store.cleanup(session, settings.proof_dir)
                except Exception:  # noqa: BLE001
                    logging.getLogger("reviews").exception("cleanup failed")
    finally:
        for task in background:
            task.cancel()
        await runner.cleanup()
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("public", "admin", "leads"):
        raise SystemExit(__doc__)
    asyncio.run(serve(mode))
