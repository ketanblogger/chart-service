"""Matching by name (SEO map §3): the page's own JavaScript (render.js, in V8) against the REAL /api/matching name mode -
validation, payload, result in three languages, the ambiguous-syllable picker and its resubmit, unreadable names."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import STATIC_DIR, i18n

client = TestClient(app)


@pytest.fixture(scope="module")
def js():
    mini_racer = pytest.importorskip("py_mini_racer")
    ctx = mini_racer.MiniRacer()
    ctx.eval((STATIC_DIR / "js" / "render.js").read_text(encoding="utf-8"))

    def call(expression: str, **variables):
        names = ", ".join(variables)
        args = ", ".join(json.dumps(value, ensure_ascii=False) for value in variables.values())
        return json.loads(ctx.eval(f"JSON.stringify((function({names}) {{ return {expression}; }})({args}))"))

    return call


def _values(boy: str, girl: str) -> dict:
    return {"boy": {"name": boy, "date": "", "time": "", "city": ""}, "girl": {"name": girl, "date": "", "time": "", "city": ""}}


def test_names_are_validated_in_the_page_language(js):
    errors = js("AstroRender.validateNames(v, 'en')", v=_values("", "  "))
    assert [(e["person"], e["field"]) for e in errors] == [("boy", "name"), ("girl", "name")]
    messages = {lang: js("AstroRender.validateNames(v, lang)", v=_values("", "Tina"), lang=lang)[0]["message"] for lang in i18n.LANGS}
    assert len(set(messages.values())) == 3 and "नाम" in messages["hi"] and "नाव" in messages["mr"]
    assert js("AstroRender.validateNames(v, 'hi')", v=_values("Keshav", "Tina")) == []


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_submit_by_name_renders_the_same_score_ui_plus_what_the_names_gave(js, lang):
    values = _values(" Keshav ", "Tina")
    body = js("AstroRender.buildNamePayload(v)", v=values)
    assert body == {"mode": "name", "boy": {"name": "Keshav"}, "girl": {"name": "Tina"}}
    response = client.post("/api/matching", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["basis"] == "name" and data["mangal_dosha"] is None
    html = js("AstroRender.renderers.matching(data, ctx)", data=data,
              ctx={"names": {"boy": "Keshav", "girl": "Tina"}, "lang": lang, "mode": "name"})
    for junk in ("undefined", "NaN", "[object", ">null<"):
        assert junk not in html
    assert f'<span class="score__total">{data["total"]:g}</span> / 36' in html  # the same score UI
    assert html.count("<tr") == 10  # 8 kootas + header + total
    for who in ("boy", "girl"):  # derived syllable, rashi and nakshatra of each name
        person = data[who]
        assert person["name_match"]["syllable"] in html
        sign, star = person["moon_sign"], person["moon_nakshatra"]
        assert (sign["name"] if lang == "en" else sign["devanagari"].replace("तुला", "तूळ" if lang == "mr" else "तुला")) in html
        assert (star["name"] if lang == "en" else star["devanagari"]) in html
    assert "Keshav" in html and "Tina" in html and 'class="birth-line"' not in html
    note = {"en": "birth details is more accurate", "hi": "अधिक सटीक", "mr": "अधिक अचूक"}[lang]
    assert note in html and "name-note" in html
    assert {"en": "Mangal dosha comparison", "hi": "मंगल दोष की तुलना", "mr": "मंगळ दोषाची तुलना"}[lang] not in html.split("name-note")[1].split("</p>", 1)[1]
    if lang != "en":
        text = re.sub(r"<[^>]+>", " ", html)
        for english in ("Boy", "Girl", "Points", "Total", "Derived", "syllable"):
            assert english not in text, english


def test_ambiguous_first_sound_shows_a_picker_and_resubmits_with_the_syllable(js):
    first = client.post("/api/matching", json=js("AstroRender.buildNamePayload(v)", v=_values("Keshav", "Tina"))).json()
    match = first["girl"]["name_match"]
    assert match["confidence"] == "ambiguous" and len(match["candidates"]) >= 2
    assert first["boy"]["name_match"]["candidates"] == []
    html = js("AstroRender.renderers.matching(data, ctx)", data=first, ctx={"lang": "hi", "mode": "name"})
    chips = re.findall(r'<button type="button" class="chip" data-name-candidate data-person="(\w+)" data-index="(\d)" aria-pressed="(\w+)" data-syllable="([^"]+)"', html)
    assert [chip[0] for chip in chips] == ["girl"] * len(match["candidates"])  # only the ambiguous name gets a picker
    assert [chip[3] for chip in chips] == [c["syllable"] for c in match["candidates"]]
    assert [chip[2] for chip in chips] == ["true"] + ["false"] * (len(chips) - 1)  # the reading that was used is marked

    # what app.js does on a chip click: resubmit the same names with the chosen candidate
    choice = match["candidates"][1]
    body = js("AstroRender.buildNamePayload(v, choices)", v=_values("Keshav", "Tina"), choices={"girl": choice})
    assert body == {"mode": "name", "boy": {"name": "Keshav"}, "girl": {"name": "Tina", "syllable": choice["syllable"]}}
    second = client.post("/api/matching", json=body).json()
    assert second["girl"]["name_match"]["confidence"] == "chosen" and second["girl"]["name_match"]["syllable"] == choice["syllable"]
    assert second["girl"]["moon_nakshatra"]["name"] == choice["nakshatra"]["name"]
    again = js("AstroRender.renderers.matching(data, ctx)", data=second, ctx={"lang": "en", "mode": "name"})
    assert choice["syllable"] in again and "undefined" not in again


def test_devanagari_names_work_and_unreadable_names_land_on_the_right_field(js):
    ok = client.post("/api/matching", json=js("AstroRender.buildNamePayload(v)", v=_values("केशव", "टीना")))
    assert ok.status_code == 200 and ok.json()["girl"]["name_match"]["syllable"] == "टी"
    bad = client.post("/api/matching", json=js("AstroRender.buildNamePayload(v)", v=_values("Keshav", "12345")))
    assert bad.status_code == 422
    for lang in i18n.LANGS:
        errors = js("AstroRender.parseApiError(422, body, 'pair', lang)", body=bad.json(), lang=lang)
        assert [(e["person"], e["field"]) for e in errors] == [("girl", "name")], lang
    hindi = js("AstroRender.parseApiError(422, body, 'pair', 'hi')", body=bad.json())[0]["message"]
    assert re.search(r"[ऀ-ॿ]", hindi) and not re.search(r"[A-Za-z]{4,}", hindi)


def test_app_js_wires_the_mode_toggle_deep_link_and_picker():
    source = (STATIC_DIR / "js" / "app.js").read_text(encoding="utf-8")
    for needle in ("R.validateNames(values, lang)", "R.buildNamePayload(values, nameChoices)", "[data-name-candidate]",
                   "mode=name", '"#by-name"', "replaceState", 'cta.hidden = mode === "name"'):
        assert needle in source, needle
    assert "location.href" not in source and "location.assign" not in source  # the toggle never navigates
