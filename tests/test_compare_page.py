import json
import re
from pathlib import Path

WEB = Path("web")


def read(path):
    return (WEB / path).read_text(encoding="utf-8")


def test_compare_lives_on_its_own_page_not_on_the_home_page():
    home = read("index.html")
    assert 'id="compare"' not in home and "comparison-box" not in home
    page = read("compare.html")
    assert '<link rel="canonical" href="https://egematch.ru/compare">' in page
    assert 'id="left-select"' in page and 'id="right-select"' in page
    assert '<script type="module" src="compare.js?v=1"></script>' in page
    assert '<a class="active" href="/compare">Сравнение</a>' in page


def test_no_page_still_points_to_the_old_home_anchor():
    pages = [*WEB.glob("*.html"), *WEB.glob("schools/*.html"), *WEB.glob("teachers/*.html"), *WEB.glob("articles/*.html")]
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert 'href="/#compare"' not in text and 'href="#compare"' not in text, page
        assert "/?compareLeft" not in text, page
    for script in ("ratings.js", "app.js"):
        assert not re.search(r"#compare(?![-\w])", read(script)), script


def test_navigation_everywhere_links_to_compare():
    for name in ("index.html", "ratings.html", "methodology.html", "compare.html", "articles/index.html", "schools/neofamily.html"):
        page = read(name)
        header = re.search(r"<header.*?</header>", page, re.S).group(0)
        assert 'href="/compare"' in header, name
        nav = re.search(r'<nav class="mobile-product-nav".*?</nav>', page, re.S)
        if nav:  # the methodology page has no bottom bar
            assert 'href="/compare"' in nav.group(0), name


def test_compare_is_routed_and_in_the_sitemap():
    rewrites = {r["source"]: r["destination"] for r in json.loads(read("vercel.json"))["rewrites"]}
    assert rewrites["/compare"] == "/compare.html"
    assert "<loc>https://egematch.ru/compare</loc>" in read("sitemap.xml")


def test_old_home_links_are_forwarded_to_the_compare_page():
    home = read("index.html")
    assert 'l.hash==="#compare"' in home and 'l.replace("/compare"' in home


def test_school_page_and_ratings_tray_open_the_compare_page_with_the_pair():
    assert re.search(r'href="/compare\?compareLeft=NeoFamily"', read("schools/neofamily.html"))
    assert "`/compare?${params.toString()}`" in read("ratings.js")
    assert "/compare?${new URLSearchParams({compareLeft" in read("app.js")
