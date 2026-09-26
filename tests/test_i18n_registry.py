"""The URL registry (app/web/i18n.py): SEO map paths, round-trips, hreflang sets, legacy redirects."""

import pytest

from app.web import i18n


def test_paths_are_exactly_the_seo_map():
    expected = {
        ("home", "en"): "/", ("home", "hi"): "/hi/", ("home", "mr"): "/mr/",
        ("kundali", "en"): "/birth-chart", ("kundali", "hi"): "/hi/kundli", ("kundali", "mr"): "/mr/kundali",
        ("matching", "en"): "/horoscope-matching", ("matching", "hi"): "/hi/kundali-matching",
        ("matching", "mr"): "/mr/patrika-matching",
        ("mangal-dosha", "en"): "/mangal-dosha", ("mangal-dosha", "hi"): "/hi/mangal-dosha",
        ("mangal-dosha", "mr"): "/mr/mangal-dosha",
        ("sade-sati", "en"): "/sade-sati", ("sade-sati", "hi"): "/hi/sade-sati", ("sade-sati", "mr"): "/mr/sade-sati",
        ("consultation", "en"): "/ai-astrologer", ("consultation", "hi"): "/hi/ai-jyotish",
        ("consultation", "mr"): "/mr/ai-jyotish",
        ("rashifal-hub", "en"): "/horoscope", ("rashifal-hub", "hi"): "/hi/rashifal",
        ("rashifal-hub", "mr"): "/mr/rashi-bhavishya",
        ("rashifal-weekly", "en"): "/horoscope/weekly", ("rashifal-weekly", "hi"): "/hi/rashifal/saptahik",
        ("rashifal-weekly", "mr"): "/mr/rashi-bhavishya/saptahik",
    }
    for (key, lang), path in expected.items():
        assert i18n.url_for(key, lang) == path


def test_rashifal_paths_per_language():
    assert i18n.url_for("rashifal-reading", "en", rashi="tula", period="today") == "/horoscope/libra/today"
    assert i18n.url_for("rashifal-reading", "hi", rashi="tula", period="today") == "/hi/rashifal/tula/aaj"
    assert i18n.url_for("rashifal-reading", "mr", rashi="simha", period="monthly") == "/mr/rashi-bhavishya/singh/masik"
    assert i18n.url_for("rashifal-reading", "hi", rashi="mesha", period="6-months") == "/hi/rashifal/mesh/6-mahine"
    assert i18n.url_for("rashifal-reading", "mr", rashi="meena", period="yearly") == "/mr/rashi-bhavishya/meen/varshik"
    assert i18n.url_for("rashifal-reading", "en", rashi="karka", period="weekly") == "/horoscope/cancer/weekly"
    assert i18n.url_for("rashifal-rashi", "hi", rashi="vrishchika") == "/hi/rashifal/vrishchik"
    assert i18n.url_for("rashifal-rashi", "en", rashi="dhanu") == "/horoscope/sagittarius"
    # the SEO map's spellings, in zodiac order
    assert i18n.RASHI_SLUGS["hi"] == ("mesh", "vrishabh", "mithun", "kark", "singh", "kanya", "tula", "vrishchik",
                                      "dhanu", "makar", "kumbh", "meen")
    assert i18n.RASHI_SLUGS["mr"] == i18n.RASHI_SLUGS["hi"]
    assert i18n.RASHI_SLUGS["en"][0] == "aries" and i18n.RASHI_SLUGS["en"][-1] == "pisces"
    assert i18n.PERIOD_KEYS == ("today", "weekly", "monthly", "6-months", "yearly")  # "monthly" replaced "3-months"


def test_rashi_keys_are_the_engine_slugs():
    from app.engine.constants import sign_info

    assert list(i18n.RASHI_KEYS) == [sign_info(i)["slug"] for i in range(12)]
    assert [sign_info(i)["key"].lower() for i in range(12)] == list(i18n.RASHI_SLUGS["en"])


def test_rashi_key_accepts_any_spelling():
    for value in ("tula", "libra", 7):
        assert i18n.rashi_key(value) == "tula"
    assert i18n.rashi_key("mesh") == i18n.rashi_key("mesha") == i18n.rashi_key("aries") == "mesha"
    assert i18n.rashi_index("pisces") == 12
    with pytest.raises(KeyError):
        i18n.rashi_key("weekly")
    with pytest.raises(KeyError):
        i18n.rashi_key(13)


def test_url_for_rejects_bad_input():
    with pytest.raises(KeyError):
        i18n.url_for("nope")
    with pytest.raises(KeyError):
        i18n.url_for("about", "hi")  # policy pages are English-only
    with pytest.raises(KeyError):
        i18n.url_for("rashifal-reading", "en", rashi="tula")  # period missing
    with pytest.raises(KeyError):
        i18n.url_for("rashifal-reading", "en", rashi="tula", period="3-months")  # retired period
    with pytest.raises(KeyError):
        i18n.url_for("home", "en", rashi="tula")


def test_every_path_round_trips_and_is_unique():
    rows = list(i18n.all_paths())
    paths = [row[0] for row in rows]
    # (6 + 2 + 12 + 60) x 3 languages, + 6 English-only policy pages, + 1 English-only CALCULATOR.
    # That last term is deliberately its own: it is a page in i18n.EN_ONLY_TOOL_KEYS, which is a different
    # thing from a policy page and from a page whose translation is missing. If /sidereal-birth-chart ever
    # gains hi and mr twins it leaves this term and joins the x 3 group, moving the total by three rather
    # than by one - so check which of those two worlds you are in before adjusting the number.
    assert len(paths) == len(set(paths)) == 247
    for path, key, lang, params in rows:
        assert i18n.resolve(path) == (key, lang, params)
        assert i18n.url_for(key, lang, **params) == path
        assert i18n.lang_of_path(path) == lang
    assert sum(1 for row in rows if row[1] == "rashifal-reading") == 180


