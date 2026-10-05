from pathlib import Path

APP = (Path("web") / "app.js").read_text(encoding="utf-8")


def test_quiz_asks_format_support_and_teacher_importance():
    for key in ("key:'format'", "key:'goal'", "key:'support'", "key:'teacher'"):
        assert key in APP
    assert "const QUIZ_TOTAL=quizSteps.filter(step=>step.questionNumber).length;" in APP
    assert "`Вопрос ${step.questionNumber} из ${QUIZ_TOTAL}`" in APP


def test_format_is_close_to_a_deal_breaker_and_uses_school_lesson_data():
    assert "schoolFilters[school.name]?.lessons" in APP
    assert "format==='recorded'?PENALTY.recordedMissing:PENALTY.formatMissing" in APP


def test_support_answer_feeds_both_old_fields_and_bot_payload_carries_format_and_teacher():
    assert "if(step.key==='support'){siteQuiz.answers.curator=value;siteQuiz.answers.control=value;}" in APP
    payload = APP[APP.index("function quizPayload"):].split("\n")[0]
    assert payload.count("_${") == 10 and "_none_${a.control}_${a.format||'any'}_${a.teacher||'2'}" in payload


def test_result_shows_pros_cons_and_a_distinguishing_badge():
    assert "function matchBadge(top,item,index)" in APP
    assert 'class="quiz-match-cons"' in APP and 'class="quiz-match-badge"' in APP


def test_level_and_target_are_two_independent_rows_on_one_screen():
    assert "key:'level'" not in APP and "key:'target'" not in APP
    assert "{key:'goal',questionNumber:4," in APP and "pair:true" in APP
    assert "const GOAL_LEVELS=[['Почти с нуля','low'],['Что-то знаю','middle'],['База хорошая','high']];" in APP
    assert "[['Просто сдать','60'],['70+','70'],['80+','80'],['90+','90']]" in APP  # any level can pick any target


def test_answers_multiply_weights_and_schools_are_ranked_against_each_other():
    assert "const IMPORTANCE={" in APP and "function importanceOf(a)" in APP
    assert "function position(key,value)" in APP
    assert "const percent=50+Object.values(factors).reduce((x,y)=>x+y,0);" in APP
    for old in ("personalizedWeights", "matchPercent", "priorityEdge", "/10*1000)/10"):
        assert old not in APP


def test_caution_box_uses_brand_colors_not_an_off_palette_beige():
    css = (Path("web") / "composition.css").read_text(encoding="utf-8")
    rule = css[css.index(".quiz-match-cons{"):].split("}")[0]
    assert "var(--blush)" in rule and "#fff4ec" not in rule
