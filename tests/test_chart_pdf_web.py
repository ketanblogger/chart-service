"""The free Basic Chart PDF button, as the page serves it (the download itself is app/pdf's; this is the web side).

The block is server-rendered rather than drawn by render.js for one reason: its blurb quotes both paid tier prices,
and a price is never typed into copy or into JavaScript - it comes from app/payments/catalogue.py at request time.
So the test that matters most here is the one that moves the catalogue and watches the page move with it.

The refusal paths (429 rate limit, 503 busy/unavailable, a dead connection) are wording, not logic, on this side:
every one of them has to leave the reader with the chart they already have. India's mobile carriers run
large-scale CGNAT, so the hourly limit lands on ordinary visitors who did nothing wrong - the note must read like
a note, and must never be the server's English sentence leaking into a Hindi page.
"""

import re

import pytest

from app.payments import catalogue
from app.web import STATIC_DIR, i18n, pages
from tests.test_trust_copy import AI, ENGINE
from tests.test_web import client

DOWNLOAD_KEYS = ("download_button", "download_text", "download_working",
                 "download_busy", "download_limit", "download_failed")
NOTE_KEYS = ("download_busy", "download_limit", "download_failed")


def _block(html: str) -> str:
    assert 'class="chart-download"' in html, "the free chart PDF block is not on the page"
    return html.split('class="chart-download"', 1)[1].split("</div>", 1)[0]


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_kundali_page_offers_the_free_chart_pdf(lang):
    html = client.get(i18n.url_for("kundali", lang)).text
    block = _block(html)
    copy = pages.get("kundali", lang)
    assert copy.extra["download_button"] in block
    assert copy.extra["download_text"] in block
    # the button lives inside the result section, so it appears with the chart and not before it
    assert html.index('id="result"') < html.index('class="chart-download"') < html.index('id="cta"')


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_only_the_kundali_page_offers_it(lang):
    """Every other tool page renders the same template; none of them draws a chart, so none of them offers a
    chart PDF. This is the assertion that fails if the block is ever hoisted out of its `page_key` guard."""
    for key in i18n.TOOL_KEYS:
        html = client.get(i18n.url_for(key, lang)).text
        assert ('class="chart-download"' in html) == (key == "kundali"), (key, lang)
    assert 'class="chart-download"' not in client.get(i18n.url_for("consultation", lang)).text


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_every_string_the_button_needs_exists_and_is_that_language(lang):
    copy = pages.get("kundali", lang)
    for key in DOWNLOAD_KEYS:
        assert copy.extra.get(key), f"{key} missing from {lang}"
    assert len({copy.extra[key] for key in NOTE_KEYS}) == 3, "the three refusals say the same thing"
    if lang != "en":
        for key in DOWNLOAD_KEYS:
            assert re.search(r"[ऀ-ॿ]", copy.extra[key]), f"{lang} {key} is not written in its own script"


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_a_refusal_points_back_at_the_chart_that_is_already_free(lang):
    """All three notes must offer the reader something, not just report a failure. The free chart is the
    something: it is on the page already and no limit applies to reading it."""
    copy = pages.get("kundali", lang)
    free_word = {"en": "free", "hi": "मुफ़्त", "mr": "मोफत"}[lang]
    for key in NOTE_KEYS:
        assert free_word in copy.extra[key], f"{lang} {key} does not point at the free chart: {copy.extra[key]!r}"
    # ... and the wording is the page's own, so the server's English `detail.message` is never shown as-is.
    block = _block(client.get(i18n.url_for("kundali", lang)).text)
    for attribute in ("data-busy", "data-limit", "data-failed"):
        assert attribute in block, f"{attribute} is not rendered for the browser to use"


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_blurb_prices_come_from_the_catalogue(lang, monkeypatch):
    """Move the catalogue and the page moves with it. A number typed into the copy would survive this."""
    raw = pages.raw("kundali", lang).extra["download_text"]
    assert "{price_kundali_simple}" in raw and "{price_kundali}" in raw
    assert not re.search(r"₹\s*\d", raw), "a rupee amount is written into the copy"

    real = catalogue.prices_inr()
    bumped = {product: amount + 7 for product, amount in real.items()}
    monkeypatch.setattr(catalogue, "prices_inr", lambda: bumped)
    block = _block(client.get(i18n.url_for("kundali", lang)).text)
    for product in ("kundali-report-simple", "kundali-report"):
        assert f"₹{bumped[product]}" in block, (lang, product)
        assert f"₹{real[product]}" not in block, (lang, product)


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_blurb_keeps_the_trust_rule_in_one_clause(lang):
    """The engine-beside-AI rule is satisfied section-wide by tests/test_trust_copy.py, but this sentence is the one
    place on the site that says "no AI" out loud - so here the engine is named in the same sentence, not merely
    the same section, and a later edit that splits them fails."""
    text = pages.get("kundali", lang).extra["download_text"]
    sentences = [part for part in re.split(r"(?<=[.।])\s+", text) if AI.search(part)]
    assert sentences, f"{lang}: the blurb no longer mentions AI at all - is it still saying what this is not?"
    for sentence in sentences:
        assert ENGINE.search(sentence), f"{lang}: 'AI' without the engine in the same sentence: {sentence!r}"


def test_the_download_is_wired_to_the_free_endpoint_and_handles_every_refusal():
    """The one thing in app.js worth pinning: a POST cannot be a plain link, so the file arrives as a blob and
    is saved through a temporary <a download>. If that turns back into an <a href>, the download breaks."""
    js = (STATIC_DIR / "js" / "app.js").read_text(encoding="utf-8")
    assert '"/api/chart/pdf"' in js
    assert "createObjectURL" in js and 'link.download = filename' in js
    assert "revokeObjectURL" in js, "the blob URL is never released"
    # The refusal table, so each HTTP status is mapped to a note rather than buried in a ternary.
    table = re.search(r"var NOTE_FOR_STATUS = \{([^}]*)\}", js)
    assert table, "NOTE_FOR_STATUS is gone - how does a refusal choose its wording now?"
    assert dict(re.findall(r"(\d+):\s*\"(\w+)\"", table.group(1))) == {"429": "limit", "503": "busy"}
    assert '|| "failed"' in js, "a status with no entry must still say something"
