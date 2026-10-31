"""The sheet: twenty designs out of one template, a photo that never reaches the disk, and the
credit line that goes on the free ones.

The people are invented.
"""
import datetime as dt
import re
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from app.biodata import core, designs, model, sheet

ROOT = Path(__file__).resolve().parents[1]
BORN = dt.date(1991, 4, 3)
FIELDS = model.fields_from({"full_name": "Keshav Pardeshi", "qualification": "B.E. Mechanical",
                            "father_name": "Anil Pardeshi", "devak": "Umbar", "gotra": "Kashyap"})
JPEG = b"\xff\xd8\xff" + b"not really a jpeg but it starts like one" * 4
PNG = b"\x89PNG\r\n\x1a\n" + b"body" * 8


def kundli(**kw):
    return core.from_birth(BORN, language=kw.pop("language", "mr"), **kw)


def markup(html: str) -> str:
    """The document WITHOUT its inlined stylesheet.

    Every class this sheet uses is also DEFINED in that stylesheet, so `"bd-photo" in html` is true
    on a sheet with no photo and `"bd-row--unsettled" in html` is true on one with nothing unsettled.
    Two assertions here were written that way and both passed for the wrong reason until they were
    pointed at a sheet that should have failed them. Ask the markup, never the document.
    """
    return re.sub(r"<style>.*?</style>", "", html, flags=re.S)


def test_twenty_designs_three_of_them_free():
    assert len(designs.DESIGNS) == 20
    assert designs.FREE == ("classic", "traditional", "modern")
    assert len(designs.PREMIUM) == 17
    assert set(designs.NAMES) == set(designs.DESIGNS)
    for key, design in designs.DESIGNS.items():
        assert design["ornament"] in designs.ORNAMENTS, key
        assert set(design["names"]) == {"en", "hi", "mr"}, key
        assert set(design["tokens"]) == {"ink", "accent", "paper", "band", "head", "body"}, key


def test_a_premium_design_needs_the_payment_and_falls_back_rather_than_erroring():
    """A 400 here would lose everything the person typed, which is the expensive part of this page."""
    assert designs.design("ganesh-gold")["key"] == "classic"
    assert designs.design("ganesh-gold", paid=True)["key"] == "ganesh-gold"
    assert designs.design("no-such-design", paid=True)["key"] == "classic"
    assert designs.design(None)["key"] == "classic"
    html = sheet.build(FIELDS, design_key="ganesh-gold")
    assert "biodata--classic" in markup(html) and "biodata--ganesh-gold" not in markup(html)


def test_no_font_token_carries_a_quote():
    """THE ESCAPING TRAP. These tokens land inside a <style> block in an autoescaping template, so a
    quoted family name arrives as `&#34;Report Devanagari&#34;`, the declaration is invalid, Chromium
    falls back to DejaVu and every Devanagari character prints as a box. It shipped exactly once, into
    a rendered PDF, before this test existed."""
    for key, design in designs.DESIGNS.items():
        for token in ("head", "body"):
            assert '"' not in design["tokens"][token], key
            assert "'" not in design["tokens"][token], key
            assert "Report Devanagari" in design["tokens"][token], key
    html = sheet.build(FIELDS, language="mr", design_key="traditional")
    assert "&#34;" not in html and "&#39;" not in html
    assert re.search(r"--body: Report Devanagari, Report Sans;", html)


def test_the_sheet_declares_the_faces_it_prints_with():
    """sheet.css is inlined INSTEAD of print.css, so it has to carry its own @font-face block - a
    document with none renders Devanagari as boxes no matter what the family names say."""
    css = (ROOT / "app/biodata/sheet.css").read_text(encoding="utf-8")
    # Counting the DECLARATION, brace and all: the prose above it in that stylesheet mentions the
    # at-rule by name, and a bare substring count scored the comment as a fifth face.
    assert css.count("@font-face {") == 4
    for file in ("NotoSansDevanagari-Regular.ttf", "NotoSansDevanagari-Bold.ttf",
                 "NotoSans-Regular.ttf", "NotoSans-Bold.ttf"):
        assert f'url("fonts/{file}")' in css, file
        assert (ROOT / "app/pdf/fonts" / file).is_file(), file


def test_every_invocation_character_has_a_glyph():
    """A missing glyph is a box at the very top of a sheet somebody hands to a prospective family."""
    covered = set()
    for file in ("NotoSansDevanagari-Regular.ttf", "NotoSans-Regular.ttf"):
        font = TTFont(ROOT / "app/pdf/fonts" / file)
        for table in font["cmap"].tables:
            covered |= set(table.cmap)
    for key, text in designs.INVOCATIONS.items():
        for char in text.replace(" ", ""):
            assert ord(char) in covered, f"{key}: {char!r} has no glyph"


