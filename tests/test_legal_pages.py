import json
import re
from pathlib import Path

WEB = Path("web")


def read(path):
    return (WEB / path).read_text(encoding="utf-8")


def test_legal_pages_are_routed_and_in_the_sitemap():
    rewrites = {r["source"]: r["destination"] for r in json.loads(read("vercel.json"))["rewrites"]}
    sitemap = read("sitemap.xml")
    for route in ("privacy", "terms"):
        assert rewrites[f"/{route}"] == f"/{route}.html"
        assert f"<loc>https://egematch.ru/{route}</loc>" in sitemap
        assert f'<link rel="canonical" href="https://egematch.ru/{route}">' in read(f"{route}.html")


def test_every_page_footer_links_to_both_legal_pages():
    pages = [*WEB.glob("*.html"), *WEB.glob("schools/*.html"), *WEB.glob("teachers/*.html"), *WEB.glob("articles/*.html")]
    for page in pages:
        text = page.read_text(encoding="utf-8")
        footer = re.search(r"<footer.*?</footer>", text, re.S)
        if not footer or page.name.startswith("yandex_"):
            continue
        assert 'href="/privacy"' in footer.group(0) and 'href="/terms"' in footer.group(0), page


def test_privacy_policy_names_every_third_party_the_browser_talks_to():
    policy = read("privacy.html")
    for processor in ("Telegram", "Яндекс.Метрика", "Vercel", "Supabase"):
        assert processor in policy
    assert "482623207383" in policy and "482623207383" in read("terms.html")


def test_metrika_loads_only_after_cookie_consent():
    script = read("analytics.js")
    assert script.count("mc.yandex.ru/metrika/tag.js") == 1
    start = script.index("function startMetrika()")
    assert script.index("mc.yandex.ru/metrika/tag.js") > start
    assert "if(consent==='yes')startMetrika()" in script
    assert "data-cookie=\"yes\"" in script and "data-cookie=\"no\"" in script
    assert "webvisor:false" in script


def test_policy_explains_the_cookie_choice_and_lets_it_be_changed():
    policy = read("privacy.html")
    assert '<h2 id="cookies">' in policy
    assert "data-cookie-settings" in policy
    assert "только после того, как посетитель нажимает «Принять»" in policy


def test_policy_describes_site_leads_and_the_age_gate():
    policy = read("privacy.html")
    for needed in ("3.4. Данные заявки в школу", "Передача заявки в школу", "365 дней", "самостоятельным оператором", "родитель (законный представитель)"):
        assert needed in policy
    assert "Выбрать школу" in policy and "Выбрать школу" in read("terms.html")
