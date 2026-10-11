"""The home-page numbers: the counting logic is run with a fake clock (tests/js/facts-count.test.js) and the wiring
that keeps other scripts from cutting the count short is checked in the files."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_counting_logic_with_a_fake_clock():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    result = subprocess.run([node, str(ROOT / "tests" / "js" / "facts-count.test.js")], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_home_numbers_have_one_owner_and_a_real_value_in_the_html():
    html, app, css, motion = read("web/index.html"), read("web/app.js"), read("web/composition.css"), read("web/motion.js")
    assert 'src="facts-count.js?v=' in html
    assert re.search(r'<b data-fact="schools">\d+</b>', html) and re.search(r'<b data-fact="teachers">\d+\+</b>', html)
    assert "egeSetFact" in app and "facts.textContent=" not in app and "people.textContent=" not in app
    assert ".hs-fact b[data-fact].is-ready{visibility:visible" in css and ".hs-fact b[data-fact]{visibility:hidden" in css
    assert "<noscript><style>.hs-fact b[data-fact]{visibility:visible" in html
    assert "hs-fact" not in motion          # motion.js no longer touches them
