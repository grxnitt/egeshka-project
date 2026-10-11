"""Site reviews: validation, hostile uploads, the email-code flow, deletion and the moderation console."""
import asyncio
import io
import json
import os
import re
import time
from pathlib import Path

import pytest
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from reviews_service import admin_app, images, public_api, validation
from reviews_service.config import Settings
from reviews_service.models import (Base, Review, ReviewCriterionScore, ReviewDraft, ReviewProof, School, Teacher,
                                    User)
from reviews_service.security import Keys
from reviews_service.validation import ReviewError

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://egematch.ru"
SECRET = "x" * 40


def png(width=400, height=300, color=(40, 80, 200), exif=False, mode="RGB"):
    picture = Image.new(mode, (width, height), color if mode == "RGB" else None)
    out = io.BytesIO()
    if exif:
        data = Image.Exif()
        data[0x010F] = "SecretPhone"          # Make
        data[0x8825] = {2: (55.0, 45.0, 0.0)}  # GPS
        picture.save(out, format="JPEG", exif=data.tobytes())
    else:
        picture.save(out, format="PNG")
    return out.getvalue()


# ---------- validation ----------

def test_email_rules():
    assert validation.normalize_email("  Ivan@Mail.RU ") == "ivan@mail.ru"
    for bad in ("", "no-at", "a@b", "x@mailinator.com", "a" * 300 + "@mail.ru", "<script>@x.ru"):
        with pytest.raises(ReviewError):
            validation.normalize_email(bad)
    assert validation.identity_email("i.van+reviews@googlemail.com") == "ivan@gmail.com"
    assert validation.identity_email("pe.tr@ya.ru") == validation.identity_email("pe-tr@yandex.ru")
    assert validation.mask_email("ivanov@mail.ru").startswith("iv") and "ivanov" not in validation.mask_email("ivanov@mail.ru")


class FakeSchool:
    id, is_active = 1, True
    criteria_status = json.dumps({"curator_score": "tier", "platform_score": "none"})


GOOD_TEXT = "Хорошо объясняют вторую часть, домашки проверяют подробно и быстро."


def school_scores(**extra):
    scores = {"teachers_score": 9, "practice_score": 8, "feedback_score": 8, "workload_score": 7,
              "organization_score": 9}
    scores.update(extra)
    return scores


def test_review_asks_only_what_the_school_offers():
    data = {"scores": school_scores(), "positive": GOOD_TEXT, "negative": "", "period": "2025/26"}
    clean = validation.clean_review(data, FakeSchool, None)
    assert clean["score"] == 8 and "curator_score" not in clean["scores"]
    clean = validation.clean_review({**data, "scores": school_scores(curator_score=6)}, FakeSchool, None)
    assert clean["scores"]["curator_score"] == 6               # a 'tier' criterion may be rated
    for broken in (school_scores(platform_score=9),            # 'none' criterion: not asked, so refused
                   {"teachers_score": 9},                      # missing required scores
                   school_scores(teachers_score=11), school_scores(teachers_score=True),
                   school_scores(teachers_score="9"), school_scores(teachers_score=7.5)):
        with pytest.raises(ReviewError):
            validation.clean_review({**data, "scores": broken}, FakeSchool, None)


def test_review_text_rules():
    base = {"scores": school_scores(), "period": "2025/26", "negative": ""}
    for positive in ("коротко", "Отлично, вот промокод: https://spam.example/x " + GOOD_TEXT, "x" * 2001,
                     "Пишите мне в tg, сайт school-deal.ru " + GOOD_TEXT):
        with pytest.raises(ReviewError):
            validation.clean_review({**base, "positive": positive}, FakeSchool, None)
    with pytest.raises(ReviewError):
        validation.clean_review({**base, "positive": GOOD_TEXT, "period": "2019"}, FakeSchool, None)
    clean = validation.clean_review({**base, "positive": "‮Переворот​ " + GOOD_TEXT + "\x00\x07"}, FakeSchool, None)
    assert "‮" not in clean["positive"] and "\x00" not in clean["positive"] and "​" not in clean["positive"]


def test_form_token_needs_time_and_our_signature():
    keys = Keys(SECRET)
    now = time.time()
    assert not keys.form_token_ok(keys.form_token(now), now + 2)          # posted too fast
    assert keys.form_token_ok(keys.form_token(now), now + 30)
    assert not keys.form_token_ok(keys.form_token(now), now + 5 * 3600)   # stale
    assert not keys.form_token_ok(Keys("y" * 40).form_token(now), now + 30)
    assert not keys.form_token_ok("garbage", now)


