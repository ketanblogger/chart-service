"""Panchang basics and Shani dhaiya (engine additions for Phase 7). Anchors are astronomical facts:
the new moon of the 8 April 2024 solar eclipse (18:21 UT) and the full moon of the 7 September 2025
lunar eclipse (18:09 UT), plus festival dates fixed by tithi-at-sunrise."""

from datetime import date, datetime, timezone

import pytest

from app import engine
from app.engine.panchang import REFERENCE_PLACE, panchang, tithi_info


def test_amavasya_at_the_april_2024_solar_eclipse():
    result = panchang(date(2024, 4, 8))
    assert result["tithi"]["name"] == "Amavasya" and result["tithi"]["paksha"]["key"] == "krishna"
    assert result["tithi"]["index"] == 30
    assert result["tithi"]["ends_at"] in ("2024-04-08T23:50+05:30", "2024-04-08T23:51+05:30", "2024-04-08T23:52+05:30")
    assert result["vara"]["key"] == "Monday" and result["vara"]["lord"]["key"] == "Moon"


def test_purnima_at_the_september_2025_lunar_eclipse():
    result = panchang(date(2025, 9, 7))
    assert result["tithi"]["name"] == "Purnima" and result["tithi"]["paksha"]["key"] == "shukla"
    assert result["tithi"]["ends_at"].startswith("2025-09-07T23:3")
    assert result["vara"]["key"] == "Sunday" and result["vara"]["lord"]["key"] == "Sun"


@pytest.mark.parametrize("day, paksha, tithi", [
    (date(2025, 3, 30), "shukla", "Pratipada"),   # Gudi Padwa
    (date(2025, 4, 6), "shukla", "Navami"),       # Ram Navami
    (date(2025, 7, 10), "shukla", "Purnima"),     # Guru Purnima
    (date(2025, 8, 27), "shukla", "Chaturthi"),   # Ganesh Chaturthi
])
def test_festival_tithis_at_sunrise(day, paksha, tithi):
    result = panchang(day)
    assert (result["tithi"]["paksha"]["key"], result["tithi"]["name"]) == (paksha, tithi)


def test_shape_sunrise_and_end_times():
    result = panchang(date(2026, 9, 21))
    assert result["place"] == REFERENCE_PLACE and result["date"] == "2026-09-21"
    assert "2026-09-21T06:20+05:30" < result["sunrise"] < "2026-09-21T06:40+05:30"  # Mumbai, around the equinox
    assert result["tithi"]["ends_at"] > result["sunrise"] and result["nakshatra"]["ends_at"] > result["sunrise"]
    assert result["nakshatra"]["name"] == "Uttarashadha" and result["nakshatra"]["devanagari"]
    # the Moon's nakshatra at sunrise agrees with the transit function at the same moment
    moon = engine.current_transits(datetime.fromisoformat(result["sunrise"]))["grahas"]["Moon"]
    assert moon["nakshatra"]["name"] == result["nakshatra"]["name"]


def test_another_place_moves_sunrise():
    mumbai, kolkata = panchang(date(2026, 9, 21)), panchang(date(2026, 9, 21), lat=22.5726, lon=88.3639)
    assert kolkata["sunrise"] < mumbai["sunrise"] and kolkata["place"]["name"] is None


def test_tithi_numbering():
    assert tithi_info(0)["name"] == "Pratipada" and tithi_info(0)["paksha"]["key"] == "shukla"
    assert tithi_info(14)["name"] == "Purnima" and tithi_info(15)["name"] == "Pratipada"
    assert tithi_info(15)["paksha"]["key"] == "krishna" and tithi_info(29)["name"] == "Amavasya"
    assert [tithi_info(i)["index"] for i in (0, 29)] == [1, 30]


def test_dhaiya_follows_saturn_in_meena():
    now = datetime(2026, 9, 21, tzinfo=timezone.utc)  # Saturn in Meena since 29 March 2025
    simha, dhanu, mesha = (engine.dhaiya(sign, now) for sign in (5, 9, 1))
    assert (simha["active"], simha["kind"], simha["saturn_house_from_moon"]) == (True, "eighth", 8)
    assert (dhanu["active"], dhanu["kind"], dhanu["saturn_house_from_moon"]) == (True, "fourth", 4)
    assert simha["period"]["start"] == "2025-03-29" and simha["period"]["end"] > "2027-01-01"
    assert mesha == {**mesha, "active": False, "kind": None, "period": None}
    assert engine.sade_sati(1, now)["active"] is True  # Mesha: Saturn in the 12th
    active = [sign for sign in range(1, 13) if engine.dhaiya(sign, now)["active"]]
    assert active == [5, 9]
