import json
import re
from pathlib import Path

WEB = Path("web")
STATIC_PAGES = ("index.html", "ratings.html", "compare.html", "methodology.html", "404.html")


def test_apple_touch_icon_and_favicon_ico_exist_and_match_the_svg_mark():
    assert (WEB / "favicon.ico").exists()
    for name in ("apple-touch-icon.png", "icon-192.png", "icon-512.png"):
        assert (WEB / "assets" / name).exists(), name


def test_every_page_links_the_apple_touch_icon_and_ico_favicon():
    pages = [WEB / name for name in STATIC_PAGES]
    pages += [WEB / "schools" / "neofamily.html", WEB / "teachers" / "100ballov-artem-imaev.html", WEB / "articles" / "index.html"]
    for page in pages:
        html = page.read_text(encoding="utf-8")
        assert re.search(r'<link rel="apple-touch-icon" href="[^"]*assets/apple-touch-icon\.png">', html), page
        assert re.search(r'<link rel="icon" href="[^"]*favicon\.ico" sizes="32x32">', html), page


def test_manifest_lists_png_icons_for_android_and_pwa_installs():
    manifest = json.loads((WEB / "site.webmanifest").read_text(encoding="utf-8"))
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes
