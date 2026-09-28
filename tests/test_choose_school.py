import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
import build_school_pages  # noqa: E402

WEB = Path("web")


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def test_lead_urls_dict_exists_and_defaults_to_empty():
    from egeshka_bot.db import LEAD_URLS

    assert LEAD_URLS == {}


def test_choose_school_url_falls_back_to_official_site_with_utm_tags():
    school = {"url": "https://example.com/course?ref=abc", "leadUrl": None}
    url = build_school_pages.choose_school_url(school)
    assert url.startswith("https://example.com/course?")
    assert "ref=abc" in url
    assert "utm_source=egematch" in url
    assert "utm_medium=cta" in url
    assert "utm_campaign=choose_school" in url


def test_choose_school_url_prefers_a_negotiated_lead_url():
    school = {"url": "https://example.com", "leadUrl": "https://example.com/sales?src=egematch"}
    assert build_school_pages.choose_school_url(school) == "https://example.com/sales?src=egematch"


def test_catalog_exports_a_lead_url_field_for_every_school():
    catalog = json.loads((WEB / "catalog.json").read_text(encoding="utf-8"))
    for school in catalog["schools"]:
        assert "leadUrl" in school


def test_school_page_has_a_choose_school_button():
    catalog = json.loads((WEB / "catalog.json").read_text(encoding="utf-8"))
    school = next(s for s in catalog["schools"] if s["name"] == "Умскул")
    page = read(f"schools/{school['reviewSlug']}.html")
    assert re.search(
        r'<a class="button blue" href="[^"]+" target="_blank" rel="noopener" '
        r'data-choose-school="Умскул" data-source="school_page">Выбрать школу',
        page,
    )
    # the official site stays, only demoted to a plain inline link
    assert "официальном сайте ↗" in page


def test_teacher_page_has_a_choose_school_button_pointing_at_the_teachers_school():
    school_page = read("schools/umskul.html")
    slug_map = json.loads(re.search(r"window\.TEACHER_SLUGS=(\{.*?\});", school_page).group(1))
    any_slug = next(iter(slug_map.values()))
    page = read(f"teachers/{any_slug}.html")
    assert 'data-choose-school="Умскул" data-source="teacher_page">Выбрать школу' in page
    # the teacher's own profile link stays, only demoted to an outline button
    assert '<a class="button outline" href="/schools/umskul">О школе' in page


def test_ratings_js_school_dialog_offers_choose_school_before_the_site_link():
    script = read("ratings.js")
    assert "chooseSchoolUrl" in script
    assert "detail-lead-action" in script
    assert "data-source=\"school_dialog\"" in script
    assert "data-source=\"teacher_dialog\"" in script


def test_compare_price_card_offers_choose_school():
    script = read("compare.js")
    assert "chooseSchoolUrl" in script
    assert 'data-source="compare_price"' in script
    assert "Выбрать школу" in script


def test_quiz_result_cards_offer_choose_school():
    script = read("app.js")
    assert "chooseSchoolUrl" in script
    assert 'data-source="quiz_result"' in script
    assert "quiz-choose-link" in script


def test_school_content_exports_choose_school_url_helper():
    script = read("school-content.js")
    assert "export function chooseSchoolUrl" in script
    assert "utm_campaign','choose_school'" in script


def test_analytics_tracks_choose_school_clicks_as_a_dedicated_goal():
    script = read("analytics.js")
    assert "data-choose-school" in script
    assert "goal('choose_school'" in script
