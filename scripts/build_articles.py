"""Build the articles section from content/articles/*.md.

Run after adding or editing an article:  python3 scripts/build_articles.py
(python3 scripts/build_school_pages.py runs it too, so header/footer changes reach the articles.)

Writes web/articles/index.html, one page per article, web/articles/feed.xml, content/articles.json
(read by the sitemap) and ready-to-paste Telegram posts to content/telegram/<slug>.txt.
Covers come from scripts/make_article_covers.py. The file format is described in content/articles/README.md.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path

import build_school_pages as site

ROOT = site.ROOT
WEB = site.WEB
SITE = site.SITE
CONTENT = ROOT / "content" / "articles"
TELEGRAM_OUT = ROOT / "content" / "telegram"
OUT = WEB / "articles"
CHANNEL = "https://t.me/EgeMatch_blog"
AUTHOR = "Редакция ЕГЭ Мэтч"
MSK = timezone(timedelta(hours=3))
MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
READING_SPEED = 180  # words per minute


@dataclass
class Article:
    slug: str
    title: str
    description: str
    published: datetime
    cover: str
    tg: str
    tldr: list
    sources: list
    body_html: str
    minutes: int
    words: int = 0
    tldr_html: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def url(self):
        return f"{SITE}/articles/{self.slug}"

    @property
    def date_label(self):
        return f"{self.published.day} {MONTHS[self.published.month - 1]} {self.published.year}"


# ---------------------------------------------------------------- markdown

SAFE_URL = re.compile(r"^(https?://|/|#|mailto:)")


def inline(text):
    """Escape HTML, then apply the tiny inline syntax: **bold**, *italic*, [text](url)."""
    text = escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)

    def link(match):
        label, url = match.group(1), match.group(2)
        if not SAFE_URL.match(url):
            return label
        if url.startswith(("http://", "https://")):
            return f'<a href="{url}" target="_blank" rel="noopener">{label}</a>'
        return f'<a href="{url}">{label}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)


def anchor(text):
    return site.translit(re.sub(r"[^\w\s-]", "", text)) or "section"


def render_directive(kind, title, lines):
    if kind == "callout":
        return (
            f'<aside class="art-callout"><p class="art-callout-title t-h3">{inline(title)}</p>'
            f"{render_lines(lines)}</aside>"
        )
    if kind == "stats":
        cells = []
        for line in lines:
            if "|" not in line:
                continue
            value, _, caption = line.partition("|")
            value = value.strip()
            unit = re.match(r"^([+\-−]?\d[\d\s.,]*[%+]?)\s+(\D.*)$", value)
            big = f"{inline(unit.group(1))}<small>{inline(unit.group(2))}</small>" if unit else inline(value)
            cells.append(f'<div class="art-stat"><b>{big}</b><span>{inline(caption.strip())}</span></div>')
        return f'<div class="art-stats">{"".join(cells)}</div>'
    raise ValueError(f"Unknown block ':::{kind}'")


def render_lines(lines):
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    def collect(prefix_re):
        nonlocal i
        items = []
        while i < len(lines) and re.match(prefix_re, lines[i].strip()):
            items.append(re.sub(prefix_re, "", lines[i].strip(), count=1))
            i += 1
        return items

    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            flush()
            i += 1
        elif stripped.startswith(":::"):
            flush()
            kind, _, title = stripped[3:].strip().partition(" ")
            j, block = i + 1, []
            while j < len(lines) and lines[j].strip() != ":::":
                block.append(lines[j])
                j += 1
            out.append(render_directive(kind, title.strip(), block))
            i = j + 1
        elif stripped.startswith("### "):
            flush()
            out.append(f"<h3>{inline(stripped[4:])}</h3>")
            i += 1
        elif stripped.startswith("## "):
            flush()
            out.append(f'<h2 id="{anchor(stripped[3:])}" class="t-h3">{inline(stripped[3:])}</h2>')
            i += 1
        elif stripped.startswith("- "):
            flush()
            out.append("<ul>" + "".join(f"<li>{inline(item)}</li>" for item in collect(r"- ")) + "</ul>")
        elif re.match(r"\d+\.\s", stripped):
            flush()
            out.append("<ol>" + "".join(f"<li>{inline(item)}</li>" for item in collect(r"\d+\.\s")) + "</ol>")
        elif stripped.startswith("> "):
            flush()
            out.append(f"<blockquote><p>{inline(' '.join(collect(r'> ')))}</p></blockquote>")
        elif image := re.fullmatch(r'!\[(.*?)\]\((\S+?)(?:\s+"(.*?)")?\)', stripped):
            flush()
            alt, src, caption = image.groups()
            cap = f"<figcaption>{inline(caption)}</figcaption>" if caption else ""
            out.append(f'<figure><img src="{escape(src, quote=True)}" alt="{escape(alt, quote=True)}" loading="lazy">{cap}</figure>')
            i += 1
        else:
            para.append(stripped)
            i += 1
    flush()
    return "\n".join(out)


# ---------------------------------------------------------------- content


def parse_front_matter(raw, name):
    match = re.match(r"---\n(.*?)\n---\n(.*)", raw, re.S)
    if not match:
        raise ValueError(f"{name}: front matter (--- block) is missing")
    meta, key = {}, None
    for line in match.group(1).splitlines():
        if line.startswith("- ") and key:
            meta.setdefault(key, []).append(line[2:].strip())
            continue
        name_part, _, value = line.partition(":")
        key = name_part.strip()
        meta[key] = value.strip() or []
    return meta, match.group(2).strip() + "\n"


def word_count(html):
    text = re.sub(r"<[^>]+>", " ", html)
    return len(re.findall(r"[\w\-]+", text))


def load_article(path):
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"), path.name)
    if str(meta.get("draft", "")).lower() in ("true", "yes", "1"):
        return None
    for required in ("title", "description", "date", "cover", "tldr", "tg"):
        if not meta.get(required):
            raise ValueError(f"{path.name}: '{required}' is required")
    published = datetime.strptime(meta["date"], "%Y-%m-%d %H:%M").replace(tzinfo=MSK)
    cover = meta["cover"]
    for ext in ("svg", "png"):
        if not (WEB / "assets" / "articles" / f"{cover}.{ext}").exists():
            raise ValueError(f"{path.name}: cover '{cover}.{ext}' not found in web/assets/articles")
    sources = []
    for item in meta.get("sources", []):
        label, _, url = item.rpartition(" | ")
        if not label or not url.startswith(("http://", "https://")):
            raise ValueError(f"{path.name}: source must look like 'Title | https://...': {item!r}")
        sources.append((label, url))
    body_html = render_lines(body.splitlines())
    tldr_html = "".join(f"<li>{inline(item)}</li>" for item in meta["tldr"])
    words = word_count(body_html) + word_count(tldr_html)
    minutes = max(1, round(words / READING_SPEED))
    if not re.fullmatch(r"[a-z0-9-]{1,80}", path.stem):
        raise ValueError(f"{path.name}: use latin letters, digits and dashes (up to 80) in the file name")
    return Article(
        slug=path.stem, title=meta["title"], description=meta["description"], published=published,
        cover=cover, tg=meta["tg"], tldr=meta["tldr"], sources=sources, body_html=body_html, minutes=minutes,
        words=words, tldr_html=tldr_html,
    )


def load_articles():
    articles = [load_article(path) for path in sorted(CONTENT.glob("*.md")) if path.name.lower() != "readme.md"]
    return sorted((a for a in articles if a), key=lambda a: a.published, reverse=True)


# ---------------------------------------------------------------- pages


def chrome(active_articles=True):
    header, footer = site.shared_chrome()
    if active_articles:
        header = header.replace('<a class="active" href="/ratings">', '<a href="/ratings">')
        header = header.replace('<a href="/articles">Статьи</a>', '<a class="active" href="/articles">Статьи</a>')
        footer = footer.replace(' class="active"', "")
        footer = re.sub(
            r'(<nav class="mobile-product-nav".*?)<a href="/articles">Статьи</a>',
            r'\1<a class="active" href="/articles">Статьи</a>', footer, count=1, flags=re.S,
        )
    return header, footer


def cover_svg(article):
    return f"/assets/articles/{article.cover}.svg"


def cover_png(article):
    return f"{SITE}/assets/articles/{article.cover}.png"


def minutes_label(minutes):
    return f"{minutes} мин чтения"


def card(article, featured=False):
    css = "article-card is-featured" if featured else "article-card"
    return (
        f'<a class="{css}" href="/articles/{article.slug}">'
        f'<span class="article-card-cover"><img src="{cover_svg(article)}" alt="" width="1200" height="630" loading="lazy"></span>'
        f'<span class="article-card-body"><span class="article-card-meta"><span>{article.date_label}</span><span>{minutes_label(article.minutes)}</span></span>'
        f'<h2 class="article-card-title">{escape(article.title)}</h2>'
        f'<span class="article-card-text">{escape(article.description)}</span>'
        f'<span class="article-card-more">Читать <i aria-hidden="true">→</i></span></span></a>'
    )


CTA_BLOCK = f"""<aside class="article-cta" aria-label="Что дальше">
  <div class="art-cta-card art-cta-channel"><h2 class="t-h3">Такие разборы — в Telegram</h2><p>Изменения ЕГЭ, новости онлайн-школ и честные разборы. Коротко и по делу.</p><a class="button" href="{CHANNEL}" target="_blank" rel="noopener" data-source="article_cta">Открыть Telegram-канал <span>↗</span></a></div>
  <div class="art-cta-card art-cta-rating"><h2 class="t-h3">Выбираешь школу?</h2><p>Сравни школы по семи критериям и отзывам учеников.</p><a class="button dark" href="/ratings">Рейтинг школ <span>→</span></a></div>
