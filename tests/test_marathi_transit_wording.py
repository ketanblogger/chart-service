"""Why Devanagari drafts are rejected for `sign` and `house` many times more often than English ones.

THE NUMBERS THAT STARTED THIS: 134 Marathi `sign` rejections against 5 English, and 26 Marathi `house`
against 5. The obvious suspect was the checker - a Marathi phrasing it does not recognise - and the
standing rule is that the checker never gets looser, so the first job was to find out whether it is
actually asymmetric before touching anything.

IT IS NOT. Equivalent English and Marathi sentences are treated identically: the bare form fails in both,
and every legitimate transit marker passes in both. That is measured below rather than asserted, and it is
measured in BOTH directions - a guard that only checked that correct Marathi passes would also pass if the
checker had stopped checking Marathi altogether.

SO THE CAUSE IS LINGUISTIC, not a bug. "शनी मीन राशीत आहे" is the natural, unmarked Marathi for a position,
while English's natural phrasing for a moving body already contains its verb: "Shani moves into Meena".
English gets the transit cue for free; Marathi has to add it deliberately. The fix is in the prompt - the
passing forms are given as patterns to use rather than as a rule not to break - and these tests hold the
diagnosis in place so the next person does not start by loosening the checker.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.ai import validator

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "kundali_book_mr.json"


@pytest.fixture(scope="module")
def facts():
    return validator.collect_facts(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _transit_only_sign(facts) -> tuple[str, str, str]:
    """A graha the data has in a sign ONLY as a transit, with that sign's names. That is the case the whole
    natal/transit distinction is about; a sign the graha also occupies natally would pass either way and
    prove nothing."""
    from app.engine.constants import sign_info

    for graha in ("Saturn", "Jupiter", "Mars"):
        natal = facts.natal_signs.get(graha) or set()
        for index in sorted(getattr(facts, "graha_signs", {}).get(graha, set())):
            if index not in natal:
                sign = sign_info(index - 1)
                return graha, sign["name"], sign["devanagari"]
    raise AssertionError("the fixture has no transit-only sign; this test needs one")


#: Each case: the sentence, and whether the checker should accept it. The bare locative must be REFUSED in
#: both languages - that is the check doing its job - and every marked form must be accepted in both.
def _cases(graha_latin: str, sign_latin: str, sign_deva: str):
    return [
        # English
        ("en", False, f"{graha_latin} is in {sign_latin} rashi."),
        ("en", True, f"{graha_latin} moves into {sign_latin} rashi."),
        ("en", True, f"{graha_latin} is currently in {sign_latin} rashi."),
        ("en", True, f"{graha_latin} is in {sign_latin} rashi from 16 November."),
        # Marathi and Hindi, the same four claims
        ("mr", False, f"शनी {sign_deva} राशीत आहे."),
        ("mr", True, f"शनी {sign_deva} राशीत प्रवेश करतो."),
        ("mr", True, f"सध्या शनी {sign_deva} राशीत आहे."),
        ("mr", True, f"१६ नोव्हेंबरपासून शनी {sign_deva} राशीत आहे."),
        ("mr", True, f"गोचरात शनी {sign_deva} राशीत आहे."),
        ("mr", True, f"शनी {sign_deva} राशीत भ्रमण करत आहे."),
    ]


def test_the_checker_treats_the_two_languages_the_same(facts):
    """The whole diagnosis, in one assertion. If this ever fails, the asymmetry IS in the checker and the
    prompt is not the place to look."""
    graha, sign_latin, sign_deva = _transit_only_sign(facts)
    wrong = []
    for lang, should_pass, text in _cases("Shani", sign_latin, sign_deva):
        passed = not validator.check_text(text, facts)
        if passed is not should_pass:
            wrong.append(f"{lang}: expected {'pass' if should_pass else 'FAIL'}, got "
                         f"{'pass' if passed else 'FAIL'} - {text}")
    assert not wrong, "the checker is not symmetric across languages:\n    " + "\n    ".join(wrong)


def test_the_bare_locative_is_still_refused_in_both_languages(facts):
    """THE OTHER DIRECTION. A test that only checked that marked Marathi passes would stay green if the
    checker stopped looking at Marathi at all - which is the one change this diagnosis must never be used
    to justify."""
    graha, sign_latin, sign_deva = _transit_only_sign(facts)
    for text in (f"Shani is in {sign_latin} rashi.", f"शनी {sign_deva} राशीत आहे.",
                 f"शनि {sign_deva} राशि में है."):
        issues = validator.check_text(text, facts)
        assert any(issue.kind == "sign" for issue in issues), f"no longer refused: {text}"


def test_the_prompt_gives_the_passing_forms_as_patterns(facts):
    """The rule was already explained in prose, and the drafts still failed. What is new is that the
    passing shapes are spelled out to be copied, in the per-language block where the other Marathi
    corrections live - and in BOTH prompts, because the rashifal pages are checked by the same validator
    as the books."""
    import inspect

    from app.ai import prompts

    source = inspect.getsource(prompts)
    assert source.count("THE LOCATIVE IS THE TRAP") == 2, source.count("THE LOCATIVE IS THE TRAP")
    for pattern in ("पासून", "प्रवेश करतो", "सध्या", "गोचरात"):
        assert pattern in source, pattern


def test_the_prompt_still_forbids_dating_a_natal_placement(facts):
    """The patterns must not be read as "always add a date". A birth chart is one instant; a natal
    placement with प्रवेश in it is a new false sentence, and the instruction says so."""
    import inspect

    from app.ai import prompts

    source = inspect.getsource(prompts)
    assert "must not carry them" in source


def test_a_natal_placement_passes_bare_and_needs_no_marker(facts):
    """The counterpart in behaviour: where the bare locative is correct, it is accepted."""
    from app.engine.constants import sign_info

    for graha, signs in facts.natal_signs.items():
        if not signs:
            continue
        sign = sign_info(sorted(signs)[0] - 1)
        text = f"{graha} is in {sign['name']} rashi."
        assert not [i for i in validator.check_text(text, facts) if i.kind == "sign"], text
        return
    raise AssertionError("the fixture has no natal sign to check")


# ---- the other measured cause: Hindi words in a Marathi draft ----------------------------------------

def test_a_hindi_word_in_marathi_is_told_which_marathi_word_belongs_there():
    """THE COMMONEST MARATHI REJECTION in the stored runs - 18 of them, every one the word यह - and the
    message said only "write Marathi". That names the fault and not the fix, and a retry handed a category
    rather than a word writes something else wrong, pays for a second call and can fail again.

    The neighbouring wrong-words check has always named the replacement. This one now does too."""
    from app.ai import language

    findings = language.language_findings("हे फल यह महिना चांगला आहे.", "mr")
    assert findings, "a Hindi word in Marathi must still be refused"
    message = findings[0][0]
    assert "यह" in message and "हे" in message, message


def test_every_blocked_hindi_word_has_a_marathi_replacement():
    """A word in the block list with no replacement would print an empty quote at the reader's expense,
    and the mapping is what makes the message actionable - so the two cannot drift apart."""
    from app.ai.language import _HINDI_TO_MARATHI

    assert _HINDI_TO_MARATHI, "the mapping is empty"
    for hindi, marathi in _HINDI_TO_MARATHI.items():
        assert hindi and marathi and hindi != marathi, (hindi, marathi)


def test_correct_marathi_is_not_refused_by_that_check():
    """The other direction: the check must not fire on Marathi that is already right."""
    from app.ai import language

    assert not language.language_findings("हे चांगले आहे आणि पुढे जाईल.", "mr")