def test_the_invocation_is_type_and_there_is_no_picture_of_a_deity():
    """The Ganesh designs carry the written invocation, which is what the real sheets print. This
    project does not generate or ship images of deities, and the repository is public and AGPL, so
    there is no traced or stock art anywhere in the template either."""
    assert designs.INVOCATIONS["ganesh"] == "॥ श्री गणेशाय नमः ॥"
    template = (ROOT / "app/pdf/templates/biodata.html").read_text(encoding="utf-8")
    # The only <img> elements are the person's own photo and the opt-in QR, both data URIs.
    assert template.count("<img") == 2
    assert "{{ photo }}" in template and "{{ qr.image }}" in template
    assert "http://" not in template and "https://" not in template   # nothing fetched from anywhere


@pytest.mark.parametrize("raw, kept", [
    (JPEG, True), (PNG, True),
    (b"RIFF" + b"\x00" * 4 + b"WEBP" + b"rest", True),
    (b"RIFF" + b"\x00" * 4 + b"WAVE" + b"rest", False),     # a RIFF container that is not an image
    (b"\x00\x01\x02 some other file", False),
    (b"", False), (None, False),
    (b"\xff\xd8\xff" + b"x" * (sheet.MAX_PHOTO_BYTES + 1), False),
])
def test_only_a_file_that_really_is_an_image_is_embedded(raw, kept):
    """The signature, not the filename or the content-type - a browser lets the caller set both."""
    uri = sheet.photo_data_uri(raw)
    assert (uri is not None) == kept
    if kept:
        assert uri.startswith("data:image/") and ";base64," in uri


def test_the_photo_is_a_data_uri_and_never_a_path(tmp_path):
    """There is no file to serve, so there is no URL to guess and no directory to list."""
    before = {p.name for p in tmp_path.iterdir()}
    html = sheet.build(FIELDS, paid=True, photo=JPEG, frame="oval")
    assert "data:image/jpeg;base64," in markup(html)
    assert "bd-photo bd-photo--oval" in markup(html)
    assert {p.name for p in tmp_path.iterdir()} == before
    assert "/var/" not in html and "file://" not in html


def test_a_photo_is_not_printed_on_a_free_sheet():
    """Frames are a premium feature, so a free render drops the photo rather than printing it
    unframed - and a sheet that silently kept an upload it was not going to use would be storing a
    face for no reason."""
    html = sheet.build(FIELDS, paid=False, photo=JPEG)
    # The MARKUP, not the document: the stylesheet is inlined, so it defines .bd-photo on every
    # sheet whether or not one is printed, and a bare substring search finds its own CSS.
    assert "data:image" not in markup(html) and '<figure class="bd-photo' not in markup(html)


def test_the_credit_line_is_on_the_free_sheets_and_not_the_paid_one():
    free = sheet.build(FIELDS, language="mr", design_key="classic")
    paid = sheet.build(FIELDS, language="mr", design_key="ganesh-gold", paid=True)
    assert designs.MADE_ON["mr"] in free
    assert designs.MADE_ON["mr"] not in paid
    # Small, at the foot - never a bar across a sheet that is about to be shown to another family.
    css = (ROOT / "app/biodata/sheet.css").read_text(encoding="utf-8")
    assert "position: absolute" not in css.split(".bd-made")[1].split("}")[0]


def test_devak_and_gotra_print_once_in_the_kundli_block():
    html = sheet.build(FIELDS, language="mr", kundli=kundli())
    assert html.count("Umbar") == 1 and html.count("Kashyap") == 1
    assert "देवक" in html and "गोत्र" in html
    assert "devak" not in [key for key, _ in model.SECTIONS["family"]]


def test_an_unsettled_row_is_marked_and_explained_rather_than_hidden():
    html = sheet.build(FIELDS, language="mr", kundli=kundli())
    assert "bd-row bd-row--unsettled" in markup(html)
    assert sheet.NO_TIME_NOTE["mr"] in html
    settled = sheet.build(FIELDS, language="mr",
                          kundli=kundli(birth_time=dt.time(14, 25), lat=18.52, lon=73.86))
    assert "bd-row bd-row--unsettled" not in markup(settled)
    assert sheet.NO_TIME_NOTE["mr"] not in settled


@pytest.mark.parametrize("language", ["en", "hi", "mr"])
def test_the_sheet_renders_in_each_language_with_that_languages_labels(language):
    html = sheet.build(FIELDS, language=language, kundli=kundli(language=language))
    assert f'<html lang="{language}">' in html
    assert model.SECTION_TITLES["kundli"][language] in html
    assert core.LABELS[language]["rashi"] in html
    assert designs.MADE_ON[language] in html


def test_an_empty_section_does_not_print_its_heading():
    """A biodata with an empty "Education and work" heading looks like a form somebody abandoned."""
    only_name = model.fields_from({"full_name": "Keshav Pardeshi"})
    html = sheet.build(only_name, language="en")
    assert model.SECTION_TITLES["personal"]["en"] in html
    assert model.SECTION_TITLES["work"]["en"] not in html
    assert model.SECTION_TITLES["contact"]["en"] not in html
