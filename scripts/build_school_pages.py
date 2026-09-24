"""Generate static school pages, the school links block and sitemap.xml from web/catalog.json.

Run after changing catalog data:  python3 scripts/build_school_pages.py
"""
import json
import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
SITE = "https://egematch.online"
BOT = "https://t.me/egematch_bot"
CSS_VERSIONS = {
    "styles.css": "30",
    "refinements.css": "35",
    "typography.css": "31",
    "composition.css": "76",
}
CRITERIA = {
    "teachers_score": "Преподаватели",
    "practice_score": "Практика и ДЗ",
    "feedback_score": "Проверка работ",
    "curator_score": "Кураторы",
    "platform_score": "Платформа",
    "workload_score": "Нагрузка и темп",
    "organization_score": "Организация обучения",
}
LINKS_START = "<!-- school-links:start -->"
LINKS_END = "<!-- school-links:end -->"


def num(value):
    return f"{value:.1f}".replace(".", ",")


def first_sentence(text):
    match = re.match(r"(.+?[.!?])(\s|$)", text.strip())
    return match.group(1) if match else text.strip()


def abs_href(fragment):
    return re.sub(
        r'href="(?!https?:|#|/|mailto:)([^"]+)"', lambda m: f'href="/{m.group(1)}"', fragment
    )


def shared_chrome():
    ratings = (WEB / "ratings.html").read_text(encoding="utf-8")
    header = re.search(r"<header.*?</header>", ratings, re.S).group(0)
    footer = re.search(r"<footer.*?</footer>", ratings, re.S).group(0)
    nav = re.search(r'<nav class="mobile-product-nav".*?</nav>', ratings, re.S).group(0)
    footer = footer.replace('<a href="#">', '<a href="javascript:void(0)" onclick="window.scrollTo({top:0,behavior:\'smooth\'})">')
    return abs_href(header), abs_href(nav) + "\n" + abs_href(footer)


def page_head(school, url):
    subjects = len(school["subjects"])
    description = (
        f"{first_sentence(school['description'])} "
        f"Оценка {num(school['score'])} из 10, цены, {subjects} предметов, преподаватели "
        f"и как оставить отзыв."
    )
    title = f"{school['name']}: оценка, цены и преподаватели для ЕГЭ — ЕГЭ Мэтч"
    css = "\n".join(
        f'  <link rel="stylesheet" href="/{name}?v={version}">' for name, version in CSS_VERSIONS.items()
    )
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Главная", "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": "Рейтинг школ", "item": f"{SITE}/ratings"},
            {"@type": "ListItem", "position": 3, "name": school["name"], "item": url},
        ],
    }
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <base href="/">
  <meta name="theme-color" content="#FAF8F5">
  <meta name="description" content="{escape(description, quote=True)}">
  <link rel="canonical" href="{url}">
  <meta property="og:type" content="website"><meta property="og:site_name" content="ЕГЭ Мэтч">
  <meta property="og:title" content="{escape(title, quote=True)}"><meta property="og:description" content="{escape(description, quote=True)}">
  <meta property="og:url" content="{url}"><meta property="og:image" content="{SITE}/assets/og-cover.png">
  <meta name="twitter:card" content="summary_large_image">
  <title>{escape(title)}</title>
  <link rel="icon" href="/assets/egeshka-logo-icon.svg" type="image/svg+xml">
  <link rel="manifest" href="/site.webmanifest">
{css}
  <script type="application/ld+json">{json.dumps(breadcrumb, ensure_ascii=False)}</script>
