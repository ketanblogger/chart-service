"""Does our written text borrow from the pages the verses came from.

THE RULE IS AN EIGHT-WORD RUN. Any eight consecutive words that appear in a source page appear in
ours by copying, not by coincidence - at that length the chance of two writers independently
producing the same sequence about the same subject is small enough to treat a hit as a finding and
look at it. Shorter runs are not evidence: "this mantra is recited on Tuesday" is six words long
and belongs to nobody.

WHAT IS COMPARED, AND WHAT IS NOT. Only OUR written part - the introduction, the meanings, the
notes on recitation, the FAQ - is checked. The verses themselves are the source's text by
definition and are excluded, or every page would fail on the thing it exists to print. So are the
text's own name and the deity's.

NORMALISED FIRST, because a copy with the punctuation changed is still a copy: case folded, Hindi
and Latin punctuation dropped, whitespace collapsed.
"""
from __future__ import annotations

import re
import unicodedata

RUN = 8

_DROP = re.compile(r"[।॥.,;:!?()\[\]{}\"'“”‘’…\-–—/|]+")


def words(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text).lower()
    return _DROP.sub(" ", text).split()


def runs(text: str, n: int = RUN) -> set[tuple]:
    tokens = words(text)
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def borrowed(ours: str, sources: list[str], *, n: int = RUN,
             verses: str = "") -> list[str]:
    """Every n-word run of ours that also appears in a source, as readable strings.

    `verses` is OUR OWN TEXT OF THE SCRIPTURE, and runs found in it are not borrowings. An
    explainer that discusses a refrain will quote the refrain, and the refrain is in the source
    page because the source page prints the same verse - that is the text itself travelling, not
    our prose copying theirs. Without this the check fires hardest on the pages that explain the
    verse most closely, which is exactly backwards.
    """
    theirs: set[tuple] = set()
    for source in sources:
        theirs |= runs(source, n)
    scripture = runs(verses, n) if verses else set()
    return sorted(" ".join(run) for run in (runs(ours, n) & theirs) - scripture)


def word_count(text: str) -> int:
    return len(words(text))
