"""HTTP API for site leads. Run next to the bot:  python -m egeshka_bot.leads_api

GET  /api/lead-schools            schools that currently accept leads (empty while LEADS_ENABLED is off)
GET  /api/lead-consent?school=    the consent text for that school and its version
POST /api/leads                   create a lead (JSON); returns a withdraw token the student can keep
POST /api/leads/withdraw          {"token": "..."} withdraw a lead
"""
import asyncio
import logging

from aiohttp import web

from . import leads
from .config import Settings
from .db import init_db

log = logging.getLogger("leads_api")


def create_app(settings: Settings, session_factory) -> web.Application:
    origins = {item.strip() for item in settings.leads_allowed_origins.split(",") if item.strip()}
    limiter = leads.RateLimiter()
    withdraw_limiter = leads.RateLimiter(limit=20, window=3600)

    @web.middleware
    async def cors(request, handler):
        origin = request.headers.get("Origin", "")
        if request.method == "OPTIONS":
            response = web.Response(status=204)
        else:
            try:
                response = await handler(request)
            except web.HTTPException as exc:
                response = exc
        if origin in origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Vary"] = "Origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    def visitor_key(request):
        """Who is asking, for rate limits. Behind our proxy the LAST X-Forwarded-For entry is the one the proxy added;
        the first entries can be forged by the visitor, so they must not decide the limit."""
        forwarded = [part.strip() for part in request.headers.get("X-Forwarded-For", "").split(",") if part.strip()]
        return forwarded[-1] if forwarded else (request.remote or "")

    def reply(payload, status=200):
        return web.json_response(payload, status=status)

    async def lead_schools(request):
        if not settings.leads_enabled:
            return reply({"schools": []})
        async with session_factory() as session:
            return reply({"schools": await leads.enabled_schools(session), "consentVersion": leads.CONSENT_VERSION})

    async def lead_consent(request):
        if not settings.leads_enabled:
            return reply({"error": "off"}, 404)
        async with session_factory() as session:
            school, cfg = await leads.school_config(session, request.query.get("school", ""))
            if not school:
                return reply({"error": "off"}, 404)
            return reply({"text": leads.consent_text(school.name, cfg, settings), "version": leads.CONSENT_VERSION})

    async def create_lead(request):
        if not settings.leads_enabled:
            return reply({"error": "off"}, 404)
        visitor = visitor_key(request)
        if not limiter.allow(visitor):
            return reply({"error": "Слишком много заявок. Попробуйте позже."}, 429)
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            return reply({"error": "Некорректный запрос."}, 400)
        async with session_factory() as session:
            school, cfg = await leads.school_config(session, str(data.get("school", "")) if isinstance(data, dict) else "")
            if not school:
                return reply({"error": "Эта школа пока не принимает заявки через сайт."}, 404)
            try:
                clean = leads.clean_request(data, cfg)
            except leads.LeadError as exc:
                return reply({"error": str(exc)}, 400)
            lead, token, duplicate = await leads.create_lead(session, school, clean)
            if duplicate:
                return reply({"ok": True, "duplicate": True})
            await leads.deliver_lead(session, settings, lead, school, cfg)  # on failure the retry loop picks it up
            return reply({"ok": True, "token": token, "id": lead.id})

    async def withdraw(request):
        if not withdraw_limiter.allow(visitor_key(request)):
            return reply({"error": "Слишком много попыток. Попробуйте позже."}, 429)
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            return reply({"error": "Некорректный запрос."}, 400)
        async with session_factory() as session:
            done = await leads.withdraw(session, settings, str(data.get("token", "")) if isinstance(data, dict) else "")
        return reply({"ok": done})

    app = web.Application(middlewares=[cors], client_max_size=4096)
    app.add_routes([
        web.get("/api/lead-schools", lead_schools),
        web.get("/api/lead-consent", lead_consent),
        web.post("/api/leads", create_lead),
        web.post("/api/leads/withdraw", withdraw),
        web.route("OPTIONS", "/api/{tail:.*}", lambda request: web.Response(status=204)),
    ])
    return app


async def run(settings: Settings):
    if settings.leads_enabled and (not settings.operator_contact or "владелец сервиса" in settings.operator_name):
        raise SystemExit("LEADS_ENABLED needs OPERATOR_NAME and OPERATOR_CONTACT: the consent text must name the operator.")
    engine, session_factory = await init_db(settings.database_url)
    runner = web.AppRunner(create_app(settings, session_factory))
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", settings.leads_port).start()  # a reverse proxy (Caddy) faces the internet
    log.warning("leads API on 127.0.0.1:%s, leads_enabled=%s", settings.leads_port, settings.leads_enabled)
    while True:
        await asyncio.sleep(60)
        if settings.leads_enabled:
            try:
                await leads.retry_pending(session_factory, settings)
            except Exception:  # noqa: BLE001
                log.exception("retry loop failed")


if __name__ == "__main__":
    asyncio.run(run(Settings()))
