"""Paid-report tests for the three flat-section products, plus the shared machinery every AI-written
string goes through (the fact validator, the safety screen, the SDK wrapper, the payment gate).

The flagship ₹249 Kundali book has its own file, tests/test_kundali_book.py: it is generated part by
part against a different prompt and schema, so `kundali-report` is deliberately absent from the
product loops here. The validator fixture below still uses the book's fact set, because that is the
richest one in production and the validator is shared by the book, the flat reports and the chat.
"""

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from app.ai import report as report_module
from app.ai.client import AINotConfigured, ClaudeClient, LLMResult
from app.ai.products import PRODUCTS
from app.ai.prompts import DISCLAIMERS, INTERPRET_ONLY, SYSTEM_PROMPT, compact_json
from app.ai.report import Birth, build_data, generate_report
from app.ai.safety import screen_text
from app.ai.schema import report_schema
from app.ai.validator import check_text, collect_facts
from app.main import app

# Public reference charts - see tests/reference_charts.py. KALAM is the feature-rich primary
# (Karka lagna, Vrishchika rashi, 9 yogas, mangal dosha "high"); NEHRU is the second person for
# matching, and is also a second-Vimshottari-cycle chart. AS_OF is pinned so these do not change
# meaning as real time passes.
from tests.reference_charts import AS_OF as REFERENCE_AS_OF
from tests.reference_charts import KALAM as PRIMARY
from tests.reference_charts import NEHRU

AS_OF = REFERENCE_AS_OF.date()
KALAM = Birth(dt.date.fromisoformat(PRIMARY.request()["date"]),
              dt.time.fromisoformat(PRIMARY.request()["time"]),
              PRIMARY.request()["lat"], PRIMARY.request()["lon"],
              PRIMARY.request()["timezone"], PRIMARY.place)
NEHRU_BIRTH = Birth(dt.date.fromisoformat(NEHRU.request()["date"]),
                    dt.time.fromisoformat(NEHRU.request()["time"]),
                    NEHRU.request()["lat"], NEHRU.request()["lon"],
                    NEHRU.request()["timezone"], NEHRU.place)
KALAM_JSON = {"date": PRIMARY.request()["date"], "time": PRIMARY.request()["time"],
              "lat": PRIMARY.request()["lat"], "lon": PRIMARY.request()["lon"]}
NEHRU_JSON = {"date": NEHRU.request()["date"], "time": NEHRU.request()["time"],
              "lat": NEHRU.request()["lat"], "lon": NEHRU.request()["lon"]}



def content_for(slug: str, paragraph: str = "Guru in your chart supports steady growth through patience.") -> dict:
    """A schema-shaped, clean report body like the model would return."""
    return {
        "title": "Your report",
        "summary": "A calm, practical reading of your chart.",
        "sections": [
            {"id": section_id, "heading": section_id.replace("_", " ").title(), "paragraphs": [paragraph],
             "subsections": [], "bullets": [], "table": None}
            for section_id, _ in PRODUCTS[slug].sections
        ],
        "remedies": [
            {"title": f"Remedy {n}", "type": "mantra", "description": "Steadies the mind.",
             "how_to": "Chant Om Namah Shivaya 108 times.", "frequency": "Monday mornings"}
            for n in range(1, 7)
        ],
    }


