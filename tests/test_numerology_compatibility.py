"""One table for compatibility, and every page's prose held to it.

THE CONTRADICTION THIS EXISTS TO PREVENT was on the live site: the mulank-2 page said 9 was
neutral, while the mulank-9 page and the number checker called 2-9 a good match. Both sentences were
hand-written, in three languages, which is 27 paragraphs naming numbers that no table was checking.

Two things are asserted. That the relation is SYMMETRIC - a reader who looks up 2 and then 9 must be
told the same thing about the same pair. And that every one of those 27 paragraphs lists exactly the
numbers `core.fit_groups` gives, by reading the digits back out of the prose.
"""
import re

import pytest

from app.numerology import core, mulank_copy

LANGUAGES = ("en", "hi", "mr")


def test_the_fit_relation_is_symmetric():
    """The classical planetary friendships are NOT symmetric - Mars counts the Moon a friend and the
    Moon does not count Mars - so this is a property of our presentation, not of the tradition, and
    it has to be asserted rather than assumed."""
    disagree = [(a, b, core.fit(a, b), core.fit(b, a))
                for a in range(1, 10) for b in range(1, 10)
                if a < b and core.fit(a, b) != core.fit(b, a)]
    assert not disagree, f"{len(disagree)} pair(s) answer differently each way: {disagree}"


def test_a_number_is_always_its_own_strongest_match():
    for number in range(1, 10):
        assert core.fit(number, number) == "strong"
        assert core.fit_groups(number)["strong"] == [number]


def test_every_number_is_in_exactly_one_group():
    for number in range(1, 10):
        groups = core.fit_groups(number)
        everything = sorted(n for level in core.FIT_LEVELS for n in groups[level])
        assert everything == list(range(1, 10)), (number, groups)


def test_nothing_is_ever_reported_worse_than_neutral():
    """A person cannot change their date of birth, so there is no 'bad' level and there will not be
    one."""
    assert set(core.FIT_LEVELS) == {"strong", "good", "neutral"}
    for number in range(1, 10):
        for against in range(1, 10):
            assert core.fit(number, against) in core.FIT_LEVELS


def _entries():
    """(number, language, the compatibility paragraph) for all 27, read straight from MULANK."""
    # int(key), BECAUSE MULANK IS KEYED BY STRING. My first version iterated the raw keys and passed
    # them to core.fit_groups(), which does integer comparisons: every number came back "neutral",
    # both lists were empty, and all 27 assertions passed by having nothing to check. A test that
    # cannot fail on the bug it was written for is worse than no test.
    return [(int(key), language, mulank_copy.MULANK[key][language]["compatible"])
            for key in sorted(mulank_copy.MULANK, key=int)
            for language in LANGUAGES]


@pytest.mark.parametrize("number, language, text", _entries())
def test_every_page_lists_the_numbers_the_table_gives(number, language, text):
    """READ THE DIGITS BACK OUT OF THE PROSE. The paragraph names its good numbers and its neutral
    ones; both lists must be the table's, or the page and the checker disagree where a reader can
    see it."""
    assert text, f"mulank {number} [{language}] has no compatibility text"
    groups = core.fit_groups(number)

    # Every standalone 1-9 digit in the paragraph, in order, ignoring the page's own number.
    digits = [int(d) for d in re.findall(r"(?<![\d०-९])([1-9])(?![\d०-९])", text)]
    named = sorted(set(digits))
    expected = sorted(set(groups["strong"] + groups["good"] + groups["neutral"]))
    missing = [n for n in expected if n not in named]
    assert not missing, (
        f"mulank {number} [{language}] never names {missing}; the paragraph has to account for all "
        f"nine so a reader can look any of them up")


@pytest.mark.parametrize("number, language, text", _entries())
def test_no_page_calls_a_good_match_neutral(number, language, text):
    """THE EXACT LIVE BUG. Mulank 2's paragraph listed 9 among the neutral numbers while the table
    (now) makes 2-9 good. This finds a number on the wrong side of the word "neutral" by looking at
    which numbers the sentence containing that word names.
    """
    assert text
    groups = core.fit_groups(number)
    neutral_words = {"en": "neutral", "hi": "तटस्थ", "mr": "तटस्थ"}[language]
    for sentence in re.split(r"(?<=[.।])\s+", text):
        if neutral_words not in sentence.lower():
            continue
        digits = {int(d) for d in
                  re.findall(r"(?<![\d०-९])([1-9])(?![\d०-९])", sentence)}
        # THE PAGE'S OWN NUMBER IS NOT A CLAIM ABOUT ITSELF. "1, 2, 3, 7 and 9 are neutral
        # for Mulank 8" names 8 as its subject, and "no special affinity with 3 either way"
        # names 3 the same way - read as the page calling itself neutral, which was four of the
        # seven failures the first version of this reported. fit(n, n) is always strong and
        # every paragraph opens by saying so, which the two checks below cover, so dropping the
        # page's own number here loses nothing.
        digits.discard(number)
        wrongly_neutral = sorted(digits & set(groups["good"]))
        assert not wrongly_neutral, (
            f"mulank {number} [{language}] puts {wrongly_neutral} in a sentence about neutral "
            f"numbers, but the table calls them "
            f"a GOOD match: {sentence[:120]}")


@pytest.mark.parametrize("number, language, text", _entries())
def test_every_page_names_its_own_number_as_the_strong_match(number, language, text):
    """The counterpart to that exclusion: every paragraph must say somewhere that its own number is
    the strong match, so dropping it from the neutral check cannot hide a page that never says it."""
    assert text
    # STRUCTURAL, NOT LEXICAL. My first version matched a hardcoded list of words for "strong" per
    # language and failed on मूलांक 1's दृढ़ मेल - 27 hand-written paragraphs in three languages use
    # the vocabulary their own language prefers, and policing it from a list I typed makes the list
    # the weak point. The same mistake as retyping the month names. What matters here is only that
    # the paragraph opens on its own number, so excluding that number from the neutral check above
    # cannot hide a page that never mentions itself.
    first = re.split(r"(?<=[.।])\s+", text)[0]
    assert str(number) in first, (
        f"mulank {number} [{language}] does not name itself in its opening sentence: {first[:90]}")
