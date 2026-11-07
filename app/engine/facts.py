"""`chart["report"]` - every fact the flagship Kundali report needs, assembled in one place.

The two-layer rule: the engine computes ALL facts, the AI only interprets. This module is the
single call that produces the whole fact set, so no caller has to remember the order things depend on
(navamsa and dignity first, then yogas, then the ranking that reads them).

Blocks, and the chapter of the printed book each one feeds:

    navamsa      chart basics   the D9 chart: lagna, every graha's D9 sign and house, vargottama
    dignity      chart basics   per graha: combustion, exaltation/debilitation/moolatrikona/own sign,
                             house lordships, natural benefic/malefic class
    aspects      personality    whole-sign drishti per graha
    yogas        highlights     every detected yoga with the exact combination that triggered it
    highlights   highlights     this chart's top 3 strengths and top 3 cautions, ranked deterministically
    gemstone     remedies       the stone the chart's lordships select, and the stones to avoid
    dhaiya       remedies       Shani's 4th/8th-from-Moon transit, the companion to `chart["sade_sati"]`
    timeline     life timeline  the complete dated window list, plus the year-by-year table feed

Nothing here calls an AI, reads the network, or depends on a request. Everything is JSON-serialisable
and deterministic: the same chart and the same `as_of` always produce the same bytes.
"""

from datetime import datetime

from .aspects import graha_aspects
from .core import as_utc
from .dignity import graha_dignities
from .gemstone import gemstones
from .highlights import highlights
from .sadesati import dhaiya as compute_dhaiya
from .timeline import build_timeline
from .varga import navamsa_chart
from .yogas import yogas


def report_facts(chart: dict, as_of: datetime | None = None, timeline_knobs: dict | None = None) -> dict:
    """The `report` block for an already-computed chart. See the module docstring for the blocks."""
    as_of_utc = as_utc(as_of)
    navamsa = navamsa_chart(chart)
    dignities = graha_dignities(chart)
    detected = yogas(chart, navamsa, dignities)
    moon_sign = chart["grahas"]["Moon"]["sign"]["index"]
    dhaiya = compute_dhaiya(moon_sign, as_of_utc, chart["input"]["timezone"])
    return {
        "as_of": as_of_utc.isoformat(timespec="seconds"),
        "navamsa": navamsa,
        "dignity": dignities,
        "aspects": graha_aspects(chart),
        "yogas": detected,
        "highlights": highlights(chart, dignities, navamsa, detected, dhaiya),
        "gemstone": gemstones(chart),
        "dhaiya": dhaiya,
        "timeline": build_timeline(chart, dignities, navamsa, as_of=as_of_utc, knobs=timeline_knobs),
    }