class FakeClient:
    """Returns queued bodies in order (the last one repeats) and records every call."""

    def __init__(self, *bodies):
        self.bodies = list(bodies)
        self.calls = []

    def generate_json(self, *, system, user, schema):
        self.calls.append({"system": system, "user": user, "schema": schema})
        body = self.bodies[min(len(self.calls), len(self.bodies)) - 1]
        return LLMResult(data=json.loads(json.dumps(body)), model="claude-opus-5", stop_reason="end_turn",
                         usage={"input_tokens": 9000, "output_tokens": 7000,
                                "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
                         request_id=f"req_{len(self.calls)}")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.delenv("REPORTS_UNLOCKED", raising=False)
    for name in ("REPORT_MODEL", "REPORT_MAX_ATTEMPTS", "REPORT_EFFORT"):
        monkeypatch.delenv(name, raising=False)


# ---- prompt ----------------------------------------------------------------------------------------


def test_system_prompt_has_the_interpret_only_sentence_verbatim():
    assert INTERPRET_ONLY == (
        "Use ONLY the provided chart/transit data; do not calculate positions, dates or degrees yourself."
    )
    assert INTERPRET_ONLY in SYSTEM_PROMPT


def test_prompt_carries_the_whole_chart_language_and_sections(monkeypatch):
    fake = FakeClient(content_for("sade-sati-guide"))
    report = generate_report("sade-sati-guide", "mr", [KALAM], as_of=AS_OF, client=fake)
    call = fake.calls[0]
    assert call["system"] == SYSTEM_PROMPT and INTERPRET_ONLY in call["system"]
    _, prompt_data = build_data(PRODUCTS["sade-sati-guide"], [KALAM], AS_OF)
    assert compact_json(prompt_data) in call["user"]  # default: the compact encoding (app/ai/compact.py) - same facts
    shown = prompt_data["chart"]
    assert shown["lagna"]["sign"] == "Karka" and shown["lagna"]["degree"] == report["data"]["chart"]["lagna"]["degree_dms"]
    rows = {row["graha"]: row for row in shown["grahas (house = counted from the lagna)"]}
    assert len(rows) == 9 and rows["Guru"] == {**rows["Guru"], "sign": "Karka", "house": 1, "rules_houses": [6, 9], "in_own_sign": False}
    assert len(shown["houses"]) == 12 and len(shown["dasha"]["mahadashas [lord, start, end]"]) == 9
    current = report["data"]["chart"]["dasha"]["current"]["antardasha"]
    assert shown["dasha"]["current"]["antardasha"] == ["Budha", current["start"], current["end"]]
    assert prompt_data["names"]["signs"]["Karka"].startswith("कर्क") and prompt_data["names"]["grahas"]["Guru"].startswith("गुरु")
    assert "Marathi" in call["user"] and AS_OF.isoformat() in call["user"]
    for section_id, _ in PRODUCTS["sade-sati-guide"].sections:
        assert f"`{section_id}`" in call["user"]
    assert call["schema"] == report_schema(PRODUCTS["sade-sati-guide"])

    monkeypatch.setenv("REPORT_COMPACT_DATA", "0")  # raw engine JSON mode: the full chart, byte for byte apart from mangal wording
    raw = FakeClient(content_for("sade-sati-guide"))
    report = generate_report("sade-sati-guide", "mr", [KALAM], as_of=AS_OF, client=raw, use_cache=False)
    for key in ("lagna", "grahas", "houses", "dasha", "sade_sati"):
        assert compact_json(report["data"]["chart"][key]) in raw.calls[0]["user"], key


def test_model_never_sees_the_engines_cancelled_wording_for_a_present_mangal_dosha(monkeypatch):
    for compact in ("1", "0"):
        monkeypatch.setenv("REPORT_COMPACT_DATA", compact)
        for slug, births in (("mangal-dosha-remedy", [KALAM]), ("matching-report", [KALAM, NEHRU_BIRTH])):
            fake = FakeClient(content_for(slug))
            report = generate_report(slug, "en", births, as_of=AS_OF, client=fake, use_cache=False)
            user = fake.calls[0]["user"]
            assert "ineffective" not in user and "cancel each other" not in user and "softens the dosha" in user
            assert "present, with mitigating factors" in user
            engine_text = json.dumps(report["data"])  # the PDF / API data keeps the engine's own text
            assert "ineffective" in engine_text


def test_system_prompt_is_stable_for_prompt_caching():
    a, b = FakeClient(content_for("mangal-dosha-remedy")), FakeClient(content_for("sade-sati-guide"))
    generate_report("mangal-dosha-remedy", "en", [KALAM], as_of=AS_OF, client=a)
    generate_report("sade-sati-guide", "hi", [NEHRU_BIRTH], as_of=AS_OF, client=b)
    assert a.calls[0]["system"] == b.calls[0]["system"]


def test_schema_fits_structured_output_limits():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for banned in ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "pattern"):
                assert banned not in node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for product in PRODUCTS.values():
        if not product.book:  # the book has its own schema, checked in tests/test_kundali_book.py
            walk(report_schema(product))


# ---- report shape, as_of pinning -------------------------------------------------------------------


def test_report_shape_and_pinned_as_of():
    report = generate_report("sade-sati-guide", "en", [KALAM], as_of=AS_OF, client=FakeClient(content_for("sade-sati-guide")))
    assert set(report) == {"id", "product", "product_name", "language", "title", "summary", "sections",
                           "remedies", "disclaimer", "data", "meta"}
    assert [s["id"] for s in report["sections"]] == [s for s, _ in PRODUCTS["sade-sati-guide"].sections]
    assert report["disclaimer"] == DISCLAIMERS["en"] and "faith-based" in report["disclaimer"]
    chart = report["data"]["chart"]
    assert chart["lagna"]["sign"]["name"] == "Karka" and chart["moon_rashi"]["name"] == "Vrishchika"
    assert chart["dasha"]["as_of"] == AS_OF.isoformat() == report["meta"]["as_of"] == chart["sade_sati"]["as_of"]
    meta = report["meta"]
    assert meta["model"] == "claude-opus-5" and meta["attempts"] == 1 and meta["checks"]["clean"]
    assert meta["usage"]["output_tokens"] == 7000
    assert meta["cost_estimate_usd"] == pytest.approx(9000 * 5 / 1e6 + 7000 * 25 / 1e6)


