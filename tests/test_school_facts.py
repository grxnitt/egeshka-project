import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGAL = json.loads((ROOT / "content" / "school_legal.json").read_text(encoding="utf-8"))
FACTS = json.loads((ROOT / "content" / "school_facts.json").read_text(encoding="utf-8"))
CATALOG = json.loads((ROOT / "web" / "catalog.json").read_text(encoding="utf-8"))
SLUGS = {school["reviewSlug"] for school in CATALOG["schools"]}


def page(slug):
    return (ROOT / "web" / "schools" / f"{slug}.html").read_text(encoding="utf-8")


def test_facts_belong_to_known_schools_and_have_valid_values():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", FACTS["checked"])
    for slug, item in FACTS["schools"].items():
        assert slug in SLUGS
        assert set(item) <= {"license", "deduction", "deduction_text", "installment", "trial", "refund"}
        assert item.get("deduction", "yes") in ("yes", "no")
        lic = item.get("license")
        if lic:
            assert lic.get("number") or lic.get("url") or lic.get("claimed") or lic.get("found") is False
            if lic.get("url"):
                assert lic["url"].startswith("https://")
            if lic.get("source") == "registry" and lic.get("found") is not False:
                # A full registry number: a truncated one (e.g. ".../002547") was published once and must never be again.
                assert re.fullmatch(r"Л035-\d{5}-\d{2}/\d{8}", lic["number"]), (slug, lic["number"])
                assert LEGAL[slug].get("inn"), slug


def test_block_is_drawn_only_for_schools_with_confirmed_facts():
    for slug in SLUGS:
        html = page(slug)
        assert ('id="facts"' in html) == bool(FACTS["schools"].get(slug)), slug


def test_block_states_the_source_and_the_check_date():
    html = page("umskul")
    assert "Факты о школе" in html and "сверена с реестром Рособрнадзора" in html
    assert "Остальное — со слов школы" in html and "8 октября 2026" in html
    assert "№Л035-01272-16/00254722" in html


def test_registry_licence_links_to_the_search_by_the_schools_inn():
    for slug, item in FACTS["schools"].items():
        lic = item.get("license") or {}
        if lic.get("source") == "registry":
            assert f"https://islod.obrnadzor.gov.ru/rlic/?eoName={LEGAL[slug]['inn']}" in page(slug), slug
            if lic.get("found") is not False:
                assert f"№{lic['number']}" in page(slug), slug


def test_school_that_says_no_deduction_is_shown_as_such():
    html = page("100ballov")
    assert "вычет пока не предоставляется" in html
    assert 'class="is-no"' in html


def test_missing_data_is_not_rendered_as_a_negative():
    # Only a school's own "no" may produce a negative row; unknowns are simply absent.
    for slug in SLUGS:
        html = page(slug)
        item = FACTS["schools"].get(slug, {})
        expected_no = item.get("deduction") == "no" or (item.get("license") or {}).get("found") is False
        assert ('class="is-no"' in html) == expected_no, slug


def test_school_not_found_in_the_registry_is_shown_as_not_found_not_as_unlicensed_claim():
    html = page("exammy")
    assert "В реестре Рособрнадзора лицензия не найдена" in html
    assert "eoName=631917326709" in html
