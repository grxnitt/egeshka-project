import json
import re
from pathlib import Path

WEB = Path("web")


def test_every_school_has_a_static_page_in_sitemap():
    catalog = json.loads((WEB / "catalog.json").read_text(encoding="utf-8"))
    sitemap = (WEB / "sitemap.xml").read_text(encoding="utf-8")
    for school in catalog["schools"]:
        slug = school["reviewSlug"]
        page = (WEB / "schools" / f"{slug}.html").read_text(encoding="utf-8")
        url = f"https://egematch.ru/schools/{slug}"
        assert f'<link rel="canonical" href="{url}">' in page
        assert f"<h1>{school['name']}</h1>" in page
        assert f"<loc>{url}</loc>" in sitemap


def test_school_pages_list_all_teachers_of_the_school():
    catalog = json.loads((WEB / "catalog.json").read_text(encoding="utf-8"))
    school = next(s for s in catalog["schools"] if s["name"] == "Умскул")
    page = (WEB / "schools" / f"{school['reviewSlug']}.html").read_text(encoding="utf-8")
    teachers = [t for t in catalog["teachers"] if t["school"] == "Умскул"]
    assert f"Преподаватели ({len(teachers)})" in page


def test_ratings_page_links_to_every_school_page():
    catalog = json.loads((WEB / "catalog.json").read_text(encoding="utf-8"))
    ratings = (WEB / "ratings.html").read_text(encoding="utf-8")
    linked = set(re.findall(r'href="/schools/([a-z0-9]+)"', ratings))
    assert linked == {s["reviewSlug"] for s in catalog["schools"]}


def unique_teachers(catalog):
    return {(t["school"], t["name"]) for t in catalog["teachers"]}


def test_school_page_links_every_teacher_to_their_own_page():
    catalog = json.loads((WEB / "catalog.json").read_text(encoding="utf-8"))
    page = (WEB / "schools" / "umskul.html").read_text(encoding="utf-8")
    people = {t["name"] for t in catalog["teachers"] if t["school"] == "Умскул"}

    assert page.count('class="sp-teacher"') == len(people)
    assert 'id="teachers"' in page and 'data-back="/ratings"' in page
    assert "<dialog" not in page and "ratings.js" not in page


def test_every_teacher_has_a_noindex_page_and_a_catalog_slug():
    catalog = json.loads((WEB / "catalog.json").read_text(encoding="utf-8"))
    slugs = {t["slug"] for t in catalog["teachers"]}

    assert all(t.get("slug") for t in catalog["teachers"])
    assert len(slugs) == len(unique_teachers(catalog))
    for slug in slugs:
        page = (WEB / "teachers" / f"{slug}.html").read_text(encoding="utf-8")
        assert '<meta name="robots" content="noindex,follow">' in page
        assert f'<link rel="canonical" href="https://egematch.ru/teachers/{slug}">' in page
    assert "/teachers/" not in (WEB / "sitemap.xml").read_text(encoding="utf-8")


def test_ratings_cards_are_plain_links_to_school_pages():
    script = (WEB / "ratings.js").read_text(encoding="utf-8")

    assert '<a class="card-open" href="/schools/${school.reviewSlug}">' in script
    assert '<a class="card-teachers" href="/schools/${school.reviewSlug}#teachers">' in script
    assert "location.replace(`/schools/" in script and "location.replace(`/teachers/" in script
