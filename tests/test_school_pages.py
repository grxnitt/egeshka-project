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


def test_school_pages_open_teacher_dialogs():
    catalog = json.loads((WEB / "catalog.json").read_text(encoding="utf-8"))
    teachers = [t for t in catalog["teachers"] if t["school"] == "Умскул"]
    page = (WEB / "schools" / "umskul.html").read_text(encoding="utf-8")
    assert page.count("data-open-teacher=") == len(teachers)
    assert '<dialog id="detail-dialog">' in page
    assert '<script type="module" src="/ratings.js' in page
    assert '<base href="/">' in page
