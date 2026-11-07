"""The report card: primary, personalised, and carrying nothing in a URL.

Six changes, one card. The ones with teeth are the last two: a name and a date of birth must never
appear in a link again, and the card must not promise the report anything the report does not
contain.
"""
import datetime as dt
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.numerology import core
from app.numerology.copy import CARD, REPORT
from app.web import i18n

LANGS = ("en", "hi", "mr")
FORM = {"content-type": "application/x-www-form-urlencoded"}
ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _result(client, lang="en", body="name=Asha+Vernekar&day=29&month=3&year=1988"):
    return client.post(i18n.url_for("numerology", lang), content=body, headers=FORM).text


# ---- 6. nothing identifying in a URL --------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_no_link_on_a_numerology_page_carries_a_name_or_a_date(client, lang):
    """THE PRIVACY FIX. A name and a date of birth together identify somebody. In a URL they land in
    the access log of every hop, go to third parties in the Referer, stay in history, and are copied
    intact by anybody who shares the link. The comment that used to sit beside this code called it
    "nothing sensitive and nothing new" because the reader had typed it into a public calculator -
    which confuses what a reader gives one server with what a URL hands everybody."""
    pages = [_result(client, lang), client.get(i18n.url_for("mulank", lang, number=4)).text]
    for body in pages:
        for href in re.findall(r'href="([^"]*)"', body):
            assert not re.search(r"[?&](name|date|day|month|year)=", href), href


@pytest.mark.parametrize("lang", LANGS)
def test_the_report_cta_posts_its_fields(client, lang):
    body = _result(client, lang)
    form = re.search(r'<form class="report-card__form"[^>]*method="post"[^>]*action="([^"]+)"(.*?)</form>',
                     body, re.S)
    assert form, "the report CTA is not a form"
    assert "?" not in form.group(1), form.group(1)
    fields = dict(re.findall(r'name="(\w+)" value="([^"]*)"', form.group(2)))
    assert fields == {"name": "Asha Vernekar", "day": "29", "month": "3", "year": "1988"}


def test_the_posted_form_lands_on_a_filled_report_page(client):
    """The whole point: the reader does not type their name and birthday a second time, and it never
    appears in a URL on the way."""
    body = client.post("/numerology-report",
                       content="name=Asha+Vernekar&day=29&month=3&year=1988", headers=FORM).text
    assert 'value="Asha Vernekar"' in body
    assert '<option value="29" selected>' in body
    assert 'data-product="numerology-report"' in body
    assert 'class="num-error"' not in body


def test_the_chat_cta_carries_the_question_but_not_the_reader(client):
    """The chosen question is the reader's words about a topic and identifies nobody; a link to
    "ask about my career" is a reasonable thing to share. The name and date are not."""
    body = _result(client)
    # SCOPED TO THE CHIP LIST. My first version matched every <li><a> on the page and caught the
    # "back to the calculator" link, which is not a chip and carries nothing.
    strip = re.search(r'<ul class="ask-box__chips">(.*?)</ul>', body, re.S)
    assert strip, "the chip list is gone"
    chips = re.findall(r'<a href="([^"]+)"', strip.group(1))
    assert chips, "the chips are gone"
    for href in chips:
        assert "numerology=1" in href and "q=" in href
        assert "name=" not in href and "date=" not in href


def test_the_handover_script_uses_session_storage_and_scrubs_the_url():
    js = (ROOT / "app/static/js/numerology-handover.js").read_text(encoding="utf-8")
    # THE RULE MUST NOT TRIP ON THE COMMENT EXPLAINING IT: the file says "sessionStorage, NOT
    # localStorage" and the first version of this test failed on its own rationale. Assert the
    # CALL, not the word.
    assert "sessionStorage" in js
    assert "window.localStorage" not in js, (
        "a handover for one visit must not outlive the tab")
    assert "replaceState" in js
    for key in ("name", "date", "day", "month", "year"):
        assert f'"{key}"' in js, f"{key} is not scrubbed from the URL"


def test_the_calculator_publishes_the_subject_for_the_handover(client):
    body = _result(client)
    marker = re.search(r'<div id="numerology-subject"[^>]*>', body)
    assert marker and 'data-name="Asha Vernekar"' in marker.group(0)
    assert 'data-born="1988-03-29"' in marker.group(0)


# ---- 1 and 5. the report is the primary offer, the chat is below it -------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_the_report_card_comes_before_the_chat_card(client, lang):
    body = _result(client, lang)
    assert body.index('class="report-card"') < body.index('class="ask-box"')


