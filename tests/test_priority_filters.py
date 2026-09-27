"""The "Что для тебя особенно важно?" chips on /ratings, and their round trip with the quiz.

Design: picking a priority chip is a hard filter (school's score for that criterion must be
>= STRONG_THRESHOLD), using the exact same 8.5 cutoff and the same four criterion keys
(teacher/practice/curator/platform -> teachers_score/practice_score/curator_score/platform_score)
the quiz already uses for its own "сильные X" match reasons (egeshka_bot/scoring.py,
web/app.js matchSchool) - one vocabulary and one number everywhere, not a second ad hoc system.
A criterion the school does not offer is null in catalog.json (see the criteria-availability
system), so it fails the >= 8.5 check on its own without special-casing "none" here.
"""
import re
from pathlib import Path

WEB = Path("web")


def test_ratings_priority_filter_reuses_the_quiz_criterion_map_and_threshold():
    js = (WEB / "ratings.js").read_text(encoding="utf-8")
    assert "const PRIORITY_FIELD={teacher:'teachers_score',practice:'practice_score',curator:'curator_score',platform:'platform_score'};" in js
    assert "const STRONG_THRESHOLD=8.5;" in js
    # a missing criterion is null in the catalog -> Number(null) is 0 -> fails the threshold, no extra "none" check needed
    assert "filterState.priorities.some(key=>Number(school.criteria[PRIORITY_FIELD[key]])<STRONG_THRESHOLD)" in js


def test_priority_chips_are_multi_select_up_to_two_like_the_quiz_priorities():
    js = (WEB / "ratings.js").read_text(encoding="utf-8")
    assert "function togglePriority(key)" in js
    assert "if(filterState.priorities.length===2)filterState.priorities.shift();" in js
    assert "priorities:(initialParams.get('priority')||'').split(',').filter(key=>PRIORITY_FIELD[key]).slice(0,2)".replace("priorities:", "filterState.priorities=") in js


def test_priority_state_round_trips_through_the_url_and_reset_clears_it():
    js = (WEB / "ratings.js").read_text(encoding="utf-8")
    assert "priority:filterState.priorities.join(',')" in js  # written by updateFilterUrl
    assert re.search(r"function resetFilters\(\)\{[^}]*priorities:\[\]", js)


def test_visible_cards_show_the_real_number_behind_an_active_priority():
    js = (WEB / "ratings.js").read_text(encoding="utf-8")
    assert "function priorityBadges(school)" in js
    assert "school-card-priority" in js
    assert "не на всех тарифах" in js  # a 'tier' criterion still counts but is flagged, matching the compare/school-page convention
    assert "${priorityBadges(school)}${decisionFields(school)}" in js


def test_quiz_offers_the_priorities_carried_from_ratings_and_carries_its_own_back():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    # ratings -> quiz: pre-fills subject/budget (real skip) and flags the matching priority option (no fake skip)
    assert "siteQuiz.suggestedPriorities=String(preset.priority||'').split(',').filter(key=>PRIORITY_LABELS[key]);" in app
    assert "const suggested=(step.key==='priority1'||step.key==='priority2')&&siteQuiz.suggestedPriorities.includes(value);" in app
    assert 'class="${suggested?\'is-suggested\':\'\'}"' in app
    # quiz -> ratings: the priorities actually chosen in the quiz (not 'price', which has no ratings chip)
    assert "const priorities=[a.priority1,a.priority2].filter(value=>value&&value!=='price'&&value!=='none');" in app
    assert "if(priorities.length)params.set('priority',priorities.join(','));" in app


def test_priority_field_keys_match_the_quiz_scoring_module_exactly():
    import sys
    sys.path.insert(0, ".")
    from egeshka_bot.scoring import PRIORITY_TO_FIELD

    js = (WEB / "ratings.js").read_text(encoding="utf-8")
    match = re.search(r"const PRIORITY_FIELD=\{([^}]*)\};", js)
    assert match
    pairs = dict(re.findall(r"(\w+):'(\w+)'", match.group(1)))
    assert pairs == PRIORITY_TO_FIELD


def test_strong_threshold_matches_the_bot_scoring_reason_cutoff():
    scoring = Path("egeshka_bot/scoring.py").read_text(encoding="utf-8")
    assert "value >= 8.5" in scoring  # school_score()'s own "сильные X" reason threshold
    assert "const STRONG_THRESHOLD=8.5;" in (WEB / "ratings.js").read_text(encoding="utf-8")
