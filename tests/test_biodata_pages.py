"""The biodata maker as a page: the form, the preview, the two files, the unlock and the QR.

The people are invented.
"""
import datetime as dt
import io
import re
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.biodata import copy as biodata_copy
from app.biodata import designs, qr
from app.main import app
from app.payments import catalogue
from app.web import i18n

FORM = {"full_name": "Keshav Pardeshi", "qualification": "B.E. Mechanical",
        "father_name": "Anil Pardeshi", "devak": "Umbar", "birth_day": "3", "birth_month": "4",
        "birth_year": "1991", "birth_time_text": "14:25", "birth_city": "Pune",
        "design": "traditional"}


@pytest.fixture
def client():
    return TestClient(app)


def markup(html: str) -> str:
    return re.sub(r"<style>.*?</style>", "", html, flags=re.S)


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_maker_answers_in_every_tree_with_its_own_heading(client, lang):
    path = i18n.url_for("biodata", lang)
    response = client.get(path)
    assert response.status_code == 200
    words = biodata_copy.PAGE[lang]
    assert f"<h1>{words['h1']}</h1>" in response.text
    assert f"<title>{words['title']}" in response.text
    assert words["lede"] in response.text


def test_the_hindi_and_marathi_headings_are_not_the_same_words():
    """Marathi says लग्न where Hindi says विवाह. Identical headings across two trees is a page that
    was translated by copying, and this project has shipped that collision before."""
    assert biodata_copy.PAGE["mr"]["h1"] != biodata_copy.PAGE["hi"]["h1"]
    assert "लग्न" in biodata_copy.PAGE["mr"]["h1"]
    assert i18n.url_for("biodata", "mr") != i18n.url_for("biodata", "hi")
    assert "lagna" in i18n.url_for("biodata", "mr")


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_form_offers_every_field_and_a_month_by_name(client, lang):
    html = client.get(i18n.url_for("biodata", lang)).text
    from app.biodata import model

    for key in model.ALL_FIELDS:
        assert f'name="{key}"' in html, key
    # Three selects, never <input type="date"> - a browser draws that in ITS locale, so 1991-04-03
    # shows as "04/03/1991" and reads as 4 March to somebody in India.
    assert 'type="date"' not in html
    assert 'name="birth_day"' in html and 'name="birth_month"' in html


def test_the_preview_comes_back_with_the_sheet_and_the_downloads(client):
    response = client.post(i18n.url_for("biodata", "mr"), data={**FORM, "want": "preview"})
    assert response.status_code == 200
    assert "अनुराधा" in response.text and "Keshav Pardeshi" in response.text
    assert 'value="pdf"' in response.text and 'value="docx"' in response.text
    # The fields come back as hidden inputs: a download is one POST, and nothing was stored between.
    assert response.text.count('type="hidden"') >= len([v for v in FORM.values() if v])


def test_the_pdf_and_the_docx_are_the_real_files(client):
    pdf = client.post(i18n.url_for("biodata", "mr"), data={**FORM, "want": "pdf"})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert "attachment" in pdf.headers["content-disposition"]

    doc = client.post(i18n.url_for("biodata", "mr"), data={**FORM, "want": "docx"})
    assert doc.status_code == 200 and doc.content[:2] == b"PK"
    inside = zipfile.ZipFile(io.BytesIO(doc.content))
    assert "word/document.xml" in inside.namelist()
    assert "अनुराधा" in inside.read("word/document.xml").decode()


def test_the_blank_word_format_downloads_from_its_own_page(client):
    page = client.get(i18n.url_for("biodata-word", "en"))
    assert page.status_code == 200 and "?download=1" in page.text
    blank = client.get(i18n.url_for("biodata-word", "en") + "?download=1")
    assert blank.status_code == 200 and blank.content[:2] == b"PK"
    document = zipfile.ZipFile(io.BytesIO(blank.content)).read("word/document.xml").decode()
    assert "Keshav" not in document            # blank means blank


def test_a_premium_design_is_shown_locked_rather_than_hidden(client):
    """Hiding them would mean the ninety-nine rupees buys something nobody can see beforehand."""
    html = markup(client.get(i18n.url_for("biodata", "en")).text)
    for key in designs.PREMIUM:
        assert f'value="{key}"' in html, key
    assert html.count("bd-design--locked") == len(designs.PREMIUM)
    assert "disabled" in html


def test_an_unpaid_visitor_gets_the_free_design_whatever_they_post(client):
    response = client.post(i18n.url_for("biodata", "en"),
                           data={**FORM, "design": "ganesh-gold", "want": "preview"})
    assert "biodata--classic" in markup(response.text)
    assert designs.MADE_ON["en"] in response.text


def test_the_unlock_is_a_catalogue_product_at_ninety_nine_and_is_on_the_pricing_page(client):
    entry = catalogue.item("biodata-premium")
    assert entry is not None and entry.kind == "download" and entry.price_inr == 99
    assert entry.gst.base_paise + entry.gst.gst_paise == 9900
    assert "Biodata premium designs" in client.get("/pricing").text


def test_the_unlock_refuses_birth_details(client):
    """A download is bought, not generated. Asking for a chart here would be collecting birth data
    for nothing - and on this page it would contradict its own privacy line."""
    body = {"product": "biodata-premium", "email": "someone@example.com", "place_of_supply": "27",
            "birth": {"date": "1991-04-03", "time": "14:25", "city": "Pune"}}
    assert client.post("/api/payments/order", json=body).status_code == 422


def test_the_qr_is_only_made_when_the_box_is_ticked(client):
    without = client.post(i18n.url_for("biodata", "mr"), data={**FORM, "want": "preview"})
    assert "data:image/svg+xml" not in without.text
    with_qr = client.post(i18n.url_for("biodata", "mr"),
                          data={**FORM, "qr": "1", "want": "preview"})
    assert "data:image/svg+xml" in with_qr.text


def test_the_qr_prefills_partner_one_and_switching_it_off_stops_it(client):
    token = qr.issue(birth_date=dt.date(1991, 4, 3), birth_time=dt.time(14, 25), lat=18.52,
                     lon=73.86, place="Pune", person="Keshav")
    page = client.get(i18n.url_for("matching", "en") + f"?biodata={token}")
    boy = page.text.split('data-person="boy"')[1].split('data-person="girl"')[0]
    assert 'value="Keshav"' in boy and 'value="14:25"' in boy and 'value="Pune"' in boy
    assert '<option value="1991" selected' in boy
    girl = page.text.split('data-person="girl"')[1]
    assert 'value="Keshav"' not in girl

    qr.revoke(token)
    after = client.get(i18n.url_for("matching", "en") + f"?biodata={token}")
    assert after.status_code == 200
    assert 'value="Keshav"' not in after.text.split('data-person="boy"')[1]


def test_a_nonsense_or_missing_token_changes_nothing(client):
    plain = client.get(i18n.url_for("matching", "en")).text
    for token in ("", "rubbish", "a.b"):
        page = client.get(i18n.url_for("matching", "en") + f"?biodata={token}")
        assert page.status_code == 200
        assert 'value="Keshav"' not in page.text
    assert "selected" not in plain.split('data-person="boy"')[1].split('data-person="girl"')[0]


def test_the_privacy_section_says_all_three_things(client):
    import html as html_module

    for lang in ("en", "hi", "mr"):
        # UNESCAPED. The English line contains an apostrophe, which the template escapes to &#39; -
        # so a raw substring search fails on the one language whose copy has punctuation in it.
        page = html_module.unescape(client.get(i18n.url_for("biodata", lang)).text)
        for line in biodata_copy.PAGE[lang]["privacy"]:
            assert line in page
