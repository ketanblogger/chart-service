"""The remedy-linkage counter, and the thing that makes a counter worth trusting.

A COUNT OF ZERO AND A COUNTER THAT CANNOT MATCH LOOK IDENTICAL. This file's main job is to prove the
needle still matches what the checker actually writes - so that if somebody rewords the rule, the test
fails here rather than the report quietly saying "none" forever and the remedy work being closed on it.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.rashifal import generate

spec = importlib.util.spec_from_file_location("remedy_rejections", Path("scripts/remedy_rejections.py"))
counter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(counter)


def test_the_needle_matches_what_the_checker_writes():
    """The rule and the counter are in different files; this is the only thing holding them together."""
    page = {"headline": "A steady month", "summary": "Work steadies.",
            "sections": {"career_money": "Work steadies this month and a senior backs you."},
            "tip": "Chant the Hanuman Chalisa on Tuesday for Mangal."}
    problems = generate.style_problems(page, "en")
    assert problems, "the checker no longer refuses a tip whose graha the reading never discusses"
    assert any(counter.NEEDLE.search(problem) for problem in problems), \
        f"the counter would not recognise its own rule: {problems}"


def test_a_linked_remedy_is_not_counted():
    """A tip naming a graha the reading DOES discuss is the correct case and must not inflate the
    number somebody is about to make a decision on."""
    page = {"headline": "Mangal steadies", "summary": "Mangal steadies the month.",
            "sections": {"career_money": "Mangal moves through your tenth house and work steadies."},
            "tip": "Chant the Hanuman Chalisa on Tuesday for Mangal."}
    problems = generate.style_problems(page, "en")
    assert not any(counter.NEEDLE.search(problem) for problem in problems)


@pytest.mark.parametrize("run_id, expected", [
    ("f9579a9e-20260927T101553", "2026-09-27"),
    ("da669739-20261023T000501", "2026-10-23"),
])
def test_the_day_comes_from_the_run_id(run_id, expected):
    """The run id carries the moment the run started. Reading the day from it rather than from the
    file's mtime means a file copied or restored does not land on the wrong day."""
    assert counter.run_day(run_id, Path("scripts/remedy_rejections.py")) == expected


def test_a_run_id_with_no_stamp_says_where_the_day_came_from():
    """Rather than skipping the run silently, or presenting an mtime as though it were the run time."""
    day = counter.run_day("no-stamp-here", Path("scripts/remedy_rejections.py"))
    assert day.endswith("(mtime)")


def test_it_reads_and_writes_nothing():
    """It will be run on the production server against live run files."""
    source = Path("scripts/remedy_rejections.py").read_text(encoding="utf-8")
    for banned in ("write_text", "open(", "unlink", "rmtree", "db.transaction"):
        assert banned not in source.replace("path.read_text", "").replace("json.loads", ""), banned