@pytest.mark.parametrize("slug", sorted(s for s, p in PRODUCTS.items() if not p.book))
@pytest.mark.parametrize("language", ["en", "hi", "mr"])
def test_every_product_and_language_generates(slug, language):
    births = [KALAM, NEHRU_BIRTH] if PRODUCTS[slug].kind == "pair" else [KALAM]
    report = generate_report(slug, language, births, as_of=AS_OF, client=FakeClient(content_for(slug)))
    assert report["product"] == slug and report["language"] == language
    assert report["disclaimer"] == DISCLAIMERS[language]
    if slug == "matching-report":
        assert set(report["data"]) == {"boy_chart", "girl_chart", "matching"}
        assert report["data"]["matching"]["max_total"] == 36


def test_marathi_disclaimer_is_marathi_not_hindi():
    assert "आहे" in DISCLAIMERS["mr"] and " है" not in DISCLAIMERS["mr"]
    assert " है" in DISCLAIMERS["hi"] and "आहे" not in DISCLAIMERS["hi"]


# ---- safety screen ---------------------------------------------------------------------------------


@pytest.mark.parametrize("text, category", [
    ("This period carries a risk of death in the family.", "death"),
    ("Saturn here shortens longevity.", "death"),
    ("You may face a heart attack or need surgery around this time.", "illness"),
    ("There is a chance of cancer in later years.", "illness"),
    ("Beware of a road accident and a possible divorce.", "catastrophe"),
    ("Wear a blue sapphire of five carats.", "gemstone"),
    ("इस दशा में मृत्यु का भय रहेगा।", "death"),
    ("आपको कैंसर या गंभीर बीमारी हो सकती है।", "illness"),
    ("वाहन दुर्घटना और तलाक के योग हैं।", "catastrophe"),
    ("नीलम धारण करें।", "gemstone"),
    ("या काळात कुटुंबात मृत्यूची शक्यता आहे.", "death"),
    ("तुम्हाला कर्करोग किंवा हृदयविकाराचा झटका येऊ शकतो.", "illness"),
    ("वाहन अपघात आणि घटस्फोटाचे योग आहेत.", "catastrophe"),
    ("पुष्कराज रत्न धारण करा.", "gemstone"),
])
def test_safety_screen_catches_forbidden_topics_in_three_languages(text, category):
    """`gemstone` is a hit everywhere except the gemstone chapter of the flagship book, which passes
    `allow_gemstone=True` - see tests/test_kundali_book.py for that one carve-out."""
    assert category in {hit.category for hit in screen_text(text)}


@pytest.mark.parametrize("text", [
    "With Chandra in Karka (Cancer) you are caring and intuitive; a stroke of luck comes through diet and routine.",
    "Your lagna lord aids steady progress. Meet deadlines calmly and avoid heated arguments.",
    "रोज सकाळी नामस्मरण करा आणि शनिवारी गरजूंना अन्नदान करा. दिवाळीत कुटुंबासोबत वेळ घालवा.",
    "प्रतिदिन हनुमान चालीसा का स्मरण करें और शनिवार को सेवा करें।",
    "रत्नागिरी येथे जन्मलेल्या तुमच्या कुंडलीत कर्क राशीत चंद्र आहे.",
])
def test_safety_screen_leaves_normal_astrology_text_alone(text):
    assert screen_text(text) == []


def test_unsafe_output_is_regenerated_with_feedback():
    bad = content_for("sade-sati-guide")
    bad["sections"][2]["paragraphs"].append("या काळात अपघात होण्याची शक्यता आहे.")
    fake = FakeClient(bad, content_for("sade-sati-guide"))
    report = generate_report("sade-sati-guide", "mr", [KALAM], as_of=AS_OF, client=fake)
    assert len(fake.calls) == 2 and report["meta"]["attempts"] == 2
    assert "rejected by the automatic checker" in fake.calls[1]["user"] and "अपघात" in fake.calls[1]["user"]
    assert report["meta"]["checks"]["clean"]
    assert report["meta"]["usage"]["output_tokens"] == 14000  # both calls are counted in the cost


def test_unsafe_text_is_removed_when_regeneration_does_not_fix_it():
    bad = content_for("sade-sati-guide")
    bad["sections"][1]["paragraphs"].append("There is a danger of a fatal accident in 2027.")
    bad["remedies"].append({"title": "Neelam", "type": "habit", "description": "Buy a blue sapphire.",
                            "how_to": "Wear it.", "frequency": "Always"})
    fake = FakeClient(bad)
    report = generate_report("sade-sati-guide", "en", [KALAM], as_of=AS_OF, client=fake)
    assert len(fake.calls) == 2
    everything = json.dumps({k: report[k] for k in ("title", "summary", "sections", "remedies")})
    assert "fatal" not in everything and "sapphire" not in everything
    assert len(report["sections"][1]["paragraphs"]) == 1 and len(report["remedies"]) == 6
    checks = report["meta"]["checks"]
    assert not checks["clean"] and {r["type"] for r in checks["redactions"]} == {"safety"}


# ---- fact validator --------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def facts():
    """The flagship book's fact set: the richest one in production, and the one the house-convention
    and transit rules were written against. The validator itself is shared by every product."""
    from app.ai import engine_facts
    from app.ai.report import _chart, book_facts

    chart = _chart(KALAM, AS_OF)
    return book_facts({"chart": chart, **engine_facts.report_facts(chart, AS_OF)})


