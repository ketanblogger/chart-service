"""Numerology in the consultation, and the proof that the chart chat is unchanged.

THE CHART CHAT IS A LIVE PAID FEATURE and its system prompt is the cached prefix of every
conversation on this site. Adding numerology to it would be a bad trade at any price, so the numbers
are APPENDED as a fourth block and only for a chat that asked for them: a chat that did not gets
exactly the three parts it always got, in the same order, byte for byte. Most of this file asserts
that rather than the new feature.

NOTHING IS CARRIED THROUGH SIGN-IN. The numbers are recomputed from the same birth date the chart is
built from, so there is one implementation of the arithmetic and the chat cannot drift from the
calculator.

Invented people only; `tests/` is published.
"""

import datetime as dt

import pytest

from app.ai import chat_prompts
from app.numerology import core

BIRTH = {"date": "1991-04-03", "time": "06:12:00", "lat": 19.9975, "lon": 73.7898,
         "timezone": "Asia/Kolkata", "city": "Nashik"}
AS_OF = dt.date(2026, 10, 25)
CONTEXT = {"as_of": "2026-10-25", "chart": {"lagna": "Mesha"}}


# ---- the chart chat is untouched -------------------------------------------------------------------


def test_a_chat_without_numbers_has_the_three_parts_it_always_had():
    parts = chat_prompts.build_system(CONTEXT, "en")
    assert len(parts) == 3


def test_every_existing_part_is_byte_identical_when_numbers_are_added():
    """THE ASSERTION THIS FILE EXISTS FOR. The system prompt and the chart block are the cached
    prefix of every paid conversation; moving either by one character would invalidate all of them."""
    plain = chat_prompts.build_system(CONTEXT, "en")
    with_numbers = chat_prompts.build_system({**CONTEXT, "numerology": {"mulank": 3}}, "en")
    assert plain[0]["text"] == with_numbers[0]["text"], "the system prompt moved"
    assert plain[1]["text"] == with_numbers[1]["text"], "the chart block moved"
    assert plain[-1]["text"] == with_numbers[-1]["text"], "the style line moved"
    assert len(with_numbers) == len(plain) + 1


def test_the_numbers_are_not_inside_the_chart_block():
    """They are stored on the session context so one row holds everything, but <chart_data> is the
    chart. Leaving them in would put them in the prompt twice and change the cached chart block."""
    parts = chat_prompts.build_system({**CONTEXT, "numerology": {"mulank": 3}}, "en")
    assert "mulank" not in parts[1]["text"]
    assert parts[1]["text"].startswith("<chart_data>")


def test_the_numbers_appear_exactly_once():
    """Once, in their own block. The rules talk about numbers in general and name none of them, so
    a count of one is the whole prompt mentioning this reader's mulank a single time."""
    parts = chat_prompts.build_system({**CONTEXT, "numerology": {"mulank": 3}}, "en")
    assert sum(part["text"].count("mulank") for part in parts) == 1


def test_a_chat_without_numbers_never_sees_the_numerology_rules():
    parts = chat_prompts.build_system(CONTEXT, "en")
    joined = " ".join(part["text"] for part in parts)
    assert "Chaldean" not in joined
    assert "<numerology>" not in joined


# ---- what the model is told ---------------------------------------------------------------------------


def test_the_rules_forbid_recomputing_the_numbers():
    """The numbers are ours. A model that adds them up again is a second implementation nobody
    tested, and it will disagree with the calculator on the page the reader just used."""
    rules = chat_prompts.NUMEROLOGY_RULES
    assert "do not recompute" in rules.lower() or "not recompute" in rules.lower()
    assert "COMPUTED" in rules or "computed" in rules


@pytest.mark.parametrize("forbidden", ["unlucky", "bad", "weak", "dosh", "problem"])
def test_the_rules_name_every_word_the_model_may_not_use(forbidden):
    assert forbidden in chat_prompts.NUMEROLOGY_RULES.lower()


def test_the_rules_forbid_telling_anybody_to_change_a_number_or_a_name():
    rules = chat_prompts.NUMEROLOGY_RULES.lower()
    assert "change their name" in rules
    assert "phone number" in rules and "house" in rules


def test_the_rules_allow_only_the_three_levels():
    rules = chat_prompts.NUMEROLOGY_RULES.lower()
    assert "strong match" in rules and "good match" in rules and "neutral" in rules
    assert "no fourth" in rules


def test_the_rules_are_chaldean_only():
    assert "CHALDEAN" in chat_prompts.NUMEROLOGY_RULES
    assert "Pythagorean" in chat_prompts.NUMEROLOGY_RULES  # named so it can be forbidden


def test_the_rules_allow_no_outside_seller_and_only_our_own_report():
    rules = chat_prompts.NUMEROLOGY_RULES.lower()
    assert "outside numerologists" in rules or "outside" in rules
    assert "guarantee" in rules


# ---- the numbers themselves ----------------------------------------------------------------------------


def test_the_block_carries_the_numbers_the_calculator_shows():
    """One implementation, so the chat and the page cannot disagree. Worked by hand in
    tests/test_numerology_core.py: 3 April 1991 is mulank 3, bhagyank 9; KESHAV is 22 -> 4."""
    block = core.for_chat(dt.date(1991, 4, 3), "Keshav")
    assert block["mulank"] == 3 and block["bhagyank"] == 9
    assert block["name_number"] == 4 and block["name_number_total"] == 22
    assert block["system"] == "Chaldean"


def test_the_readers_name_is_never_in_the_block():
    """The chat has always treated a name as display-only and never sent it to the model. A name
    number does not need the name - it needs the number the name adds up to."""
    import json

    block = core.for_chat(dt.date(1991, 4, 3), "Keshav")
    assert "Keshav" not in json.dumps(block)
    assert "keshav" not in json.dumps(block).lower()


def test_a_name_that_cannot_be_read_simply_has_no_name_number():
    block = core.for_chat(dt.date(1991, 4, 3), "केशव")
    assert "name_number" not in block
    assert block["mulank"] == 3, "the date still works"


def test_no_name_at_all_still_gives_the_date_numbers():
    block = core.for_chat(dt.date(1991, 4, 3))
    assert block["mulank"] == 3 and block["bhagyank"] == 9
    assert "name_number" not in block


def test_the_session_adds_numbers_only_when_asked():
    from app.ai.chat import _session_data

    plain, _, _ = _session_data(BIRTH, AS_OF)
    with_numbers, _, _ = _session_data(BIRTH, AS_OF, numerology_for="Keshav")
    assert "numerology" not in plain
    assert with_numbers["numerology"]["mulank"] == 3
    assert {k: v for k, v in with_numbers.items() if k != "numerology"} == plain


def test_the_request_defaults_to_no_numerology():
    """A chat that does not ask for it is exactly the chat it was before numerology existed."""
    from app.ai.chat_routes import StartRequest

    assert StartRequest.model_fields["numerology"].default is False
