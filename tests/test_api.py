import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.reference_charts import INDIRA, KALAM

client = TestClient(app)

# Public, published births - see tests/reference_charts.py. INDIRA_BY_CITY exercises the city
# lookup: hers is the one reference whose birthplace is in the city list AND whose timezone a city
# entry can express (1917, so genuinely IST). The city table's coordinates differ from the source's
# by a few hundredths of a degree, so this route is used for FORM behaviour, never to assert a
# chart value - those go through .request() with exact coordinates.
INDIRA_BY_CITY = INDIRA.city_request()
KALAM_BIRTH = KALAM.request()
PUNE = {"date": "1997-08-14", "time": "06:15", "lat": 18.5196, "lon": 73.8554, "timezone": "+05:30"}


def test_cities_include_miraj_with_sane_coordinates():
    cities = client.get("/api/cities").json()["cities"]
    assert len(cities) >= 100
    names = [city["name"] for city in cities]
    assert len(set(names)) == len(names)
    for expected in ("Miraj", "Sangli", "Kolhapur", "Pune", "Mumbai", "Delhi"):
        assert expected in names
    for city in cities:
        assert 6 < city["lat"] < 36 and 68 < city["lon"] < 98  # inside India
        assert city["tz"] == "Asia/Kolkata"
    miraj = next(city for city in cities if city["name"] == "Miraj")
    assert miraj["lat"] == pytest.approx(16.83, abs=0.02)
    assert miraj["lon"] == pytest.approx(74.65, abs=0.03)


def test_chart_by_city():
    response = client.post("/api/chart", json=INDIRA_BY_CITY)
    assert response.status_code == 200
    chart = response.json()
    assert chart["input"]["city"] == "Prayagraj (Allahabad)"
    assert chart["input"]["timezone"] == "Asia/Kolkata"
    assert chart["moon_rashi"]["name"] == "Makara"
    assert chart["janma_nakshatra"]["name"] == "Uttarashadha"
    assert set(chart) == {
        "input", "meta", "lagna", "grahas", "moon_rashi", "janma_nakshatra",
        "houses", "dasha", "mangal_dosha", "sade_sati", "accuracy",
    }


def test_chart_by_coordinates_matches_chart_by_city():
    by_city = client.post("/api/chart", json=INDIRA_BY_CITY).json()
    city = by_city["input"]
    by_coordinates = client.post("/api/chart", json={
        "date": INDIRA_BY_CITY["date"], "time": INDIRA_BY_CITY["time"],
        "lat": city["lat"], "lon": city["lon"]}).json()
    assert by_coordinates["input"]["city"] is None
    assert by_coordinates["grahas"] == by_city["grahas"]
    assert by_coordinates["lagna"] == by_city["lagna"]


def test_city_lookup_is_forgiving():
    """City names are public geography, unrelated to whose birth is being computed: lower case,
    stray spaces and the old name of a renamed city all resolve."""
    birth = {"date": INDIRA_BY_CITY["date"], "time": INDIRA_BY_CITY["time"]}
    for name in ("miraj", " Miraj ", "Belgaum", "Belagavi (Belgaum)", "allahabad", "Prayagraj"):
        assert client.post("/api/chart", json={**birth, "city": name}).status_code == 200, name


def test_invalid_requests_get_422():
    bad_requests = [
        {"date": "1931-10-15", "time": "01:15"},  # no place
        # city-only, so an unknown name has nothing to fall back to; with lat/lon present the
        # coordinates win and an unknown city is simply ignored.
        {"date": "1931-10-15", "time": "01:15", "city": "Atlantis"},
        {"date": "1931-10-15", "time": "01:15", "lat": 9.2881},  # lon missing
        {"date": "1931-10-15", "time": "01:15", "lat": 96.0, "lon": 79.3129},
        {"date": "1931-10-32", "time": "01:15", "city": "Chennai"},  # no 32nd of October
        {**KALAM_BIRTH, "timezone": "Mars/Olympus"},
    ]
    for body in bad_requests:
        assert client.post("/api/chart", json=body).status_code == 422, body


def test_mangal_dosha():
    body = client.post("/api/mangal-dosha", json=KALAM_BIRTH).json()
    assert set(body) == {"input", "lagna", "moon_rashi", "mars", "mangal_dosha"}
    assert body["mangal_dosha"]["present"] is True
    assert body["mars"]["sign"]["name"] == "Tula"


def test_sade_sati():
    body = client.post("/api/sade-sati", json=KALAM_BIRTH).json()
    assert set(body) == {"input", "moon_rashi", "janma_nakshatra", "sade_sati"}
    assert body["sade_sati"]["moon_sign"]["name"] == "Vrishchika"
    assert body["sade_sati"]["cycle"]["which"] in ("current", "next")


def test_matching():
    response = client.post("/api/matching", json={"boy": KALAM_BIRTH, "girl": PUNE})
    assert response.status_code == 200
    body = response.json()
    assert [k["koota"] for k in body["kootas"]] == [
        "varna", "vashya", "tara", "yoni", "graha_maitri", "gana", "bhakoot", "nadi",
    ]
    assert 0 <= body["total"] <= 36
    assert body["max_total"] == 36
    assert body["boy"]["input"]["city"] is None          # this birth is given as lat/lon
    assert body["boy"]["input"]["lat"] == KALAM.lat
    assert body["boy"]["moon_sign"]["name"] == "Vrishchika"
    assert set(body["mangal_dosha"]) == {"boy", "girl", "compatible"}
    assert client.post("/api/matching", json={"boy": KALAM_BIRTH}).status_code == 422


def test_transits():
    now = client.get("/api/transits").json()
    assert len(now["grahas"]) == 9
    assert "events" not in now

    body = client.get("/api/transits", params={"at": "2026-09-21T00:00:00Z", "rashi": "dhanu", "end": "2026-12-31T00:00:00Z"}).json()
    assert body["rashi"]["name"] == "Dhanu"
    assert body["grahas"]["Saturn"]["house"] == 4
    assert any(e["type"] == "ingress" and e["graha"]["key"] == "Jupiter" and e["to_sign"]["name"] == "Simha" for e in body["events"])
    assert all("house" in e for e in body["events"])

    assert client.get("/api/transits", params={"rashi": "ophiuchus"}).status_code == 422
    assert client.get("/api/transits", params={"at": "2026-09-21T00:00:00Z", "end": "2026-09-01T00:00:00Z"}).status_code == 422