@pytest.fixture(scope="module")
def near_facts(facts):
    """Non-window book prose (and the chat) are checked against the birth chart plus the current
    year's transits, never against the whole twenty-year span."""
    from app.ai import engine_facts
    from app.ai.report import _chart
    from app.ai.validator import near_horizon

    return near_horizon(facts, engine_facts.report_facts(_chart(KALAM, AS_OF), AS_OF)["timeline"])


@pytest.fixture(scope="module")
def in_window(facts):
    """`in_window("Jupiter", "2026-10")` -> the facts as they are checked inside the timeline window
    that transit falls in. Timeline prose is always checked this way in production: the book spans
    about twenty years, and over twenty years a slow graha visits every sign, so an unscoped check
    would wave through any house at all."""
    from app.ai import engine_facts
    from app.ai.report import _chart
    from app.ai.validator import narrow_to_window

    windows = engine_facts.all_windows(engine_facts.report_facts(_chart(KALAM, AS_OF), AS_OF)["timeline"])
    cache = {}

    def find(graha: str, month: str):
        if (graha, month) not in cache:
            window = next(w for w in windows.values()
                          if any(t["graha"]["key"] == graha and t["date"].startswith(month)
                                 for t in w.get("transits") or []))
            cache[(graha, month)] = narrow_to_window(facts, window)
        return cache[(graha, month)]

    return find


def kinds(text, facts):
    return [issue.kind for issue in check_text(text, facts)]


def test_validator_accepts_engine_facts_in_all_date_styles(facts):
    # current antardasha is Rahu-Rahu, 2024-04-08 to 2026-12-20 (engine output for the test chart)
    good = [
        "Your Budha antardasha runs from 20 August 2026 to 25 November 2028.",
        "It ends on November 25, 2028 (2028-11-25), also written 25/11/2028.",
        "बुध अंतर्दशा 25 नवंबर 2028 को समाप्त होगी।",
        "बुधाची अंतर्दशा २५ नोव्हेंबर २०२८ रोजी संपते.",
        "In November 2028 the next period begins; 2027 is a year for steady work.",
        "Your lagna is Karka and Chandra sits in Vrishchika in the 5th house.",
        "तुमचे कर्क लग्न आहे आणि चंद्र वृश्चिक राशीत पंचम स्थानात आहे.",
        "आपका चंद्र वृश्चिक राशि में पंचम भाव में है।",
        "Shani in Dhanu in your sixth house asks for patience with daily work.",
    ]
    for text in good:
        assert check_text(text, facts) == [], text


def test_validator_catches_an_invented_dasha_date(facts):
    assert kinds("Your Budha antardasha ends on 14 March 2027.", facts) == ["date"]
    assert kinds("बुधाची अंतर्दशा 14 मार्च 2027 रोजी संपते.", facts) == ["date"]
    assert kinds("The period ends on 2028-11-26.", facts) == ["date"]
    assert kinds("Things improve from July 2099.", facts) == ["month"]  # beyond everything the book covers
    assert kinds("A turning point comes on 30 February 2027.", facts) == ["date"]


def test_validator_catches_invented_years_degrees_and_placements(facts):
    assert "year" in kinds("Expect a big change in 2150.", facts)
    assert kinds("Your Moon is at 14°05' exactly.", facts) == ["degree"]
    assert kinds("Chandra in Vrishabha makes you steady.", facts) == ["sign"]
    assert kinds("With Shani in the 10th house you work hard.", facts) == ["house"]
    assert kinds("तुमच्या कुंडलीत चंद्र वृषभ राशीत आहे.", facts) == ["sign"]
    assert kinds("शनि दशम भाव में है।", facts) == ["house"]
    assert kinds("Your lagna is Mesha, which gives drive.", facts) == ["lagna"]


def test_validator_catches_a_false_own_sign_claim(near_facts, in_window):
    """Checked against the near horizon, which is what non-window book prose and the chat both use.
    The rule reads in-scope transits for slow grahas, so the scope is part of the guarantee."""
    wrong = [
        "त्याचा स्वामी शनी षष्ठ भावात स्वतःच्याच धनु राशीत बसलेला आहे.",  # Dhanu belongs to Guru, not Shani
        "Shani sits in the sixth house in its own sign Dhanu.",
        "Chandra is in Vrishchika, Shani's own sign.",
        "With Guru (your 6th lord) placed strongly in its own sign in the 1st house, growth follows.",  # live chat, run 2
        "Guru aapka 6th lord hai aur apni hi rashi Vrishchika mein baitha hai.",
        "गुरू प्रथम भावात स्वराशीत आहे.",
    ]
    for text in wrong:
        assert kinds(text, near_facts) == ["dignity"], text
    right = [
        "Shukra sits in the fourth house in Tula (Libra), Venus's own sign.", "Shukra is in its own sign Tula.",
        "शुक्र चतुर्थ भावात स्वतःच्याच तूळ राशीत बसलेला आहे.", "शुक्र चतुर्थ भाव में अपनी ही तुला राशि में है।",
        "शुक्र इथे स्वतःच्या राशीत आहे, कारण तूळ राशीचा स्वामी शुक्रच आहे.", "Shukra apni hi rashi Tula mein hai.",
        "Mangal sits with Shukra, who is in its own sign.",
        "You like to make your own decisions and keep your own house in order.",
        # both cost a needless regeneration in a live run before the rule was made precision-first:
        "Shukra sits with Mangal in the fourth house in Tula, in its own sign, which gives staying power.",
        "Guru moves through Chandra's own sign that year.",
    ]
    for text in right:
        assert check_text(text, near_facts) == [], text
    # A 2031 transit SIGN is not in the near horizon, so naming it outside a window fails; prose that
    # wants to talk about 2031 belongs in a 2031 window, and there it passes. Note the guarantee is
    # about the PLACEMENT, not the date - see the KNOWN LIMIT in tests/test_historical_defects.py.
    far = "Guru settles into Dhanu on 17 February 2031, lifting confidence through Chandra's own sign."
    assert kinds(far, near_facts) == ["sign"]
    assert check_text(far, in_window("Jupiter", "2031-10")) == []


