"""Generate static school pages, the school links block and sitemap.xml from web/catalog.json.

Run after changing catalog data:  python3 scripts/build_school_pages.py
"""
import json
import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
SITE = "https://egematch.ru"
BOT = "https://t.me/egematch_bot"
CSS_VERSIONS = {
    "styles.css": "34",
    "refinements.css": "35",
    "typography.css": "31",
    "composition.css": "90",
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
TEACHER_CRITERIA = {
    "explanation": "Объяснение материала",
    "practice": "Практика и разбор ошибок",
    "atmosphere": "Атмосфера и вовлечённость",
    "structure": "Структура и темп занятий",
    "exam_value": "Польза для экзамена",
}
TRANSLIT = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    ["a","b","v","g","d","e","e","zh","z","i","y","k","l","m","n","o","p","r","s","t","u","f","kh","ts","ch","sh","shch","","y","","e","yu","ya"],
))
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


def translit(text):
    out = "".join(TRANSLIT.get(ch, ch) for ch in text.lower())
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", out)).strip("-")


def teacher_people(catalog, school_slugs):
    """One entry per (school, name); subjects merged, slugs unique."""
    people, used = {}, set()
    for record in catalog["teachers"]:
        key = (record["school"], record["name"])
        if key not in people:
            base = f"{school_slugs[record['school']]}-{translit(record['name'])}"
            slug, n = base, 2
            while slug in used:
                slug, n = f"{base}-{n}", n + 1
            used.add(slug)
            people[key] = {**record, "slug": slug, "subjects": list(record.get("subjects") or [record["subject"]])}
        else:
            for subject in record.get("subjects") or [record["subject"]]:
                if subject not in people[key]["subjects"]:
                    people[key]["subjects"].append(subject)
    return people


NAV_SCRIPT = """<script>
(function(){
  var q=new URLSearchParams(location.search),back=document.querySelector('[data-back]');
  if(back){
    if(q.get('from')==='quiz'&&back.getAttribute('data-back')==='/ratings'){back.setAttribute('href','/?resume=quiz');back.textContent='\\u2190 \\u041a \\u0440\\u0435\\u0437\\u0443\\u043b\\u044c\\u0442\\u0430\\u0442\\u0430\\u043c \\u043f\\u043e\\u0434\\u0431\\u043e\\u0440\\u0430';}
    else if(document.referrer){try{var r=new URL(document.referrer);if(r.origin===location.origin&&r.pathname.indexOf(back.getAttribute('data-back'))===0){back.addEventListener('click',function(e){e.preventDefault();history.back();});}}catch(e){}}
  }
  var map=window.TEACHER_SLUGS,t=q.get('teacher');
  if(map&&t&&map[t])location.replace('/teachers/'+map[t]);
})();
</script>"""

FILTER_SCRIPT = """<script>
(function(){
  var buttons=document.querySelectorAll('[data-filter]'),items=document.querySelectorAll('.sp-teachers li'),out=document.getElementById('sp-count');
  if(!buttons.length)return;
  function word(n){var a=n%100,b=n%10;return a>=11&&a<=14?'\\u043f\\u0440\\u0435\\u043f\\u043e\\u0434\\u0430\\u0432\\u0430\\u0442\\u0435\\u043b\\u0435\\u0439':b===1?'\\u043f\\u0440\\u0435\\u043f\\u043e\\u0434\\u0430\\u0432\\u0430\\u0442\\u0435\\u043b\\u044c':b>=2&&b<=4?'\\u043f\\u0440\\u0435\\u043f\\u043e\\u0434\\u0430\\u0432\\u0430\\u0442\\u0435\\u043b\\u044f':'\\u043f\\u0440\\u0435\\u043f\\u043e\\u0434\\u0430\\u0432\\u0430\\u0442\\u0435\\u043b\\u0435\\u0439';}
  buttons.forEach(function(button){button.addEventListener('click',function(){
    var value=button.getAttribute('data-filter'),shown=0;
    buttons.forEach(function(b){var on=b===button;b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on));});
    items.forEach(function(li){var ok=!value||li.getAttribute('data-subjects').split('|').indexOf(value)>-1;li.hidden=!ok;if(ok){li.classList.toggle('tone-b',shown%2===1);shown++;}});
    if(out)out.textContent=value?value+' \\u00b7 '+shown+' '+word(shown):'';
  });});
})();
</script>"""