# ---------- hostile uploads ----------

def run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def sanitizer():
    item = images.Sanitizer()
    yield item
    item.close()


def test_images_are_redrawn_without_metadata(sanitizer):
    webp, width, height = run(sanitizer.clean(png(exif=True)))
    assert images.sniff(webp) == "WEBP" and (width, height) == (400, 300)
    redrawn = Image.open(io.BytesIO(webp))
    assert not redrawn.getexif() and "icc_profile" not in redrawn.info and "exif" not in redrawn.info
    assert b"SecretPhone" not in webp
    big, w, h = run(sanitizer.clean(png(4000, 3000)))
    assert max(w, h) == images.MAX_SIDE


@pytest.mark.parametrize("payload", [
    b"<html><script>alert(1)</script></html>",
    b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>',
    b"%PDF-1.7\n1 0 obj<</JS (app.alert(1))>>",
    b"GIF89a" + b"\x00" * 100,
    b"MZ\x90\x00" + b"\x00" * 200,                         # a Windows executable
    b"\x89PNG\r\n\x1a\n" + b"<?php system($_GET['x']); ?>" * 20,   # PNG header, not a PNG
    b"\xff\xd8\xff\xe0" + os.urandom(3000),                # JPEG header, garbage body
    b"",
])
def test_anything_that_is_not_a_real_image_is_refused(sanitizer, payload):
    with pytest.raises(images.ImageError):
        run(sanitizer.clean(payload))


def test_polyglot_keeps_only_pixels(sanitizer):
    # a real PNG with a script appended after the image data: decodes, but the appended bytes do not survive
    data = png() + b"<script>alert(document.cookie)</script>"
    webp, *_ = run(sanitizer.clean(data))
    assert b"script" not in webp


def test_decompression_bomb_is_refused(sanitizer):
    out = io.BytesIO()
    Image.new("1", (12000, 12000)).save(out, format="PNG")    # tiny file, 144 MP once decoded
    assert len(out.getvalue()) < 200_000
    with pytest.raises(images.ImageError):
        run(sanitizer.clean(out.getvalue()))


def test_file_names_cannot_escape_the_folder():
    for bad in ("../../etc/passwd", "a.webp", "x" * 40 + ".webp", "/abs/" + "a" * 40 + ".webp", "a" * 40 + ".svg"):
        with pytest.raises(images.ImageError):
            images.safe_path("/var/x", bad)
    assert images.safe_path("/var/x", "a" * 40 + ".webp") == "/var/x/" + "a" * 40 + ".webp"


# ---------- the whole flow over HTTP ----------

class Mailbox:
    def __init__(self):
        self.sent = []

    async def __call__(self, to, subject, body):
        self.sent.append((to, subject, body))

    def last_code(self):
        return re.search(r"\b(\d{6})\b", self.sent[-1][2]).group(1)