def test_validator_separates_birth_chart_placements_from_transits(facts, in_window):
    guru_2026 = in_window("Jupiter", "2026-10")
    # live Marathi report at effort low claimed "पंचम भावात धनु राशीत गुरू, चंद्र आणि शुक्र एकत्र" - Guru only *transits* Dhanu
    assert kinds("सिंह राशीत गुरू आणि चंद्र एकत्र असल्यामुळे शिक्षण केंद्रस्थानी आहे.", facts) == ["sign"]
    assert kinds("With Guru in Simha alongside the Moon you are wise.", facts) == ["sign"]
    for transit in ["Guru enters Karka on 25 January 2027, a supportive shift.",
                    "25 जानेवारी 2027 रोजी गुरू कर्क राशीत प्रवेश करतो.",
                    "Guru sits in the 1st house in Karka."]:
        assert check_text(transit, guru_2026) == [], transit
    assert check_text("Shani is currently in Meena, the 4th from your Moon.",
                      in_window("Saturn", "2027-06")) == []
    # a transit that is real, but not in THIS window: the window is the unit, so it is still rejected
    assert kinds("Shani enters Mesha in this window.", guru_2026) == ["sign"]
    assert kinds("Guru moves into Kanya this month.", guru_2026) == ["sign"]
    assert kinds("Guru in Mesha from 31 October 2026 helps.", guru_2026) == ["sign"]


def test_lordships_are_derived_from_the_engine_and_sent_to_the_model():
    fake = FakeClient(content_for("sade-sati-guide"))
    report = generate_report("sade-sati-guide", "en", [KALAM], as_of=AS_OF, client=fake)
    table = report["data"]["lordships"]
    assert table["Jupiter"] == {"rules_houses": [6, 9], "in_own_sign": False, "sign_lord": "Moon"}
    assert table["Saturn"] == {"rules_houses": [7, 8], "in_own_sign": False, "sign_lord": "Jupiter"}
    assert table["Sun"]["rules_houses"] == [2] and table["Rahu"]["rules_houses"] == []
    assert '"rules_houses":[6,9],"in_own_sign":false' in fake.calls[0]["user"] and "`rules_houses`" in SYSTEM_PROMPT


def test_rejected_drafts_are_recorded_for_monitoring():
    bad = content_for("sade-sati-guide")
    bad["sections"][2]["paragraphs"].append("Shani sits in the sixth house in its own sign Dhanu.")
    report = generate_report("sade-sati-guide", "en", [KALAM], as_of=AS_OF, client=FakeClient(bad, content_for("sade-sati-guide")))
    (draft,) = report["meta"]["checks"]["rejected_drafts"]
    assert draft["attempt"] == 1 and draft["problems"][0]["kind"] == "dignity" and report["meta"]["checks"]["clean"]
    # A dignity claim that survives the retry is CUT, not shipped with a warning attached. This test
    # asserted the opposite until 2026-09-22, when `dignity` was promoted out of SOFT_KINDS: the soft
    # treatment let "Guru ... in Karka, its own sign of exaltation" reach a delivered book with the
    # checker's own diagnosis sitting in the same file. Dhanu belongs to Guru, not Shani, so this is
    # a factual error about the customer's chart in a product sold on accuracy - losing the paragraph
    # is the cheaper mistake. See validator.REDACT_KINDS for the measurement that justified the change.
    stubborn = generate_report("sade-sati-guide", "hi", [KALAM], as_of=AS_OF, client=FakeClient(bad))
    checks = stubborn["meta"]["checks"]
    assert checks["warnings"] == [] and checks["redactions"][0]["kind"] == "dignity"
    assert "own sign Dhanu" not in json.dumps(stubborn["sections"])


