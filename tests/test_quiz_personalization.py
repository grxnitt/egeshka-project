from pathlib import Path

APP = (Path("web") / "app.js").read_text(encoding="utf-8")


def test_quiz_asks_format_support_and_teacher_importance():
    for key in ("key:'format'", "key:'goal'", "key:'support'", "key:'teacher'"):
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


def test_level_and_target_come_from_one_goal_question():
    assert "key:'level'" not in APP and "key:'target'" not in APP
    assert "const [level,target]=value.split('|');siteQuiz.answers.level=level;siteQuiz.answers.target=target;" in APP


def test_percent_stretches_the_real_score_band_instead_of_dividing_by_ten():
    assert "const matchPercent=fit=>" in APP and "(fit-FIT_FLOOR)/(FIT_CEIL-FIT_FLOOR)" in APP
    assert "/10*1000)/10" not in APP  # the old score/10 mapping squeezed every school into 85-99%
    assert "function priorityEdge(school,a,teachersValue)" in APP
    assert "fit=fit+bf+need.delta+ff.delta+priorityEdge(school,a,teachersValue);" in APP


def test_caution_box_uses_brand_colors_not_an_off_palette_beige():
    css = (Path("web") / "composition.css").read_text(encoding="utf-8")
    rule = css[css.index(".quiz-match-cons{"):].split("}")[0]
    assert "var(--blush)" in rule and "#fff4ec" not in rule