def make_head(title, description, url, crumbs, noindex=False):
    css = "\n".join(
        f'  <link rel="stylesheet" href="/{name}?v={version}">' for name, version in CSS_VERSIONS.items()
    )
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": n, "name": name, "item": item}
            for n, (name, item) in enumerate(crumbs, 1)
        ],
    }
    robots = '\n  <meta name="robots" content="noindex,follow">' if noindex else ""
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <base href="/">{robots}
  <meta name="theme-color" content="#FAF8F5">
  <meta name="description" content="{escape(description, quote=True)}">
  <link rel="canonical" href="{url}">
  <meta property="og:type" content="website"><meta property="og:site_name" content="ЕГЭ Мэтч">
  <meta property="og:title" content="{escape(title, quote=True)}"><meta property="og:description" content="{escape(description, quote=True)}">
  <meta property="og:url" content="{url}"><meta property="og:image" content="{SITE}/assets/og-cover.png?v=3">
  <meta name="twitter:card" content="summary_large_image">
  <title>{escape(title)}</title>
  <link rel="icon" href="/assets/egeshka-logo-icon.svg" type="image/svg+xml">
  <link rel="manifest" href="/site.webmanifest">
  <link rel="preload" href="/assets/fonts/onest-cyrillic-wght-normal.woff2" as="font" type="font/woff2" crossorigin><link rel="preload" href="/assets/fonts/unbounded-cyrillic-wght-normal.woff2" as="font" type="font/woff2" crossorigin><link rel="preload" href="/assets/fonts/onest-symbols-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
{css}
  <script type="application/ld+json">{json.dumps(breadcrumb, ensure_ascii=False)}</script>
</head>"""


def page_head(school, url):
    description = (
        f"{first_sentence(school['description'])} "
        f"Оценка {num(school['score'])} из 10, цены, {len(school['subjects'])} предметов, преподаватели "
        f"и как оставить отзыв."
    )
    title = f"{school['name']}: оценка, цены и преподаватели для ЕГЭ — ЕГЭ Мэтч"
    crumbs = [("Главная", f"{SITE}/"), ("Рейтинг школ", f"{SITE}/ratings"), (school["name"], url)]
    return make_head(title, description, url, crumbs)


def subject_label(subject):
    return subject[:1].upper() + subject[1:]


def teacher_card(person, index=0):
    subjects = ", ".join(person["subjects"])
    initial = escape(person["name"].strip()[:1])
    description = escape(person.get("description") or "")
    tone = ' class="tone-b"' if index % 2 else ""
    return (
        f'<li{tone} data-subjects="{escape("|".join(person["subjects"]), quote=True)}">'
        f'<a class="sp-teacher" href="/teachers/{person["slug"]}"><span class="sp-monogram" aria-hidden="true">{initial}</span>'
        f'<span class="sp-teacher-main"><b>{escape(person["name"])}</b><small>{escape(subjects)}</small>'
        f'<span class="sp-desc">{description}</span></span><i aria-hidden="true">→</i></a></li>'
    )


def build_page(school, people, others, header, footer, teacher_slugs):
    slug = school["reviewSlug"]
    url = f"{SITE}/schools/{slug}"
    criteria_rows = "".join(
        f'<li><span>{escape(label)}</span><i aria-hidden="true"><b style="width:{school["criteria"][key] * 10:.0f}%"></b></i>'
        f'<strong>{num(school["criteria"][key])}</strong></li>'
        for key, label in CRITERIA.items()
        if key in school["criteria"]
    )
    subjects = "".join(f"<li>{escape(subject_label(s))}</li>" for s in school["subjects"])
    if people:
        teacher_subjects = sorted({s for person in people for s in person["subjects"]})
        filter_html = ""
        if len(teacher_subjects) > 1:
            chips = '<button type="button" class="active" data-filter="" aria-pressed="true">Все</button>' + "".join(
                f'<button type="button" data-filter="{escape(s, quote=True)}" aria-pressed="false">{escape(s)}</button>'
                for s in teacher_subjects
            )
            filter_html = f'<div class="sp-filter" role="group" aria-label="Фильтр преподавателей по предмету">{chips}</div><p class="sp-hint" id="sp-count" aria-live="polite"></p>'
        teachers_block = (
            f'<section class="sp-section" id="teachers"><h2>Преподаватели ({len(people)})</h2>'
            f'{filter_html}<ul class="sp-teachers">{"".join(teacher_card(p, n) for n, p in enumerate(people))}</ul></section>'
        )
    else:
        teachers_block = (
            '<section class="sp-section" id="teachers"><h2>Преподаватели</h2>'
            "<p>Школа работает по модели репетиторского сервиса: конкретного преподавателя "
            "выбирают на сайте школы.</p></section>"
        )
    other_links = "".join(
        f'<a href="/schools/{o["reviewSlug"]}">{escape(o["name"])}</a>' for o in others
    )
    compare_url = "/?" + "compareLeft=" + re.sub(r"\s", "+", school["name"]) + "#compare"
    review_url = f'{BOT}?start=review_{slug}'
    card_url = f'{BOT}?start=school_{slug}'
    slug_map = json.dumps({p["name"]: p["slug"] for p in people}, ensure_ascii=False)
    body = f"""<body class="school-page-body">
{header}
<main class="school-page wrap">
  <nav class="breadcrumbs" aria-label="Навигация"><a href="/">Главная</a><span>›</span><a href="/ratings">Рейтинг школ</a><span>›</span><span aria-current="page">{escape(school["name"])}</span></nav>
  <p class="back-row"><a class="back-link" href="/ratings" data-back="/ratings">← К рейтингу</a></p>
  <section class="hero hero-centered school-hero">
    <div class="hero-glow hero-glow-blue" aria-hidden="true"></div><div class="hero-glow hero-glow-pink" aria-hidden="true"></div>
    <div class="hero-copy"><h1>{escape(school["name"])}</h1><p class="lead">{escape(school["description"])}</p><div class="sp-score"><small>Оценка ЕГЭ Мэтча</small><strong>{num(school["score"])}</strong><span>из 10</span></div></div>
  </section>
  <p class="sp-note">Оценка складывается из редакционной оценки по семи критериям и отзывов учеников: подтверждённые весят больше. Пока отзывов мало, она в основном редакционная. <a href="/methodology">Как считается оценка</a></p>
  <section class="sp-section"><h2>Оценка по критериям</h2><ul class="sp-criteria">{criteria_rows}</ul></section>
  <section class="sp-facts"><article><h2>Стоимость</h2><p>{escape(school["price"])}</p><p class="sp-inline-link"><a href="{escape(school["url"])}" target="_blank" rel="noopener">Проверить актуальные цены на сайте школы ↗</a></p></article><article><h2>Формат обучения</h2><p>{escape(school["format"])}</p></article></section>
  <section class="sp-section"><h2>Предметы ({len(school["subjects"])})</h2><ul class="sp-chips">{subjects}</ul></section>
  <section class="sp-two"><article><h2>Почему выбирают</h2><p>{escape(school["strengths"])}</p></article><article><h2>Что проверить перед покупкой</h2><p>{escape(school["weaknesses"])}</p></article></section>
  {teachers_block}
  <div class="sp-actions"><a class="button dark" href="{card_url}" target="_blank" rel="noopener" data-source="school_page">Курсы и отзывы в боте <span>↗</span></a><a class="button blue" href="{compare_url}">Сравнить с другой школой <span>→</span></a><a class="button outline" href="{review_url}" target="_blank" rel="noopener">Оставить отзыв <span>↗</span></a></div>
  <p class="sp-site-link">В боте: тарифы, преподаватели и отзывы учеников. Условия и цены школа публикует на <a href="{escape(school["url"])}" target="_blank" rel="noopener">официальном сайте ↗</a></p>
  <section class="sp-section"><h2>Другие школы</h2><nav class="sp-more" aria-label="Другие школы">{other_links}</nav><p class="sp-more-all"><a href="/ratings">Весь рейтинг →</a></p></section>
