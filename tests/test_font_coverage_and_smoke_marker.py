"""Two small things that each cost an investigation.

ONE: a PDF that fell back to a system font logged "fallback fonts: FreeSerif, FreeSans" and nothing about
why. It happened twice in two days on the free chart sheet, and neither occurrence could be explained
afterwards - the PDF was not kept and nobody could name the character. The render has the text in hand, so
it can say exactly what no bundled font draws.

TWO: the System health page has always had a "last smoke check" panel, and it has always said that nothing
writes an artefact so nothing has timestamped it. The one place somebody looks to find out whether a
deploy was checked could not answer. The script knows its own result.
"""
from __future__ import annotations

import pytest


# ---- what the bundled fonts cannot draw --------------------------------------------------------------

def test_the_bundled_fonts_are_read_and_cover_the_scripts_we_publish_in():
    from app.pdf.browser import bundled_coverage

    covered = bundled_coverage()
    assert len(covered) > 2000, "the font coverage could not be read at all"
    for sample in ("Aa1", "आहे", "कुंडली", "₹", "°"):
        for char in sample:
            assert ord(char) in covered, f"{char!r} is not drawable by any bundled font"


@pytest.mark.parametrize("text, expected", [
    ("Asha Vernekar", []),
    ("तुमच्या कुंडलीत", []),
    ("Guru → 2030", ["→"]),
    ("ஆஷா", ["ஆ", "ஷ", "ா"]),
])
def test_it_names_exactly_what_cannot_be_drawn(text, expected):
    from app.pdf.browser import uncovered

    assert uncovered(text) == expected


def test_whitespace_is_not_a_finding():
    from app.pdf.browser import uncovered

    assert uncovered("a\n\tb  c") == []


def test_the_description_is_something_a_log_line_can_carry():
    from app.pdf.browser import describe_uncovered

    said = describe_uncovered("ஆ")
    assert "U+0B86" in said and "TAMIL" in said
    assert "\n" not in said, "a log line must stay one line"


def test_a_clean_document_describes_nothing():
    from app.pdf.browser import describe_uncovered

    assert describe_uncovered("Lagna Vrishchika 19°13'37\" - ₹119") == ""


# ---- the smoke check leaves its result ---------------------------------------------------------------

def _smoke_module():
    import importlib
    import sys
    from pathlib import Path

    scripts = str(Path(__file__).resolve().parents[1] / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return importlib.import_module("smoke_check")


def test_the_smoke_check_writes_a_marker_whatever_the_outcome(tmp_path, monkeypatch):
    """Written on failure too: a FAILED check that ran is a different thing from no check at all, and a
    marker that only appeared on success would make those two look the same."""
    smoke = _smoke_module()
    marker = tmp_path / "smoke-check.log"
    monkeypatch.setenv("ADMIN_SMOKE_MARKER", str(marker))
    smoke._write_marker("https://example.invalid", "2 failure(s), 1 warning(s), 0 skipped",
                        ["the first thing", "the second thing"], ["a warning"], [])
    written = marker.read_text(encoding="utf-8")
    assert "2 failure(s)" in written
    assert "FAIL: the first thing" in written and "warn: a warning" in written
    assert "https://example.invalid" in written


def test_system_health_reads_what_the_smoke_check_wrote(tmp_path, monkeypatch):
    """The two halves meeting: the panel that could never answer, answering."""
    smoke = _smoke_module()
    marker = tmp_path / "smoke-check.log"
    monkeypatch.setenv("ADMIN_SMOKE_MARKER", str(marker))
    smoke._write_marker("https://example.invalid", "0 failure(s), 0 warning(s), 0 skipped", [], [], [])
    from app.admin import health

    result = health.last_smoke_check()
    assert result["recorded"] is True and result.get("age")  # settings are read per call; nothing to clear


def test_the_panel_says_so_when_nothing_has_run(tmp_path, monkeypatch):
    """The honest answer when there is no marker - not a blank, and not a claim that all is well."""
    monkeypatch.setenv("ADMIN_SMOKE_MARKER", str(tmp_path / "never-written.log"))
    from app.admin import health

    result = health.last_smoke_check()
    assert result["recorded"] is False and result.get("note")  # settings are read per call; nothing to clear


def test_main_actually_calls_the_marker_writer():
    """THE GAP THIS FILLS. The tests above exercise `_write_marker` directly, so deleting the ONE call to
    it in `main()` left them all green - the helper worked perfectly and nothing used it. Checked by
    reading main's own syntax tree, because the alternative is running a whole smoke check in a unit test.
    """
    import ast
    import inspect

    smoke = _smoke_module()
    tree = ast.parse(inspect.getsource(smoke.main))
    called = {node.func.id for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "_write_marker" in called, "main() no longer records the result anywhere"
