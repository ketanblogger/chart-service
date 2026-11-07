"""A reply stays in one script, and that script is the one the reader wrote in.

THIS RULE ALREADY EXISTED when the proprietor reported seeing a romanised-Marathi reply mix scripts
mid-word and carry an Urdu letter. It went in on 2026-10-06 and is in the deployed tree, chat_style
.script_problems is a HARD check on both attempts, and its own docstring names the پ case. So these
tests are not a new rule - they pin the reported symptoms as cases, which is what the report is
actually worth: a bug nobody can reproduce from the code still deserves its examples written down.

If it happens again after this, the fault is NOT in these three checks and the next place to look is
the fallback and the canned replies, which do not pass through script_problems at all.
"""
import pytest

from app.ai import chat_style as cs


# ---- the script of a chat is the reader's own ----------------------------------------------------

@pytest.mark.parametrize("message, expected", [
    ("Maza mulank 2 ahe, career baddal sanga", "mr-Latn"),
    ("Mera mulank 2 hai, career ke baare mein bataiye", "hi-Latn"),
    ("माझा मूलांक 2 आहे", "mr"),
    ("मेरा मूलांक 2 है", "hi"),
    ("What does my mulank say about my career?", "en"),
])
def test_the_style_comes_from_what_the_reader_wrote(message, expected):
    """A reader who writes in Latin letters is answered in Latin letters. The style is settled from
    their FIRST message, which is what makes "the script the user wrote in" the rule rather than a
    guess from the page language."""
    assert cs.settle(message, default="en") == expected


# ---- the three faults, as reported ---------------------------------------------------------------

def test_an_arabic_or_urdu_letter_is_refused():
    """The exact case: پ in "ekapaठoپाठ". A letter from neither script is not a worse answer, it is
    an unreadable one."""
    problems = cs.script_problems("ekapaठoپाठ", "mr-Latn")
    assert problems
    assert any("another script entirely" in p for p in problems)
    assert any("پ" in p for p in problems), "the offending letter is not named back"


@pytest.mark.parametrize("word", ["sध्या", "vegळe", "usके"])
def test_one_word_holding_both_scripts_is_refused(word):
    """"sध्या", "vegळe", "usके" - every one seen live, each a Latin letter and a Devanagari
    letter inside a single word."""
    problems = cs.script_problems(f"Tumcha mulank 2 ahe, {word} changla kaal ahe", "mr-Latn")
    assert any("mixes Latin and Devanagari" in p for p in problems), word


def test_a_digit_with_devanagari_is_refused_by_the_style_rule_not_the_word_rule():
    """"8व्या" IS refused in a Latin conversation, but not as a mixed WORD: a digit is not a
    letter, so that word is pure Devanagari. The docstring in chat_style used to list it among the
    mixed words, which overstated what the word rule does - and my first version of this test
    believed the docstring rather than the code. In a Devanagari conversation it is simply right."""
    latin = cs.script_problems("Tumcha mulank 2 ahe, 8व्या changla kaal ahe", "mr-Latn")
    assert latin and any("Devanagari character" in p for p in latin)
    assert not any("mixes Latin and Devanagari" in p for p in latin)
    assert cs.script_problems("तुमच्या 8व्या स्थानात गुरू आहे", "mr") == []


def test_a_reply_in_the_other_script_is_refused():
    problems = cs.script_problems("तुमचा मूलांक 2 आहे, सध्या चांगला काळ आहे", "mr-Latn")
    assert any("Latin letters" in p for p in problems)


@pytest.mark.parametrize("style, reply", [
    ("mr-Latn", "Tumcha mulank 2 ahe, sadhya changla kaal ahe"),
    ("hi-Latn", "Aapka mulank 2 hai, abhi accha samay hai"),
    ("mr", "तुमचा मूलांक 2 आहे, सध्या चांगला काळ आहे"),
    ("hi", "आपका मूलांक 2 है, अभी अच्छा समय है"),
    ("en", "Your mulank is 2, and this is a steady stretch"),
])
def test_a_clean_reply_in_its_own_script_passes(style, reply):
    """The other half of the measurement. A rule that refuses good writing is a bill: every one of
    these is what the style asks for and must not be rejected."""
    assert cs.script_problems(reply, style) == []


def test_a_numerology_reply_is_held_to_the_same_rule():
    """The numerology consultation goes through the same reply loop, so it inherits this. Asserted
    because the path is new and "it inherits it" is the kind of thing that stops being true."""
    mixed = "Tumcha mulank 2 ahe ani bhagyank 4 आहे"
    assert cs.script_problems(mixed, "mr-Latn")


def test_the_check_is_hard_on_both_attempts():
    """It was soft once - "worth one regeneration, never worth withholding the answer" - and that is
    exactly how "Kundalit sध्या Chandra mahadasha" reached a paying customer: the second draft was
    delivered whether or not it was clean."""
    import pathlib

    source = (pathlib.Path(__file__).resolve().parents[1]
              / "app/ai/chat.py").read_text(encoding="utf-8")
    assert "problems = problems or chat_style.script_problems(reply_text, language)" in source
    # ...and that line must sit BEFORE the soft-problem branch, or it is soft again.
    hard = source.index("problems = problems or chat_style.script_problems")
    soft = source.index("problems = _soft_problems(")
    assert hard < soft, "the script check has drifted after the soft branch"
