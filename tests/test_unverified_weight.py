from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "supabase" / "migrations" / "022_unverified_review_weight.sql").read_text(encoding="utf-8")


def test_unverified_reviews_count_with_a_weight_of_a_fifth_and_cannot_pile_up():
    # schools: weight 0.2 each, all of them together at most (confirmed + 1)
    assert "least(0.2 * p.u_count, p.v_count + 1.0)" in SQL
    # teachers: the same rule, shared out per review
    assert "least(0.2 * c.u_count, c.v_count + 1.0) / c.u_count" in SQL
    # the rating starts from an effective weight of 3, and is preliminary below 10
    assert "coalesce(v.n_eff, 0) < 3" in SQL and "coalesce(v.n_eff, 0) < 10 as is_preliminary" in SQL
    # the blend itself is unchanged: n / (n + 5)
    assert "v.n_eff / (v.n_eff + 5)" in SQL


def test_the_site_reads_the_new_counter():
    client = (ROOT / "web" / "supabase-client.js").read_text(encoding="utf-8")
    assert "unverified_review_count" in client and "unverifiedReviewCount" in client


def test_the_form_tells_people_what_a_review_without_a_screenshot_does():
    form = (ROOT / "web" / "review.html").read_text(encoding="utf-8")
    assert "с весом в пять раз меньше" in form
