"""The charts the whole test suite is anchored on: three public, independently published births.

WHY PUBLIC CHARTS. The accuracy claim this engine makes is that it reproduces charts a reader can
check for themselves. If the suite pinned whatever our own code happened to produce, it would be
self-confirming: it would keep passing while the engine drifted. So the primary expectations below
come from OUTSIDE - an astrology publisher's own numbers - and every one of them carries the source
and the date it was fetched.

Engine-generated values are still used, but only as REGRESSION PINS for feature coverage (that a
yoga list does not change shape, that a timeline stays contiguous). Anything that is a regression
pin rather than external proof says so where it is asserted. A pin proves nothing about accuracy.

WHAT IS PINNED, AND WHAT IS NOT. Planets and nakshatras are the firm anchor: they depend on the
date and, weakly, the time, so published sources agree about them. The LAGNA is treated separately,
because it moves about 1° every four minutes and several of these births have a disputed minute.
Where a source's ascendant differs from ours, `lagna_dispute` says so in the source's own numbers
rather than hiding it, and the test asserts our value while naming theirs.

THE THREE CHARTS, chosen for coverage rather than fame:

    key            lagna    rashi       exercises
    nehru          Simha*   Karka       the arcsecond-level planetary anchor; a disputed ascendant
    kalam          Karka    Vrishchika  the feature-rich report: 9 yogas, Neecha Bhanga, two Pancha
                                        Mahapurusha, Vipreeta, Budhaditya, Pitra dosha, a debilitated
                                        Chandra, two exalted and two combust grahas, mangal dosha at
                                        "high" with cancellations, a vargottama graha
    vivekananda    Dhanu    Kanya       a third lagna and rashi family, a moolatrikona Mangal, a
                                        parivartana, and an ayanamsa disagreement worth documenting
    (gandhi)                            navamsa only - all nine D9 positions published together

Sade-sati and dhaiya are functions of the Moon sign AND the moment they are asked about, not of the
birth data, so they are exercised by pinning a different `as_of` on these same charts rather than by
hunting for a birth that happens to be in sade-sati today. `STATES` below records which moment puts
which chart into which phase; a test that wants an active sade-sati uses that.

None of this is anyone's private data. `app/engine/cities.py` separately contains ~124 Indian cities
including Miraj: that is public geography, not a birth record, and is unrelated to these charts.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from functools import lru_cache

from app.engine import compute_chart
from app.engine.reference import SELF_CHECK

# The moment every report-level expectation is evaluated at. Pinned so the suite does not change
# meaning as real time passes.
AS_OF = datetime(2026, 9, 22, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Reference:
    key: str
    name: str
    born: date
    at: time
    lat: float
    lon: float
    tz: str
    place: str
    source: str
    fetched: str
    # compare=False keeps Reference hashable (a dict field would otherwise break __hash__) and keeps
    # equality about the birth, not about the prose around it.
    city: str | None = field(default=None, compare=False)          # resolvable by engine.find_city
    published: dict = field(default_factory=dict, compare=False)   # what the source states
    lagna_dispute: str | None = field(default=None, compare=False)  # where the source differs
    note: str | None = field(default=None, compare=False)

    @property
    def args(self) -> tuple:
        return (self.born, self.at, self.lat, self.lon, self.tz)

    def chart(self, as_of: datetime = AS_OF, detail: str = "basic") -> dict:
        """The computed chart, cached - the suite asks for these many times over."""
        return _compute(self.args, as_of, detail)

    def request(self) -> dict:
        """The body an /api route wants for this birth, as coordinates."""
        return {"date": self.born.isoformat(), "time": self.at.isoformat(timespec="minutes"),
                "lat": self.lat, "lon": self.lon, "timezone": self.tz}

    def city_request(self) -> dict:
        """The same birth given as a CITY, for the web forms that require one from the dropdown.

        Only NEHRU and INDIRA have this. See CITY_REFERENCES below for why the others do not.
        """
        if not self.city:
            raise ValueError(
                f"{self.key} has no city form: either its birthplace is not in app/engine/cities.py, "
                f"or it pins an explicit UTC offset that a city entry cannot express. Use "
                f"{', '.join(r.key.upper() for r in CITY_REFERENCES)} for a city-based flow, or "
                f"{self.key}.request() for coordinates. See CITY_REFERENCES for the reasoning.")
        return {"date": self.born.isoformat(), "time": self.at.isoformat(timespec="minutes"),
                "city": self.city}


@lru_cache(maxsize=64)
def _compute(args: tuple, as_of: datetime, detail: str) -> dict:
    return compute_chart(*args, as_of=as_of, detail=detail)


# Nehru's birth data lives in app/engine/reference.py, because the running service recomputes this
# same chart at /health/ready; taking it from there keeps one definition of the numbers.
NEHRU = Reference(
    key="nehru",
    name=SELF_CHECK["name"],
    born=SELF_CHECK["date"],
    at=SELF_CHECK["time"],
    lat=SELF_CHECK["lat"], lon=SELF_CHECK["lon"], tz=SELF_CHECK["tz"],
    place=SELF_CHECK["place"],
    source="AstroSage celebrity horoscope, "
           "https://celebrity.astrosage.com/jawaharlal-nehru-birth-chart.asp - birth data rated "
           '"Accurate (A)", source given as Kundli Sangraha (Bhat)',
    fetched="2026-09-21",
    # Sign and degree within the sign, exactly as that page prints them. Our longitudes agree to
    # within arc-seconds for every graha it lists.
    published={
        "Sun": ("Vrishchika", 0.2917), "Moon": ("Karka", 18.0864), "Mars": ("Kanya", 9.9956),
        "Mercury": ("Tula", 17.1797), "Jupiter": ("Dhanu", 15.1825), "Venus": ("Tula", 7.3878),
        "Saturn": ("Simha", 10.7753),
    },
    note=(
        "TIMEZONE CONVENTION, and it matters more than it looks. This chart is computed at an "
        "explicit +05:30, not at \"Asia/Kolkata\". India had no standard time in 1889, and zoneinfo "
        "correctly resolves Asia/Kolkata to MADRAS time (+05:21:10) for that year - but the source "
        "whose numbers we check against applied modern IST, so comparing like for like needs their "
        "clock. The 8m50s between the two conventions moves this ascendant from Karka 28\u00b017' to "
        "Simha 0\u00b013', across a sign boundary, and drags the Moon 4 arc-minutes with it. On the "
        "source's own clock all seven grahas agree to within 1.2 arc-minutes and the ascendant to "
        "7.6 - no dispute at all. This chart carried a documented 'disputed ascendant' for a while "
        "purely because the code said Asia/Kolkata while the comment claimed +05:30."
    ),
)

KALAM = Reference(
    key="kalam",
    name="A. P. J. Abdul Kalam",
    born=date(1931, 10, 15),
    at=time(1, 15),
    lat=9.2881, lon=79.3129, tz="Asia/Kolkata",
    place="Rameswaram, Tamil Nadu",
    source="Indian Astrology 2000, "
           "https://www.indianastrology2000.com/astrology-articles/"
           "astrological-analysis-of-mr-apj-abdul-kalam-.html",
    fetched="2026-09-22",
    # That analysis is prose, not a table, so what it states is recorded as claims a test can check.
    published={
        "lagna_sign": "Karka",
        "janma_nakshatra": "Anuradha",
        "moon_sign": "Vrishchika",
        "moon_dignity": "debilitated",
        "moon_house": 5,
        "jupiter_dignity": "exalted",
        "jupiter_house": 1,
        "jupiter_rules": [6, 9],
        "mercury_dignity": "exalted",
        "mercury_house": 3,
        "sun_house": 3,
        "budhaditya": True,
        "saturn_house": 6,
        "saturn_rules": [7, 8],
    },
    note=("Six independent statements in that analysis - the ascendant, the nakshatra, the Moon's "
          "sign, debilitation and house, Guru's exaltation, house and lordships, Budha's exaltation "
          "and the Budhaditya with Surya, and Shani's house and lordships - all hold in this engine. "
          "This is the chart the report-level tests use, because it exercises the most features."),
)

VIVEKANANDA = Reference(
    key="vivekananda",
    name="Swami Vivekananda",
    born=date(1863, 1, 12),
    at=time(6, 33, 33),
    lat=22.5726, lon=88.3639, tz="+05:53",
    place="Calcutta (Kolkata), West Bengal - local mean time, decades before IST existed",
    source="VedAstro Astro-Databank, https://vedastro.org/astro-databank/Swami-Vivekananda-1863.html",
    fetched="2026-09-22",
    published={
        "lagna_sign": "Dhanu",
        "moon_sign": "Kanya",
        "janma_nakshatra": "Hasta",
        "janma_pada": 3,
    },
    note=(
        "AYANAMSA DISAGREEMENT, fully accounted for. That page states Surya in Makara; this engine "
        "puts Surya at Dhanu 29°25', thirty-five arc-minutes short of the Makara cusp. The page "
        "says which ayanamsa it uses - RAMAN - and the Raman ayanamsa is about 1.1° smaller than "
        "Lahiri, which this platform uses throughout. A smaller ayanamsa gives a larger sidereal "
        "longitude, so the same Surya lands at roughly Makara 0°30' under Raman and Dhanu 29°25' "
        "under Lahiri: one chart, two ayanamsas, and Surya happens to fall in the 1.1° gap between "
        "them. Vivekananda was born a few hours before the Sun's actual ingress that day. The "
        "quantities that do not depend on the ayanamsa choice - the lagna sign, the Moon's sign and "
        "its nakshatra AND pada - agree exactly. The disagreement is kept here rather than hidden "
        "because it is the clearest evidence in the suite that the Lahiri choice is a real one."
    ),
)

GANDHI = Reference(
    key="gandhi",
    name="Mahatma Gandhi",
    born=date(1869, 10, 2),
    at=time(7, 11, 53),
    lat=21.6417, lon=69.6293, tz="+04:38",
    place="Porbandar, Gujarat - local mean time",
    source="Sithars Astrology, https://sitharsastrology.com/blog/mahatma-gandhi-birth-chart-analysis",
    fetched="2026-09-21",
    # This source publishes a whole NAVAMSA, which is rare; it is the D9 verification and nothing else.
    published={
        "navamsa": {
            "Sun": "Mithuna", "Moon": "Meena", "Mars": "Vrishabha", "Mercury": "Makara",
            "Jupiter": "Dhanu", "Venus": "Vrishabha", "Saturn": "Makara",
            "Rahu": "Tula", "Ketu": "Mesha",
        },
    },
    lagna_dispute=(
        "That source's D9 ascendant is Makara against this engine's Vrishchika. Gandhi's minute of "
        "birth is disputed and the ascendant is the only quantity sensitive to it; all nine grahas, "
        "which are not, agree exactly."
    ),
)


INDIRA = Reference(
    key="indira",
    name="Indira Gandhi",
    born=date(1917, 11, 19),
    at=time(23, 11),
    # The coordinates the SOURCE itself prints (25N57, 81E50), not the city centre, so the ascendant
    # comparison below is like for like. The grahas are unaffected either way.
    lat=25.95, lon=81.8333, tz="Asia/Kolkata",
    place="Allahabad (Prayagraj), Uttar Pradesh",
    city="Allahabad",
    source="AstroSage celebrity horoscope, "
           "https://celebrity.astrosage.com/indira-gandhi-birth-chart.asp - birth data rated "
           '"Accurate (A)", source given as Kundli Sangraha (Bhat)',
    fetched="2026-09-22",
    # The best-documented chart in this set: that page prints sign, degree, nakshatra AND pada for
    # all nine grahas, plus which are combust and which retrograde, plus the ascendant to the second.
    published={
        "Sun": ("Vrishchika", 4.13306, "Anuradha", 1),
        "Moon": ("Makara", 5.58889, "Uttarashadha", 3),
        "Mars": ("Simha", 16.38500, "Purva Phalguni", 1),
        "Mercury": ("Vrishchika", 13.24333, "Anuradha", 3),
        "Jupiter": ("Vrishabha", 14.96750, "Rohini", 2),
        "Venus": ("Dhanu", 21.01083, "Purvashadha", 3),
        "Saturn": ("Karka", 21.89111, "Ashlesha", 2),
        "Rahu": ("Dhanu", 10.56444, "Mula", 4),
        "Ketu": ("Mithuna", 10.56444, "Ardra", 2),
        "lagna_sign": "Karka",
        "lagna_degree": 27.49667,
        "combust": ["Mercury"],
        "retrograde": ["Jupiter", "Rahu", "Ketu"],
    },
    note=(
        "THE ONLY EXTERNALLY VERIFIED ASCENDANT in this set, and the reason this chart was added. "
        "Nehru's and Gandhi's ascendants are both disputed, so until this chart there was no test "
        "anywhere proving the engine computes a LAGNA correctly against a published source - only "
        "grahas. Here the published ascendant is Karka 27 deg 29'48\" and this engine gives "
        "Karka 27 deg 30'04\": sixteen arc-seconds apart. Eight of the nine grahas match on sign, "
        "degree, nakshatra and pada; Shani is six arc-minutes off (Karka 21 deg 47'14\" against "
        "their 21 deg 53'28\"), with sign, nakshatra and pada all agreeing - an ephemeris "
        "difference, not a timing one, since Shani moves only about two arc-minutes a day. It is "
        "also the only woman's chart in the set, which matters because guna milan's kootas are "
        "not symmetric between the two charts."
    ),
)

CHARTS = (NEHRU, KALAM, VIVEKANANDA, INDIRA)

# WHICH REFERENCES CAN BE GIVEN AS A CITY. The web forms make the visitor pick a place from the
# dropdown (app/engine/cities.py, ~124 Indian cities) rather than typing coordinates, so a flow that
# validates "choose the place of birth from the list" can only use a reference whose birthplace is
# in that list AND whose timezone a city entry can carry. Two of the five qualify:
#
#   indira          Allahabad is in the list and her 1917 birth is genuinely IST -> .city_request()
#   nehru           Allahabad is in the list, but this reference pins an explicit +05:30 to match
#                   its source's convention, which a city entry cannot express (the city would give
#                   the historically correct Madras time and a different chart - see NEHRU.note)
#   kalam           Rameswaram is NOT in the list (a real town, and arguably a gap in the list, but
#                   adding it is a product decision, not a test fix)
#   vivekananda,
#   gandhi          Porbandar is not in the list; Calcutta is, and zoneinfo handles 1863 correctly
#                   (Asia/Kolkata resolves to +05:53:20 there, twenty seconds from this reference's
#                   explicit offset), so the CLOCK is safe - it is only the city table's coordinates
#                   that differ. They stay coordinate-only for exactness, not for safety.
#
# A city form never reproduces a reference chart exactly anyway: the city table's coordinates differ
# from the source's by a few hundredths of a degree, which is a few arc-minutes of ascendant. Use
# .city_request() for web flows that must pick a place from the dropdown, and .request() whenever a
# chart VALUE is being asserted.
CITY_REFERENCES = tuple(reference for reference in CHARTS if reference.city)
BY_KEY = {reference.key: reference for reference in (*CHARTS, GANDHI)}



# --- matching needs a PAIR, not two individuals -----------------------------------------------------
#
# Guna milan is a pure function of two charts. No published per-koota breakdown for a famous couple
# could be found (searched 2026-09-22: the sources that discuss celebrity matches give a total at
# best, and most give only prose), and the one historical couple where both charts would have been
# ideal - Jawaharlal and Kamala Nehru - has no published chart for Kamala at all.
#
# So the external half is each chart's own published Moon NAKSHATRA AND PADA, which is exactly what
# the 36 points are computed from: Hasta pada 3, Ashlesha pada 4 and Uttarashadha pada 3 are all
# printed by the sources above. The score is then a deterministic consequence of two independently
# verifiable inputs - derived, not invented, and NOT a self-confirming pin. The tests say which half
# is which.
#
# NEITHER PAIRING IS A COUPLE, and none is implied: these are the charts in this set that are
# published in enough detail to anchor a match, chosen for what they exercise. Two pairs are kept
# because one clean match and one with a dosha cover different code:
#
#   MATCH_PAIR      Vivekananda + Indira  25.0/36 "good"          Bhakoot scores 0, bhakoot dosha present
#   MATCH_PAIR_LOW  Gandhi + Indira       13.0/36 "below_average"  Gana and Nadi both score 0, nadi dosha
#
# Both carry mangal dosha on both sides, which exercises the dosha-comparison block.
MATCH_PAIR = (VIVEKANANDA, INDIRA)
MATCH_PAIR_LOW = (GANDHI, INDIRA)

# The chart the report-level and timeline tests use: the richest feature coverage of the three.
PRIMARY = KALAM

# Sade-sati and dhaiya depend on when they are asked about. These pairings are Shani's actual
# transits, so they are as checkable as any other transit - they are not a property of the birth.
STATES = {
    "dhaiya_eighth": (NEHRU, datetime(2024, 6, 1, tzinfo=timezone.utc)),
    "dhaiya_fourth": (KALAM, datetime(2024, 6, 1, tzinfo=timezone.utc)),
    "sade_sati_rising": (NEHRU, datetime(2032, 6, 1, tzinfo=timezone.utc)),
    "sade_sati_peak": (NEHRU, datetime(2035, 6, 1, tzinfo=timezone.utc)),
    "sade_sati_setting": (NEHRU, datetime(2038, 6, 1, tzinfo=timezone.utc)),
}

# app/hardening.py's /health/ready calls engine.self_check(), which recomputes NEHRU and checks the
# ephemeris-sensitive quantities. See app/engine/reference.py for why it does not assert the lagna.
