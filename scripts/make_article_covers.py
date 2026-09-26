"""Draw flat brand covers for articles: SVG for the page and PNG (1200x630) for social previews.

Run after adding a cover:  python3 scripts/make_article_covers.py
Each cover is a function below; articles pick one with the `cover:` front matter key.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "assets" / "articles"
W, H = 1200, 630
BLUE, PINK, INK, WHITE = "#344bd8", "#ff4d8d", "#181923", "#ffffff"
LAVENDER = "#eceaff"


class Canvas:
    """Tiny drawing surface that renders the same shapes to SVG and to an anti-aliased PNG."""

    def __init__(self, bg, scale=2):
        self.s = scale
        self.svg = [f'<rect width="{W}" height="{H}" fill="{bg}"/>']
        self.img = Image.new("RGB", (W * scale, H * scale), bg)
        self.d = ImageDraw.Draw(self.img)

    def rect(self, x, y, w, h, r=0, fill=WHITE):
        s = self.s
        self.d.rounded_rectangle([x * s, y * s, (x + w) * s - 1, (y + h) * s - 1], radius=r * s, fill=fill)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"/>')

    def bar(self, x, y, w, h, r, fill):
        """Rectangle with only the top corners rounded."""
        s = self.s
        self.d.rounded_rectangle(
            [x * s, y * s, (x + w) * s - 1, (y + h) * s - 1], radius=r * s, fill=fill, corners=(True, True, False, False)
        )
        path = f"M{x} {y + h}V{y + r}A{r} {r} 0 0 1 {x + r} {y}H{x + w - r}A{r} {r} 0 0 1 {x + w} {y + r}V{y + h}Z"
        self.svg.append(f'<path d="{path}" fill="{fill}"/>')

    def circle(self, cx, cy, r, fill=WHITE):
        s = self.s
        self.d.ellipse([(cx - r) * s, (cy - r) * s, (cx + r) * s - 1, (cy + r) * s - 1], fill=fill)
        self.svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/>')

    def ring(self, cx, cy, r, width, color):
        s = self.s
        outer = r + width / 2
        self.d.ellipse(
            [(cx - outer) * s, (cy - outer) * s, (cx + outer) * s - 1, (cy + outer) * s - 1],
            outline=color,
            width=int(width * s),
        )
        self.svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{width}"/>')

    def arc(self, cx, cy, r, width, start, end, color):
        s = self.s
        outer = r + width / 2
        self.d.arc(
            [(cx - outer) * s, (cy - outer) * s, (cx + outer) * s - 1, (cy + outer) * s - 1],
            start,
            end,
            fill=color,
            width=int(width * s),
        )
        a1, a2 = math.radians(start), math.radians(end)
        x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        x2, y2 = cx + r * math.cos(a2), cy + r * math.sin(a2)
        large = 1 if (end - start) % 360 > 180 else 0
        self.svg.append(
            f'<path d="M{x1:.1f} {y1:.1f}A{r} {r} 0 {large} 1 {x2:.1f} {y2:.1f}" fill="none" stroke="{color}" stroke-width="{width}"/>'
        )

    def poly(self, pts, fill):
        s = self.s
        self.d.polygon([(x * s, y * s) for x, y in pts], fill=fill)
        points = " ".join(f"{x:g},{y:g}" for x, y in pts)
        self.svg.append(f'<polygon points="{points}" fill="{fill}"/>')

    def line(self, pts, color, width):
        s = self.s
        self.d.line([(x * s, y * s) for x, y in pts], fill=color, width=int(width * s), joint="curve")
        for x, y in (pts[0], pts[-1]):
            r = width / 2
            self.d.ellipse([(x - r) * s, (y - r) * s, (x + r) * s, (y + r) * s], fill=color)
        points = " ".join(f"{x:g},{y:g}" for x, y in pts)
        self.svg.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
        )

    def sparkle(self, cx, cy, big, fill):
        small = big * 0.28
        self.poly(
            [(cx, cy - big), (cx + small, cy - small), (cx + big, cy), (cx + small, cy + small),
             (cx, cy + big), (cx - small, cy + small), (cx - big, cy), (cx - small, cy - small)],
            fill,
        )

    def tick(self, cx, cy, color=WHITE, size=1.0, width=5):
        self.line([(cx - 8 * size, cy), (cx - 2 * size, cy + 7 * size), (cx + 9 * size, cy - 7 * size)], color, width)

    def save(self, name):
        OUT.mkdir(parents=True, exist_ok=True)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" aria-hidden="true">'
            + "".join(self.svg)
            + "</svg>\n"
        )
        (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")
        self.img.resize((W, H), Image.LANCZOS).save(OUT / f"{name}.png", optimize=True)


def cover_exam():
    c = Canvas(BLUE)
    c.ring(930, 330, 200, 70, "#4a60e2")
    c.circle(985, 195, 80, PINK)
    c.circle(1075, 445, 26, WHITE)
    c.circle(760, 140, 16, "#8b9bf0")
    c.rect(150, 80, 470, 470, 40, WHITE)
    c.rect(196, 128, 200, 30, 15, PINK)
    c.rect(196, 190, 340, 16, 8, LAVENDER)
    c.rect(196, 220, 270, 16, 8, LAVENDER)
    rows = [(300, BLUE, 300), (378, PINK, 250), (456, None, 200)]
    for y, color, bar_w in rows:
        if color:
            c.circle(214, y + 17, 18, color)
            c.tick(214, y + 17, WHITE, 0.9, 4)
        else:
            c.ring(214, y + 17, 17, 4, "#c9cde6")
        c.rect(252, y + 9, bar_w, 16, 8, "#dfe2f7")
    c.sparkle(690, 470, 34, "#8b9bf0")
    return c


def cover_market():
    c = Canvas(PINK)
    c.ring(90, 90, 120, 50, BLUE)
    for row in range(3):
        for col in range(4):
            c.circle(900 + col * 44, 70 + row * 44, 6, "#ff85ad")
    heights = [130, 190, 260, 330, 370, 392]
    base = 545
    tops = []
    for i, h in enumerate(heights):
        x = 130 + i * 156
        c.bar(x, base - h, 120, h, 30, INK if i == len(heights) - 1 else WHITE)
        tops.append((x + 60, base - h - 42))
    c.line(tops, BLUE, 10)
    for x, y in tops:
        c.circle(x, y, 17, BLUE)
        c.circle(x, y, 8, WHITE)
    return c


def cover_ai():
    c = Canvas(INK)
    c.ring(140, 560, 150, 46, "#262839")
    c.rect(120, 90, 560, 170, 48, BLUE)
    c.poly([(190, 258), (150, 322), (262, 258)], BLUE)
    for i, w in enumerate((360, 430, 250)):
        c.rect(172, 132 + i * 36, w, 18, 9, "#c4ceff")
    c.rect(480, 330, 600, 190, 52, WHITE)
    c.poly([(1010, 518), (1050, 584), (930, 518)], WHITE)
    c.rect(532, 374, 230, 22, 11, PINK)
    c.rect(532, 418, 470, 18, 9, "#dcdce6")
    c.rect(532, 454, 340, 18, 9, "#dcdce6")
    c.sparkle(985, 165, 88, PINK)
    c.sparkle(850, 100, 38, "#8b9bf0")
    c.sparkle(1100, 290, 24, WHITE)
    return c


def cover_scores():
    c = Canvas(LAVENDER)
    cx, cy, r, w = 400, 315, 170, 74
    c.ring(cx, cy, r, w, WHITE)
    c.arc(cx, cy, r, w, -90, 180, BLUE)
    end = math.radians(180)
    c.circle(cx, cy - r, w / 2, BLUE)
    c.circle(cx + r * math.cos(end), cy + r * math.sin(end), w / 2, BLUE)
    c.circle(cx, cy, 92, PINK)
    c.tick(cx, cy, WHITE, 2.2, 12)
    for i, (fill, filled) in enumerate(((BLUE, 300), (PINK, 240), (INK, 180))):
        y = 140 + i * 120
        c.rect(720, y, 360, 72, 36, WHITE)
        c.rect(720, y, filled + 40, 72, 36, fill)
        c.circle(756, y + 36, 16, WHITE)
    c.sparkle(1060, 78, 34, PINK)
    c.circle(650, 560, 18, "#c9c4f5")
    return c


def cover_admission():
    c = Canvas("#f8dce8")
    c.circle(930, 130, 90, PINK)
    c.ring(1085, 545, 80, 36, BLUE)
    c.circle(730, 590, 16, WHITE)
    c.sparkle(800, 92, 32, BLUE)
    dx = 60
    c.poly([(150 + dx, 262), (400 + dx, 120), (650 + dx, 262)], BLUE)
    c.rect(170 + dx, 262, 460, 30, 8, BLUE)
    c.circle(400 + dx, 208, 28, WHITE)
    for x in (206, 306, 406, 506):
        c.rect(x + dx, 304, 62, 184, 12, WHITE)
    c.rect(150 + dx, 488, 500, 34, 10, BLUE)
    c.rect(122 + dx, 522, 556, 30, 10, INK)
    for i, (color, w) in enumerate(((BLUE, 210), (PINK, 170), (INK, 130))):
        y = 290 + i * 84
        c.rect(760, y, 260, 60, 30, WHITE)
        c.circle(792, y + 30, 18, color)
        c.tick(792, y + 30, WHITE, 0.8, 4)
        c.rect(826, y + 22, w - 60, 16, 8, "#e7e3f4")
    return c


def shield_points(cx, top, bottom, half, steps=14):
    """Outline of a shield: straight sides, curved sides towards the bottom point."""
    mid = top + (bottom - top) * 0.42
    points = [(cx - half, top), (cx + half, top), (cx + half, mid)]
    for i in range(1, steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * (cx + half) + 2 * (1 - t) * t * (cx + half) + t ** 2 * cx
        y = (1 - t) ** 2 * mid + 2 * (1 - t) * t * (bottom - (bottom - mid) * 0.25) + t ** 2 * bottom
        points.append((x, y))
    for i in range(1, steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * cx + 2 * (1 - t) * t * (cx - half) + t ** 2 * (cx - half)
        y = (1 - t) ** 2 * bottom + 2 * (1 - t) * t * (bottom - (bottom - mid) * 0.25) + t ** 2 * mid
        points.append((x, y))
    return points


def cover_safety():
    c = Canvas(INK)
    c.ring(1080, 560, 130, 44, "#262839")
    c.rect(110, 120, 400, 380, 44, WHITE)
    c.rect(150, 168, 190, 22, 11, "#dcdce6")
    c.rect(150, 214, 310, 18, 9, "#dcdce6")
    c.rect(150, 250, 250, 18, 9, "#dcdce6")
    c.rect(150, 340, 310, 62, 31, BLUE)
    c.rect(150, 424, 310, 34, 17, "#dcdce6")
    c.circle(470, 140, 44, PINK)
    c.rect(464, 116, 12, 30, 6, WHITE)
    c.circle(470, 160, 7, WHITE)
    c.poly(shield_points(790, 100, 540, 190), BLUE)
    c.poly(shield_points(790, 150, 490, 138), "#4a60e2")
    c.circle(790, 300, 80, PINK)
    c.tick(790, 300, WHITE, 2.4, 14)
    c.sparkle(1050, 170, 40, "#8b9bf0")
    c.sparkle(600, 560, 22, PINK)
    return c


def cover_teacher():
    c = Canvas("#e9edff")
    c.circle(1010, 150, 84, PINK)
    c.ring(1085, 520, 70, 30, BLUE)
    c.sparkle(790, 92, 32, BLUE)
    c.circle(120, 560, 16, PINK)
    c.rect(140, 90, 580, 380, 40, INK)
    for i, w in enumerate((400, 320, 360)):
        c.rect(196, 148 + i * 58, w, 20, 10, "#c9cde6")
    c.ring(590, 372, 44, 9, PINK)
    c.tick(590, 372, PINK, 1.5, 9)
    c.rect(196, 330, 250, 20, 10, "#4a60e2")
    c.rect(196, 372, 190, 20, 10, "#4a60e2")
    c.rect(120, 470, 620, 30, 15, BLUE)
    for i, (color, w, x) in enumerate(((PINK, 300, 780), (WHITE, 250, 810), (BLUE, 210, 840))):
        y = 396 - i * 66
        c.rect(x, y, w, 56, 16, color)
        c.rect(x + 22, y + 20, w - 90, 16, 8, "#ffffff" if color != WHITE else "#dfe2f7")
    return c


def cover_errors():
    c = Canvas(PINK)
    c.ring(1080, 90, 90, 44, "#ff85ad")
    c.circle(90, 560, 70, BLUE)
    c.sparkle(740, 520, 30, WHITE)
    c.rect(150, 60, 430, 510, 38, WHITE)
    c.rect(196, 108, 190, 28, 14, INK)
    marked = {1, 3}
    for i in range(6):
        y = 176 + i * 62
        if i in marked:
            c.rect(190, y - 10, 344, 44, 14, "#ffe1ec")
            c.circle(500, y + 12, 15, PINK)
            c.line([(493, y + 5), (507, y + 19)], WHITE, 4)
            c.line([(507, y + 5), (493, y + 19)], WHITE, 4)
        c.rect(206, y + 4, 240 if i % 2 else 290, 16, 8, "#dfe2f7")
    c.circle(840, 300, 132, WHITE)
    for i, h in enumerate((90, 150, 210)):
        c.bar(756 + i * 62, 396 - h, 44, h, 12, (BLUE, PINK, INK)[i])
    c.ring(840, 300, 132, 30, BLUE)
    c.line([(935, 395), (1050, 510)], INK, 40)
    return c


COVERS = {
    "exam": cover_exam,
    "market": cover_market,
    "ai": cover_ai,
    "scores": cover_scores,
    "admission": cover_admission,
    "safety": cover_safety,
    "teacher": cover_teacher,
    "errors": cover_errors,
}


def main():
    for name, draw in COVERS.items():
        draw().save(name)
    print(f"Wrote {len(COVERS)} covers to {OUT}")


if __name__ == "__main__":
    main()
