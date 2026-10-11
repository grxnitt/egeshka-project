"""Site-facing API on 127.0.0.1:8085, published by Caddy as https://data.egematch.ru/api/...

GET  /api/reviews/form            form token (anti-bot timing) and the current consent version
POST /api/reviews/draft           multipart: "payload" (JSON) + up to 3 "proof" images -> code sent to the email
POST /api/reviews/resend          {"draftToken", "email"} -> a new code (the email is not stored, so it is sent again)
POST /api/reviews/confirm         {"draftToken", "code"} -> review queued for moderation
POST /api/data/delete/request     {"email", "formToken"} -> code sent to the email
POST /api/data/delete/confirm     {"requestToken", "code"} -> every review left with that email is deleted

The service never stores an email or IP in clear text: only keyed hashes (security.Keys). Moderation is not
reachable from here at all; it runs as a separate process, on localhost only, under another database role.
"""
import asyncio
import json
import logging
import os
import time

from aiohttp import web
from sqlalchemy import func, select

from . import images, mailer, store, validation
from .models import Blocked, DeletionRequest, ReviewProof, utcnow
from .security import (MAX_CODE_ATTEMPTS, MAX_RESENDS, RESEND_COOLDOWN, Keys, RateLimiter, client_ip, new_code, new_token)
from .validation import ReviewError

log = logging.getLogger("reviews.public")
MAX_BODY = images.MAX_FILES * images.MAX_UPLOAD_BYTES + 64 * 1024
NOTIFY_EVERY = 3600


