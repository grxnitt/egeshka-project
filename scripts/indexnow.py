"""Tell Yandex (IndexNow) about new or changed pages so they are crawled sooner.

    python3 scripts/indexnow.py            # articles list + every article
    python3 scripts/indexnow.py URL [URL]  # specific pages
    python3 scripts/indexnow.py --dry-run  # only print what would be sent

Run it after the site is deployed: the key file https://egematch.ru/<key>.txt must already be live.
The key is public by design (IndexNow checks that the site owner published it).
"""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://egematch.ru"
HOST = "egematch.ru"
KEY = "dc3c4eecd116f964beebd68089145c84"
ENDPOINT = "https://yandex.com/indexnow"


def default_urls():
    urls = [f"{SITE}/articles"]
    index = ROOT / "content" / "articles.json"
    if index.exists():
        urls += [f"{SITE}/articles/{item['slug']}" for item in json.loads(index.read_text(encoding="utf-8"))]
    return urls


def payload(urls):
    return {"host": HOST, "key": KEY, "keyLocation": f"{SITE}/{KEY}.txt", "urlList": urls}


def main(argv):
    dry = "--dry-run" in argv
    urls = [a for a in argv if not a.startswith("--")] or default_urls()
    body = json.dumps(payload(urls)).encode("utf-8")
    print(f"{len(urls)} URL(s) -> {ENDPOINT}")
    for url in urls:
        print("  ", url)
    if dry:
        return 0
    request = urllib.request.Request(
        ENDPOINT, data=body, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            print("HTTP", response.status, "(200/202 = accepted)")
    except Exception as error:  # noqa: BLE001 - print any network or HTTP error for the operator
        print("Failed:", error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