@pytest.mark.parametrize("lang", LANGS)
def test_the_report_card_sits_under_the_grid_it_talks_about(client, lang):
    body = _result(client, lang)
    assert body.index("lo-shu") < body.index('class="report-card"')


@pytest.mark.parametrize("lang", LANGS)
def test_the_mulank_pages_put_the_report_first_too(client, lang):
    body = client.get(i18n.url_for("mulank", lang, number=7)).text
    assert body.index('class="report-card"') < body.index('class="ask-box"')


def test_the_chat_card_is_still_there(client):
    """Secondary, not removed. Somebody who did not want the report is offered the conversation."""
    body = _result(client)
    assert 'class="ask-box"' in body and "ask-box__chips" in body


# ---- 2. the card speaks about this reader's own grid ---------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_the_card_reads_this_readers_grid_back_to_them(client, lang):
    body = _result(client, lang)
    line = re.search(r'<p class="report-card__personal">(.*?)</p>', body, re.S)
    assert line, "no personalised line"
    text = " ".join(line.group(1).split())
    grid = core.profile("Asha Vernekar", dt.date(1988, 3, 29))["lo_shu"]
    for number in grid["missing"]:
        assert str(number) in text, (number, text)
    assert "{" not in text, f"an unfilled placeholder: {text}"


def test_the_personal_line_states_missing_numbers_without_calling_them_a_fault():
    """NO FEAR-SELLING. The product brief says a missing number is an area somebody works at, never
    a fault and never something to fix - and the report itself says so. A card that implied
    otherwise would contradict the document it is selling."""
    from app.numerology import pages

    line = pages._personal_line("en", core.profile("Asha", dt.date(1988, 3, 29)))
    for scare in ("weak", "problem", "fault", "danger", "suffer", "fix", "warning", "unlucky"):
        assert scare not in line.lower(), f"the card sells by fear: {scare!r} in {line!r}"


def test_the_card_promises_no_number_of_spellings():
    """The writer's brief asks for alternative spellings without fixing HOW MANY. A card that says
    "3 options" when the report gives two has lied for money, so no count is claimed anywhere."""
    for lang in LANGS:
        assert not re.search(r"\b[0-9]+\b", CARD[lang]["tail"]), CARD[lang]["tail"]


@pytest.mark.parametrize("lang", LANGS)
def test_the_line_agrees_in_number_with_the_planes_it_names(lang):
    """One complete plane and two read differently in all three languages."""
    from app.numerology import pages

    one = pages._personal_line(lang, core.profile("Asha", dt.date(1234, 5, 6)))
    many = pages._personal_line(lang, core.profile("Asha", dt.date(1988, 3, 29)))
    assert one and many and one != many


def test_a_mulank_page_has_no_personalised_line(client):
    """It has no calculator, so there are no numbers of this reader's to read back."""
    body = client.get("/mulank-3").text
    assert 'class="report-card"' in body
    assert "report-card__personal" not in body
    assert "report-card__form" not in body, "a form with nothing to post is just a slower link"


# ---- 3. the preview is a real page of the real report ---------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_the_card_shows_a_page_of_the_real_report(client, lang):
    body = _result(client, lang)
    img = re.search(r'<img class="report-card__preview" src="([^"]+)"[^>]*>', body)
    assert img, "no preview image"
    assert img.group(1) == f"/static/img/sample/{lang}-numerology-5.webp"
    assert (ROOT / "app" / img.group(1).lstrip("/")).exists(), "the image is not checked in"
    assert 'alt="' in img.group(0) and 'width=' in img.group(0) and 'height=' in img.group(0)


@pytest.mark.parametrize("lang", LANGS)
def test_each_language_shows_a_page_in_its_own_language(lang):
    """A Hindi reader shown an English page is being shown a product they will not receive."""
    assert (ROOT / f"app/static/img/sample/{lang}-numerology-5.webp").exists()
    assert REPORT[lang]["preview_alt"] != REPORT["en"]["preview_alt"] or lang == "en"


def test_the_sample_is_an_invented_person():
    """Standing rule: no real birth data and no real names anywhere in the repository."""
    source = (ROOT / "scripts/sample_preview.py").read_text(encoding="utf-8")
    assert '"name": "Asha Kulkarni"' in source and '"born": "1990-05-14"' in source