</main>
{footer}
<script>window.TEACHER_SLUGS={slug_map};</script>
<script src="/analytics-config.js?v=1"></script>
<script src="/analytics.js?v=5"></script>
{NAV_SCRIPT}
{FILTER_SCRIPT}
</body>
</html>
"""
    return page_head(school, url) + "\n" + body


def build_teacher_page(person, school, colleagues, header, footer):
    school_slug = school["reviewSlug"]
    school_url = f"/schools/{school_slug}"
    url = f"{SITE}/teachers/{person['slug']}"
    subjects = " · ".join(person["subjects"])
    score = person.get("studentScore")
    score_text = "—" if score is None else num(score)
    score_note = "Нужно 3 отзыва" if score is None else "из 10" + ("*" if person.get("isPreliminary") else "")
    criteria = person.get("criteria") or {}
    has_criteria = any(v is not None for v in criteria.values())
    rows = "".join(
        (
            f'<li><span>{escape(label)}</span><i aria-hidden="true"><b style="width:{criteria[key] * 10:.0f}%"></b></i><strong>{num(criteria[key])}</strong></li>'
            if criteria.get(key) is not None
            else f'<li class="sp-empty"><span>{escape(label)}</span><em>Пока нет оценки</em></li>'
        )
        for key, label in TEACHER_CRITERIA.items()
    )
    reviews_hint = (
        f'{person.get("verifiedReviewCount", 0)} подтверждённых отзывов'
        if has_criteria
        else "Появятся, когда наберётся вес трёх подтверждённых отзывов."
    )
    same_subject = [c for c in colleagues if set(c["subjects"]) & set(person["subjects"])]
    others = (same_subject + [c for c in colleagues if c not in same_subject])[:16]
    other_links = "".join(f'<a href="/teachers/{c["slug"]}">{escape(c["name"])}</a>' for c in others)
    review_url = f"{BOT}?start=review_{school_slug}"
    card_url = f"{BOT}?start=school_{school_slug}"
    title = f"{person['name']} — {subjects}, {school['name']} | ЕГЭ Мэтч"
    description = f"{person['name']}, преподаватель {school['name']}: {subjects}. Описание, оценки учеников и как оставить отзыв."
    crumbs = [
        ("Главная", f"{SITE}/"),
        ("Рейтинг школ", f"{SITE}/ratings"),
        (school["name"], f"{SITE}{school_url}"),
        (person["name"], url),
    ]
    body = f"""<body class="school-page-body teacher-page-body">
{header}
<main class="school-page wrap">
  <nav class="breadcrumbs" aria-label="Навигация"><a href="/">Главная</a><span>›</span><a href="/ratings">Рейтинг школ</a><span>›</span><a href="{school_url}">{escape(school["name"])}</a><span>›</span><span aria-current="page">{escape(person["name"])}</span></nav>
  <p class="back-row"><a class="back-link" href="{school_url}#teachers" data-back="{school_url}">← Все преподаватели школы</a></p>
  <section class="hero hero-centered school-hero">
    <div class="hero-glow hero-glow-blue" aria-hidden="true"></div><div class="hero-glow hero-glow-pink" aria-hidden="true"></div>
    <div class="hero-copy"><p class="teacher-kicker"><a href="{school_url}">{escape(school["name"])}</a></p><h1>{escape(person["name"])}</h1><p class="lead">{escape(subjects)}</p><div class="sp-score"><small>Оценка учеников</small><strong>{score_text}</strong><span>{score_note}</span></div></div>
  </section>
  <section class="sp-section"><h2>О преподавателе</h2><p class="sp-body">{escape(person.get("description") or "")}</p></section>
  <section class="sp-section"><h2>Оценки учеников</h2><p class="sp-hint">{escape(reviews_hint)}</p><ul class="sp-criteria">{rows}</ul></section>
  <div class="sp-actions"><a class="button dark" href="{card_url}" target="_blank" rel="noopener" data-source="teacher_page">Курсы школы и отзывы в боте <span>↗</span></a><a class="button blue" href="{school_url}">О школе <span>→</span></a><a class="button outline" href="{review_url}" target="_blank" rel="noopener">Оставить отзыв <span>↗</span></a></div>
  <p class="sp-site-link">Профиль на сайте школы: <a href="{escape(person["url"])}" target="_blank" rel="noopener">{escape(person["name"])} ↗</a></p>
  <section class="sp-section"><h2>Другие преподаватели школы</h2><nav class="sp-more" aria-label="Другие преподаватели школы">{other_links}</nav><p class="sp-more-all"><a href="{school_url}#teachers">Все преподаватели школы →</a></p></section>
