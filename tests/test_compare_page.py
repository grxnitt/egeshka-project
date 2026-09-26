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


def test_every_how_it_works_step_opens_the_place_it_describes():
    home = read("index.html")
    cards = re.findall(r'<article class="how-card" data-step="(\d)">.*?<a class="how-link" href="([^"]+)"', home, re.S)
    # the real path: guided pick (quiz) -> rating -> compare -> bot
    assert cards == [("1", "/?start=quiz"), ("2", "/ratings#choose-subject"), ("3", "/compare"), ("4", "https://t.me/egematch_bot")]
    assert 'data-quiz-link' in home and 'data-bot-link data-source="how_step"' in home
    assert 'id="choose-subject"' in read("ratings.html")
    assert "querySelectorAll('[data-quiz-link]')" in read("app.js")
    assert "goal('how_step'" in read("analytics.js")


def test_home_shows_the_newest_articles_with_a_link_to_all_of_them():
    import sys
    sys.path.insert(0, "scripts")
    import build_articles

    home = read("index.html")
    block = re.search(r'<section class="home-articles.*?</section>', home, re.S).group(0)
    assert 'href="/articles"' in block
    linked = re.findall(r'class="article-card" href="/articles/([a-z0-9-]+)"', block)
    assert linked == [a.slug for a in build_articles.load_articles()][:3]
    assert "<h3 class=\"article-card-title\">" in block and "<h2" not in block.split("</h2>", 1)[1]


def test_header_action_is_the_quiz_on_every_content_page():
    for name in ("index.html", "ratings.html", "methodology.html", "compare.html", "articles/index.html", "schools/neofamily.html"):
        header = re.search(r"<header.*?</header>", read(name), re.S).group(0)
        assert re.search(r'class="header-action" href="/\?start=quiz"[^>]*>Подобрать ', header), name


def test_quiz_shows_a_calculation_screen_before_the_result_and_waits_for_a_slow_catalog():
    app = read("app.js")
    assert "function runQuizCalculation()" in app and "Считаем совпадения" in app
    assert "renderSiteQuiz({instant:true})" in app  # coming back from a school page skips the animation
    assert "await Promise.race([catalogReady" in app  # slow network: keep the screen, do not fail
    css = read("composition.css")
    assert ".quiz-calc-orbit" in css and "prefers-reduced-motion" in css.split(".quiz-calc-sr")[1]