</aside>"""


GLOWS = '<div class="hero-glow hero-glow-blue" aria-hidden="true"></div><div class="hero-glow hero-glow-pink" aria-hidden="true"></div>'
RSS_LINK = f'\n  <link rel="alternate" type="application/rss+xml" title="ЕГЭ Мэтч — статьи" href="/articles/feed.xml">'
SCRIPTS = f"""<script src="/analytics-config.js?v=1"></script>
<script src="/analytics.js?v=9"></script>
{site.NAV_SCRIPT}"""


def article_extra_head(article):
    published = article.published.isoformat()
    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": article.title,
        "description": article.description,
        "image": [cover_png(article)],
        "datePublished": published,
        "dateModified": published,
        "inLanguage": "ru",
        "wordCount": article.words,
        "timeRequired": f"PT{article.minutes}M",
        "isAccessibleForFree": True,
        "author": {"@type": "Organization", "name": AUTHOR, "url": f"{SITE}/"},
        "publisher": {
            "@type": "Organization",
            "name": "ЕГЭ Мэтч",
            "logo": {"@type": "ImageObject", "url": f"{SITE}/assets/egeshka-logo-icon.svg"},
        },
        "mainEntityOfPage": article.url,
    }
    return (
        f'\n  <meta name="robots" content="max-image-preview:large,max-snippet:-1">'
        f'<meta property="article:published_time" content="{published}">'
        f'<meta property="article:author" content="{AUTHOR}">'
        f'<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
        f"{RSS_LINK}\n"
        f'  <script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script>'
    )


def build_article_page(article, others, header, footer):
    tldr = "".join(f"<li>{inline(item)}</li>" for item in article.tldr)
    sources = ""
    if article.sources:
        items = "".join(
            f'<li><a href="{escape(url, quote=True)}" target="_blank" rel="noopener">{escape(label)}</a></li>'
            for label, url in article.sources
        )
        sources = (
            '<section class="article-sources"><h2 class="t-title">Источники</h2><ol>' + items + "</ol>"
            "<p>Цифры и факты взяты из перечисленных материалов. Выводы и советы — мнение редакции.</p></section>"
        )
    related = ""
    if others:
        related = (
            '<section class="article-more"><h2 class="t-h2">Читайте также</h2><div class="article-grid">'
            + "".join(card(o) for o in others[:2])
            + '</div><p class="article-all"><a href="/articles">Все статьи →</a></p></section>'
        )
    short_title = article.title if len(article.title) <= 48 else article.title[:45].rstrip(" ,:") + "…"
    crumbs = [("Главная", f"{SITE}/"), ("Статьи", f"{SITE}/articles"), (article.title, article.url)]
    head = site.make_head(
        f"{article.title} — ЕГЭ Мэтч", article.description, article.url, crumbs,
        og_type="article", image=cover_png(article), extra=article_extra_head(article),
    )
    body = f"""<body class="article-page-body">
{header}
<main class="article-page wrap">
  <nav class="breadcrumbs" aria-label="Навигация"><a href="/">Главная</a><span>›</span><a href="/articles">Статьи</a><span>›</span><span aria-current="page">{escape(short_title)}</span></nav>
  <p class="back-row"><a class="back-link" href="/articles" data-back="/articles">← Все статьи</a></p>
  <article class="article">
    <header class="hero hero-centered article-hero">
      {GLOWS}
      <div class="hero-copy"><p class="article-meta"><time datetime="{article.published.isoformat()}">{article.date_label}</time><span>{minutes_label(article.minutes)}</span></p><h1>{escape(article.title)}</h1><p class="lead">{escape(article.description)}</p><p class="article-author">{AUTHOR}</p></div>
    </header>
    <figure class="article-cover"><img src="{cover_svg(article)}" alt="" width="1200" height="630" fetchpriority="high"></figure>
    <div class="article-body">
      <section class="art-tldr" aria-label="Коротко"><p class="art-tldr-title">Коротко</p><ul>{tldr}</ul></section>
      {article.body_html}
    </div>
    {sources}
    {CTA_BLOCK}
  </article>
  {related}
