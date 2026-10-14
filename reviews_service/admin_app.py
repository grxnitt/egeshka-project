"""Moderation, on 127.0.0.1:8090 only. Never published by Caddy: the only way in is an SSH tunnel with the owner's key
(scripts/admin.sh). Even so, every request is checked as if the page were public:

- Host must be localhost:8090 / 127.0.0.1:8090 (stops DNS-rebinding pages from talking to the tunnel);
- every change needs the X-Admin-Token header from the page, and Origin, if sent, must be this same address
  (another site open in the browser can neither read the token nor send that header without CORS, which we never allow);
- the page itself has a strict Content-Security-Policy and renders review text only as text (no innerHTML);
- screenshots are served from our own re-encoded WebP files, with nosniff and a sandboxing CSP.
"""
import json
import logging
import secrets
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from aiohttp import web
from sqlalchemy import delete, func, select

from . import audit, console_tools, images, lead_admin_api, store
from .models import Blocked, Review, ReviewCriterionScore, ReviewProof, School, Teacher, User, utcnow

log = logging.getLogger("reviews.admin")
STATIC = Path(__file__).with_name("admin_static")
MOSCOW = ZoneInfo("Europe/Moscow")
PAGE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; "
            "form-action 'none'; frame-ancestors 'none'; base-uri 'none'")


