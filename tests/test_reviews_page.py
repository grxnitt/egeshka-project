import json
from pathlib import Path

WEB = Path("web")


def read(path):
    return (WEB / path).read_text(encoding="utf-8")


def test_reviews_page_exists_with_no_personal_data():
    page = read("reviews.html")
    assert '<link rel="canonical" href="https://egematch.ru/reviews">' in page
    assert 'id="review-list"' in page and 'id="review-filter"' in page
    assert 'data-mode="schools"' in page and 'data-mode="teachers"' in page
    # The whole point: real text, real per-criterion scores, no e-mail; a name only if the author chose to sign.
    assert "Почты авторов не показываем" in page and "модератор" in page
    # the "N+ reviews" sticker is filled in by the script and stays hidden below 10 reviews
    assert 'id="reviews-sticker"' in page and "hidden" in page.split('id="reviews-sticker"')[1].split(">")[0]


def test_reviews_js_only_renders_the_signature_the_author_chose():
    script = read("reviews.js")
    assert "fetchPublicReviews" in script
    # It must read school/teacher identity to link the card, never a user id or account name.
    assert "user_id" not in script and "username" not in script
    # The only person-related field is the signature the author chose (a first name or nickname), always escaped.
    assert "escape(review.display_name)" in script


def test_public_reviews_view_excludes_personal_columns():
    migration = Path("supabase/migrations/012_public_reviews.sql").read_text(encoding="utf-8")
    column_list = migration.split("select\n", 1)[1].split("from public.reviews", 1)[0]
    for column in ("user_id", "proof_file_id", "proof_consent", "proof_admin_messages"):
        assert column not in column_list
    assert "grant select on public.public_reviews to anon, authenticated;" in migration


def test_nav_points_to_the_reviews_page_everywhere():
    for name in ("index.html", "ratings.html", "compare.html", "methodology.html", "schools/umskul.html"):
        header = read(name)
        assert '<a href="/reviews">Отзывы</a>' in header or '<a class="active" href="/reviews">Отзывы</a>' in header
    assert '<a class="active" href="/reviews">Отзывы</a>' in read("reviews.html")


def test_reviews_page_is_in_sitemap_and_vercel_rewrites():
    sitemap = read("sitemap.xml")
    assert "<loc>https://egematch.ru/reviews</loc>" in sitemap
    vercel = json.loads(read("vercel.json"))
    assert {"source": "/reviews", "destination": "/reviews.html"} in vercel["rewrites"]


def test_bot_links_out_to_the_reviews_page():
    bot = Path("egeshka_bot/bot.py").read_text(encoding="utf-8")
    assert 'SITE_URL = "https://egematch.ru"' in bot
    assert "/reviews?school=" in bot and "/reviews?teacher=" in bot
