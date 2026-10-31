"""The mantra registry: provenance, the release gate, and the texts themselves.

There are no mantra PAGES yet and these tests do not pretend otherwise. What is built is the
registry, the provenance record and the gate that decides whether a text may be seen - and the gate
is the part worth testing first, because it is what stops an unverified text reaching a reader.
"""
import datetime as dt
import re

import pytest

from app.mantra import texts as T

DEVA = re.compile(r"[ऀ-ॿ]")


def test_every_text_records_where_it_came_from():
    """PROVENANCE IS A FIELD, NOT A FOOTNOTE. A text on this site has to be able to say which
    edition it is, because a reader comparing it with their printed copy deserves an answer."""
    assert T.PHASE_1, "the registry is empty"
    for text in T.PHASE_1:
        assert text.sources, text.slug
        for source in text.sources:
            assert source.label and source.url.startswith("https://"), (text.slug, source)
        assert text.checked, f"{text.slug} does not say what comparing its sources found"
        assert text.author, text.slug


def test_a_text_with_one_source_can_never_be_live():
    """TWO INDEPENDENT SOURCES IS THE BAR. One source is a draft however clean it looks, and the
    gate reads the source count rather than relying on anybody remembering to hold it back."""
    for text in T.PHASE_1:
        if not T.is_verified(text):
            assert text.release is None, (
                f"{text.slug} has {len(text.sources)} source(s) and a release date")
            assert not T.is_live(text, dt.date(2099, 1, 1)), text.slug


def test_the_gate_is_a_pure_function_of_the_date():
    """No job, no row, no state to get out of step: before the date it is not there, on the date it
    is. The whole release mechanism is this function."""
    text = T.PHASE_1[0]
    scheduled = type(text)(**{**text.__dict__, "release": dt.date(2027, 3, 1)})
    assert not T.is_live(scheduled, dt.date(2027, 2, 28))
    assert T.is_live(scheduled, dt.date(2027, 3, 1))
    assert T.is_live(scheduled, dt.date(2027, 3, 2))
    assert not T.is_live(type(text)(**{**text.__dict__, "release": None}), dt.date(2099, 1, 1))


def test_only_a_verified_text_can_carry_a_release_date():
    """THE INVARIANT, now that the review round is done and dates are set.

    This test used to assert that nothing was scheduled at all, which was true of the batch before
    the texts had been read and is the weaker claim: it would have passed just as happily if the
    scheduling had been wrong in every other way. What has to hold from here on is that a date and
    a second check go together - a text nobody has verified cannot be given a date, and a text that
    has one is therefore always one that was checked twice.
    """
    for text in T.PHASE_1:
        if text.release is not None:
            assert T.is_verified(text), f"{text.slug} is scheduled but not verified"
    assert T.live(T.FIRST_RELEASE - dt.timedelta(days=1)) == (), "something is live too early"
    scheduled = [t for t in T.PHASE_1 if t.release]
    assert len(scheduled) == 20, f"{len(scheduled)} scheduled"
    assert [t.slug for t in T.PHASE_1 if not t.release] == [
        "vishnu-sahasranamam", "lalita-sahasranamam"]


def test_released_on_names_exactly_that_days_texts():
    """What IndexNow would be told about on a release morning."""
    day = dt.date(2027, 3, 1)
    assert T.released_on(day) == ()
    text = T.PHASE_1[0]
    scheduled = type(text)(**{**text.__dict__, "release": day})
    assert scheduled.release == day and T.is_live(scheduled, day)


@pytest.mark.parametrize("slug", [t.slug for t in T.PHASE_1])
def test_every_text_has_real_verses_in_devanagari(slug):
    verses = T.verses(slug)
    assert verses, slug
    for verse in verses:
        assert verse["n"], (slug, verse)
        assert len(DEVA.findall(verse["text"])) >= 8, (slug, verse["text"][:40])
    # Nothing a model wrote: markup and wiki syntax would be the fingerprint of a bad extraction.
    joined = " ".join(v["text"] for v in verses)
    for fingerprint in ("[[", "]]", "{{", "<br", "'''", "=="):
        assert fingerprint not in joined, (slug, fingerprint)


def test_the_unsourced_texts_are_recorded_as_such():
    """The gap is a fact in the code rather than a paragraph in a report nobody reads twice.

    The COUNT is not pinned - it falls as sources are found, and a test that pinned it would have to
    be edited every time the batch made progress, which is a test measuring the editor. What is
    pinned is the invariant: every one of the 24 is in exactly one of the two lists.
    """
    assert T.UNSOURCED, "nothing left unsourced - if that is true, say so deliberately"
    assert "sundarkand" in T.UNSOURCED
    assert not (set(T.UNSOURCED) & set(T.BY_SLUG)), "a text cannot be both sourced and unsourced"
    assert len(T.PHASE_1) + len(T.UNSOURCED) == 24
    assert len(set(T.UNSOURCED)) == len(T.UNSOURCED), "a slug is listed twice"


def test_the_sourcing_record_exists_and_says_the_number():
    from pathlib import Path

    doc = Path(__file__).resolve().parents[1] / "docs/MANTRA_SOURCING.md"
    assert doc.is_file()
    body = doc.read_text(encoding="utf-8")
    assert "Hanuman Chalisa" in body and "Valmiki" in body
    # The doc has to carry the CURRENT count, so the record and the code cannot drift apart.
    assert f"**{len(T.UNSOURCED)}**" in body, f"the doc does not state {len(T.UNSOURCED)} unsourced"
    assert f"**{sum(1 for t in T.PHASE_1 if T.is_verified(t))}**" in body