def moscow(moment) -> str:
    """Times are stored in UTC; the moderator reads Moscow time."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(MOSCOW).strftime("%Y-%m-%d %H:%M")


def create_app(settings, session_factory) -> web.Application:
    token = secrets.token_urlsafe(32)          # new on every start; reload the page after a restart
    hosts = {f"127.0.0.1:{settings.admin_port}", f"localhost:{settings.admin_port}"}
    origins = {f"http://{host}" for host in hosts}

    @web.middleware
    async def guard(request, handler):
        if request.host not in hosts:
            return web.Response(status=421, text="Wrong host")
        if request.method not in ("GET", "HEAD"):
            origin = request.headers.get("Origin")
            if origin is not None and origin not in origins:
                return web.Response(status=403, text="Wrong origin")
            if not secrets.compare_digest(request.headers.get("X-Admin-Token", ""), token):
                return web.Response(status=403, text="Missing token")
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            response = exc
        response.headers.setdefault("Content-Security-Policy", PAGE_CSP)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        return response

    async def page(request):
        html = (STATIC / "admin.html").read_text(encoding="utf-8").replace("__ADMIN_TOKEN__", token)
        return web.Response(text=html, content_type="text/html")

    async def asset(request):
        name = request.match_info["name"]
        if name not in ("admin.js", "admin.css", "partners.js", "tools.js"):
            raise web.HTTPNotFound()
        kind = "application/javascript" if name.endswith(".js") else "text/css"
        return web.Response(text=(STATIC / name).read_text(encoding="utf-8"), content_type=kind)

    async def describe(session, reviews):
        ids = [r.id for r in reviews]
        schools = {s.id: s.name for s in (await session.execute(select(School))).scalars()}
        teacher_ids = {r.teacher_id for r in reviews if r.teacher_id}
        teachers = {t.id: t.name for t in (await session.execute(
            select(Teacher).where(Teacher.id.in_(teacher_ids or {0})))).scalars()}
        proofs = {}
        for proof in (await session.execute(select(ReviewProof).where(ReviewProof.review_id.in_(ids or [0])))).scalars():
            proofs.setdefault(proof.review_id, []).append({"id": proof.id, "width": proof.width, "height": proof.height})
        since = utcnow() - timedelta(days=30)
        result = []
        for r in reviews:
            same_person = (await session.execute(select(func.count()).select_from(Review).where(
                Review.user_id == r.user_id, Review.id != r.id))).scalar_one()
            same_ip = 0
            if r.ip_hash:
                same_ip = (await session.execute(select(func.count()).select_from(Review).where(
                    Review.ip_hash == r.ip_hash, Review.id != r.id, Review.created_at >= since))).scalar_one()
            result.append({
                "id": r.id, "school": schools.get(r.school_id, "?"), "teacher": teachers.get(r.teacher_id),
                "scores": json.loads(r.criteria_json or "{}"), "score": r.score, "positive": r.text_positive,
                "negative": r.text_negative, "period": r.study_period, "status": r.moderation_status,
                "verified": r.verified, "created": moscow(r.created_at), "author": r.display_name,
                "proofs": proofs.get(r.id, []), "samePerson": same_person, "sameNetwork": same_ip,
            })
        return result

    async def queue(request):
        status = request.query.get("status", "pending")
        if status not in ("pending", "approved", "rejected"):
            raise web.HTTPBadRequest()
        async with session_factory() as session:
            order = Review.created_at.asc() if status == "pending" else Review.created_at.desc()
            reviews = list((await session.execute(select(Review).where(
                Review.moderation_status == status, Review.source == "site").order_by(order).limit(100))).scalars())
            return web.json_response({"reviews": await describe(session, reviews)})

    async def proof(request):
        try:
            proof_id = int(request.match_info["id"])
        except ValueError:
            raise web.HTTPNotFound() from None
        async with session_factory() as session:
            item = await session.get(ReviewProof, proof_id)
        if item is None or item.review_id is None:
            raise web.HTTPNotFound()
        try:
            data = Path(images.safe_path(settings.proof_dir, item.file_name)).read_bytes()
        except (FileNotFoundError, images.ImageError):
            raise web.HTTPNotFound() from None
        if images.sniff(data) != "WEBP":
            raise web.HTTPNotFound()
        response = web.Response(body=data, content_type="image/webp")
        response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
        response.headers["Content-Disposition"] = "inline"
        return response

    async def decide(request):
        try:
            review_id = int(request.match_info["id"])
            action = request.match_info["action"]
            data = await request.json() if request.can_read_body else {}
        except (ValueError, json.JSONDecodeError):
            raise web.HTTPBadRequest() from None
        if action not in ("approve", "reject", "delete") or not isinstance(data, dict):
            raise web.HTTPBadRequest()
        async with session_factory() as session:
            review = await session.get(Review, review_id)
            if review is None or review.source != "site":
                raise web.HTTPNotFound()
            was_public = review.moderation_status == "approved"
            block = data.get("block") if action == "reject" else None
            if block in ("author", "network"):
                owner = await session.get(User, review.user_id)
                value, kind = (owner.email_hash, "email") if block == "author" else (review.ip_hash, "ip")
                if value:
                    exists = await session.scalar(select(func.count()).select_from(Blocked).where(Blocked.kind == kind, Blocked.value == value))
                    if not exists:
                        session.add(Blocked(kind=kind, value=value, reason=f"отзыв №{review.id}: {str(data.get('reason') or 'накрутка')[:120]}"))
                else:
                    block = None          # nothing to block (the network hash is gone after a decision)
            files = list((await session.execute(select(ReviewProof.file_name).where(
                ReviewProof.review_id == review.id))).scalars())
            await session.execute(delete(ReviewProof).where(ReviewProof.review_id == review.id))
            if action == "delete":
                user_id = review.user_id
                await session.execute(delete(ReviewCriterionScore).where(ReviewCriterionScore.review_id == review.id))
                await session.delete(review)
                await session.flush()
                left = (await session.execute(select(func.count()).select_from(Review).where(
                    Review.user_id == user_id))).scalar_one()
                user = await session.get(User, user_id)
                if not left and user is not None and user.telegram_id is None:
                    await session.delete(user)
            else:
                review.moderation_status = "approved" if action == "approve" else "rejected"
                review.verified = action == "approve" and data.get("verified") is True
                review.moderated_at = utcnow()
                review.ip_hash = None     # needed only to spot a flood while the review waited for moderation
            await audit.record(session, f"review_{action}", f"отзыв №{review_id}",
                               {"author": "автор заблокирован", "network": "сеть заблокирована"}.get(block, ""))
            await session.commit()
            if was_public or action == "approve":
                await store.refresh_ratings(session)
        for name in files:                # screenshots are deleted as soon as a decision is made
            images.remove_file(settings.proof_dir, name)
        log.info("review %s: %s", review_id, action)
        return web.json_response({"ok": True})

    app = web.Application(middlewares=[guard], client_max_size=16 * 1024)
    app.add_routes([
        web.get("/", page),
        web.get("/static/{name}", asset),
        web.get("/api/reviews", queue),
        web.get("/proof/{id}", proof),
        web.post("/api/reviews/{id}/{action}", decide),
    ])
    lead_admin_api.register(app, settings, session_factory)
    console_tools.register(app, settings, session_factory)
    return app
