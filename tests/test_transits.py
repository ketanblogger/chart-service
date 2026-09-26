from datetime import datetime, timezone

import pytest

from app.engine import current_transits, transit_events
from app.engine.constants import GRAHA_KEYS


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_current_transits_defaults_to_now_with_all_grahas():
    result = current_transits()
    assert list(result["grahas"]) == GRAHA_KEYS
    assert abs((datetime.fromisoformat(result["datetime_utc"]) - datetime.now(timezone.utc)).total_seconds()) < 60
    for graha in result["grahas"].values():
        assert 0 <= graha["degree"] < 30
        assert 1 <= graha["pada"] <= 4
        assert "house" not in graha


def test_positions_at_a_known_moment():
    grahas = current_transits(_utc(2026, 9, 21))["grahas"]
    signs = {key: graha["sign"]["name"] for key, graha in grahas.items()}
    assert signs["Saturn"] == "Meena"
    assert signs["Jupiter"] == "Karka"
    assert signs["Sun"] == "Kanya"
    assert grahas["Saturn"]["retrograde"] is True
    assert grahas["Sun"]["retrograde"] is False


def test_naive_datetime_is_read_as_ist():
    assert current_transits(datetime(2026, 9, 21, 5, 30))["datetime_utc"] == "2026-09-21T00:00:00+00:00"


def test_houses_from_rashi_accept_any_sign_spelling():
    when = _utc(2026, 9, 21)
    by_slug = current_transits(when, rashi="meena")
    assert by_slug["rashi"]["key"] == "Pisces"
    assert by_slug["grahas"]["Saturn"]["house"] == 1  # Saturn is in Meena
    assert by_slug["grahas"]["Sun"]["house"] == 7  # Kanya is 7th from Meena
    for spelling in ("Pisces", "Meena", 12, "12"):
        assert current_transits(when, rashi=spelling) == by_slug
    with pytest.raises(ValueError):
        current_transits(when, rashi="ophiuchus")


def test_ingresses_match_published_panchang_dates():
    events = transit_events(_utc(2025, 3, 1), _utc(2026, 2, 1))
    assert all(event["graha"]["key"] != "Moon" for event in events)  # long period: Moon left out
    ingress_dates = {
        (e["graha"]["key"], e["to_sign"]["name"]): e["datetime"][:10] for e in events if e["type"] == "ingress"
    }
    assert ingress_dates[("Saturn", "Meena")] == "2025-03-29"
    assert ingress_dates[("Jupiter", "Mithuna")] == "2025-12-05"  # retrograde re-entry overwrites 14 May
    assert ingress_dates[("Rahu", "Kumbha")] == "2025-05-18"
    assert ingress_dates[("Ketu", "Simha")] == "2025-05-18"
    assert ingress_dates[("Sun", "Makara")] == "2026-01-14"  # Makar Sankranti


def test_stations_and_retrograde_ingresses():
    events = transit_events(_utc(2025, 3, 1), _utc(2026, 2, 1), rashi="dhanu")
    stations = [(e["graha"]["key"], e["direction"], e["datetime"][:10]) for e in events if e["type"] == "station"]
    assert ("Saturn", "retrograde", "2025-07-13") in stations
    assert ("Saturn", "direct", "2025-11-28") in stations
    assert ("Jupiter", "retrograde", "2025-11-11") in stations
    jupiter = [e for e in events if e["type"] == "ingress" and e["graha"]["key"] == "Jupiter"]
    assert [(e["to_sign"]["name"], e["retrograde"], e["house"]) for e in jupiter] == [
        ("Mithuna", False, 7), ("Karka", False, 8), ("Mithuna", True, 7),
    ]
    times = [e["datetime_utc"] for e in events]
    assert times == sorted(times)


def test_short_periods_include_moon_ingresses():
    events = transit_events(_utc(2026, 9, 21), _utc(2026, 9, 28))
    moon = [e for e in events if e["graha"]["key"] == "Moon"]
    assert 2 <= len(moon) <= 4  # the Moon changes sign about every 2.3 days
    for previous, following in zip(moon, moon[1:]):
        assert previous["to_sign"] == following["from_sign"]


def test_end_before_start_is_rejected():
    with pytest.raises(ValueError):
        transit_events(_utc(2026, 9, 21), _utc(2026, 9, 20))
