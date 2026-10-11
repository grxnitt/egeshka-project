"""Local run of the review service for checking the site form in a browser. Never used on the server.

  .venv/bin/python scripts/dev_reviews.py /path/to/scratch

SQLite database seeded from web/catalog.json, public API on 127.0.0.1:8085 (allows http://localhost:8934),
moderation on 127.0.0.1:8090. Letters are not sent: each one is appended to <scratch>/mail.log.
"""
import asyncio
import json
import sys
from pathlib import Path

from aiohttp import web
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reviews_service import admin_app, public_api  # noqa: E402
from reviews_service.config import Settings  # noqa: E402
from reviews_service.models import Base, School, Teacher  # noqa: E402


async def main(scratch: Path):
    scratch.mkdir(parents=True, exist_ok=True)
    db = scratch / "reviews-dev.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    catalog = json.loads((ROOT / "web" / "catalog.json").read_text(encoding="utf-8"))
    async with sessions() as session:
        if await session.get(School, catalog["schools"][0]["id"]) is None:
            ids = {}
            for s in catalog["schools"]:
                session.add(School(id=s["id"], name=s["name"], criteria_status=json.dumps(s.get("criteriaStatus") or {}), is_active=True))
                ids[s["name"]] = s["id"]
            for t in catalog["teachers"]:
                session.add(Teacher(id=t["id"], school_id=ids[t["school"]], name=t["name"], is_active=True))
            await session.commit()
    settings = Settings(hmac_secret="dev-secret-dev-secret-dev-secret-0123", proof_dir=str(scratch / "proofs"),
                        allowed_origins="http://localhost:8934,http://127.0.0.1:8934")
    mail_log = scratch / "mail.log"

    async def fake_mail(to, subject, body):
        with mail_log.open("a", encoding="utf-8") as handle:
            handle.write(f"--- to {to}: {subject}\n{body}\n")

    for app, port in ((public_api.create_app(settings, sessions, send_mail=fake_mail), 8085),
                      (admin_app.create_app(settings.model_copy(update={"admin_port": 8090}), sessions), 8090)):
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", port).start()
    print("dev review service: public 8085, admin 8090; mail ->", mail_log, flush=True)
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
