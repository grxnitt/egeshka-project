"""Console tools: editorial scores with history, audit log, block list and the review form honouring it."""
import asyncio
import json
import re
import time

import pytest
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from reviews_service import admin_app, public_api, validation
from reviews_service.config import Settings
from reviews_service.console_tools import ScoreError, clean_scores, editorial
from reviews_service.models import AdminLog, Base, Blocked, Review, School, SchoolScoreHistory, User
from reviews_service.security import Keys

LOCAL = {"Host": "127.0.0.1:8090"}
KEYS = ("teachers_score", "practice_score", "feedback_score", "curator_score", "platform_score", "workload_score", "organization_score")
CURRENT = {key: 8.0 for key in KEYS}
YES = {key: "yes" for key in KEYS}


def run(coro):
    return asyncio.run(coro)


def test_editorial_score_skips_criteria_the_school_does_not_offer():
    scores = {**CURRENT, "curator_score": 3.0}
    assert editorial(scores, YES) < 8.0
    assert editorial(scores, {**YES, "curator_score": "none"}) == 8.0


def test_score_form_validation():
    ok, statuses, changes = clean_scores({"scores": {**CURRENT, "teachers_score": 9.04}, "statuses": YES}, CURRENT, YES)
    assert ok["teachers_score"] == 9.0 and changes == {"teachers_score": [8.0, 9.0]}
    for bad in ({"scores": {**CURRENT, "teachers_score": 11}, "statuses": YES},
                {"scores": {**CURRENT, "teachers_score": "abc"}, "statuses": YES},
                {"scores": CURRENT, "statuses": {**YES, "teachers_score": "none"}},      # teachers are always scored
                {"scores": CURRENT, "statuses": {**YES, "curator_score": "none", "feedback_score": "none", "platform_score": "none"}},
                {"scores": CURRENT, "statuses": {**YES, "curator_score": "maybe"}}, {"scores": CURRENT}, []):
        with pytest.raises(ScoreError):
            clean_scores(bad, CURRENT, YES)


