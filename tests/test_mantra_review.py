"""The review sheet: what counts as a verse, what counts as agreement, and what gets asked.

The texts here are invented fragments in Devanagari, not scripture, so a wrong assertion cannot
quietly teach the comparator to accept a wrong reading.
"""
from app.mantra import review


def test_a_line_without_a_danda_is_not_a_verse():
    """A DANDA IS THE DISCRIMINATOR. Devotional sites wrap the text in navigation, headings and
    promotional strips that are ALL in Devanagari, so "is it Devanagari" does not separate the
    recitation from the furniture. Before this, "प्रेरक कहानियाँ" - a menu item - was being
    compared against scripture as though it were a pada."""
    lines = [
        "प्रेरक कहानियाँ",                                   # a menu item, no danda
        "गूगल पर भक्ति भारत को अपना प्रीफ़र्ड सोर्स बनाएँ",   # a promotional strip
        "राम दूत अतुलित बल धामा ।",                          # a pada
        "अंजनि पुत्र पवनसुत नामा ॥",
    ]
    got = review.padas(lines, require_danda=True)
    assert got == ["राम दूत अतुलित बल धामा", "अंजनि पुत्र पवनसुत नामा"]
    # Without the flag a menu item survives, which is why an HTML source always passes it and a
    # wikitext poem block - where no line is punctuated - never does.
    assert "प्रेरक कहानियाँ" in review.padas(lines)[0]


def test_a_pada_is_split_on_the_danda_and_loses_its_number():
    lines = ["जय हनुमान ज्ञान गुन सागर । जय कपीस तिहुँ लोक उजागर ॥१॥"]
    got = review.padas(lines, require_danda=True)
    assert got == ["जय हनुमान ज्ञान गुन सागर", "जय कपीस तिहुँ लोक उजागर"]
    assert all("१" not in p and "1" not in p for p in got)


def test_typesetting_is_folded_but_a_different_letter_is_not():
    """रूपं and रूपम् are one word typeset twice, and compounding is a choice. A different
    CONSONANT is a different word in a text people say aloud, and must survive the folding - the
    Awadhi महाबीर against the Sanskritised महावीर is the decision this sheet exists to collect."""
    assert review.fold("निर्वाण रूपं") == review.fold("निर्वाणरूपम्")
    assert review.fold("जय हनुमान") == review.fold("जय  हनुमान")
    assert review.fold("महाबीर बिक्रम") != review.fold("महावीर विक्रम")
    assert review.fold("नमामिशमीशान") != review.fold("नमामीशमीशान")


def test_compare_marks_agreement_and_pairs_the_nearest_reading():
    a = ["राम दूत अतुलित बल धामा", "महाबीर बिक्रम बजरंगी", "एक पूरी तरह अलग पंक्ति यहाँ"]
    b = ["राम दूत अतुलित बल धामा", "महावीर विक्रम बजरंगी"]
    rows = review.compare(a, b)
    assert [r["state"] for r in rows] == ["agree", "differ", "differ"]
    # the differing pada is shown WITH the other source's reading, which is the point of the sheet
    assert rows[1]["b"] == "महावीर विक्रम बजरंगी"
    # ...and one with no comparable reading says so rather than pairing something unrelated
    assert rows[2]["b"] == ""


def test_the_summary_counts_what_the_sheet_claims():
    rows = review.compare(["अब यहाँ एक पंक्ति आती है", "दूसरी पंक्ति यहाँ पर आती"],
                          ["अब यहाँ एक पंक्ति आती है"])
    assert review.summary(rows) == {"padas": 2, "agree": 1, "differ": 1, "unmatched": 1}


def test_the_sheet_shows_both_readings_a_box_and_nothing_borrowed():
    """Only the verse text is in question. No meaning, translation or note is taken from either
    source, and the sheet must not imply otherwise."""
    rows = review.compare(["महाबीर बिक्रम बजरंगी"], ["महावीर विक्रम बजरंगी"])
    html = review.build_html(title="परीक्षण", slug="test", source_a="site-a.example",
                             source_b="site-b.example", rows=rows, css="")
    assert "महाबीर बिक्रम बजरंगी" in html and "महावीर विक्रम बजरंगी" in html
    assert "&#9744;" in html                       # a box to tick, twice: one per reading
    assert html.count("&#9744;") == 2
    assert "site-a.example" in html and "site-b.example" in html
    assert 'lang="hi"' in html
    # NOTHING BORROWED, checked as a property rather than by banning words: every run of Devanagari
    # on the sheet has to come from a reading or from the title. Banning the word "meaning" failed
    # on the sheet's own note explaining that meanings are not taken from either source - a comment
    # tripping the rule it explains, which this project has now done often enough to expect.
    import re

    allowed = {"महाबीर बिक्रम बजरंगी", "महावीर विक्रम बजरंगी", "परीक्षण"}
    found = {m.strip() for m in re.findall(r"[\u0900-\u097f][\u0900-\u097f\s]*", html)}
    stray = {f for f in found if f and f not in allowed}
    assert not stray, f"Devanagari on the sheet that came from neither source: {stray}"


def test_a_text_whose_sources_agree_says_so_rather_than_showing_an_empty_table():
    rows = review.compare(["राम दूत अतुलित बल धामा"], ["राम दूत अतुलित बल धामा"])
    html = review.build_html(title="t", slug="t", source_a="a", source_b="b", rows=rows, css="")
    assert "agree throughout" in html