</main>
{footer}
{SCRIPTS}
</body>
</html>
"""
    return head + "\n" + body


def build_index_page(articles, header, footer):
    url = f"{SITE}/articles"
    description = "Коротко о ЕГЭ, онлайн-школах и рынке образования: изменения экзамена, цифры, разборы. Каждая статья читается за 3–4 минуты."
    crumbs = [("Главная", f"{SITE}/"), ("Статьи", url)]
    head = site.make_head("Статьи о ЕГЭ и онлайн-школах — ЕГЭ Мэтч", description, url, crumbs, extra=RSS_LINK)
    cards = ""
    if articles:
        cards = card(articles[0], featured=True)
        if articles[1:]:
            cards += '<div class="article-grid">' + "".join(card(a) for a in articles[1:]) + "</div>"
    else:
        cards = '<p class="article-empty">Скоро здесь появятся первые статьи.</p>'
    body = f"""<body class="articles-page-body">
{header}
<main class="articles-page wrap">
  <nav class="breadcrumbs" aria-label="Навигация"><a href="/">Главная</a><span>›</span><span aria-current="page">Статьи</span></nav>
  <section class="hero hero-centered articles-hero">
    {GLOWS}
    <div class="hero-copy"><h1><span class="brand-dot">Статьи</span></h1><p class="lead">Коротко о ЕГЭ, онлайн-школах и рынке образования.<br> Каждая статья читается за 3–4 минуты.</p></div>
  </section>
  <section class="article-list" aria-label="Список статей">
    {cards}
  </section>
  {CTA_BLOCK}
  <p class="article-all article-rss"><a href="/articles/feed.xml">RSS-лента статей</a></p>