</head>"""


def subject_label(subject):
    return subject[:1].upper() + subject[1:]


def build_page(school, teachers, others, header, footer):
    slug = school["reviewSlug"]
    url = f"{SITE}/schools/{slug}"
    criteria_rows = "".join(
        f'<li><span>{escape(label)}</span><i aria-hidden="true"><b style="width:{school["criteria"][key] * 10:.0f}%"></b></i>'
        f'<strong>{num(school["criteria"][key])}</strong></li>'
        for key, label in CRITERIA.items()
        if key in school["criteria"]
    )
    subjects = "".join(f"<li>{escape(subject_label(s))}</li>" for s in school["subjects"])
    if teachers:
        teacher_items = "".join(
            f'<li><button type="button" data-open-teacher="{escape(t["name"], quote=True)}" '
            f'data-school="{escape(school["name"], quote=True)}"><b>{escape(t["name"])}</b>'
            f'<span>{escape(", ".join(t["subjects"]))}</span></button></li>'
            for t in teachers
        )
        teachers_block = (
            f'<section class="sp-section"><h2>Преподаватели ({len(teachers)})</h2>'
            f'<p class="sp-hint">Нажми на преподавателя, чтобы открыть карточку.</p>'
            f'<ul class="sp-teachers">{teacher_items}</ul></section>'
        )
    else:
        teachers_block = (
            '<section class="sp-section"><h2>Преподаватели</h2>'
            "<p>Школа работает по модели репетиторского сервиса: конкретного преподавателя "
            "выбирают на сайте школы.</p></section>"
        )
    other_links = "".join(
        f'<a href="/schools/{o["reviewSlug"]}">{escape(o["name"])}</a>' for o in others
    )
    compare_url = "/?" + "compareLeft=" + re.sub(r"\s", "+", school["name"]) + "#compare"
    review_url = f'{BOT}?start=review_{slug}'
    body = f"""<body class="school-page-body">
{header}
<main class="school-page wrap">
  <nav class="breadcrumbs" aria-label="Навигация"><a href="/">Главная</a><span>›</span><a href="/ratings">Рейтинг школ</a><span>›</span><span aria-current="page">{escape(school["name"])}</span></nav>
  <header class="sp-hero"><div><h1>{escape(school["name"])}</h1><p class="sp-lead">{escape(school["description"])}</p></div><div class="sp-score"><small>Оценка ЕГЭ Мэтча</small><strong>{num(school["score"])}</strong><span>из 10</span></div></header>
  <p class="sp-note">Оценка складывается из редакционной оценки по семи критериям и подтверждённых отзывов учеников. Пока отзывов мало, она в основном редакционная. <a href="/methodology">Как считается оценка</a></p>
  <section class="sp-section"><h2>Оценка по критериям</h2><ul class="sp-criteria">{criteria_rows}</ul></section>
  <section class="sp-facts"><article><h2>Стоимость</h2><p>{escape(school["price"])}</p></article><article><h2>Формат обучения</h2><p>{escape(school["format"])}</p></article></section>
  <section class="sp-section"><h2>Предметы ({len(school["subjects"])})</h2><ul class="sp-chips">{subjects}</ul></section>
  <section class="sp-two"><article><h2>Почему выбирают</h2><p>{escape(school["strengths"])}</p></article><article><h2>Что проверить перед покупкой</h2><p>{escape(school["weaknesses"])}</p></article></section>
  {teachers_block}
  <div class="sp-actions"><a class="button dark" href="{escape(school["url"])}" target="_blank" rel="noopener">Сайт школы <span>↗</span></a><a class="button blue" href="{compare_url}">Сравнить с другой школой <span>↗</span></a><a class="button outline" href="{review_url}" target="_blank" rel="noopener">Оставить отзыв <span>↗</span></a></div>
  <section class="sp-section"><h2>Другие школы</h2><nav class="sp-more" aria-label="Другие школы">{other_links}<a href="/ratings">Весь рейтинг →</a></nav></section>
</main>
{footer}
<dialog id="detail-dialog"><button class="close" aria-label="Закрыть">×</button><div id="dialog-content" tabindex="0" aria-label="Подробности"></div></dialog>
<script src="/analytics-config.js?v=1"></script>
<script src="/analytics.js?v=3"></script>
<script src="/supabase-config.js?v=1"></script>
<script type="module" src="/ratings.js?v=56"></script>
</body>
</html>
"""
    return page_head(school, url) + "\n" + body


def links_block(schools):
    links = "".join(
        f'<a href="/schools/{s["reviewSlug"]}">{escape(s["name"])}</a>'
        for s in sorted(schools, key=lambda s: -s["score"])
    )
    return (
        f'{LINKS_START}<details class="school-links wrap"><summary>Страницы школ ({len(schools)})'
        f'<span class="faq-icon" aria-hidden="true"></span></summary>'
        f'<nav aria-label="Страницы школ">{links}</nav></details>{LINKS_END}'
    )


def update_ratings_links(schools):
    path = WEB / "ratings.html"
    text = path.read_text(encoding="utf-8")
    block = links_block(schools)
    if LINKS_START in text:
        text = re.sub(re.escape(LINKS_START) + ".*?" + re.escape(LINKS_END), lambda m: block, text, flags=re.S)
    else:
        text = text.replace('<section class="faq wrap"', block + '\n<section class="faq wrap"', 1)
    path.write_text(text, encoding="utf-8")


def write_sitemap(schools):
    static = [("/", "1.0", "weekly"), ("/ratings", "0.9", "weekly"), ("/methodology", "0.6", "monthly")]
    rows = [f"  <url><loc>{SITE}{p}</loc><changefreq>{f}</changefreq><priority>{pr}</priority></url>" for p, pr, f in static]
    rows += [
        f"  <url><loc>{SITE}/schools/{s['reviewSlug']}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>"
        for s in sorted(schools, key=lambda s: s["reviewSlug"])
    ]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(rows) + "\n</urlset>\n"
    (WEB / "sitemap.xml").write_text(xml, encoding="utf-8")


def main():
    catalog = json.loads((WEB / "catalog.json").read_text(encoding="utf-8"))
    schools = catalog["schools"]
    header, footer = shared_chrome()
    out = WEB / "schools"
    out.mkdir(exist_ok=True)
    for path in out.glob("*.html"):
        path.unlink()
    for school in schools:
        teachers = sorted(
            (t for t in catalog["teachers"] if t["school"] == school["name"]), key=lambda t: t["name"]
        )
        others = [s for s in sorted(schools, key=lambda s: -s["score"]) if s["name"] != school["name"]]
        (out / f"{school['reviewSlug']}.html").write_text(
            build_page(school, teachers, others, header, footer), encoding="utf-8"
        )
    update_ratings_links(schools)
    write_sitemap(schools)
    print(f"Generated {len(schools)} school pages")


if __name__ == "__main__":
    main()