</main>
{footer}
<script src="/analytics-config.js?v=1"></script>
<script src="/analytics.js?v=5"></script>
{NAV_SCRIPT}
</body>
</html>
"""
    return make_head(title, description, url, crumbs, noindex=True) + "\n" + body


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
    text = re.sub(re.escape(LINKS_START) + ".*?" + re.escape(LINKS_END) + r"\n?", "", text, flags=re.S)
    text = text.replace("</main>", block + "\n</main>", 1)
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


def patch_catalog_slugs(catalog, people):
    changed = False
    for record in catalog["teachers"]:
        slug = people[(record["school"], record["name"])]["slug"]
        if record.get("slug") != slug:
            record["slug"] = slug
            changed = True
    if changed:
        (WEB / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    catalog = json.loads((WEB / "catalog.json").read_text(encoding="utf-8"))
    schools = catalog["schools"]
    school_slugs = {s["name"]: s["reviewSlug"] for s in schools}
    people = teacher_people(catalog, school_slugs)
    patch_catalog_slugs(catalog, people)
    header, footer = shared_chrome()
    for folder in ("schools", "teachers"):
        (WEB / folder).mkdir(exist_ok=True)
        for path in (WEB / folder).glob("*.html"):
            path.unlink()
    for school in schools:
        members = sorted((p for (name, _), p in people.items() if name == school["name"]), key=lambda p: p["name"])
        others = [s for s in sorted(schools, key=lambda s: -s["score"]) if s["name"] != school["name"]]
        (WEB / "schools" / f"{school['reviewSlug']}.html").write_text(
            build_page(school, members, others, header, footer, school_slugs), encoding="utf-8"
        )
        for person in members:
            colleagues = [m for m in members if m is not person]
            (WEB / "teachers" / f"{person['slug']}.html").write_text(
                build_teacher_page(person, school, colleagues, header, footer), encoding="utf-8"
            )
    update_ratings_links(schools)
    write_sitemap(schools)
    print(f"Generated {len(schools)} school pages and {len(people)} teacher pages")


if __name__ == "__main__":
    main()
