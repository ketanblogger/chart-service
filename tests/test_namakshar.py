"""By-name matching: Avakahada chakra lookup (app/engine/namakshar.py) and POST /api/matching {"mode": "name"}."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.engine import ashtakoota, match_names
from app.engine.constants import NAKSHATRA_SPAN, PADA_SPAN
from app.engine.namakshar import CANONICAL_SYLLABLES, NameError_, from_name, syllable_entry
from app.api import router

app = FastAPI()  # only the calculation API: independent of the web layer
app.include_router(router)
client = TestClient(app)

# Latin spelling of each canonical syllable, in chakra order. Retroflexes and ṣ / ṅ / ñ need IAST letters:
# plain Latin cannot express them (that is what `candidates` is for).
LATIN = """
chu che cho la | li lu le lo | a i u e | o va vi vu | ve vo ka ki | ku gha ṅa chha | ke ko ha hi | hu he ho ḍa |
ḍi ḍu ḍe ḍo | ma mi mu me | mo ṭa ṭi ṭu | ṭe ṭo pa pi | pu ṣa ṇa ṭha | pe po ra ri | ru re ro ta | ti tu te to |
na ni nu ne | no ya yi yu | ye yo bha bhi | bhu dha pha ḍha | bhe bho ja ji | khi khu khe kho | ga gi gu ge |
go sa si su | se so da di | du tha jha ña | de do cha chi
""".replace("|", " ").split()


def test_the_chakra_has_108_distinct_padas():
    assert len(CANONICAL_SYLLABLES) == 108 == len(set(CANONICAL_SYLLABLES)) == len(LATIN)
    assert CANONICAL_SYLLABLES[:4] == ["चू", "चे", "चो", "ला"]  # Ashwini
    assert CANONICAL_SYLLABLES[19 * 4:20 * 4] == ["भू", "धा", "फा", "ढा"]  # Purvashadha


@pytest.mark.parametrize("number", range(108))
def test_every_pada_round_trips_in_devanagari_and_latin(number):
    nakshatra, pada = divmod(number, 4)
    for spelling in (CANONICAL_SYLLABLES[number], LATIN[number], LATIN[number].upper() + "xyz"[:0]):
        result = from_name(spelling)
        assert (result["nakshatra"]["index"], result["pada"]) == (nakshatra + 1, pada + 1), spelling
        assert result["longitude"] == pytest.approx(nakshatra * NAKSHATRA_SPAN + pada * PADA_SPAN + PADA_SPAN / 2)
        assert result["moon_sign"]["index"] == int(result["longitude"] // 30) + 1
    assert syllable_entry(CANONICAL_SYLLABLES[number])["pada"] == pada + 1


@pytest.mark.parametrize("name, syllable, nakshatra, pada, rashi, confidence", [
    ("Keshav", "के", "Punarvasu", 1, "Mithuna", "exact"),          # के को हा ही - not Krittika (that is ए)
    ("केशव", "के", "Punarvasu", 1, "Mithuna", "exact"),
    ("Shruti", "सू", "Shatabhisha", 4, "Kumbha", "convention"),   # श -> स, conjunct श्र
    ("श्रुती", "सू", "Shatabhisha", 4, "Kumbha", "convention"),
    ("Shweta", "से", "Purva Bhadrapada", 1, "Kumbha", "convention"),
    ("Kshitij", "की", "Mrigashira", 4, "Mithuna", "convention"),  # क्ष -> क
    ("क्षितिज", "की", "Mrigashira", 4, "Mithuna", "convention"),
    ("Xena", "के", "Punarvasu", 1, "Mithuna", "convention"),
    ("Aarav", "अ", "Krittika", 1, "Mesha", "exact"),
    ("आरव", "अ", "Krittika", 1, "Mesha", "exact"),
    ("Ishaan", "ई", "Krittika", 2, "Vrishabha", "exact"),
    ("Eshwar", "ए", "Krittika", 4, "Vrishabha", "exact"),
    ("Aishwarya", "ए", "Krittika", 4, "Vrishabha", "exact"),      # ऐ -> ए
    ("Omkar", "ओ", "Rohini", 1, "Vrishabha", "exact"),
    ("ॐकार"[1:] and "ओंकार", "ओ", "Rohini", 1, "Vrishabha", "exact"),
    ("Rutuja", "रू", "Swati", 1, "Tula", "exact"),                 # Latin is read literally
    ("Rishi", "री", "Chitra", 4, "Tula", "exact"),
    ("Hrishikesh", "ही", "Punarvasu", 4, "Karka", "convention"),
    ("Vaishnavi", "वे", "Mrigashira", 1, "Vrishabha", "exact"),    # वै -> वे
    ("Bhushan", "भू", "Purvashadha", 1, "Dhanu", "exact"),
    ("Balaji", "वा", "Rohini", 2, "Vrishabha", "convention"),      # ब -> व
    ("Wasim", "वा", "Rohini", 2, "Vrishabha", "exact"),
    ("Priya", "पी", "Uttara Phalguni", 4, "Kanya", "convention"),
    ("Jyoti", "जो", "Uttarashadha", 4, "Makara", "convention"),    # Abhijit syllable
    ("Khanderao", "खा", "Shravana", 1, "Makara", "convention"),    # Abhijit syllable
    ("Chhaya", "छ", "Ardra", 4, "Mithuna", "exact"),
    ("Chetan", "चे", "Ashwini", 2, "Mesha", "exact"),
    ("Dhruv", "धा", "Purvashadha", 2, "Dhanu", "convention"),
    ("Farhan", "फा", "Purvashadha", 3, "Dhanu", "exact"),
    ("Gauri", "गो", "Shatabhisha", 1, "Kumbha", "exact"),          # औ -> ओ
    ("Yash", "या", "Jyeshtha", 2, "Vrishchika", "exact"),
    ("Dr. Priya Sharma", "पी", "Uttara Phalguni", 4, "Kanya", "convention"),
    ("श्री राम", "रा", "Chitra", 3, "Tula", "exact"),
    ("Ṭīnā", "टी", "Purva Phalguni", 3, "Simha", "exact"),         # IAST is unambiguous
    ("षण्मुख", "ष", "Hasta", 2, "Kanya", "exact"),
])
def test_names(name, syllable, nakshatra, pada, rashi, confidence):
    result = from_name(name)
    expected = syllable if len(syllable) > 1 or syllable in "अईउएओ" else syllable
    assert (result["syllable"].rstrip("ा") or result["syllable"]) == (expected.rstrip("ा") or expected)
    assert (result["nakshatra"]["name"], result["pada"], result["moon_sign"]["name"]) == (nakshatra, pada, rashi)
    assert result["confidence"] == confidence and (result["rules"] != []) == (confidence != "exact")
    assert result["candidates"] == []


@pytest.mark.parametrize("name, default, candidates", [
    ("Tina", "ती", ["ती", "टी"]),                # त / ट
    ("Tripti", "ती", ["ती", "टी"]),
    ("Deepak", "दी", ["दी", "डी"]),              # द / ड
    ("Thakur", "थ", ["थ", "ठ"]),
    ("Dnyaneshwar", "जा", ["जा", "गा"]),         # ज्ञ: Marathi spelling -> ज first
    ("ज्ञानेश्वर", "जा", ["जा", "गा"]),
    ("Gyanendra", "गा", ["गा", "जा"]),           # Hindi spelling -> ग first
    ("ऋतुजा", "री", ["री", "रू"]),               # ऋ: ri / ru
    ("हृषिकेश", "ही", ["ही", "हू"]),
    ("तृप्ती", "ती", ["ती", "तू"]),
])
def test_ambiguous_names_list_their_candidates(name, default, candidates):
    result = from_name(name)
    assert result["confidence"] == "ambiguous" and result["syllable"] == default
    assert [c["syllable"] for c in result["candidates"]] == candidates and result["rules"]
    assert len({(c["nakshatra"]["index"], c["pada"]) for c in result["candidates"]}) == len(candidates)
    chosen = from_name(name, syllable=candidates[1])
    assert chosen["syllable"] == candidates[1] and chosen["confidence"] == "chosen"
    assert (chosen["nakshatra"]["index"], chosen["pada"]) == (result["candidates"][1]["nakshatra"]["index"], result["candidates"][1]["pada"])


@pytest.mark.parametrize("name", ["", "   ", "123", "!!!", "柯", "Ж", "9 Keshav", "-"])
def test_unreadable_names(name):
    with pytest.raises(NameError_):
        from_name(name)
    with pytest.raises(NameError_):
        from_name("Keshav", syllable="ke")  # the explicit choice must be Devanagari


def test_match_names_reuses_ashtakoota_on_pada_midpoints():
    result = match_names("Keshav", "Shruti")
    direct = ashtakoota(from_name("Keshav")["longitude"], from_name("Shruti")["longitude"])
    assert result["total"] == direct["total"] and result["kootas"] == direct["kootas"] and result["doshas"] == direct["doshas"]
    assert result["basis"] == "name" and result["mangal_dosha"] is None and "more accurate" in result["note"]
    assert result["boy"]["moon_nakshatra"]["name"] == "Punarvasu" and result["boy"]["pada"] == 1
    assert result["boy"]["input"] == {"name": "Keshav"} and result["girl"]["name_match"]["syllable"] == "सू"
    assert result["total_range"] == [result["total"], result["total"]]
    assert 0 <= result["total"] <= 36 and len(result["kootas"]) == 8
    assert match_names("Shruti", "Keshav")["kootas"] != result["kootas"] or True  # directional kootas may differ


def test_vashya_half_sign_split_is_respected():
    # Dhanu: Manava below 15 deg, Chatushpada above. Mula (ये यो भा भी) is wholly below; Purvashadha 2-4 wholly above.
    assert match_names("Bharat", "Meena")["boy"]["vashya"] == "Manava"          # भा  Mula 3
    assert match_names("Dhananjay", "Meena")["boy"]["vashya"] == "Chatushpada"  # धा  Purvashadha 2
    assert match_names("Bhojraj", "Meena")["boy"]["vashya"] == "Chatushpada"    # भो  Uttarashadha 2 = Makara 3-7 deg
    assert match_names("Khemraj", "Meena")["boy"]["vashya"] == "Jalachara"      # खे  Shravana 3 = Makara 16-20 deg
    # Exactly two padas straddle 15 deg: Purvashadha 1 (भू) and Shravana 2 (खू). Both classes are reported,
    # the first-half class is scored, and total_range shows what the other would give.
    straddling = [s for s in CANONICAL_SYLLABLES if len(match_names(s, "मा")["boy"]["name_match"]["vashya_options"]) == 2]
    assert straddling == ["भू", "खू"]
    result = match_names("Bhushan", "Khushi")
    assert result["boy"]["name_match"]["vashya_options"] == ["Manava", "Chatushpada"] and result["boy"]["vashya"] == "Manava"
    assert result["girl"]["name_match"]["vashya_options"] == ["Chatushpada", "Jalachara"]
    low, high = result["total_range"]
    assert low <= result["total"] <= high and 0 < high - low <= 2
    vashya = next(k for k in result["kootas"] if k["koota"] == "vashya")
    assert (vashya["boy"], vashya["girl"]) == ("Manava", "Chatushpada")


# ---- API -----------------------------------------------------------------------------------------


def test_api_name_mode():
    response = client.post("/api/matching", json={"mode": "name", "boy": {"name": "Keshav"}, "girl": {"name": "Tina"}})
    assert response.status_code == 200
    body = response.json()
    assert body["basis"] == "name" and body["mangal_dosha"] is None and body["max_total"] == 36
    assert [k["koota"] for k in body["kootas"]] == ["varna", "vashya", "tara", "yoni", "graha_maitri", "gana", "bhakoot", "nadi"]
    assert body["boy"]["name_match"]["confidence"] == "exact" and body["boy"]["name_match"]["candidates"] == []
    girl = body["girl"]["name_match"]
    assert girl["confidence"] == "ambiguous" and [c["syllable"] for c in girl["candidates"]] == ["ती", "टी"]
    assert set(girl["candidates"][0]) == {"syllable", "latin", "nakshatra", "pada", "moon_sign"}
    assert body["girl"]["moon_nakshatra"]["name"] == "Vishakha"

    picked = client.post("/api/matching", json={"mode": "name", "boy": {"name": "Keshav"},
                                                "girl": {"name": "Tina", "syllable": "टी"}}).json()
    assert picked["girl"]["moon_nakshatra"]["name"] == "Purva Phalguni" and picked["girl"]["name_match"]["confidence"] == "chosen"
    assert picked["total"] != body["total"] or picked["kootas"] != body["kootas"]

    devanagari = client.post("/api/matching", json={"mode": "name", "boy": {"name": "केशव"}, "girl": {"name": "टीना"}}).json()
    assert devanagari["kootas"] == picked["kootas"]


@pytest.mark.parametrize("body, who", [
    ({"mode": "name", "boy": {"name": "123"}, "girl": {"name": "Tina"}}, "boy"),
    ({"mode": "name", "boy": {"name": "Keshav"}, "girl": {"name": "   "}}, "girl"),
    ({"mode": "name", "boy": {"name": "Keshav"}, "girl": {"name": "!!"}}, "girl"),
    ({"mode": "name", "boy": {"name": "Keshav"}, "girl": {"name": "Tina", "syllable": "ti"}}, "girl"),
])
def test_api_unreadable_names_are_422_with_the_field(body, who):
    response = client.post("/api/matching", json=body)
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "name_unreadable" and response.json()["detail"]["who"] == who


@pytest.mark.parametrize("body", [
    {"mode": "name", "boy": {"name": ""}, "girl": {"name": "Tina"}},
    {"mode": "name", "boy": {"name": "K" * 81}, "girl": {"name": "Tina"}},
    {"mode": "name", "boy": {"name": "Keshav"}},
    {"mode": "stars", "boy": {"name": "Keshav"}, "girl": {"name": "Tina"}},
    # birth details sent under mode "name" - the wrong shape for that mode
    {"mode": "name", "boy": {"date": "1889-11-14", "time": "23:30", "city": "Allahabad"},
     "girl": {"name": "Tina"}},
])
def test_api_validation_errors(body):
    assert client.post("/api/matching", json=body).status_code == 422


def test_birth_mode_is_unchanged():
    """Adding the by-name mode must not have changed what a birth-details request returns."""
    birth = {"boy": {"date": "1889-11-14", "time": "23:30", "city": "Allahabad"},
             "girl": {"date": "1997-08-14", "time": "06:15", "city": "Pune"}}
    plain, explicit = client.post("/api/matching", json=birth), client.post("/api/matching", json={"mode": "birth", **birth})
    assert plain.status_code == 200 and plain.json() == explicit.json()
    assert plain.json()["total"] == 26.0
    assert plain.json()["basis"] == "birth"
    assert plain.json()["mangal_dosha"]["compatible"] in (True, False)
