"""Rasterize web/assets/egeshka-logo-icon.svg into the PNG/ICO sizes iOS, Android and
link-preview cards expect (they don't reliably fall back to the SVG favicon).

Run after the source SVG changes:  python3 scripts/make_site_icons.py
"""
import re
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "web" / "assets" / "egeshka-logo-icon.svg"
OUT = ROOT / "web" / "assets"
INK = (24, 25, 35)
DOT = (255, 77, 141)
PAPER = (250, 248, 245)
VIEWBOX = 512


def parse_path(d, transform):
    """Minimal parser for the M/L/H/V/Z-only, absolute-coordinate path this icon uses."""
    tokens = re.findall(r"[MLHVZ]|-?\d+(?:\.\d+)?", d)
    subpaths, points, cur, i = [], [], (0.0, 0.0), 0
    while i < len(tokens):
        cmd = tokens[i]
        i += 1
        if cmd == "Z":
            subpaths.append([transform(*p) for p in points])
            points = []
            continue
        if cmd == "M":
            if points:
                subpaths.append([transform(*p) for p in points])
                points = []
            cur = (float(tokens[i]), float(tokens[i + 1]))
            i += 2
            points.append(cur)
            # implicit lineto pairs may follow an M, same as this icon's second subpath
            while i + 1 < len(tokens) and tokens[i] not in "MLHVZ":
                cur = (float(tokens[i]), float(tokens[i + 1]))
                points.append(cur)
                i += 2
        elif cmd == "L":
            cur = (float(tokens[i]), float(tokens[i + 1]))
            i += 2
            points.append(cur)
        elif cmd == "H":
            cur = (float(tokens[i]), cur[1])
            i += 1
            points.append(cur)
        elif cmd == "V":
            cur = (cur[0], float(tokens[i]))
            i += 1
            points.append(cur)
    if points:
        subpaths.append([transform(*p) for p in points])
    return subpaths


def render(size, background=None):
    scale = 4
    img = Image.new("RGBA", (size * scale, size * scale), background or (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size * scale / VIEWBOX

    def mark_transform(x, y):
        # mirrors the SVG's `translate(86 440) scale(.4 -.4)` on the <g> holding the mark
        return ((86 + 0.4 * x) * s, (440 - 0.4 * y) * s)

    svg = SVG.read_text(encoding="utf-8")
    path_d = re.search(r'<path d="([^"]+)"', svg).group(1)
    for polygon in parse_path(path_d, mark_transform):
        draw.polygon(polygon, fill=INK)
    circle = re.search(r'<circle cx="(\d+)" cy="(\d+)" r="(\d+)"', svg)
    cx, cy, r = (float(v) * s for v in circle.groups())
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=DOT)
    return img.resize((size, size), Image.LANCZOS)


def main():
    # Transparent PWA/manifest icons.
    for size in (192, 512):
        render(size).save(OUT / f"icon-{size}.png")
    # iOS/link-preview icons expect an opaque background (iOS adds its own rounded mask).
    render(180, background=PAPER).convert("RGB").save(OUT / "apple-touch-icon.png")
    # Several explicit PNG sizes so the browser/OS picks a crisp match instead of stretching
    # a single small favicon.ico up - that's what looked blocky when shown larger than 32px.
    for size in (16, 32, 48, 96, 192, 512):
        render(size, background=PAPER).convert("RGB").save(OUT / f"favicon-{size}.png")
    favicons = [render(s, background=PAPER).convert("RGB") for s in (16, 32, 48, 64, 128, 256)]
    favicons[0].save(OUT.parent / "favicon.ico", sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256)])
    print(f"Wrote icon-192/512.png, favicon-*.png, apple-touch-icon.png and favicon.ico to {OUT}/ and {OUT.parent}/")


if __name__ == "__main__":
    main()
