"""One spelling of every rashi in Marathi, wherever a Marathi reader can see it.

Marathi writes the seventh rashi तूळ and the ninth धनू. Both differ from Hindi, and both have drifted
before: the page title once said धनु above a page that said धनू forty-two times. That one was fixed by
DERIVING the Python tables from `app/rashifal/i18n.rashi_name` instead of writing them out again - but the
browser's own table, which labels the result chart, is JavaScript and was still a hand-written copy. So the
chart said धनु while the page around it said धनू.

This checks the copies that cannot be derived - the JavaScript table and the Marathi prose - against the
one authority. A test, not a convention, because every drift so far has been somebody editing one copy.
"""

import json
import re
from pathlib import Path

import pytest

from app.rashifal.i18n import rashi_name

ROOT = Path(__file__).resolve().parents[1]
RENDER_JS = (ROOT / "app" / "static" / "js" / "render.js").read_text(encoding="utf-8")
LANGS = ("hi", "mr")


def _js_table(lang: str) -> list[str]:
    """The twelve rashi names out of render.js's SIGN_NAMES.

    Anchored to SIGN_NAMES by name: render.js has several objects keyed `hi:`/`mr:` - month names and
    graha names among them - and a looser pattern happily returned the months and compared those.
    """
    block = re.search(r"var SIGN_NAMES = \{(.*?)\n  \};", RENDER_JS, re.S)
    assert block, "render.js no longer has a SIGN_NAMES table - this check cannot pass vacuously"
    match = re.search(r"^\s*%s: (\[[^\]]*\])" % lang, block.group(1), re.M)
    assert match, f"SIGN_NAMES has no {lang} table"
    return json.loads(match.group(1))


@pytest.mark.parametrize("lang", LANGS)
def test_the_browsers_rashi_table_agrees_with_the_spelling_authority(lang):
    table = _js_table(lang)
    assert len(table) == 12, f"{lang}: {len(table)} names, not twelve"
    expected = [rashi_name(index, lang) for index in range(1, 13)]
    assert table == expected, (
        f"{lang}: the table the result chart reads disagrees with app/rashifal/i18n.rashi_name at "
        + ", ".join(f"{i + 1}: {got!r} vs {want!r}" for i, (got, want) in enumerate(zip(table, expected))
                    if got != want))


def test_marathi_writes_the_ninth_rashi_with_the_long_vowel():
    """Named on its own because it is the one that keeps coming back, and because a reader who sees both
    spellings on one page does not conclude that one of them is a typo - they conclude we do not know."""
    assert rashi_name(9, "mr") == "धनू"
    assert rashi_name(7, "mr") == "तूळ"
    assert "धनू" in _js_table("mr") and "धनु" not in _js_table("mr")


# The Marathi strings that are prose rather than a table, and so cannot be derived from anything.
MARATHI_PROSE = (
    ROOT / "app" / "static" / "js" / "render.js",
    ROOT / "app" / "pdf" / "labels.py",
    ROOT / "app" / "web" / "content" / "rashi_mr.py",
    ROOT / "app" / "web" / "content" / "mr.py",
)
# Marathi runs together with Hindi in these files, so only the lines that are unmistakably Marathi are read:
# `किंवा`, `स्थानी`, `राशीत`, `तूळ` and `मंगळ` do not occur in the Hindi copy.
MARATHI_MARKERS = ("किंवा", "स्थानी", "राशीत", "तूळ", "मंगळ", "राशिभविष्य", "असणे")


def test_no_marathi_sentence_spells_the_ninth_rashi_the_hindi_way():
    offenders = []
    for path in MARATHI_PROSE:
        if not path.exists():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if line.lstrip().startswith(("#", "//", "*")):
                continue                      # a comment may discuss the wrong spelling; prose may not
            if any(marker in line for marker in MARATHI_MARKERS) and re.search(r"धनु(?!ष)", line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:70]}")
    assert not offenders, "Marathi prose spelling the ninth rashi the Hindi way:\n  " + "\n  ".join(offenders)
