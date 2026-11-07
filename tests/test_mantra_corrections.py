"""The correction engine: a correction never loses a pada unless it says so.

THIS IS THE TEST THE REVIEWER ASKED FOR, and it exists because a line of the Hanuman Ashtak was
lost to a correction meant only to remove a typo. The source printed

    मोह भयो यह संकट भारो I

with a Latin I where the danda belongs, and the correction dropped the whole pada to be rid of the
I - deleting a line of scripture with it. The output was one pada shorter and looked, from every
angle except a reader who knew the stanza, exactly like a correctly corrected text. It was caught by
a human reading against a printed book, which is the only thing that could have caught it, and the
accounting below is what makes it a test failure instead.
"""
import pytest

from app.mantra import corrections as C, texts as T


def test_a_set_that_shortens_a_pada_is_allowed_but_never_removes_it():
    out = C.apply(["एक दो तीन", "चार पाँच छह"], [C.setp(1, "एक")])
    assert out == ["एक", "चार पाँच छह"]


def test_a_correction_that_empties_a_pada_raises():
    """The old engine ended `for p in out if p.strip()`, so a correction that emptied a pada made it
    vanish with no drop recorded. That was the second silent path to losing a line."""
    with pytest.raises(ValueError, match="emptied pada"):
        C.apply(["एक दो तीन", "चार पाँच छह"], [C.setp(1, "   ")])
    with pytest.raises(ValueError, match="emptied pada"):
        C.apply(["एक दो तीन", "चार पाँच छह"], [C.fix(2, "चार पाँच छह", "")])


def test_a_drop_naming_a_pada_the_text_does_not_have_raises():
    """A no-op drop is a numbering mistake wearing a disguise: if one number is out of range, the
    others in the same list are suspect too. `drop(*range(5, 200))` on a 104-pada text hid behind
    this for a whole batch."""
    with pytest.raises(ValueError, match="names pada"):
        C.apply(["एक", "दो"], [C.drop(2, 5)])


def test_keep_first_says_the_intent_and_counts_exactly():
    out = C.apply(["एक", "दो", "तीन", "चार"], [C.keep_first(2)])
    assert out == ["एक", "दो"]


def test_the_accounting_is_padas_in_minus_dropped_plus_inserted():
    padas = ["एक", "दो", "तीन"]
    out = C.apply(padas, [C.drop(2), C.after(3, "चार", "पाँच")])
    assert len(out) == len(padas) - 1 + 2 == 4
    assert out == ["एक", "तीन", "चार", "पाँच"]


def test_fix_raises_when_its_target_string_is_absent():
    """A correction that matched nothing would leave the text looking corrected and not be."""
    with pytest.raises(ValueError, match="is not in"):
        C.apply(["एक दो तीन"], [C.fix(1, "चार", "पाँच")])


def test_fixp_is_numbered_by_pada_even_where_fix_is_numbered_by_difference_row():
    """On a two-source text every other op is numbered by its row in the differences table. Passing
    a pada number to fix() there edits whichever pada sits at that row, or raises. The Hanuman
    Chalisa's pada-88 correction is the case: row 88 of a twenty-row table does not exist."""
    padas = [f"pada {n}" for n in range(1, 20)]
    diff_index = [2, 5, 9]
    out = C.apply(padas, [C.fixp(12, "pada 12", "बारह")], diff_index=diff_index)
    assert out[11] == "बारह"
    with pytest.raises(IndexError):
        C.apply(padas, [C.fix(12, "pada 12", "बारह")], diff_index=diff_index)


# ---- the reviewer's final corrections, asserted on the built text ---------------------------------

@pytest.mark.parametrize("slug, pada, expected", [
    ("hanuman-chalisa", 88, "कीजै नाथ हृदय महँ डेरा"),
    ("aarti-kunj-bihari-ki", 20, "देवता दरसन को तरसै"),
    ("aarti-kunj-bihari-ki", 22, "बजे मुरचंग, मधुर मिरदंग, ग्वालिन संग"),
    ("hanuman-ashtak", 41, "रावन जुध अजान कियो तब,"),
    ("hanuman-ashtak", 44, "मोह भयो यह संकट भारो"),
])
def test_the_final_review_corrections_are_in_the_text(slug, pada, expected):
    verses = {int(v["n"]): v["text"] for v in T.verses(slug)}
    assert verses[pada] == expected


def test_the_duplicated_half_lines_are_gone_from_aarti_kunj_bihari():
    """The whole line was restored after pada 21, which left the source's two half-lines standing
    behind it. Keeping all three printed the same words twice."""
    verses = [v["text"] for v in T.verses("aarti-kunj-bihari-ki")]
    assert "बजे मुरचंग, मधुर मिरदंग, ग्वालिन संग" in verses
    assert "मधुर मिरदंग," not in verses
    assert "ग्वालिन संग," not in verses


def test_hanuman_ashtak_stanza_six_reads_exactly_as_the_book_does():
    verses = {int(v["n"]): v["text"] for v in T.verses("hanuman-ashtak")}
    assert [verses[n] for n in range(41, 49)] == [
        "रावन जुध अजान कियो तब,",
        "नाग कि फाँस सबै सिर डारो",
        "श्रीरघुनाथ समेत सबै दल,",
        "मोह भयो यह संकट भारो",
        "आनि खगेस तबै हनुमान जु,",
        "बंधन काटि सुत्रास निवारो",
        "को नहिं जानत है जग में कपि",
        "संकटमोचन नाम तिहारो",
    ]


def test_every_stanza_of_hanuman_ashtak_ends_with_the_refrain():
    """Eight stanzas, eight refrains. The source printed it once."""
    body = " ".join(v["text"] for v in T.verses("hanuman-ashtak"))
    assert body.count("संकटमोचन नाम तिहारो") == 8
    assert "I" not in body, "a Latin letter where a danda belongs"


def test_no_text_carries_a_latin_letter_run_inside_the_verse():
    """A Latin run in Devanagari verse is either a stray danda substitute or a source's own note.
    Both were found in this batch, and both are the kind of thing a reader notices and we do not."""
    import re

    for text in T.PHASE_1:
        for verse in T.verses(text.slug):
            assert not re.search(r"[A-Za-z]{2,}", verse["text"]), (text.slug, verse["n"],
                                                                   verse["text"])
