from pathlib import Path

APP = (Path("web") / "app.js").read_text(encoding="utf-8")


def test_quiz_asks_format_support_and_teacher_importance():
    for key in ("key:'format'", "key:'support'", "key:'teacher'"):
        assert key in APP
    assert "const QUIZ_TOTAL=quizSteps.filter(step=>step.questionNumber).length;" in APP
    assert "`Вопрос ${step.questionNumber} из ${QUIZ_TOTAL}`" in APP


def test_format_is_close_to_a_deal_breaker_and_uses_school_lesson_data():
    assert "schoolFilters[school.name]?.lessons" in APP
    assert "delta:format==='recorded'?-.8:-1.5" in APP


def test_support_answer_feeds_both_old_fields_and_bot_payload_stays_nine_fields():
    assert "if(step.key==='support'){siteQuiz.answers.curator=value;siteQuiz.answers.control=value;}" in APP
    payload = APP[APP.index("function quizPayload"):].split("\n")[0]
    assert payload.count("_${") == 9


def test_result_shows_pros_cons_and_a_distinguishing_badge():
    assert "function matchBadge(top,item,index)" in APP
    assert 'class="quiz-match-cons"' in APP and 'class="quiz-match-badge"' in APP