def test_houses_are_counted_from_the_lagna_unless_the_text_says_from_the_moon(facts, in_window):
    guru_2026, shani_2027 = in_window("Jupiter", "2026-10"), in_window("Saturn", "2027-06")
    # live chat defect found by the team lead: Simha is this chart's LAGNA (1st house); it is 9th only
    # from the Dhanu Moon
    wrong = [
        ("Guru also enters your 9th house transit-wise around 25 January 2027.", "house", guru_2026),
        ("Guru bhi 25 January 2027 ko aapke 9th house (Karka) mein pravesh karega.", "house_sign", guru_2026),
        ("25 जानेवारी 2027 रोजी गुरू कर्क राशीत, म्हणजे नवम भावात प्रवेश करतो.", "house_sign", guru_2026),
        ("Your 9th house is Karka, so fortune matters to you.", "house_sign", facts),
        ("नवम भाव कर्क राशीचा आहे.", "house_sign", facts),
    ]
    for text, kind, checker in wrong:
        assert kind in kinds(text, checker), text
    right = [
        ("Guru enters Karka, your 1st house (9th from your Moon sign), on 25 January 2027.", guru_2026),
        ("On 25 January 2027 Guru enters your 1st house, Karka, which is the 9th from Chandra.", guru_2026),
        ("Guru 25 January 2027 ko Karka mein, yaani chandra se 9th house mein pravesh karega.", guru_2026),
        ("25 जानेवारी 2027 रोजी गुरू कर्क राशीत, म्हणजे लग्नस्थानात (चंद्रापासून नवम भावात) प्रवेश करतो.", guru_2026),
        
        ("Your 4th house is Tula (Libra), ruled by Shukra.", facts),
        ("Guru rules your 6th and 9th houses and sits in Karka in the 1st house.", facts),
        ("चतुर्थ भाव तूळ राशीचा असून त्याचा स्वामी शुक्र चतुर्थ भावात आहे.", facts),
    ]
    for text, checker in right:
        assert check_text(text, checker) == [], text


def test_a_present_mangal_dosha_is_mitigated_never_cancelled(facts):
    for text in ["तुमच्या कुंडलीतील मंगळ दोष प्रभावहीन ठरतो.", "So the dosha is cancelled for your chart.", "इसलिए आपका मंगल दोष रद्द हो जाता है।"]:
        assert kinds(text, facts) == ["wording"], text
    for text in ["गुरूच्या प्रभावामुळे मंगळ दोष बराच सौम्य होतो.", "The mitigating factors soften the dosha considerably.",
                 "The dosha is not cancelled, only softened.", "हा दोष नाहीसा होत नाही, पण सौम्य होतो."]:
        assert check_text(text, facts) == [], text
    # cosmetic: never worth a second paid generation of a whole report - it is reported as a warning instead
    body = content_for("sade-sati-guide")
    body["sections"][3]["paragraphs"].append("So the dosha is cancelled for your chart.")
    fake = FakeClient(body)
    report = generate_report("sade-sati-guide", "en", [KALAM], as_of=AS_OF, client=fake, use_cache=False)
    assert len(fake.calls) == 1 and report["meta"]["checks"]["warnings"][0]["kind"] == "wording"


def test_invented_date_triggers_regeneration_then_redaction():
    bad = content_for("sade-sati-guide")
    bad["sections"][4]["paragraphs"].append("Your Rahu antardasha ends on 14 March 2027.")
    fixed = FakeClient(bad, content_for("sade-sati-guide"))
    report = generate_report("sade-sati-guide", "en", [KALAM], as_of=AS_OF, client=fixed)
    assert len(fixed.calls) == 2 and "14 March 2027" in fixed.calls[1]["user"] and report["meta"]["checks"]["clean"]

    stubborn = FakeClient(bad)
    report = generate_report("sade-sati-guide", "hi", [KALAM], as_of=AS_OF, client=stubborn)
    assert "14 March 2027" not in json.dumps(report["sections"])
    assert report["meta"]["checks"]["redactions"][0]["kind"] == "date"


def test_stray_markup_is_stripped_from_ai_text():
    body = content_for("sade-sati-guide")
    body["summary"] = "A calm reading of your chart.</p>"  # seen in a live run
    body["sections"][0]["paragraphs"] = ["**Simha** lagna gives <b>dignity</b>.", "## Heading\nGuru 4 < 5 houses away is fine."]
    report = generate_report("sade-sati-guide", "en", [KALAM], as_of=AS_OF, client=FakeClient(body))
    assert report["summary"] == "A calm reading of your chart."
    assert report["sections"][0]["paragraphs"] == ["Simha lagna gives dignity.", "Heading\nGuru 4 < 5 houses away is fine."]
    assert report["sections"][0]["id"] == "status" and report["remedies"][0]["type"] == "mantra"


def test_missing_sections_are_rejected():
    from app.ai.client import AIBadOutput

    broken = content_for("sade-sati-guide")
    del broken["sections"][3]
    with pytest.raises(AIBadOutput):
        generate_report("sade-sati-guide", "en", [KALAM], as_of=AS_OF, client=FakeClient(broken))


# ---- cache -----------------------------------------------------------------------------------------


