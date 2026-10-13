"""Console tools: dashboard, health checks, audit log, block list and editorial scores with history."""
import asyncio
import json
import os
import shutil
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiohttp
from aiohttp import web
from sqlalchemy import delete, func, select, text

from egeshka_bot.scoring import BASE_WEIGHTS, MIN_RATED_CRITERIA

from . import audit, mailer, store
from .models import AdminLog, Blocked, Review, School, SchoolScoreHistory, utcnow

MOSCOW = ZoneInfo("Europe/Moscow")
CRITERIA = ("teachers_score", "practice_score", "feedback_score", "curator_score", "platform_score", "workload_score",
            "organization_score")
LABELS = {"teachers_score": "Преподаватели", "practice_score": "Практика и ДЗ", "feedback_score": "Проверка работ",
          "curator_score": "Кураторы", "platform_score": "Платформа", "workload_score": "Нагрузка и темп",
          "organization_score": "Организация"}
STATUSES = ("yes", "tier", "none")
BIG_CHANGE = 1.5            # the console asks for a second confirmation for a jump of this size


def moscow(moment) -> str:
    if moment is None:
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(MOSCOW).strftime("%Y-%m-%d %H:%M")


def parse_status(raw) -> dict:
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        data = {}
    return {key: data.get(key, "yes") for key in CRITERIA}


def editorial(scores: dict, status: dict):
    """Editorial score the same way refresh_rating_snapshots() weighs it: a criterion that is not offered is skipped."""
    total = weight = 0.0
    for key in CRITERIA:
        if status.get(key, "yes") == "none" or scores.get(key) is None:
            continue
        total += float(scores[key]) * BASE_WEIGHTS[key]
        weight += BASE_WEIGHTS[key]
    return round(total / weight, 1) if weight else None


class ScoreError(ValueError):
    pass


def clean_scores(payload, current_scores: dict, current_status: dict):
    """(scores, statuses, changes) from the form; raises ScoreError with the text shown to the owner."""
    if not isinstance(payload, dict) or not isinstance(payload.get("scores"), dict) or not isinstance(payload.get("statuses"), dict):
        raise ScoreError("Некорректный запрос.")
    scores, statuses, changes = {}, {}, {}
    for key in CRITERIA:
        status = payload["statuses"].get(key)
        if status not in STATUSES:
            raise ScoreError(f"Укажи статус критерия «{LABELS[key]}».")
        statuses[key] = status
        raw = payload["scores"].get(key)
        if status == "none":
            scores[key] = float(current_scores[key])      # not offered: not scored; the number stays for the history
        else:
            try:
                value = round(float(raw), 1)
            except (TypeError, ValueError):
                raise ScoreError(f"«{LABELS[key]}»: нужна оценка от 0 до 10.") from None
            if not 0 <= value <= 10 or isinstance(raw, bool):
                raise ScoreError(f"«{LABELS[key]}»: оценка от 0 до 10.")
            scores[key] = value
        if scores[key] != round(float(current_scores[key]), 1):
            changes[key] = [round(float(current_scores[key]), 1), scores[key]]
        if statuses[key] != current_status[key]:
            changes[f"{key}:status"] = [current_status[key], statuses[key]]
    offered = [key for key in CRITERIA if statuses[key] != "none"]
    if len(offered) < MIN_RATED_CRITERIA or "teachers_score" not in offered:
        raise ScoreError(f"Школа должна оцениваться минимум по {MIN_RATED_CRITERIA} критериям, включая преподавателей.")
    return scores, statuses, changes