@pytest.mark.parametrize("lang", LANGS)
def test_the_primary_button_names_the_price(client, lang):
    body = _result(client, lang)
    button = re.search(r'<button class="btn btn--cta btn--report"[^>]*>\s*(.*?)\s*<span', body, re.S)
    assert button and "199" in button.group(1), button.group(1) if button else "missing"


# ---- 4. the sticky bar ----------------------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_the_sticky_bar_appears_only_after_a_calculation(client, lang):
    assert 'id="report-bar"' in _result(client, lang)
    assert 'id="report-bar"' not in client.get(i18n.url_for("numerology", lang)).text
    assert 'id="report-bar"' not in client.get(i18n.url_for("mulank", lang, number=2)).text


def test_the_bar_is_hidden_until_a_script_shows_it(client):
    """Rendered hidden so a reader with JavaScript off never gets a bar whose dismiss cannot work."""
    bar = re.search(r'<aside class="report-bar"[^>]*>', _result(client))
    assert bar and "hidden" in bar.group(0)


def test_the_bar_can_be_dismissed_and_stays_dismissed(client):
    body = _result(client)
    assert 'id="report-bar-dismiss"' in body
    js = (ROOT / "app/static/js/numerology-handover.js").read_text(encoding="utf-8")
    assert "numerology-bar-dismissed" in js and "sessionStorage" in js


def test_the_bar_does_not_cover_the_page(client):
    """The page carries bottom padding equal to the bar while it is up. A bar that hides the last
    line of a free calculator to advertise a paid report is a worse page."""
    css = (ROOT / "app/static/css/site.css").read_text(encoding="utf-8")
    assert "body.has-report-bar" in css and "padding-bottom" in css
    js = (ROOT / "app/static/js/numerology-handover.js").read_text(encoding="utf-8")
    assert 'classList.add("has-report-bar")' in js and 'classList.remove("has-report-bar")' in js


def test_the_bar_posts_rather_than_linking(client):
    """It cannot carry the fields in an href without undoing the privacy fix, so it submits the
    card's own form."""
    js = (ROOT / "app/static/js/numerology-handover.js").read_text(encoding="utf-8")
    assert "report-card__form" in js and "form.submit()" in js


def test_the_card_does_not_say_the_same_thing_twice(client):
    """The personalised line REPLACES the generic one. Both named the Lo Shu reading and the
    spelling alternatives, so a reader saw the same promise twice - once about them and once about
    nobody. Found by looking at the rendered card rather than at the markup."""
    body = _result(client)
    card = re.search(r'<section class="report-card".*?</section>', body, re.S).group(0)
    paragraphs = [" ".join(x.split()) for x in re.findall(r"<p[^>]*>(.*?)</p>", card, re.S)]
    assert len(paragraphs) == 1, paragraphs
    assert REPORT["en"]["cta_from_result_body"].split("{")[0][:28] not in card


def test_a_mulank_page_keeps_the_generic_line(client):
    """It has no calculation, so the generic description is the only thing it can honestly say."""
    card = re.search(r'<section class="report-card".*?</section>',
                     client.get("/mulank-2").text, re.S).group(0)
    assert "report-card__personal" not in card
    assert REPORT["en"]["cta_from_result_body"].split("{")[0][:28] in card


def test_the_whole_paid_report_is_not_in_the_published_tree():
    """ONE PAGE IS A PREVIEW; NINE PAGES IS THE PRODUCT.

    The generator writes a complete numerology report to build the preview image from, and the first
    version of this work checked all three of them into app/static - a public, AGPL repository. It
    is an invented person's report, so nobody's data was exposed, but it is every section in full:
    the thing a reader pays Rs 199 for, published for free beside the card selling it.

    The free chart PDF beside these IS published whole, deliberately, because it is free and the
    sample page offers it. That is the distinction this test holds.
    """
    sample = ROOT / "app/static/img/sample"
    whole = sorted(p.name for p in sample.glob("*numerology*.pdf"))
    assert not whole, f"the paid report is in the published tree: {whole}"
    previews = sorted(p.name for p in sample.glob("*numerology*.webp"))
    assert previews == ["en-numerology-5.webp", "hi-numerology-5.webp", "mr-numerology-5.webp"]


def test_the_generator_writes_the_full_report_outside_the_published_tree():
    source = (ROOT / "scripts/sample_preview.py").read_text(encoding="utf-8")
    build = source[source.index("def build_numerology"):source.index("def build_free")]
    assert 'ROOT / "var"' in build, "the full report must not be written under app/static"
    assert "OUT /" not in build.split("rasterise")[0], build[:200]
