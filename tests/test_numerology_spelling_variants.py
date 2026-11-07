"""Spelling alternatives are computed, not written.

The first real numerology report PROMISED alternatives and gave none - it said only that "adding or
removing a letter can make 1, 6 or 5", which describes the exercise instead of doing it. A model
asked to do this will also, sooner or later, mis-add a total, and the one number on the page a
reader can check for themselves is exactly the one that must never be wrong.

EVERY NAME HERE IS INVENTED. The reported example was the proprietor's own name; it is not in this
file, in any fixture, or in any commit. The arithmetic is the same arithmetic whoever it is applied
to, so the tests use people who do not exist.
"""
import datetime as dt
import re

import pytest

from app.numerology import core

NAME = "Asha Vernekar"
INVENTED = (NAME, "Devdatta Rane", "Suresh Kulkarni", "Priya Shah")


def test_the_table_adds_up_the_way_it_is_published():
    """The Chaldean values are on the calculator page for anybody to check, so a worked example is
    worth pinning: doubling a vowel adds that vowel's value again, and nothing else moves."""
    plain = core.name_number("ASHA VERNEKAR")
    doubled = core.name_number("AASHA VERNEKAR")
    assert doubled["total"] == plain["total"] + core._LETTER_VALUE["A"]


def test_every_variant_carries_its_own_correct_total():
    """THE POINT OF COMPUTING THEM. Each printed total must be the total of the printed spelling -
    exactly - because a reader can and will check one."""
    for name in INVENTED:
        result = core.spelling_variants(name)
        for entry in [result["current"], *result["variants"]]:
            recomputed = core.name_number(entry["spelling"])
            assert recomputed["total"] == entry["total"], entry
            assert recomputed["number"] == entry["number"], entry


def test_the_readers_own_spelling_is_included_and_marked():
    result = core.spelling_variants(NAME)
    assert result["current"]["spelling"] == NAME.upper()
    assert all(v["spelling"] != result["current"]["spelling"] for v in result["variants"])


def test_between_two_and_four_options_in_total():
    """Few enough to read; enough to show the number moves."""
    for name in INVENTED:
        result = core.spelling_variants(name)
        assert 1 <= len(result["variants"]) <= core.SPELLING_LIMIT - 1, name


def test_each_alternative_reaches_a_different_number():
    """An alternative with the same number tells the reader nothing new, and two with the same
    number tell them nothing twice."""
    result = core.spelling_variants(NAME)
    numbers = [v["number"] for v in result["variants"]]
    assert len(numbers) == len(set(numbers))
    assert result["current"]["number"] not in numbers


def test_a_name_with_no_natural_alternative_says_so():
    """A real answer, not a failure - and the brief tells the writer to say it plainly."""
    result = core.spelling_variants("Ee")
    assert result["usable"] is False and result["variants"] == []
    assert result["current"]["number"] == core.name_number("Ee")["number"]


def test_a_name_that_is_not_in_latin_letters_is_handled():
    """Devanagari has no Chaldean value, so there is nothing to respell."""
    result = core.spelling_variants("आशा")
    assert result["usable"] is False and result["variants"] == []


@pytest.mark.parametrize("name", INVENTED)
def test_no_variant_is_an_implausible_spelling(name):
    """S -> SH inside ASHA gives ASHHA, and E -> EE inside EE gives EEE. An "alternative spelling"
    nobody would ever write makes the whole list look automatic."""
    for entry in core.spelling_variants(name)["variants"]:
        word = entry["spelling"].replace(" ", "")
        assert "HH" not in word, entry
        assert not re.search(r"([A-Z])\1\1", word), entry


@pytest.mark.parametrize("name", INVENTED)
def test_the_word_count_never_changes(name):
    """A variant that merged or split the words would be a different name, not a different
    spelling of this one."""
    for entry in core.spelling_variants(name)["variants"]:
        assert len(entry["spelling"].split()) == len(name.split()), entry


def test_the_list_is_deterministic():
    """The same name always gives the same alternatives in the same order, so two readings of one
    report - or a re-render of an order - cannot disagree."""
    first = core.spelling_variants(NAME)
    for _ in range(3):
        assert core.spelling_variants(NAME) == first


# ---- what reaches the writer ---------------------------------------------------------------------

BORN = dt.date(1988, 3, 29)


def test_the_report_facts_carry_the_computed_list():
    facts = core.for_report(BORN, NAME)
    assert "name_spellings" in facts
    assert facts["name_spellings"]["current"]["spelling"] == NAME.upper()


def test_the_chat_facts_are_unchanged():
    """THE PAID ORDER'S ID DEPENDS ON THIS. The digest stored on an order is computed from exactly
    what for_chat returns, so a field added for the report must not appear here - it would change
    every future order's id and stop matching the ones already sold."""
    chat = core.for_chat(BORN, NAME)
    assert "name_spellings" not in chat
    # The grid joined the spellings as report-only data: both are derived from the inputs, and both
    # are excluded from the digest for the same reason.
    assert set(core.for_report(BORN, NAME)) - set(chat) == {"name_spellings", "lo_shu_grid"}


def test_the_digest_ignores_the_spellings_so_a_paid_order_keeps_its_id():
    """THE BUG THIS ALMOST SHIPPED. The report id is a hash of the facts, so adding the spellings to
    them changed it - and fulfilment refuses when the generated id differs from the purchased one.
    Every numerology order placed before the change would have stuck at "generated report id differs
    from the purchased", which is the outage we just finished fixing, caused by adding a field.

    The spellings are a pure function of the name and the date, so they identify nothing new and are
    excluded from the digest. for_chat and for_report must agree."""
    from app.ai.report import facts_digest

    assert facts_digest(core.for_chat(BORN, NAME)) == facts_digest(core.for_report(BORN, NAME))


def test_anything_derived_is_kept_out_of_the_digest():
    """The rule, not the instance: a derived fact changes with the code that derives it, and an id
    that moves when the code changes orphans reports people have paid for."""
    from app.ai.report import _DERIVED_FACTS, facts_digest

    assert "name_spellings" in _DERIVED_FACTS
    base = core.for_chat(BORN, NAME)
    assert facts_digest({**base, "name_spellings": {"anything": "at all"}}) == facts_digest(base)


def test_fulfilment_checks_the_digest_with_for_chat_and_writes_with_for_report():
    import inspect

    from app.payments import service

    source = inspect.getsource(service._numerology_facts)
    assert "facts_digest(core.for_chat(" in source
    assert "return core.for_report(" in source


def test_the_brief_tells_the_writer_to_use_the_list_and_not_to_add_up():
    from app.ai.products import PRODUCTS

    brief = dict(PRODUCTS["numerology-report"].sections)["name_spelling"]
    assert "name_spellings" in brief
    assert "add up letters yourself" in brief
    assert "usable" in brief, "it must say what to do when there is no alternative"
    assert "OFFERED, never prescribed" in brief
