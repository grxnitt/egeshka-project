"""The quiz and the ratings filters ask overlapping questions (subject, budget). These tests
pin the two places that connect them, so a future edit to one side doesn't silently break the
other: ratings.js writes the subject/budget it collected into the "Подобрать" links, and
app.js reads them back to skip the matching quiz questions, then offers a link back to the
filtered ratings page from the result screen.
"""
from pathlib import Path

WEB = Path("web")


def test_ratings_writes_subject_and_budget_into_the_quiz_link():
    js = (WEB / "ratings.js").read_text(encoding="utf-8")
    assert "function syncQuizLink()" in js
    assert "a[href^=\"/?start=quiz\"]" in js
    assert "params.set('subject',subject)" in js
    assert "params.set('budget',filterState.budget)" in js
    # called on every state change that could affect it, and once during initial load
    assert js.count("syncQuizLink()") >= 3


def test_app_js_reads_subject_and_budget_back_and_skips_those_questions():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert "function startQuiz(preset={})" in js
    assert "quizSubjectKeys.includes(preset.subject)" in js
    assert "siteQuiz.step=1" in js and "siteQuiz.step=2" in js
    assert "startQuiz({subject:startParams.get('subject'),budget:startParams.get('budget'),priority:startParams.get('priority')})" in js


def test_quiz_result_recaps_the_answers_and_links_back_to_filtered_ratings():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert "function ratingsUrl(a)" in js
    assert "NEEDS.curator_score(a)" in js  # reuses the same "does the student need a curator" rule as scoring
    assert 'class="qr-recap"' in js
    assert '<a href="${escape(ratingsUrl(a))}">Все в рейтинге</a>' in js
    css = (WEB / "composition.css").read_text(encoding="utf-8")
    assert ".qr-recap{" in css and ".qr-actions{" in css
