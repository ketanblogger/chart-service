"""A numerology PDF never claims to be a chart reading.

The first real numerology report told its buyer, on the cover, that the interpretation was "केवळ याच
कुंडलीवर आधारित", and on the last page that it was a विवेचन of their जन्मकुंडली with "सर्व ग्रहस्थिती
... स्विस एफेमेरिस (लाहिरी अयनांश)" and "निरयन राशिचक्र, संपूर्ण-रास स्थानपद्धत, मध्यम राहू/केतू".

None of that is true of a document that is arithmetic over a name and a date. It was not one slip:
the running head, the cover tagline, the cover note, the provenance box, the "AI explains the chart"
line and the disclaimer were SIX pieces of chart boilerplate, each keyed on the product for the
muhurta report and each missed for this one.

THE WORDS ARE NOT BANNED OUTRIGHT. "No birth chart is cast and no birth time or place is used" is
the most useful sentence on the page, and a word-ban would forbid it. The rule is that such a word
may appear only inside a denial.
"""
import re

import pytest

from app.ai.prompts import NUMEROLOGY_DISCLAIMERS
from app.pdf import labels as L

LANGS = ("en", "hi", "mr")

#: Words that assert a chart was cast or an ephemeris was used.
CLAIMS = ("birth chart", "kundali", "कुंडली", "पत्रिका", "ephemeris", "एफेमेरिस", "ayanamsa",
          "अयनांश", "राशिचक्र", "ग्रहस्थिती", "रास स्थानपद्धत", "राहू/केतू", "जन्मकुंडली")

#: What makes the same word honest instead: it is being denied.
DENIALS = ("no ", "not ", "नाही", "नहीं", "कोणतीही", "कोई")


def _only_denied(text: str) -> list[str]:
    """Claim words that appear OUTSIDE a denial. Empty is the passing answer."""
    offenders = []
    for word in CLAIMS:
        for match in re.finditer(re.escape(word), text, re.IGNORECASE):
            window = text[max(0, match.start() - 60):match.end() + 60].lower()
            if not any(deny in window for deny in DENIALS):
                offenders.append(f"{word!r} in ...{window.strip()[:70]}...")
    return offenders


@pytest.mark.parametrize("lang", LANGS)
def test_the_numerology_disclaimer_claims_no_chart(lang):
    assert not _only_denied(NUMEROLOGY_DISCLAIMERS[lang]), NUMEROLOGY_DISCLAIMERS[lang]


@pytest.mark.parametrize("lang", LANGS)
def test_the_numerology_disclaimer_is_not_the_chart_one(lang):
    from app.ai.prompts import DISCLAIMERS

    assert NUMEROLOGY_DISCLAIMERS[lang] != DISCLAIMERS[lang]
    assert len(NUMEROLOGY_DISCLAIMERS[lang]) > 80, "a disclaimer still has to say the usual things"


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("key", ["numerology_cover_note", "numerology_calc_note",
                                 "numerology_cover_tagline", "numerology_running_title",
                                 "trust_calc_numerology", "trust_ai_numerology"])
def test_every_numerology_label_exists_and_claims_no_chart(lang, key):
    """SIX LABELS, because six were wrong. Each is keyed on the product, and the muhurta report had
    already been special-cased in most of these places - numerology was missed in all of them."""
    text = L.FREE_T[lang][key] if key in L.FREE_T[lang] else None
    if text is None:
        text = L.BOOK_T[lang][key] if hasattr(L, "BOOK_T") and key in L.BOOK_T.get(lang, {}) else None
    assert text, f"{lang} has no {key}"
    assert not _only_denied(text), f"{lang} {key}: {text}"


@pytest.mark.parametrize("key", ["numerology_cover_note", "numerology_calc_note",
                                 "numerology_cover_tagline", "numerology_running_title"])
def test_each_label_differs_from_its_chart_version(key):
    """A numerology label that is a copy of the chart one has not been written yet."""
    chart_key = key.replace("numerology_", "")
    for lang in LANGS:
        if chart_key in L.FREE_T[lang] and key in L.FREE_T[lang]:
            assert L.FREE_T[lang][key] != L.FREE_T[lang][chart_key], f"{lang} {key}"


def test_the_renderer_keys_all_of_them_on_the_product():
    """One table rather than a chain of conditionals, because this is the fifth and sixth thing to
    be keyed on the product and the first four were each fixed on their own."""
    import inspect

    from app.pdf import render

    source = inspect.getsource(render)
    assert "_COVER_TAGLINES" in source and "_COVER_NOTES" in source
    assert '"numerology-report"' in source
    assert "numerology_calc_note" in source


def test_the_report_itself_picks_the_numerology_disclaimer():
    import inspect

    from app.ai import report

    source = inspect.getsource(report.generate_report)
    assert 'product.kind == "numerology"' in source
    assert "NUMEROLOGY_DISCLAIMERS" in source


@pytest.mark.parametrize("lang", LANGS)
def test_a_rendered_numerology_pdf_has_no_chart_claim(lang, tmp_path):
    """THE TEST THE PROPRIETOR ASKED FOR, on the real rendered document rather than on the labels.

    The report is a fixture - no AI call - but the PDF is rendered by the real renderer, so cover,
    running head, trust box, calc note and disclaimer are all exactly what a buyer would receive."""
    # pypdf, NOT pypdfium2. Both are installed, and mixing them in one process is what killed a
    # full suite run: a pypdfium2 document's finaliser fired during garbage collection in the
    # middle of a pypdf parse, and the C library aborted the interpreter - no failure, no summary,
    # just a dump at 60%. The rest of the suite reads PDFs with pypdf; this now does too.
    import io

    import pypdf

    from app.ai.prompts import NUMEROLOGY_DISCLAIMERS
    from app.pdf.service import ensure_pdf

    report = {
        "id": "a" * 32, "product": "numerology-report", "language": lang,
        "as_of": "2026-11-06", "title": "Numerology",
        "summary": "Mulank 2, bhagyank 4.",      # a string, as the generator produces
        "sections": [{"id": "your_numbers", "heading": "Numbers", "paragraphs": ["Mulank 2."]}],
        "disclaimer": NUMEROLOGY_DISCLAIMERS[lang], "meta": {"model": "fixture"},
    }
    pdf = ensure_pdf(report, {"self": "Asha Vernekar"})
    reader = pypdf.PdfReader(io.BytesIO(pdf.read_bytes()))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert text.strip(), "the PDF has no text at all"
    assert not _only_denied(text), f"{lang}: a numerology PDF claims a chart"