def register(app: web.Application, settings, session_factory):
    mail_cache = {"at": 0.0, "ok": None, "detail": ""}

    # ---------- dashboard ----------
    async def dashboard(request):
        now = utcnow()
        month_start = datetime(now.year, now.month, 1)
        async with session_factory() as session:
            def count(query):
                return session.scalar(query)
            reviews = {
                "pending": await count(select(func.count()).select_from(Review).where(Review.moderation_status == "pending", Review.source == "site")),
                "approved": await count(select(func.count()).select_from(Review).where(Review.moderation_status == "approved", Review.source == "site")),
                "verified": await count(select(func.count()).select_from(Review).where(Review.moderation_status == "approved", Review.source == "site", Review.verified == True)),  # noqa: E712
                "new_month": await count(select(func.count()).select_from(Review).where(Review.source == "site", Review.created_at >= month_start)),
                "oldest_pending": None,
            }
            oldest = await count(select(func.min(Review.created_at)).where(Review.moderation_status == "pending", Review.source == "site"))
            if oldest:
                reviews["oldest_pending"] = moscow(oldest)
            schools = (await session.execute(select(School).where(School.is_active == True))).scalars().all()  # noqa: E712
            reviewed = sum(1 for s in schools if s.scores_reviewed_at and s.scores_reviewed_at >= month_start)
            blocked = await count(select(func.count()).select_from(Blocked))
            data = {"reviews": reviews, "scores": {"reviewed_this_month": reviewed, "total": len(schools),
                                                    "month": f"{now.year}-{now.month:02d}"}, "blocked": blocked}
            try:   # lead tables exist on the server; in a stripped test database they may not
                lead = {
                    "global": bool(await count(text("select value from site_flags where key = 'leads_enabled'"))),
                    "schools_on": await count(text("select count(*) from lead_schools where enabled")),
                    "month": await count(text("select count(*) from leads where not is_test and created_at >= :m").bindparams(m=month_start)),
                    "waiting": await count(text("select count(*) from leads where not is_test and status in ('new','failed')")),
                }
            except Exception:  # noqa: BLE001
                await session.rollback()
                lead = None
            data["leads"] = lead
        return web.json_response(data)

    # ---------- health ----------
    async def probe(name, url, headers=None, ok_status=(200,)):
        started = time.monotonic()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as http:
                async with http.get(url, headers=headers or {}) as response:
                    ok = response.status in ok_status
                    return {"name": name, "ok": ok, "detail": f"отвечает за {int((time.monotonic() - started) * 1000)} мс" if ok else f"код {response.status}"}
        except Exception as exc:  # noqa: BLE001
            return {"name": name, "ok": False, "detail": f"не отвечает ({type(exc).__name__})"}

    async def check_mail():
        # a good result is kept for 10 minutes, a failure for one, so a one-off hiccup does not sit on the dashboard
        if time.time() - mail_cache["at"] < (600 if mail_cache["ok"] else 60) and mail_cache["ok"] is not None:
            return {"name": "Почта info@egematch.ru (коды и заявки)", "ok": mail_cache["ok"], "detail": mail_cache["detail"]}
        try:
            await asyncio.wait_for(asyncio.to_thread(mailer.check_login, settings), timeout=15)
            mail_cache.update(at=time.time(), ok=True, detail="вход в ящик работает")
        except Exception as exc:  # noqa: BLE001
            mail_cache.update(at=time.time(), ok=False, detail=f"не удалось войти ({type(exc).__name__}): коды и заявки не отправятся")
        return {"name": "Почта info@egematch.ru (коды и заявки)", "ok": mail_cache["ok"], "detail": mail_cache["detail"]}

    async def health(request):
        origin = {"Origin": sorted(settings.origins)[0]} if settings.origins else {}
        checks = await asyncio.gather(
            probe("Форма отзывов (сервис)", f"http://127.0.0.1:{settings.public_port}/api/reviews/form", origin),
            probe("Заявки школам (сервис)", f"http://127.0.0.1:{settings.leads_port}/api/lead-schools", origin),
            probe("Данные для сайта (PostgREST)", f"{settings.postgrest_url}/schools?select=id&limit=1"),
            check_mail(),
        )
        result = list(checks)
        try:
            async with session_factory() as session:
                await session.execute(text("select 1"))
            result.insert(0, {"name": "База данных", "ok": True, "detail": "отвечает"})
            try:
                async with session_factory() as session:
                    newest = await session.scalar(text("select max(calculated_at) from rating_snapshots"))
                if newest is not None:
                    stamp = newest.replace(tzinfo=None) if hasattr(newest, "replace") else newest
                    age = (datetime.now(timezone.utc).replace(tzinfo=None) - stamp).total_seconds() / 3600
                    result.append({"name": "Рейтинги пересчитаны", "ok": age < 30, "detail": f"{int(age)} ч назад" + ("" if age < 30 else " — ночной пересчёт не сработал")})
            except Exception:  # noqa: BLE001 - no snapshots table (test databases)
                pass
        except Exception as exc:  # noqa: BLE001
            result.insert(0, {"name": "База данных", "ok": False, "detail": f"не отвечает ({type(exc).__name__})"})
        try:
            with open(settings.backup_status_file, encoding="utf-8") as handle:
                status = json.load(handle)
            at = datetime.fromisoformat(status["at"])
            age = (datetime.now(timezone.utc) - at).total_seconds() / 3600
            result.append({"name": "Резервная копия базы", "ok": age < 36, "detail": f"{int(age)} ч назад, {status.get('size_mb', '?')} МБ" + ("" if age < 36 else " — копия устарела")})
        except (OSError, ValueError, KeyError):
            result.append({"name": "Резервная копия базы", "ok": False, "detail": "нет данных о резервной копии"})
        try:
            usage = shutil.disk_usage(settings.proof_dir if os.path.isdir(settings.proof_dir) else "/")
            free = usage.free / usage.total * 100
            result.append({"name": "Место на диске", "ok": free > 15, "detail": f"свободно {free:.0f}%"})
        except OSError:
            pass
        return web.json_response({"checks": result, "ok": all(item["ok"] for item in result), "at": moscow(utcnow())})

    # ---------- audit log ----------
    async def audit_list(request):
        async with session_factory() as session:
            rows = (await session.execute(select(AdminLog).order_by(AdminLog.id.desc()).limit(200))).scalars().all()
        return web.json_response({"entries": [{"at": moscow(r.at), "action": r.action, "target": r.target, "detail": r.detail} for r in rows]})

    # ---------- block list ----------
    async def blocked_list(request):
        async with session_factory() as session:
            rows = (await session.execute(select(Blocked).order_by(Blocked.id.desc()))).scalars().all()
        return web.json_response({"blocked": [{"id": r.id, "kind": r.kind, "short": r.value[:8], "reason": r.reason, "at": moscow(r.created_at)} for r in rows]})

    async def unblock(request):
        block_id = int(request.match_info["id"])
        async with session_factory() as session:
            row = await session.get(Blocked, block_id)
            if row is None:
                raise web.HTTPNotFound()
            await session.execute(delete(Blocked).where(Blocked.id == block_id))
            await audit.record(session, "unblock", f"{row.kind}:{row.value[:8]}", row.reason)
            await session.commit()
        return web.json_response({"ok": True})

    # ---------- editorial scores ----------
    async def snapshot_map(_session=None):
        """Current computed scores per school. Own session: a missing table (test databases) must not poison the caller's."""
        try:
            async with session_factory() as session:
                rows = (await session.execute(text("select school_id, editorial_score, final_score, verified_review_count from rating_snapshots"))).all()
        except Exception:  # noqa: BLE001
            return {}
        return {r[0]: {"editorial": float(r[1]) if r[1] is not None else None, "final": float(r[2]) if r[2] is not None else None, "n": r[3]} for r in rows}

    def school_scores(school) -> dict:
        return {key: round(float(getattr(school, key)), 1) for key in CRITERIA}

    def score_row(school, snapshot):
        status = parse_status(school.criteria_status)
        scores = school_scores(school)
        return {"id": school.id, "name": school.name, "scores": scores, "statuses": status, "editorial": editorial(scores, status),
                "final": (snapshot or {}).get("final"), "verified": (snapshot or {}).get("n", 0),
                "reviewed_at": moscow(school.scores_reviewed_at), "reviewed_iso": school.scores_reviewed_at.isoformat() if school.scores_reviewed_at else ""}

    async def scores_list(request):
        async with session_factory() as session:
            schools = (await session.execute(select(School).where(School.is_active == True).order_by(School.name))).scalars().all()  # noqa: E712
        snaps = await snapshot_map()
        now = utcnow()
        return web.json_response({"schools": [score_row(s, snaps.get(s.id)) for s in schools], "labels": LABELS,
                                  "month": f"{now.year}-{now.month:02d}", "big_change": BIG_CHANGE,
                                  "weights": {k: BASE_WEIGHTS[k] for k in CRITERIA}})

    async def scores_save(request):
        school_id = int(request.match_info["id"])
        payload = await request.json()
        reason = str(payload.get("reason") or "").strip() if isinstance(payload, dict) else ""
        async with session_factory() as session:
            school = await session.get(School, school_id)
            if school is None:
                raise web.HTTPNotFound()
            try:
                scores, statuses, changes = clean_scores(payload, school_scores(school), parse_status(school.criteria_status))
            except ScoreError as exc:
                return web.json_response({"error": str(exc)}, status=400)
            if changes and len(reason) < 5:
                return web.json_response({"error": "Опиши основание изменения (источник, дата): хотя бы пару слов."}, status=400)
            if changes:
                for key, value in scores.items():
                    setattr(school, key, value)
                school.criteria_status = json.dumps({k: v for k, v in statuses.items() if v != "yes"}, ensure_ascii=False)
            school.scores_reviewed_at = utcnow()
            session.add(SchoolScoreHistory(school_id=school.id, reason=reason[:500] or "проверено, без изменений",
                                           changes=json.dumps(changes, ensure_ascii=False)))
            await audit.record(session, "scores", school.name, (f"{len(changes)} изм.: " if changes else "проверено без изменений: ") + (reason[:200] or "—"))
            await session.commit()
            if changes:
                await store.refresh_ratings(session)
            row_base = score_row(school, None)
        snaps = await snapshot_map()
        row_base["final"] = (snaps.get(school_id) or {}).get("final")
        row_base["verified"] = (snaps.get(school_id) or {}).get("n", 0)
        return web.json_response({"school": row_base, "changes": len(changes)})

    async def scores_history(request):
        school_id = int(request.match_info["id"])
        async with session_factory() as session:
            rows = (await session.execute(select(SchoolScoreHistory).where(SchoolScoreHistory.school_id == school_id)
                                          .order_by(SchoolScoreHistory.id.desc()).limit(50))).scalars().all()
        out = []
        for row in rows:
            try:
                changes = json.loads(row.changes or "{}")
            except ValueError:
                changes = {}
            out.append({"at": moscow(row.at), "reason": row.reason, "changes": changes})
        return web.json_response({"history": out, "labels": LABELS})

    app.add_routes([
        web.get("/api/dashboard", dashboard),
        web.get("/api/health", health),
        web.get("/api/audit", audit_list),
        web.get("/api/blocked", blocked_list),
        web.post("/api/blocked/{id:\\d+}/remove", unblock),
        web.get("/api/scores", scores_list),
        web.post("/api/scores/{id:\\d+}/save", scores_save),
        web.get("/api/scores/{id:\\d+}/history", scores_history),
    ])