def create_app(settings, session_factory, sanitizer=None, send_mail=None) -> web.Application:
    keys = Keys(settings.hmac_secret)
    sanitizer = sanitizer or images.Sanitizer()
    send_mail = send_mail or (lambda to, subject, body: mailer.send(settings, to, subject, body))
    os.makedirs(settings.proof_dir, mode=0o750, exist_ok=True)
    limits = {
        "attempt_ip": RateLimiter(30, 3600), "draft_ip": RateLimiter(6, 3600), "draft_email": RateLimiter(5, 3600), "confirm_ip": RateLimiter(30, 3600),
        "resend_ip": RateLimiter(10, 3600), "delete_ip": RateLimiter(5, 3600), "delete_email": RateLimiter(2, 3600),
        "form_ip": RateLimiter(60, 3600),
    }
    uploads = asyncio.Semaphore(2)
    notified = {"at": 0.0}

    def reply(payload, status=200):
        return web.json_response(payload, status=status)

    def fail(message, status=400):
        return reply({"error": message}, status)

    @web.middleware
    async def guard(request, handler):
        origin = request.headers.get("Origin", "")
        if request.method == "OPTIONS":
            response = web.Response(status=204)
        elif request.method == "POST" and origin not in settings.origins:
            response = fail("Запрос не с сайта egematch.ru.", 403)   # other sites cannot submit on a visitor's behalf
        else:
            try:
                response = await handler(request)
            except web.HTTPException as exc:
                response = exc
            except ReviewError as exc:
                response = fail(str(exc))
            except images.ImageError as exc:
                response = fail(str(exc))
            except Exception:  # noqa: BLE001
                log.exception("unhandled error on %s", request.path)
                response = fail("Что-то пошло не так. Попробуй ещё раз чуть позже.", 500)
        if origin in settings.origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Max-Age"] = "600"
            response.headers["Vary"] = "Origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    async def json_body(request):
        if request.content_length is not None and request.content_length > 8192:
            raise ReviewError("Некорректный запрос.")
        raw = await request.content.read(8193)          # also caps chunked bodies that declare no length
        if len(raw) > 8192:
            raise ReviewError("Некорректный запрос.")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ReviewError("Некорректный запрос.") from None
        if not isinstance(data, dict):
            raise ReviewError("Некорректный запрос.")
        return data

    def email_key(email: str) -> str:
        return keys.email(validation.identity_email(email))

    async def is_blocked(session, email_hash: str, ip_hash: str) -> bool:
        values = [value for value in (email_hash, ip_hash) if value]
        if not values:
            return False
        return bool(await session.scalar(select(func.count()).select_from(Blocked).where(Blocked.value.in_(values))))

    async def form(request):
        if not limits["form_ip"].allow(client_ip(request)):
            return fail("Слишком много запросов. Попробуй позже.", 429)
        return reply({"formToken": keys.form_token(), "consentVersion": validation.CONSENT_VERSION,
                      "periods": list(validation.STUDY_PERIODS)})

    async def read_multipart(request):
        """('payload' JSON text, [file bytes]) with every size limit enforced while reading."""
        if not request.content_type.startswith("multipart/form-data"):
            raise ReviewError("Некорректный запрос.")
        if request.content_length is not None and request.content_length > MAX_BODY:
            raise ReviewError("Файлы слишком большие: до 10 МБ каждый, не больше трёх.")
        reader = await request.multipart()
        payload, files = None, []
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "payload" and payload is None:
                raw = await part.read(decode=False)
                if len(raw) > 20_000:
                    raise ReviewError("Некорректный запрос.")
                payload = raw.decode("utf-8", "strict")
            elif part.name == "proof":
                if len(files) >= images.MAX_FILES:
                    raise ReviewError("Не больше трёх скриншотов.")
                chunks, size = [], 0
                while True:
                    chunk = await part.read_chunk(256 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > images.MAX_UPLOAD_BYTES:
                        raise ReviewError("Файл больше 10 МБ. Сделай скриншот поменьше.")
                    chunks.append(chunk)
                if size:
                    files.append(b"".join(chunks))
            else:
                raise ReviewError("Некорректный запрос.")
        return payload, files

    async def create_draft(request):
        ip = client_ip(request)
        if not limits["attempt_ip"].allow(ip):
            return fail("Слишком много попыток с этого устройства. Попробуй через час.", 429)
        raw, files = await read_multipart(request)
        data = validation.parse_payload(raw)
        if validation.honeypot_filled(data) or not keys.form_token_ok(data.get("formToken")):
            return fail("Форма заполнена слишком быстро или устарела. Обнови страницу и попробуй снова.")
        validation.check_consent(data)
        email = validation.normalize_email(data.get("email"))
        email_hash = email_key(email)
        school_id, teacher_id = validation.clean_target(data)
        async with session_factory() as session:
            if await is_blocked(session, email_hash, keys.ip(ip)):
                # Same answer as a transient failure: a blocked sender learns nothing about what was matched.
                return fail("Не получилось принять отзыв. Если это ошибка, напиши на info@egematch.ru.", 403)
            school, teacher = await store.target(session, school_id, teacher_id)
        if school is None:
            return fail("Такой школы или преподавателя нет в каталоге. Обнови страницу.")
        review = validation.clean_review(data, school, teacher)
        # Only a valid review spends the strict limits: image processing and a letter are the expensive parts.
        if not limits["draft_ip"].allow(ip):
            return fail("Слишком много отзывов с этого устройства. Попробуй через час.", 429)
        if not limits["draft_email"].allow(email_hash):
            return fail("С этой почты уже отправляли несколько отзывов за последний час. Попробуй позже.", 429)
        written = []
        try:
            async with uploads:
                for blob in files:
                    webp, width, height = await sanitizer.clean(blob)
                    name = images.new_file_name()
                    images.write_file(settings.proof_dir, name, webp)
                    written.append((name, width, height, len(webp)))
            token, code = new_token(), new_code()
            token_hash = keys.token(token)
            payload = {"school_id": school.id, "teacher_id": teacher.id if teacher else None, **review}
            async with session_factory() as session:
                draft = await store.create_draft(session, token_hash=token_hash, email_hash=email_hash,
                                                 code_hash=keys.code(token_hash, code), payload=payload,
                                                 ip_hash=keys.ip(ip), proofs=written)
                draft_id = draft.id
            written_names = [item[0] for item in written]
            written = []   # owned by the draft now; cleanup removes them if it expires
        finally:
            for name, *_ in written:
                images.remove_file(settings.proof_dir, name)
        try:
            await send_mail(email, *mailer.review_code_letter(code))
        except mailer.MailError:
            async with session_factory() as session:
                await store.drop_draft(session, draft_id)
            for name in written_names:
                images.remove_file(settings.proof_dir, name)
            return fail("Не получилось отправить письмо. Проверь адрес или попробуй позже.", 503)
        return reply({"draftToken": token, "email": validation.mask_email(email), "resendIn": RESEND_COOLDOWN})

    async def resend(request):
        if not limits["resend_ip"].allow(client_ip(request)):
            return fail("Слишком много запросов. Попробуй позже.", 429)
        data = await json_body(request)
        email = validation.normalize_email(data.get("email"))
        async with session_factory() as session:
            draft = await store.draft_by_token(session, keys.token(str(data.get("draftToken", ""))))
            if draft is None or draft.email_hash != email_key(email):
                return fail("Черновик отзыва не найден или устарел. Отправь отзыв заново.", 404)
            wait = RESEND_COOLDOWN - (utcnow() - draft.last_sent_at).total_seconds()
            if wait > 0:
                return fail(f"Новый код можно запросить через {int(wait) + 1} с.", 429)
            if draft.resends >= MAX_RESENDS:
                return fail("Код уже отправляли несколько раз. Отправь отзыв заново.", 429)
            if not limits["draft_email"].allow(draft.email_hash):   # every letter to an address counts
                return fail("На эту почту уже отправили несколько писем за последний час. Попробуй позже.", 429)
            code = new_code()
            draft.code_hash, draft.attempts = keys.code(draft.token_hash, code), 0
            draft.resends += 1
            draft.last_sent_at = utcnow()
            await session.commit()
        try:
            await send_mail(email, *mailer.review_code_letter(code))
        except mailer.MailError:
            return fail("Не получилось отправить письмо. Попробуй позже.", 503)
        return reply({"ok": True, "resendIn": RESEND_COOLDOWN})

    async def confirm(request):
        if not limits["confirm_ip"].allow(client_ip(request)):
            return fail("Слишком много попыток. Попробуй позже.", 429)
        data = await json_body(request)
        code = str(data.get("code", "")).strip()
        async with session_factory() as session:
            draft = await store.draft_by_token(session, keys.token(str(data.get("draftToken", ""))))
            if draft is None:
                return fail("Черновик отзыва не найден или устарел. Отправь отзыв заново.", 404)
            if await is_blocked(session, draft.email_hash, draft.ip_hash):
                names = list((await session.execute(select(ReviewProof.file_name).where(ReviewProof.draft_id == draft.id))).scalars())
                await store.drop_draft(session, draft.id)
                for name in names:
                    images.remove_file(settings.proof_dir, name)
                return fail("Не получилось принять отзыв. Если это ошибка, напиши на info@egematch.ru.", 403)
            result = store.check_code(draft, keys.code(draft.token_hash, code))
            if result == store.CodeResult.WRONG:
                draft.attempts += 1
                await session.commit()
                left = max(0, MAX_CODE_ATTEMPTS - draft.attempts)
                return fail(f"Код не подходит. Осталось попыток: {left}." if left else "Код не подходит. Запроси новый код.")
            if result == store.CodeResult.LOCKED:
                return fail("Слишком много неверных попыток. Запроси новый код.", 429)
            if result == store.CodeResult.EXPIRED:
                return fail("Код устарел. Запроси новый.")
            review_id, removed, replaced = await store.confirm_draft(session, draft)
        for name in removed:
            images.remove_file(settings.proof_dir, name)
        if settings.admin_notify_email and time.time() - notified["at"] > NOTIFY_EVERY:
            notified["at"] = time.time()
            asyncio.create_task(notify_admin())
        return reply({"ok": True, "replaced": replaced})

    async def notify_admin():
        try:
            async with session_factory() as session:
                count = await store.pending_count(session)
            await send_mail(settings.admin_notify_email, *mailer.moderation_letter(count))
        except Exception:  # noqa: BLE001 - a missed notification must never break a review
            log.warning("moderation notification failed")

    async def delete_request(request):
        ip = client_ip(request)
        if not limits["delete_ip"].allow(ip):
            return fail("Слишком много запросов. Попробуй через час.", 429)
        data = await json_body(request)
        if validation.honeypot_filled(data) or not keys.form_token_ok(data.get("formToken")):
            return fail("Форма устарела. Обнови страницу и попробуй снова.")
        email = validation.normalize_email(data.get("email"))
        email_hash = email_key(email)
        if not limits["delete_email"].allow(email_hash):
            return fail("Код уже отправляли несколько раз. Попробуй через час.", 429)
        token, code = new_token(), new_code()
        token_hash = keys.token(token)
        async with session_factory() as session:
            await store.create_deletion_request(session, token_hash, email_hash, keys.code(token_hash, code))
        try:
            await send_mail(email, *mailer.deletion_code_letter(code))
        except mailer.MailError:
            return fail("Не получилось отправить письмо. Попробуй позже.", 503)
        # The same answer whether or not this email has reviews: the page reveals nothing about who wrote what.
        return reply({"requestToken": token, "email": validation.mask_email(email)})

    async def delete_confirm(request):
        if not limits["confirm_ip"].allow(client_ip(request)):
            return fail("Слишком много попыток. Попробуй позже.", 429)
        data = await json_body(request)
        code = str(data.get("code", "")).strip()
        async with session_factory() as session:
            record = (await session.execute(select(DeletionRequest).where(
                DeletionRequest.token_hash == keys.token(str(data.get("requestToken", "")))))).scalar_one_or_none()
            if record is None:
                return fail("Запрос не найден или устарел. Начни заново.", 404)
            result = store.check_code(record, keys.code(record.token_hash, code))
            if result == store.CodeResult.WRONG:
                record.attempts += 1
                await session.commit()
                return fail("Код не подходит.")
            if result != store.CodeResult.OK:
                return fail("Код устарел или попыток слишком много. Начни заново.", 429)
            email_hash = record.email_hash
            await session.delete(record)
            await session.commit()
            count, files = await store.delete_person(session, email_hash)
            if count:
                await store.refresh_ratings(session)
        for name in files:
            images.remove_file(settings.proof_dir, name)
        return reply({"ok": True, "reviews": count})

    async def on_cleanup(app):
        sanitizer.close()

    app = web.Application(middlewares=[guard], client_max_size=MAX_BODY)
    app.on_cleanup.append(on_cleanup)
    app.add_routes([
        web.get("/api/reviews/form", form),
        web.post("/api/reviews/draft", create_draft),
        web.post("/api/reviews/resend", resend),
        web.post("/api/reviews/confirm", confirm),
        web.post("/api/data/delete/request", delete_request),
        web.post("/api/data/delete/confirm", delete_confirm),
    ])
    return app