async def make_env(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tools.sqlite'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add(School(id=1, name="Школа", criteria_status="{}", is_active=True, **{k: 8.0 for k in KEYS}))
        await session.commit()
    settings = Settings(hmac_secret="x" * 40, proof_dir=str(tmp_path / "proofs"), database_url="sqlite://",
                        backup_status_file=str(tmp_path / "none.json"))
    return engine, sessions, settings


def test_editing_scores_needs_a_reason_and_leaves_history_and_a_log_entry(tmp_path):
    async def scenario():
        engine, sessions, settings = await make_env(tmp_path)
        admin = TestClient(TestServer(admin_app.create_app(settings, sessions)))
        await admin.start_server()
        try:
            page = await (await admin.get("/", headers=LOCAL)).text()
            h = {**LOCAL, "X-Admin-Token": re.search(r'admin-token" content="([^"]+)', page).group(1)}
            body = {"scores": {**CURRENT, "curator_score": 6.5}, "statuses": {**YES, "curator_score": "tier"}}
            assert (await admin.post("/api/scores/1/save", json=body, headers=LOCAL)).status == 403          # token required
            r = await admin.post("/api/scores/1/save", json=body, headers=h)
            assert r.status == 400 and "основание" in (await r.json())["error"]                              # reason required
            r = await admin.post("/api/scores/1/save", json={**body, "reason": "Сайт школы: куратор только на старших тарифах, 11.10.2026"}, headers=h)
            data = await r.json()
            assert r.status == 200 and data["changes"] == 2 and data["school"]["scores"]["curator_score"] == 6.5
            assert data["school"]["statuses"]["curator_score"] == "tier" and data["school"]["reviewed_at"]
            async with sessions() as session:
                school = await session.get(School, 1)
                assert school.curator_score == 6.5 and json.loads(school.criteria_status) == {"curator_score": "tier"}
                assert len((await session.execute(select(SchoolScoreHistory))).scalars().all()) == 1
                assert (await session.execute(select(AdminLog))).scalars().first().action == "scores"
            history = await (await admin.get("/api/scores/1/history", headers=LOCAL)).json()
            assert history["history"][0]["changes"]["curator_score"] == [8.0, 6.5]
            # "checked, no changes" needs no reason and still stamps the month
            r = await admin.post("/api/scores/1/save", json={"scores": {**CURRENT, "curator_score": 6.5}, "statuses": body["statuses"]}, headers=h)
            assert r.status == 200 and (await r.json())["changes"] == 0
            listing = await (await admin.get("/api/scores", headers=LOCAL)).json()
            assert listing["schools"][0]["editorial"] is not None
            dash = await (await admin.get("/api/dashboard", headers=LOCAL)).json()
            assert dash["scores"]["reviewed_this_month"] == 1
            log = await (await admin.get("/api/audit", headers=LOCAL)).json()
            assert [e["action"] for e in log["entries"]][:2] == ["scores", "scores"]
        finally:
            await admin.close()
            await engine.dispose()
    run(scenario())


def test_blocking_an_author_stops_new_reviews_from_that_email(tmp_path):
    async def scenario():
        engine, sessions, settings = await make_env(tmp_path)
        keys, sent = Keys("x" * 40), []

        async def mail(to, subject, body):
            sent.append(body)

        public = TestClient(TestServer(public_api.create_app(settings, sessions, send_mail=mail)))
        admin = TestClient(TestServer(admin_app.create_app(settings, sessions)))
        await public.start_server()
        await admin.start_server()
        try:
            origin = {"Origin": "https://egematch.ru"}

            def payload(email):
                data = {"school_id": 1, "teacher_id": None, "scores": {k: 8 for k in KEYS}, "positive": "Достаточно длинный текст отзыва для проверки блокировки.",
                        "negative": "", "period": "2025/26", "email": email, "consent": True, "consent_version": validation.CONSENT_VERSION,
                        "formToken": keys.form_token(time.time() - 20), "website": ""}
                form = FormData()
                form.add_field("payload", json.dumps(data), content_type="application/json")
                return form

            r = await public.post("/api/reviews/draft", data=payload("spam@mail.ru"), headers=origin)
            token = (await r.json())["draftToken"]
            code = re.search(r"\b(\d{6})\b", sent[-1]).group(1)
            await public.post("/api/reviews/confirm", json={"draftToken": token, "code": code}, headers=origin)
            page = await (await admin.get("/", headers=LOCAL)).text()
            h = {**LOCAL, "X-Admin-Token": re.search(r'admin-token" content="([^"]+)', page).group(1)}
            review_id = (await (await admin.get("/api/reviews", headers=LOCAL)).json())["reviews"][0]["id"]
            r = await admin.post(f"/api/reviews/{review_id}/reject", json={"block": "author", "reason": "накрутка"}, headers=h)
            assert r.status == 200
            async with sessions() as session:
                blocked = (await session.execute(select(Blocked))).scalars().all()
                assert [b.kind for b in blocked] == ["email"] and blocked[0].value == keys.email("spam@mail.ru")
            r = await public.post("/api/reviews/draft", data=payload("spam@mail.ru"), headers=origin)      # same person: refused
            assert r.status == 403
            r = await public.post("/api/reviews/draft", data=payload("other@mail.ru"), headers=origin)       # someone else: fine
            assert r.status == 200
            blocked_list = await (await admin.get("/api/blocked", headers=LOCAL)).json()
            assert "spam@mail.ru" not in json.dumps(blocked_list) and blocked_list["blocked"][0]["short"]
            await admin.post(f"/api/blocked/{blocked_list['blocked'][0]['id']}/remove", json={}, headers=h)
            r = await public.post("/api/reviews/draft", data=payload("spam@mail.ru"), headers=origin)
            assert r.status == 200                                                                           # unblocked
        finally:
            await public.close()
            await admin.close()
            await engine.dispose()
    run(scenario())


def test_health_reports_a_missing_backup_and_a_down_service(tmp_path):
    async def scenario():
        engine, sessions, settings = await make_env(tmp_path)
        admin = TestClient(TestServer(admin_app.create_app(settings, sessions)))
        await admin.start_server()
        try:
            data = await (await admin.get("/api/health", headers=LOCAL)).json()
            by_name = {c["name"]: c for c in data["checks"]}
            assert by_name["База данных"]["ok"] is True
            assert by_name["Резервная копия базы"]["ok"] is False and by_name["Форма отзывов (сервис)"]["ok"] is False
            assert data["ok"] is False
        finally:
            await admin.close()
            await engine.dispose()
    run(scenario())


def test_console_tools_page_renders_text_only():
    from pathlib import Path
    script = (Path(__file__).resolve().parents[1] / "reviews_service" / "admin_static" / "tools.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script and "insertAdjacentHTML" not in script and "eval(" not in script


def test_every_console_script_is_valid_javascript():
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    for script in (Path(__file__).resolve().parents[1] / "reviews_service" / "admin_static").glob("*.js"):
        result = subprocess.run([node, "--check", str(script)], capture_output=True, text=True)
        assert result.returncode == 0, f"{script.name}: {result.stderr[:300]}"
