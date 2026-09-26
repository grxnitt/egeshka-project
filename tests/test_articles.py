import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, "scripts")
import build_articles  # noqa: E402

WEB = Path("web")
CONTENT = Path("content/articles")


def articles():
    return build_articles.load_articles()


def test_every_markdown_article_has_a_page_cover_and_sitemap_entry():
    sitemap = (WEB / "sitemap.xml").read_text(encoding="utf-8")
    loaded = articles()
    assert loaded, "expected at least one article"
    assert "<loc>https://egematch.ru/articles</loc>" in sitemap
    for article in loaded:
        page = (WEB / "articles" / f"{article.slug}.html").read_text(encoding="utf-8")
        assert f'<link rel="canonical" href="{article.url}">' in page
        assert f"<h1>{article.title}</h1>" in page
        assert '<meta property="og:type" content="article">' in page
        assert f'<meta property="og:image" content="https://egematch.ru/assets/articles/{article.cover}.png">' in page
        assert f"<loc>{article.url}</loc>" in sitemap
        assert (WEB / "assets" / "articles" / f"{article.cover}.svg").exists()
        assert (WEB / "assets" / "articles" / f"{article.cover}.png").exists()


def test_article_pages_have_article_structured_data_and_sources():
    for article in articles():
        page = (WEB / "articles" / f"{article.slug}.html").read_text(encoding="utf-8")
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
        data = [json.loads(block) for block in blocks]
        kinds = {item["@type"] for item in data}
        assert {"BreadcrumbList", "Article"} <= kinds
        article_data = next(item for item in data if item["@type"] == "Article")
        assert article_data["headline"] == article.title
        assert article_data["datePublished"].startswith(article.published.strftime("%Y-%m-%d"))
        assert article.sources, f"{article.slug}: cite the sources of facts and numbers"
        assert all(url.startswith("https://") for _, url in article.sources)
        assert 'class="article-sources"' in page


def test_articles_are_short_reads():
    for article in articles():
        assert 2 <= article.minutes <= 6, f"{article.slug}: {article.minutes} min"


def test_articles_index_lists_every_article_newest_first_and_feed_is_valid_rss():
    loaded = articles()
    index = (WEB / "articles" / "index.html").read_text(encoding="utf-8")
    linked = re.findall(r'class="article-card[^"]*" href="/articles/([a-z0-9-]+)"', index)
    assert linked == [a.slug for a in loaded]
    assert [a.published for a in loaded] == sorted((a.published for a in loaded), reverse=True)
    feed = ET.fromstring((WEB / "articles" / "feed.xml").read_text(encoding="utf-8"))
    items = feed.findall("./channel/item")
    assert [item.find("link").text for item in items] == [a.url for a in loaded]


def test_site_navigation_links_to_articles():
    for name in ("index.html", "ratings.html", "methodology.html"):
        page = (WEB / name).read_text(encoding="utf-8")
        assert 'href="/articles"' in page, name
    page = (WEB / "articles" / "index.html").read_text(encoding="utf-8")
    assert '<a class="active" href="/articles">Статьи</a>' in page


def test_vercel_rewrites_articles():
    rewrites = {r["source"]: r["destination"] for r in json.loads((WEB / "vercel.json").read_text())["rewrites"]}
    assert rewrites["/articles"] == "/articles/index.html"
    assert rewrites["/articles/:slug"] == "/articles/:slug.html"


def test_telegram_posts_are_generated_with_utm_links():
    for article in articles():
        post = Path("content/telegram", f"{article.slug}.txt").read_text(encoding="utf-8")
        assert post.startswith(article.tg)
        assert f"{article.url}?utm_source=telegram" in post


def test_markdown_escapes_html_and_rejects_unsafe_links():
    html = build_articles.render_lines(["Текст <script>alert(1)</script> и [ссылка](javascript:alert(1)) и [ok](/ratings)."])
    assert "<script>" not in html
    assert "javascript:" not in html
    assert '<a href="/ratings">ok</a>' in html


