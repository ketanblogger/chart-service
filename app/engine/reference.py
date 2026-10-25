"""A known-good chart the running service can recompute to prove the ephemeris is working.

`/health/ready` (app/hardening.py) calls `self_check()`. The point is to catch a broken or missing
Swiss Ephemeris data file, a mis-set ayanamsa, or a thread that never got configured - failures that
produce a plausible-looking chart rather than an exception, and would otherwise reach a paying
customer silently.

The birth used is Jawaharlal Nehru's, 14 November 1889, 23:30 at Allahabad: public, published, and
rated "Accurate (A)" by AstroSage (https://celebrity.astrosage.com/jawaharlal-nehru-birth-chart.asp,
source Kundli Sangraha), whose printed positions this engine reproduces to within about an
arc-minute. Nothing here is private data.

WHAT IS CHECKED, AND WHY NOT THE LAGNA. The expectations below are the Sun's sign, the Moon's sign
and the janma nakshatra - quantities that depend on the ephemeris and the ayanamsa but barely on the
minute of birth. The ascendant is deliberately left out: this one sits about 13 arc-minutes from the
Karka/Simha boundary, so a few minutes of clock - a timezone convention, say - moves it into the next
sign, and a probe that flips on that is reporting the convention rather than the ephemeris. A wrong
ayanamsa moves the Moon by roughly a degree, which moves the nakshatra, so these three catch the
failure this check exists for. (tests/test_chart.py does assert an ascendant, against a chart whose
ascendant is nowhere near a cusp.)
"""

import datetime as dt

SELF_CHECK = {
    "name": "Jawaharlal Nehru",
    "date": dt.date(1889, 11, 14),
    "time": dt.time(23, 30),
    "lat": 25.4358,
    "lon": 81.8463,
    # An explicit +05:30, NOT "Asia/Kolkata". India had no standard time in 1889 and zoneinfo
    # correctly resolves Asia/Kolkata to Madras time (+05:21:10) for that year - but the source
    # whose numbers we check against applied modern IST. Comparing like for like needs their clock.
    # See app/engine/tz_history in the tests for what the 8m50s difference actually does.
    "tz": "+05:30",
    "place": "Allahabad (Prayagraj), Uttar Pradesh",
    "source": "https://celebrity.astrosage.com/jawaharlal-nehru-birth-chart.asp (rated Accurate/A)",
    "expect": {
        "sun_sign": "Vrishchika",
        "moon_sign": "Karka",
        "nakshatra": "Ashlesha",
        "ephemeris": "swiss_ephemeris",
    },
}


def self_check() -> tuple[bool, str]:
    """(ok, one-line description). Never raises - a broken engine must not take the route down."""
    from .chart import compute_chart

    expect = SELF_CHECK["expect"]
    try:
        chart = compute_chart(SELF_CHECK["date"], SELF_CHECK["time"], SELF_CHECK["lat"],
                              SELF_CHECK["lon"], SELF_CHECK["tz"])
    except Exception as exc:  # noqa: BLE001 - the health route reports, it does not crash
        return False, f"reference chart failed to compute: {exc}"

    actual = {
        "sun_sign": chart["grahas"]["Sun"]["sign"]["name"],
        "moon_sign": chart["moon_rashi"]["name"],
        "nakshatra": chart["janma_nakshatra"]["name"],
        "ephemeris": chart["meta"]["ephemeris"],
    }
    wrong = {key: (value, expect[key]) for key, value in actual.items() if value != expect[key]}
    if wrong:
        detail = ", ".join(f"{key}={got!r} expected {want!r}" for key, (got, want) in sorted(wrong.items()))
        return False, f"reference chart wrong: {detail}"
    return True, (f"reference chart correct ({actual['sun_sign']} Surya, {actual['moon_sign']} rashi, "
                  f"{actual['nakshatra']})")