def test_cache_hit_avoids_a_second_ai_call(tmp_path):
    fake = FakeClient(content_for("sade-sati-guide"))
    first = generate_report("sade-sati-guide", "en", [KALAM], as_of=AS_OF, client=fake)
    second = generate_report("sade-sati-guide", "en", [KALAM], as_of=AS_OF, client=fake)
    assert len(fake.calls) == 1
    assert second["meta"]["cache_hit"] is True and first["meta"]["cache_hit"] is False
    assert second["id"] == first["id"] and second["sections"] == first["sections"]
    assert (tmp_path / "reports" / f"{first['id']}.json").is_file()
    # a different language, product or as_of date is a different report
    generate_report("sade-sati-guide", "mr", [KALAM], as_of=AS_OF, client=fake)
    generate_report("sade-sati-guide", "en", [KALAM], as_of=AS_OF + dt.timedelta(days=1), client=fake)
    assert len(fake.calls) == 3


# ---- API -------------------------------------------------------------------------------------------

http = TestClient(app)
# A flat-section product: the flagship book's own HTTP round-trip lives in tests/test_kundali_book.py.
BODY = {"product": "sade-sati-guide", "language": "mr", "birth": KALAM_JSON, "as_of": AS_OF.isoformat()}
BOOK_BODY = {"product": "kundali-report", "language": "mr", "birth": KALAM_JSON, "as_of": AS_OF.isoformat()}


def use_fake(monkeypatch, fake):
    monkeypatch.setattr(report_module, "ClaudeClient", lambda settings=None: fake)


@pytest.mark.parametrize("body", [BODY, BOOK_BODY])
def test_report_endpoint_is_locked_by_default(monkeypatch, body):
    fake = FakeClient(content_for("sade-sati-guide"))
    use_fake(monkeypatch, fake)
    response = http.post("/api/report", json=body)
    assert response.status_code == 402
    assert response.json()["detail"]["error"] == "payment_required"
    assert fake.calls == []  # no AI spend for an unpaid caller, book or flat report


def test_report_endpoint_when_unlocked_and_redownload(monkeypatch):
    monkeypatch.setenv("REPORTS_UNLOCKED", "1")
    fake = FakeClient(content_for("sade-sati-guide"))
    use_fake(monkeypatch, fake)
    response = http.post("/api/report", json=BODY)
    assert response.status_code == 200
    report = response.json()
    assert report["language"] == "mr" and report["data"]["chart"]["input"]["date"] == PRIMARY.request()["date"]
    again = http.get(f"/api/report/{report['id']}")
    assert again.status_code == 200 and again.json()["sections"] == report["sections"]
    assert len(fake.calls) == 1
    monkeypatch.delenv("REPORTS_UNLOCKED")
    assert http.get(f"/api/report/{report['id']}").status_code == 402
    assert http.get("/api/report/" + "0" * 32).status_code == 404


def test_entitlement_hook_unlocks_without_the_env_flag(monkeypatch):
    from app.ai import entitlement

    seen = {}

    def paid(request, product, report_id=None):
        seen.update(product=product, report_id=report_id)
        return True

    monkeypatch.setattr(entitlement, "is_entitled", paid)
    use_fake(monkeypatch, FakeClient(content_for("matching-report")))
    body = {"product": "matching-report", "language": "hi", "boy": KALAM_JSON, "girl": NEHRU_JSON}
    response = http.post("/api/report", json=body)
    assert response.status_code == 200 and response.json()["id"] == seen["report_id"]
    assert seen["product"] == "matching-report"


def test_report_endpoint_validates_input(monkeypatch):
    monkeypatch.setenv("REPORTS_UNLOCKED", "1")
    assert http.post("/api/report", json={**BODY, "language": "fr"}).status_code == 422
    assert http.post("/api/report", json={**BODY, "product": "free-lunch"}).status_code == 422
    assert http.post("/api/report", json={"product": "matching-report", "birth": KALAM_JSON}).status_code == 422
    assert http.post("/api/report", json={"product": "kundali-report", "boy": KALAM_JSON}).status_code == 422


def test_missing_api_key_is_a_clean_503(monkeypatch, tmp_path):
    monkeypatch.setenv("REPORTS_UNLOCKED", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))  # no `ant auth login` profile either
    with pytest.raises(AINotConfigured):
        ClaudeClient()
    response = TestClient(app, raise_server_exceptions=False).post("/api/report", json=BODY)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "ai_not_configured" and "Traceback" not in response.text
    assert "ANTHROPIC_API_KEY" not in response.text  # internals stay in the log, not in the customer's browser


# ---- real client wrapper (SDK stubbed or pointed at a closed local port; still no network) ---------


class _Block:
    def __init__(self, type, text=""):
        self.type, self.text = type, text


class _Message:
    def __init__(self, stop_reason="end_turn", text='{"ok": true}'):
        self.stop_reason, self.model, self._request_id = stop_reason, "claude-opus-5", "req_x"
        self.content = [_Block("thinking"), _Block("text", text)]
        self.usage = type("U", (), {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": None,
                                    "cache_read_input_tokens": 3})()