def test_markdown_blocks_lists_callout_and_stats():
    html = build_articles.render_lines(
        [
            "## Заголовок раздела",
            "",
            "- один",
            "- **два**",
            "",
            "1. первый",
            "2. второй",
            "",
            ":::stats",
            "154 млрд ₽ | выручка",
            "+12% | рост",
            ":::",
            "",
            ":::callout Совет",
            "- делай так",
            ":::",
        ]
    )
    assert '<h2 id="zagolovok-razdela" class="t-h3">Заголовок раздела</h2>' in html
    assert "<ul><li>один</li><li><strong>два</strong></li></ul>" in html
    assert "<ol><li>первый</li><li>второй</li></ol>" in html
    assert '<b>154<small>млрд ₽</small></b>' in html
    assert "<b>+12%</b>" in html
    assert '<aside class="art-callout"><p class="art-callout-title t-h3">Совет</p><ul><li>делай так</li></ul></aside>' in html


def test_unknown_block_is_an_error():
    try:
        build_articles.render_lines([":::mystery", "x", ":::"])
    except ValueError as error:
        assert "mystery" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_draft_articles_are_not_published(tmp_path, monkeypatch):
    (tmp_path / "hidden.md").write_text(
        "---\ntitle: T\ndescription: D\ndate: 2026-01-01 10:00\ncover: exam\ndraft: true\ntg: x\ntldr:\n- a\n---\n\nText.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(build_articles, "CONTENT", tmp_path)
    assert build_articles.load_articles() == []


def test_mobile_bottom_navigation_links_to_articles():
    for path in ("index.html", "ratings.html", "articles/index.html", "schools/neofamily.html"):
        page = (WEB / path).read_text(encoding="utf-8")
        nav = re.search(r'<nav class="mobile-product-nav".*?</nav>', page, re.S).group(0)
        assert 'href="/articles"' in nav, path
    nav = re.search(r'<nav class="mobile-product-nav".*?</nav>', (WEB / "articles/index.html").read_text(encoding="utf-8"), re.S).group(0)
    assert '<a class="active" href="/articles">Статьи</a>' in nav


def test_article_pages_end_with_exactly_two_cards_telegram_and_rating():
    for article in articles():
        page = (WEB / "articles" / f"{article.slug}.html").read_text(encoding="utf-8")
        cta = re.search(r'<aside class="article-cta".*?</aside>', page, re.S).group(0)
        assert cta.count('class="art-cta-card') == 2
        assert 'href="https://t.me/EgeMatch_blog"' in cta
        assert 'href="/ratings"' in cta
        assert "egematch_bot" not in cta and "#compare" not in cta
        assert '<script src="/analytics.js?v=10"></script>' in page


def test_feed_carries_full_text_and_cover_for_syndication():
    ns = {"c": "http://purl.org/rss/1.0/modules/content/"}
    feed = ET.fromstring((WEB / "articles" / "feed.xml").read_text(encoding="utf-8"))
    for item in feed.findall("./channel/item"):
        assert item.find("enclosure").attrib["url"].endswith(".png")
        assert len(item.find("c:encoded", ns).text) > 500
        assert 'href="/' not in item.find("c:encoded", ns).text


def test_article_structured_data_has_reading_time_and_yandex_gets_clean_param():
    for article in articles():
        page = (WEB / "articles" / f"{article.slug}.html").read_text(encoding="utf-8")
        data = next(
            json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
            if '"@type": "Article"' in b
        )
        assert data["wordCount"] == article.words and data["timeRequired"] == f"PT{article.minutes}M"
    robots = (WEB / "robots.txt").read_text(encoding="utf-8")
    assert "Clean-param: utm_source&utm_medium&utm_campaign" in robots
    assert "Sitemap: https://egematch.ru/sitemap.xml" in robots
    assert "Allow: /" in robots.split("User-agent: Yandex")[1]


def test_indexnow_key_file_is_published_and_matches_the_script():
    import indexnow

    key_file = WEB / f"{indexnow.KEY}.txt"
    assert key_file.read_text(encoding="utf-8").strip() == indexnow.KEY
    urls = indexnow.default_urls()
    assert "https://egematch.ru/articles" in urls
    assert all(url.startswith("https://egematch.ru/") for url in urls)
    body = indexnow.payload(urls)
    assert body["keyLocation"] == f"https://egematch.ru/{indexnow.KEY}.txt"