def test_weekly_hub_never_collides_with_a_rashi_slug():
    assert i18n.resolve("/horoscope/weekly") == ("rashifal-weekly", "en", {})
    assert i18n.resolve("/hi/rashifal/saptahik") == ("rashifal-weekly", "hi", {})
    assert i18n.resolve("/mr/rashi-bhavishya/saptahik") == ("rashifal-weekly", "mr", {})
    reserved = {slug for slugs in i18n.PERIOD_SLUGS.values() for slug in slugs.values()}
    for slugs in i18n.RASHI_SLUGS.values():
        assert not reserved & set(slugs)


def test_resolve_misses():
    for path in ("/nope", "/hi/horoscope", "/horoscope/tula", "/hi/rashifal/libra", "/mr/rashi-bhavishya/tula/today",
                 "/horoscope/libra/aaj", "/horoscope/libra/3-months", "/hi/about", "/birth-chart/"):
        assert i18n.resolve(path) is None, path
    assert i18n.resolve("/hi") == ("home", "hi", {})
    assert i18n.lang_of_path("/hindi-page") == "en" and i18n.lang_of_path("/mr/whatever") == "mr"


def test_alternates_are_absolute_and_identical_across_languages(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://rashikundli.com/")
    links = i18n.alternates("matching")
    assert links == {"en": "https://rashikundli.com/horoscope-matching", "hi": "https://rashikundli.com/hi/kundali-matching",
                     "mr": "https://rashikundli.com/mr/patrika-matching",
                     "x-default": "https://rashikundli.com/horoscope-matching"}
    reading = i18n.alternates("rashifal-reading", rashi="kumbha", period="weekly")
    assert reading["hi"] == "https://rashikundli.com/hi/rashifal/kumbh/saptahik"
    assert reading["x-default"] == reading["en"] == "https://rashikundli.com/horoscope/aquarius/weekly"
    assert i18n.alternates("home")["mr"] == "https://rashikundli.com/mr/"
    assert i18n.alternates("privacy") == {}  # single-language page: no hreflang
    for ref in i18n.all_pages():
        links = ref.alternates()
        if len(ref.langs) > 1:
            assert set(links) == {"en", "hi", "mr", "x-default"}
            assert [links[lang] for lang in ref.langs] == [ref.url(lang) for lang in ref.langs]


@pytest.mark.parametrize("old, query, new", [
    ("/janam-kundali", "", "/birth-chart"),
    ("/kundali-matching", "", "/horoscope-matching"),
    ("/consultation", "", "/ai-astrologer"),
    ("/marathi-kundali", "", "/mr/kundali"),
    ("/hi/kundali", "", "/hi/kundli"),   # the Hindi chart page's slug before the rename; Marathi keeps "kundali"
    ("/hi/kundali/", "", "/hi/kundli"),
    ("/rashifal", "", "/horoscope"),
    ("/rashifal", "lang=mr", "/mr/rashi-bhavishya"),
    ("/rashifal/", "lang=hi", "/hi/rashifal"),
    ("/rashifal/mesha", "", "/horoscope/aries"),
    ("/rashifal/kanya", "", "/horoscope/virgo"),
    ("/rashifal/vrishchika", "?lang=hi", "/hi/rashifal/vrishchik"),
    ("/rashifal/tula/today", "", "/horoscope/libra/today"),
    ("/rashifal/mesha/3-months", "", "/horoscope/aries/monthly"),
    ("/rashifal/mesha/3-months", "lang=hi", "/hi/rashifal/mesh/masik"),
    ("/rashifal/simha/yearly", "lang=mr", "/mr/rashi-bhavishya/singh/varshik"),
    ("/rashifal/dhanu/weekly", "lang=xx", "/horoscope/sagittarius/weekly"),
])
def test_legacy_redirects_are_single_hop(old, query, new):
    assert i18n.legacy_redirect(old, query) == new
    assert i18n.resolve(new) is not None  # lands on a real page: no chain
    assert i18n.legacy_redirect(new) is None


def test_legacy_redirect_ignores_everything_else():
    for path in ("/", "/birth-chart", "/rashifal/libra", "/rashifal/mesh", "/rashifal/mesha/monthly",
                 "/rashifal/mesha/today/extra", "/horoscope", "/hi/kundli", "/mr/kundali"):
        assert i18n.legacy_redirect(path) is None, path


def test_demand_order_and_switcher():
    for lang in i18n.LANGS:
        assert sorted(i18n.rashis_by_demand(lang)) == sorted(i18n.RASHI_KEYS)
    assert i18n.rashis_by_demand("hi")[:3] == ("tula", "kumbha", "kanya")
    assert i18n.rashis_by_demand("en")[0] == "karka" and i18n.rashis_by_demand("mr")[0] == "simha"
    links = i18n.switcher("rashifal-reading", "hi", rashi="tula", period="today")
    assert [(item["lang"], item["path"], item["current"]) for item in links] == [
        ("en", "/horoscope/libra/today", False), ("hi", "/hi/rashifal/tula/aaj", True),
        ("mr", "/mr/rashi-bhavishya/tula/aaj", False)]
    assert [item["path"] for item in i18n.switcher("privacy", "en")] == ["/privacy", "/hi/", "/mr/"]
    assert [item["path"] for item in i18n.switcher(None, "en")] == ["/", "/hi/", "/mr/"]
