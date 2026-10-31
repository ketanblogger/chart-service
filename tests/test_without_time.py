"""The "समय नहीं पता" mode: what a chart may say when the birth hour is unknown, and what it must not.

A great many people know the date and the city and not the hour. The two usual answers are both bad -
refuse them a chart, or quietly assume noon and hand them a lagna, houses and dasha dates that are
fiction. This mode is the third answer, and the tests that matter here are the ones asserting what it
REFUSES to return.
"""
from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.engine.without_time import _OTHERS, moon_sign_is_safe, what_is_known
from app.main import app

client = TestClient(app, raise_server_exceptions=False)
ENDPOINT = "/api/chart/without-time"


def test_the_endpoint_returns_what_is_settled_and_what_is_not():
    response = client.post(ENDPOINT, json={"date": "2026-10-31", "city": "Pune"})
    assert response.status_code == 200
    body = response.json()
    assert body["settled"] and isinstance(body["settled"], list)
    jupiter = [e for e in body["unsettled"] if e["graha"] == "Jupiter"]
    assert jupiter, "Jupiter enters Simha on this date; the hour decides which sign"
    assert [s["name"] for s in jupiter[0]["signs"]] == ["Karka", "Simha"]


def test_the_response_contains_no_lagna_no_house_and_no_dasha():
    """THE POINT OF THE WHOLE MODE. A caller must not be able to read a lagna off this and get a noon
    assumption dressed as a fact - which is why it is a separate endpoint rather than a flag on /chart."""
    body = client.post(ENDPOINT, json={"date": "1990-05-14", "city": "Pune"}).json()
    # CHECKED STRUCTURALLY, not by searching the flattened response: `needs_birth_time` NAMES the things
    # it refuses, so a substring search finds "houses" there and fails on a correct response. What
    # matters is that no VALUE in the payload is a lagna, a house or a dasha.
    assert set(body) == {"date", "settled", "unsettled", "needs_birth_time"}
    for entry in body["settled"] + body["unsettled"]:
        assert set(entry) <= {"graha", "sign", "signs", "depends_on_time"}, entry
        assert entry["graha"] in {"Moon", "Sun", "Mars", "Mercury", "Jupiter", "Venus", "Saturn",
                                  "Rahu", "Ketu"}
    assert set(body["needs_birth_time"]) >= {"lagna", "houses", "dasha", "mangal_dosha"}


def test_every_graha_is_checked_not_only_the_fast_ones():
    assert set(_OTHERS) == {"Sun", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"}
    known = what_is_known(dt.date(1990, 5, 14))
    checked = {e["graha"] for e in known["settled"]} | {e["graha"] for e in known["unsettled"]}
    assert checked == {"Moon", *_OTHERS}, checked


@pytest.mark.parametrize("day, graha, signs", [
    ("2026-10-31", "Jupiter", ["Karka", "Simha"]),   # a Jupiter ingress, about once a year
    ("2026-10-17", "Sun", ["Kanya", "Tula"]),        # a sankranti
    ("2026-10-02", "Moon", ["Vrishabha", "Mithuna"]),  # the commonest case by far
])
def test_a_real_ingress_is_reported_as_two_possibilities(day, graha, signs):
    """Never one sign picked silently. "It is either Mesha or Vrishabha, depending on the hour" is a
    useful thing to be told; "Mesha" would be a guess presented as a fact."""
    known = what_is_known(dt.date.fromisoformat(day))
    found = [e for e in known["unsettled"] if e["graha"] == graha]
    assert found, f"{graha} changes sign on {day} and must be undecided"
    assert [s["name"] for s in found[0]["signs"]] == signs
    assert found[0]["depends_on_time"] is True


def test_an_ordinary_day_settles_everything():
    known = what_is_known(dt.date(1990, 5, 14))
    assert known["unsettled"] == []
    assert len(known["settled"]) == 9


def test_the_moon_is_undecided_about_two_days_in_five():
    days = [dt.date(2026, 10, 1) + dt.timedelta(days=n) for n in range(30)]
    ambiguous = sum(1 for day in days if not moon_sign_is_safe(day))
    assert 8 <= ambiguous <= 18, f"{ambiguous}/30 - the Moon crosses a sign about every 2.3 days"


def test_an_unknown_city_is_refused_rather_than_guessed():
    assert client.post(ENDPOINT, json={"date": "1990-05-14", "city": "Nowhere"}).status_code == 422


def test_no_birth_time_field_is_accepted_at_all():
    """The model has no `time`, so a caller cannot smuggle one in and have it silently ignored - which
    would be worse than rejecting it, because the answer would look like it had used it."""
    response = client.post(ENDPOINT, json={"date": "1990-05-14", "city": "Pune", "time": "07:30"})
    assert response.status_code == 200
    assert "07:30" not in str(response.json())


@pytest.mark.parametrize("lang, path", [("en", "/kundli"), ("hi", "/hi/kundli"), ("mr", "/mr/kundali")])
def test_the_page_explains_the_no_time_case(lang, path):
    """A reader who does not know their birth time should find out what is still possible without
    having to submit anything first."""
    import re

    html = client.get(path).text
    body = re.sub(r"<[^>]+>", " ", html.split("<main", 1)[1].split("</main>", 1)[0]).lower()
    needles = {"en": ["without a birth time", "lagna"],
               "hi": ["जन्म समय", "लग्न"],
               "mr": ["जन्मवेळ", "लग्न"]}[lang]
    for needle in needles:
        assert needle.lower() in body, f"{path} does not explain: {needle}"