class _Stream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class _StubSDK:
    def __init__(self, message):
        self.requests = []
        outer = self

        class _Messages:
            def stream(self, **kwargs):
                outer.requests.append(kwargs)
                return _Stream(message)

        self.messages = _Messages()
        self.beta = type("Beta", (), {"messages": _Messages()})()


def real_client(monkeypatch, message=None, **env):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    client = ClaudeClient()
    if message is not None:
        client._client = _StubSDK(message)
    return client


def test_default_report_model_is_sonnet_5(monkeypatch):
    from app.ai.config import get_settings

    assert get_settings().model == "claude-sonnet-5"  # the chosen default; REPORT_MODEL overrides


def test_client_request_uses_structured_outputs_thinking_caching_and_fallbacks(monkeypatch):
    client = real_client(monkeypatch, _Message(), REPORT_MODEL="claude-opus-5")  # fallbacks are an Opus/Fable feature
    schema = report_schema(PRODUCTS["sade-sati-guide"])
    result = client.generate_json(system=SYSTEM_PROMPT, user="hello", schema=schema)
    assert result.data == {"ok": True} and result.request_id == "req_x"
    assert result.usage == {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 3}
    (request,) = client._client.requests
    assert request["model"] == "claude-opus-5" and request["max_tokens"] == 32000
    assert request["output_config"] == {"format": {"type": "json_schema", "schema": schema}, "effort": "medium"}
    assert request["thinking"] == {"type": "adaptive"}
    assert request["system"] == [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    assert request["fallbacks"] == "default" and request["betas"] == ["server-side-fallback-2026-07-01"]


def test_client_model_is_configurable_and_sonnet_skips_the_fallback_beta(monkeypatch):
    client = real_client(monkeypatch, _Message(), REPORT_MODEL="claude-sonnet-5", REPORT_EFFORT="low")
    client.generate_json(system="s", user="u", schema={})
    (request,) = client._client.requests
    assert request["model"] == "claude-sonnet-5" and request["output_config"]["effort"] == "low"
    assert "fallbacks" not in request and "betas" not in request


@pytest.mark.parametrize("message", [_Message("refusal"), _Message("max_tokens"), _Message(text="not json")])
def test_client_rejects_refusals_truncation_and_bad_json(monkeypatch, message):
    from app.ai.client import AIBadOutput

    with pytest.raises(AIBadOutput):
        real_client(monkeypatch, message).generate_json(system="s", user="u", schema={})


def test_sdk_accepts_our_request_and_connection_failure_is_a_clean_503(monkeypatch):
    """Real SDK, pointed at a closed local port: proves the kwargs are valid for anthropic 1.x and that
    an outage surfaces as 503, not a stack trace."""
    from app.ai.client import AIUnavailable

    env = {"ANTHROPIC_BASE_URL": "http://127.0.0.1:9", "REPORT_API_RETRIES": "0", "REPORT_TIMEOUT_SECONDS": "5"}
    client = real_client(monkeypatch, **env)
    with pytest.raises(AIUnavailable):
        client.generate_json(system=SYSTEM_PROMPT, user="hi", schema=report_schema(PRODUCTS["sade-sati-guide"]))
    monkeypatch.setenv("REPORTS_UNLOCKED", "1")
    response = TestClient(app, raise_server_exceptions=False).post("/api/report", json=BODY)
    assert response.status_code == 503 and response.json()["detail"]["error"] == "ai_unavailable"


def test_own_sign_check_reads_the_sign_at_the_phrase_not_any_sign_in_the_sentence(facts):
    """Live regression: "Simha lagna with Shani seated firmly in its own sign in the 7th house" was
    rejected because Simha - the LAGNA, mentioned in passing - was read as the subject of the claim.
    Shani genuinely is in its own sign, and the false positive failed a whole part three times."""
    for true_claim in [
        "This is a chart built around Karka lagna with Shukra seated firmly in its own sign in the "
        "4th house, so comfort matters.",
        "With Karka rising and Chandra in Vrishchika, Shukra in its own sign steadies the 4th.",
        "Mangal sits with Shukra, who is in its own sign.",
    ]:
        assert check_text(true_claim, facts) == [], true_claim
    # a sign sitting AT the phrase is still the subject, and still checked
    for wrong in ["Chandra is in Vrishchika, Shani's own sign.",
                  "Shani sits in the sixth house in its own sign Dhanu."]:
        assert kinds(wrong, facts) == ["dignity"], wrong


def test_a_negated_dignity_claim_is_not_a_claim(facts):
    """"Mangal is NOT in its own sign" is true of this chart. Flagging it cost two paid retries."""
    for negated in ["Mangal is not in its own sign, nor in Makara where it would sit steady.",
                    "Mangal is not sitting in its own sign or in Makara; it occupies Karka.",
                    "मंगळ स्वतःच्या राशीत नाही."]:
        assert check_text(negated, facts) == [], negated