async def make_env(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add(School(id=1, name="Школа", criteria_status=FakeSchool.criteria_status, is_active=True))
        session.add(School(id=2, name="Закрытая", criteria_status="{}", is_active=False))
        session.add(Teacher(id=7, school_id=1, name="Препод", is_active=True))
        await session.commit()
    settings = Settings(hmac_secret=SECRET, proof_dir=str(tmp_path / "proofs"), database_url="sqlite://")
    return engine, sessions, settings


def payload(keys, **over):
    data = {"school_id": 1, "teacher_id": None, "scores": school_scores(), "positive": GOOD_TEXT, "negative": "",
            "period": "2025/26", "email": "Student@Mail.ru", "consent": True,
            "consent_version": validation.CONSENT_VERSION, "formToken": keys.form_token(time.time() - 20),
            "website": ""}
    data.update(over)
    return data


def form(data, files=()):
    body = FormData()
    body.add_field("payload", json.dumps(data), content_type="application/json")
    for blob in files:
        body.add_field("proof", blob, filename="shot.png", content_type="image/png")
    return body


def test_review_flow_end_to_end(tmp_path, sanitizer):
    async def scenario():
        engine, sessions, settings = await make_env(tmp_path)
        mail, keys = Mailbox(), Keys(SECRET)
        client = TestClient(TestServer(public_api.create_app(settings, sessions, sanitizer, mail)))
        await client.start_server()
        try:
            h = {"Origin": ORIGIN}
            # another site cannot post on a visitor's behalf
            r = await client.post("/api/reviews/draft", data=form(payload(keys)), headers={"Origin": "https://evil.example"})
            assert r.status == 403
            # bots: honeypot filled, or the form posted instantly
            assert (await client.post("/api/reviews/draft", data=form(payload(keys, website="x")), headers=h)).status == 400
            fast = payload(keys, formToken=keys.form_token(time.time()))
            assert (await client.post("/api/reviews/draft", data=form(fast), headers=h)).status == 400
            # no consent, inactive school, foreign teacher
            assert (await client.post("/api/reviews/draft", data=form(payload(keys, consent=False)), headers=h)).status == 400
            assert (await client.post("/api/reviews/draft", data=form(payload(keys, school_id=2)), headers=h)).status == 400
            # a fake image is refused and nothing is left on disk
            r = await client.post("/api/reviews/draft", data=form(payload(keys), [b"<html>evil</html>"]), headers=h)
            assert r.status == 400 and not any(Path(settings.proof_dir).iterdir())
            assert not mail.sent

            r = await client.post("/api/reviews/draft", data=form(payload(keys), [png(exif=True)]), headers=h)
            assert r.status == 200, await r.text()
            draft = await r.json()
            assert "Student" not in json.dumps(draft) and draft["email"].endswith("@mail.ru")
            code = mail.last_code()
            async with sessions() as session:
                stored = (await session.execute(select(ReviewDraft))).scalar_one()
                assert "student" not in stored.payload.lower() and code not in stored.code_hash
                assert stored.email_hash == keys.email("student@mail.ru")

            # wrong codes count down and lock
            for _ in range(5):
                r = await client.post("/api/reviews/confirm", json={"draftToken": draft["draftToken"], "code": "000000" if code != "000000" else "111111"}, headers=h)
            assert r.status == 400
            r = await client.post("/api/reviews/confirm", json={"draftToken": draft["draftToken"], "code": code}, headers=h)
            assert r.status == 429                                     # locked after five misses
            # resend needs the same email (it is not stored) and waits for the cooldown
            r = await client.post("/api/reviews/resend", json={"draftToken": draft["draftToken"], "email": "other@mail.ru"}, headers=h)
            assert r.status == 404
            r = await client.post("/api/reviews/resend", json={"draftToken": draft["draftToken"], "email": "student@mail.ru"}, headers=h)
            assert r.status == 429
            async with sessions() as session:
                stored = (await session.execute(select(ReviewDraft))).scalar_one()
                stored.last_sent_at = stored.last_sent_at.replace(year=2000)
                stored.expires_at = stored.expires_at.replace(year=2100)
                await session.commit()
            r = await client.post("/api/reviews/resend", json={"draftToken": draft["draftToken"], "email": "student@mail.ru"}, headers=h)
            assert r.status == 200
            r = await client.post("/api/reviews/confirm", json={"draftToken": draft["draftToken"], "code": mail.last_code()}, headers=h)
            assert r.status == 200, await r.text()

            async with sessions() as session:
                review = (await session.execute(select(Review))).scalar_one()
                assert review.moderation_status == "pending" and not review.verified and review.source == "site"
                assert review.ip_hash and review.study_period == "2025/26"
                assert len((await session.execute(select(ReviewCriterionScore))).scalars().all()) == 5
                proof = (await session.execute(select(ReviewProof))).scalar_one()
                assert proof.review_id == review.id and proof.draft_id is None
                assert not (await session.execute(select(ReviewDraft))).scalars().all()
                user = (await session.execute(select(User))).scalar_one()
                assert user.telegram_id is None and user.consent_version == validation.CONSENT_VERSION

            # the same person reviewing the same school again replaces the old review
            r = await client.post("/api/reviews/draft", data=form(payload(keys, email="student+x@mail.ru", positive=GOOD_TEXT + " Обновил отзыв.")), headers=h)
            assert r.status == 200
            token = (await r.json())["draftToken"]
            r = await client.post("/api/reviews/confirm", json={"draftToken": token, "code": mail.last_code()}, headers=h)
            assert (await r.json())["replaced"] is True
            async with sessions() as session:
                reviews = (await session.execute(select(Review))).scalars().all()
                assert len(reviews) == 1 and "Обновил" in reviews[0].text_positive
                assert not (await session.execute(select(ReviewProof))).scalars().all()
            assert not any(Path(settings.proof_dir).iterdir())        # the old screenshot is gone from disk too

            # delete my data: same answer for any email, code required
            fresh = keys.form_token(time.time() - 20)
            r = await client.post("/api/data/delete/request", json={"email": "student@mail.ru", "formToken": fresh}, headers=h)
            req = await r.json()
            r = await client.post("/api/data/delete/confirm", json={"requestToken": req["requestToken"], "code": "999999" if mail.last_code() != "999999" else "888888"}, headers=h)
            assert r.status == 400
            r = await client.post("/api/data/delete/confirm", json={"requestToken": req["requestToken"], "code": mail.last_code()}, headers=h)
            assert (await r.json()) == {"ok": True, "reviews": 1}
            async with sessions() as session:
                assert not (await session.execute(select(Review))).scalars().all()
                assert not (await session.execute(select(User))).scalars().all()
        finally:
            await client.close()
            await engine.dispose()
    run(scenario())


# ---------- moderation console ----------

def test_admin_console_is_locked_down(tmp_path, sanitizer):
    async def scenario():
        engine, sessions, settings = await make_env(tmp_path)
        mail, keys = Mailbox(), Keys(SECRET)
        public = TestClient(TestServer(public_api.create_app(settings, sessions, sanitizer, mail)))
        admin = TestClient(TestServer(admin_app.create_app(settings, sessions)))
        await public.start_server()
        await admin.start_server()
        try:
            h = {"Origin": ORIGIN}
            r = await public.post("/api/reviews/draft", data=form(payload(keys, teacher_id=7, scores={
                "explanation": 9, "practice": 9, "atmosphere": 8, "structure": 8, "exam_value": 10}), [png()]), headers=h)
            token = (await r.json())["draftToken"]
            await public.post("/api/reviews/confirm", json={"draftToken": token, "code": mail.last_code()}, headers=h)
            local = {"Host": f"127.0.0.1:{settings.admin_port}"}

            # DNS rebinding / wrong host
            assert (await admin.get("/", headers={"Host": "evil.example"})).status == 421
            page = await (await admin.get("/", headers=local)).text()
            admin_token = re.search(r'name="admin-token" content="([^"]+)"', page).group(1)
            listing = await (await admin.get("/api/reviews", headers=local)).json()
            item = listing["reviews"][0]
            assert item["teacher"] == "Препод" and item["proofs"]
            # the screenshot comes back as our WebP with a sandbox CSP
            r = await admin.get(f"/proof/{item['proofs'][0]['id']}", headers=local)
            assert r.headers["Content-Type"] == "image/webp" and r.headers["X-Content-Type-Options"] == "nosniff"
            assert "sandbox" in r.headers["Content-Security-Policy"]
            # changes need the page token, and a foreign Origin is refused even with it
            url = f"/api/reviews/{item['id']}/approve"
            assert (await admin.post(url, json={"verified": True}, headers=local)).status == 403
            assert (await admin.post(url, json={"verified": True}, headers={**local, "X-Admin-Token": "nope"})).status == 403
            assert (await admin.post(url, json={"verified": True}, headers={**local, "X-Admin-Token": admin_token, "Origin": "https://evil.example"})).status == 403
            r = await admin.post(url, json={"verified": True}, headers={**local, "X-Admin-Token": admin_token,
                                                                         "Origin": f"http://127.0.0.1:{settings.admin_port}"})
            assert r.status == 200
            async with sessions() as session:
                review = (await session.execute(select(Review))).scalar_one()
                assert review.moderation_status == "approved" and review.verified and review.ip_hash is None
                assert not (await session.execute(select(ReviewProof))).scalars().all()
            assert not any(Path(settings.proof_dir).iterdir())      # deleted right after the decision
        finally:
            await public.close()
            await admin.close()
            await engine.dispose()
    run(scenario())


def test_admin_page_never_renders_review_text_as_html():
    script = (ROOT / "reviews_service" / "admin_static" / "admin.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script and "insertAdjacentHTML" not in script and "eval(" not in script
    assert "'unsafe-inline'" not in admin_app.PAGE_CSP and "script-src 'self'" in admin_app.PAGE_CSP


def test_after_a_review_the_page_suggests_the_other_kind():
    script = (ROOT / "web" / "review.js").read_text(encoding="utf-8")
    # school review -> pick one of its teachers; teacher review -> rate the school as a whole
    assert "Учился у конкретного преподавателя?" in script and "в целом?" in script
    assert "/review?school=" in script and "/review?teacher=" in script
    page = (ROOT / "web" / "review.html").read_text(encoding="utf-8")
    assert 'id="rf-next"' in page and 'id="rf-kind-hint"' in page


def test_reviews_sticker_starts_at_ten():
    script = (ROOT / "web" / "reviews.js").read_text(encoding="utf-8")
    milestones = re.search(r"const MILESTONES = \[([^\]]+)\]", script).group(1)
    assert [int(x) for x in milestones.split(",")][:3] == [10, 30, 50]