</main>
{footer}
{SCRIPTS}
</body>
</html>
"""
    return head + "\n" + body


def absolute_links(html):
    return re.sub(r'(href|src)="/(?!/)', lambda m: f'{m.group(1)}="{SITE}/', html)


def build_feed(articles):
    items = []
    for a in articles:
        full = absolute_links(f"<ul>{a.tldr_html}</ul>\n{a.body_html}").replace("]]>", "]]&gt;")
        size = (WEB / "assets" / "articles" / f"{a.cover}.png").stat().st_size
        items.append(
            f"<item><title>{escape(a.title)}</title><link>{a.url}</link>"
            f'<guid isPermaLink="true">{a.url}</guid><pubDate>{format_datetime(a.published)}</pubDate>'
            f"<author>noreply@egematch.ru ({AUTHOR})</author>"
            f"<description>{escape(a.description)}</description>"
            f'<enclosure url="{cover_png(a)}" length="{size}" type="image/png"/>'
            f"<content:encoded><![CDATA[{full}]]></content:encoded></item>\n"
        )
    updated = format_datetime(articles[0].published) if articles else format_datetime(datetime.now(MSK))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
        'xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>\n'
        "<title>ЕГЭ Мэтч — статьи</title>"
        f"<link>{SITE}/articles</link>"
        "<description>Коротко о ЕГЭ, онлайн-школах и рынке образования.</description>"
        "<language>ru</language>"
        f"<lastBuildDate>{updated}</lastBuildDate>"
        f'<atom:link href="{SITE}/articles/feed.xml" rel="self" type="application/rss+xml"/>\n'
        f"{''.join(items)}</channel></rss>\n"
    )


def telegram_post(article):
    link = f"{article.url}?utm_source=telegram&utm_medium=channel&utm_campaign=article"
    return f"{article.tg}\n\nЧитать на сайте: {link}\n"


def main():
    articles = load_articles()
    header, footer = chrome()
    OUT.mkdir(parents=True, exist_ok=True)
    TELEGRAM_OUT.mkdir(parents=True, exist_ok=True)
    for path in OUT.glob("*.html"):
        path.unlink()
    for path in TELEGRAM_OUT.glob("*.txt"):
        path.unlink()
    for article in articles:
        others = [a for a in articles if a is not article]
        (OUT / f"{article.slug}.html").write_text(build_article_page(article, others, header, footer), encoding="utf-8")
        (TELEGRAM_OUT / f"{article.slug}.txt").write_text(telegram_post(article), encoding="utf-8")
    (OUT / "index.html").write_text(build_index_page(articles, header, footer), encoding="utf-8")
    (OUT / "feed.xml").write_text(build_feed(articles), encoding="utf-8")
    index = [{"slug": a.slug, "date": a.published.isoformat(), "title": a.title} for a in articles]
    (ROOT / "content" / "articles.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    catalog = json.loads((WEB / "catalog.json").read_text(encoding="utf-8"))
    site.write_sitemap(catalog["schools"])
    print(f"Generated {len(articles)} articles")


if __name__ == "__main__":
    main()
