"""Compact, model-facing encoding of engine output, shared by the consultation chat and the paid reports.

Selection and relabelling only - no astronomy. Every value is copied from the engine, except two lookups
over engine fields: lordships (from the engine's sign-lord fields) and whole-sign house counts of a transit
sign from the lagna sign / Moon sign (sign indexes from the engine). Rows use the Sanskrit name; `names` lists
the Devanagari and English form of each name once, which is what makes this a third of the raw JSON.

House convention, everywhere: `house` / `house_from_lagna` is counted from the lagna (what the site's chart
shows); `house_from_moon` is counted from the Moon sign. They are never mixed under one key.

Mangal dosha wording: the engine keeps `present` true when cancellations apply ("present, with mitigating
factors"). Its English descriptions say "ineffective" / "cancel", which the model then repeats, so the
model-facing text below says "softens" instead. The PDF / API `data` still carries the engine's own text.
"""

INGRESS_GRAHAS = ("Sun", "Mars", "Jupiter", "Saturn", "Rahu", "Ketu")
STATION_GRAHAS = ("Mercury", "Venus", "Mars", "Jupiter", "Saturn")
SLOW_GRAHAS = ("Jupiter", "Saturn", "Rahu", "Ketu")

MITIGATIONS = {
    "mars_in_own_or_exaltation_sign": "Mangal is in its own sign (Mesha, Vrishchika) or in Makara, where it is steady; "
                                      "tradition holds that this softens the dosha",
    "jupiter_conjunct_or_aspecting_mars": "Guru is with Mangal or aspects it (the 5th, 7th or 9th sign from Guru); Guru's "
                                          "influence is traditionally held to soften the dosha",
    "house_sign_exception": "Mangal's house-and-sign combination is one of the classical exceptions (2nd in Mithuna/Kanya, 4th in "
                            "Mesha/Vrishchika, 7th in Karka/Makara, 8th in Dhanu/Meena, 12th in Vrishabha/Tula, from the lagna), "
                            "traditionally held to soften the dosha",
    "cancer_or_leo_lagna": "For Karka and Simha lagna Mangal is a yogakaraka (a helpful planet for the chart), so tradition "
                           "treats its dosha as much milder",
}
MANGAL_NOTES = [
    "When both partners have Mangal dosha, tradition regards the two as balancing each other.",
    "Tradition holds that the effect of Mangal dosha eases after the age of 28, when Mars matures.",
    "Dosha counted from the lagna is considered the strongest, then from the Moon, then from Venus.",
]


def house_from(sign_index: int, reference_sign_index: int) -> int:
    """Whole-sign house of a sign counted from a reference sign (both are engine sign indexes 1-12)."""
    return (sign_index - reference_sign_index) % 12 + 1


def lordships(chart: dict) -> dict:
    """Per graha: the houses it rules and whether it sits in a sign it rules - a lookup over the engine's
    `houses[].sign.lord` and `grahas[].sign.lord`, so the model never works lordship out from memory."""
    table = {}
    for key, position in chart["grahas"].items():
        nodes = key in ("Rahu", "Ketu")
        table[key] = {
            "rules_houses": [] if nodes else [h["house"] for h in chart["houses"] if h["sign"]["lord"] == key],
            "in_own_sign": (not nodes) and position["sign"]["lord"] == key,
            "sign_lord": position["sign"]["lord"],  # the dispositor
        }
    return table


class Names:
    """Collects the glossary while rows are built."""

    def __init__(self):
        self.grahas, self.signs, self.nakshatras = {}, {}, {}

    def graha(self, graha: dict) -> str:
        self.grahas[graha["name"]] = f"{graha['devanagari']} / {graha['key']}"
        return graha["name"]

    def sign(self, sign: dict) -> str:
        self.signs[sign["name"]] = f"{sign['devanagari']} / {sign['key']}, lord {sign['lord']}"
        return sign["name"]

    def nakshatra(self, nakshatra: dict) -> str:
        self.nakshatras[nakshatra["name"]] = nakshatra["devanagari"]
        return nakshatra["name"]

    def glossary(self) -> dict:
        return {"grahas": self.grahas, "signs": self.signs, "nakshatras": self.nakshatras}


def mangal_for_model(mangal: dict) -> dict:
    return {
        "present": mangal["present"],
        "status": ("present, with mitigating factors" if mangal.get("cancellation_applies") else "present")
        if mangal["present"] else "not present",
        "intensity": mangal["intensity"],
        "mars_house_from": {ref: mangal[f"from_{ref}"]["mars_house"] for ref in ("lagna", "moon", "venus")},
        "dosha_from": [ref for ref in ("lagna", "moon", "venus") if mangal[f"from_{ref}"]["dosha"]],
        "mitigating_factors": [{"factor": MITIGATIONS.get(c["key"], c["key"]), "applies": c["applies"]}
                               for c in mangal["cancellations"]],
        "tradition_notes": MANGAL_NOTES,
    }


def compact_chart(chart: dict, names: Names, as_of: str, antardasha_mahadashas: int | None = 2) -> dict:
    """Birth chart for the model. `antardasha_mahadashas`: how many mahadashas (from the current one) keep their
    antardasha rows; None keeps none (matching reports do not need them)."""
    ruled = lordships(chart)

    def position(p: dict, graha_key: str | None = None) -> dict:
        row = {"graha": names.graha(p["graha"])} if "graha" in p else {}
        row.update(sign=names.sign(p["sign"]), degree=p["degree_dms"], nakshatra=names.nakshatra(p["nakshatra"]), pada=p["pada"])
        if graha_key:
            row.update(house=p["house"], rules_houses=ruled[graha_key]["rules_houses"], in_own_sign=ruled[graha_key]["in_own_sign"])
            if p.get("retrograde"):
                row["retrograde"] = True
        return row

    dasha, sade_sati = chart["dasha"], chart["sade_sati"]
    mahadashas = dasha["mahadashas"]
    current = dasha["current"]
    out = {
        "birth": {k: chart["input"].get(k) for k in ("date", "time", "city", "timezone") if chart["input"].get(k)},
        "calculation": "Swiss Ephemeris, sidereal, Lahiri ayanamsa, whole-sign houses counted from the lagna, mean Rahu/Ketu",
        "lagna": position(chart["lagna"]),
        "moon_rashi": names.sign(chart["moon_rashi"]),
        "janma_nakshatra": {"nakshatra": names.nakshatra(chart["janma_nakshatra"]), "pada": chart["janma_nakshatra"]["pada"],
                            "lord": chart["janma_nakshatra"]["lord"]},
        "grahas (house = counted from the lagna)": [position(p, key) for key, p in chart["grahas"].items()],
        "houses": [{"house": h["house"], "sign": names.sign(h["sign"]), "lord": h["sign"]["lord"], "grahas": h["grahas"]}
                   for h in chart["houses"]],
        "dasha": {
            "system": "Vimshottari",
            "as_of": as_of,
            "current": {"mahadasha": [names.graha(current["mahadasha"]["lord"]), current["mahadasha"]["start"], current["mahadasha"]["end"]],
                        "antardasha": [names.graha(current["antardasha"]["lord"]), current["antardasha"]["start"], current["antardasha"]["end"]]},
            "mahadashas [lord, start, end]": [[names.graha(m["lord"]), m["start"], m["end"]] for m in mahadashas],
        },
        "mangal_dosha": mangal_for_model(chart["mangal_dosha"]),
        "sade_sati": {"as_of": as_of, "active": sade_sati["active"], "phase": sade_sati["phase"],
                      "saturn_sign_now": names.sign(sade_sati["saturn_sign"]),
                      "saturn_house_from_moon": sade_sati["saturn_house_from_moon"], "cycle": sade_sati.get("cycle")},
    }
    # A birth before ~1906 has run past the whole 120-year Vimshottari cycle, so the engine starts
    # the sequence again and marks the second round on the CURRENT period. The `mahadashas` table
    # above still covers only the first cycle, so without this note the writer sees a current period
    # that ends years after the table stops, and a lord it has already written about coming round
    # again - which reads as the data contradicting itself. Say so once, plainly.
    if any((current or {}).get(level, {}).get("cycle", 1) > 1 for level in ("mahadasha", "antardasha")):
        out["dasha"]["note"] = (
            "This person has lived past the full 120-year Vimshottari cycle, so the sequence has "
            "begun again and the period running now belongs to the second round. The `mahadashas` "
            "table above lists the first round only, which is why the current period falls outside "
            "it. This is expected, not an error: a lord coming round a second time is simply that, "
            "and the current period should be read on its own terms. Do not remark on the "
            "discrepancy and do not mention cycles or rounds to the reader.")
    if antardasha_mahadashas:
        # `mahadashas` covers the FIRST 120-year cycle only, so for a second-round chart no row
        # matches the running mahadasha. Falling back to index 0 would offer the writer the same
        # lord's antardashas from a century earlier - platform hit the identical trap in the PDF,
        # where a reader would have taken 1894 dates for their own. An empty list is nearly as bad:
        # it reads as "this chart has no antardashas". So the key is omitted and the writer is told
        # where the real ones are.
        index = next((i for i, m in enumerate(mahadashas) if m["start"] == current["mahadasha"]["start"]), None)
        if index is None:
            out["dasha"]["antardashas"] = ("not listed here: this chart is in the second round of the "
                                           "cycle and the table above is the first. The antardasha "
                                           "running in any period is given with that period's window.")
        else:
            out["dasha"]["antardashas [mahadasha, antardasha, start, end]"] = [
                [names.graha(m["lord"]), names.graha(a["lord"]), a["start"], a["end"]]
                for m in mahadashas[index:index + antardasha_mahadashas] for a in m["antardashas"]
                if a["end"] >= as_of]
    return out


def transit_row(event: dict, names: Names, lagna_sign: int, moon_sign: int) -> list | None:
    """[date, graha, event, sign, house_from_lagna, house_from_moon] for the events worth telling a customer about."""
    key = event["graha"]["key"]
    if event["type"] == "ingress" and key in INGRESS_GRAHAS:
        how, sign = ("enters (retrograde re-entry)" if event.get("retrograde") and key not in ("Rahu", "Ketu") else "enters"), event["to_sign"]
    elif event["type"] == "station" and key in STATION_GRAHAS:
        how, sign = f"turns {event['direction']} in", event["sign"]
    else:
        return None
    return [event["datetime"][:10], names.graha(event["graha"]), how, names.sign(sign),
            house_from(sign["index"], lagna_sign), house_from(sign["index"], moon_sign)]


TRANSIT_COLUMNS = "[date, graha, event, sign, house_from_lagna, house_from_moon]"


# =====================================================================================================
# The flagship Kundali book (app/ai/book.py).
#
# `engine.report_facts` emits ~370 KB for a busy chart - ~100k tokens, far more than belongs in a
# prompt, and most of it repeated (every window re-states each dasha lord's full natal profile). It is
# split in two, which is what keeps the book inside its cost budget:
#
#   `book_prefix(...)`  the chart-wide facts, ~5k tokens. Identical for all ten calls of one report, so
#                       it is the second prompt-cache breakpoint: written once, read nine times.
#   `windows_block(...)` only the windows a given call actually writes. A call that writes 2028 is not
#                       charged for 2046's windows.
#
# Selection and relabelling only. Nothing is computed, rounded, or date-formatted here: every printed
# range is the engine's own `range.labels[language]` (see app/ai/engine_facts.py).
# =====================================================================================================

from app.engine.timeline import HOUSE_AREAS  # noqa: E402

from .engine_facts import AREAS, label_of, window_areas  # noqa: E402

BOOK_TRANSIT_COLUMNS = "[date, graha, event, sign, house_from_lagna, house_from_moon, note]"


def _gname(graha, names: Names):
    """A graha name from either of the engine's two forms: the full {key,name,devanagari} object, or a
    bare key string (`aspects_grahas`)."""
    if isinstance(graha, str):
        from app.engine.constants import graha_name
        graha = graha_name(graha)
    return names.graha(graha)


def _lord(entry, names: Names):
    """A graha name from any of the engine's lord shapes ({lord:{...}}, a bare graha, or None)."""
    if not entry:
        return None
    graha = entry.get("lord") or entry.get("graha") or entry
    return _gname(graha, names) if isinstance(graha, dict) and "name" in graha else None


# ---- the cached prefix -------------------------------------------------------------------------------


def compact_dignity(dignity: dict, names: Names) -> dict:
    """Per graha, only the judgements the writer may repeat. `dignity` is null for Rahu and Ketu and
    `combust` is null for Surya and the nodes; those keys are simply left out rather than asserted."""
    out = {}
    for row in dignity.values():
        if not isinstance(row, dict):
            continue  # the block also carries a `rule` string
        combustion = row.get("combustion") or {}
        entry = {"dignity": (row.get("dignity") or {}).get("label"),
                 "why": (row.get("dignity") or {}).get("reason"),
                 "class": row.get("natural_class")}
        if combustion.get("applicable") and combustion.get("combust") is not None:
            entry["combust"] = bool(combustion["combust"])
        out[_gname(row["graha"], names)] = {k: v for k, v in entry.items() if v is not None}
    return out


def compact_aspects(aspects: dict, names: Names) -> dict:
    """Whole-sign drishti as houses from the lagna. Without this block the writer may not mention an
    aspect at all (app/ai/validator.py `untraceable`)."""
    return {_gname(row["graha"], names): {
        "aspects_houses_from_lagna": row.get("aspected_houses_from_lagna") or [],
        "aspects_grahas": [_gname(g, names) for g in row.get("aspects_grahas") or []]}
        for row in aspects.values() if isinstance(row, dict)}


def compact_navamsa(navamsa: dict, names: Names) -> dict:
    return {
        "note": "The D9 chart. `vargottama` means the same sign in D1 and D9, which the tradition reads "
                "as a placement that holds up under pressure.",
        "lagna": names.sign(navamsa["lagna"]["sign"]),
        "lagna_vargottama": navamsa.get("lagna_vargottama"),
        "grahas [sign, house_from_navamsa_lagna, vargottama]": {
            _gname(row["graha"], names): [names.sign(row["sign"]), row.get("house_from_navamsa_lagna"),
                                          bool(row.get("vargottama"))]
            for row in navamsa["grahas"].values()},
    }


def compact_yogas(yogas: list, names: Names) -> list:
    """Each yoga with the combination that triggered it. A challenging yoga carries its own framing,
    which is a safety instruction to the writer, not decoration."""
    rows = []
    for yoga in yogas:
        row = {"name": yoga["name"], "devanagari": yoga["devanagari"], "category": yoga["category"],
               "nature": yoga["nature"], "strength": yoga["strength"],
               "grahas": [_gname(g, names) for g in yoga.get("grahas") or []],
               "houses": yoga.get("houses") or [],
               "why_it_applies": yoga["combination"]}
        # The engine carries `framing` on challenging yogas only, and it is tied to THAT yoga (Pitra
        # Dosha's says "frame entirely as remedy and remembrance of ancestors"). Our own generic
        # wording is strictly worse, so it is a last resort, never a default.
        framing = (yoga.get("framing") or "").strip()
        if framing:
            row["how_to_frame_it"] = framing
        elif yoga.get("nature") == "challenging":
            row["how_to_frame_it"] = ("Write this as what it asks of the person and what to do about it - "
                                      "never as a threat, an illness or a loss.")
        rows.append(row)
    return rows


def compact_highlights(highlights: dict, names: Names) -> dict:
    """Part A items 5-7. The engine ranks; the writer interprets the three it is given and no others.

    `all_strengths` / `all_cautions` are deliberately dropped - they are most of the 33 KB this block
    costs and the writer is forbidden to re-rank anyway. `safety` and `health_framing` are carried
    through verbatim: they are what keeps a caution constructive.
    """
    def rows(items):
        out = []
        for item in items:
            # Two DIFFERENT engine fields, both carried: `frame` is the tone for every caution
            # ("effort", "timing"); `framing` is the extra instruction the engine attaches to a
            # health-related one. Picking either alone loses real safety wording.
            row = {"title": item["title"], "why": item["reason"], "houses": item.get("houses") or [],
                   "grahas": [_gname(g, names) for g in item.get("grahas") or []],
                   "areas": [a.get("area") if isinstance(a, dict) else a
                             for a in item.get("areas") or []],
                   "how_to_frame_it": item.get("frame")}
            extra = (item.get("framing") or "").strip()
            if item.get("health_related"):
                row["health"] = extra or highlights.get("health_framing")
            elif extra:
                row["also"] = extra
            out.append({k: v for k, v in row.items() if v})
        return out

    return {"note": "Deterministically ranked by the engine. Write exactly these three of each, in this "
                    "order; do not re-rank them and do not add a fourth.",
            "safety": highlights.get("safety"),
            "top_strengths": rows(highlights.get("top_strengths") or []),
            "top_cautions": rows(highlights.get("top_cautions") or [])}


def compact_gemstone(gemstone: dict, names: Names) -> dict:
    """Part F. `presentation` and `wearing_note` are carried through verbatim - that wording is what
    keeps the gemstone policy reversal safe (see app/ai/safety.py)."""
    def stone(row: dict) -> dict:
        return {k: v for k, v in {
            "role": row.get("role_description") or row.get("role"),
            "graha": _gname(row["graha"], names), "stone": row["stone"],
            "sanskrit": row.get("sanskrit"), "devanagari": row.get("devanagari"),
            "metal": row.get("metal"), "finger": row.get("finger"), "day": row.get("day"),
            "weight": (row.get("weight") or {}).get("guidance"), "mantra": row.get("mantra"),
            "substitute": row.get("substitute"), "because": row.get("because"),
        }.items() if v is not None}

    return {
        "presentation": gemstone.get("presentation"),
        "wearing_note": gemstone.get("wearing_note"),
        "recommended": [stone(row) for row in gemstone.get("recommended") or []],
        "avoid": [{"graha": _gname(row["graha"], names), "stone": row["stone"],
                   "devanagari": row.get("devanagari"), "because": row.get("because")}
                  for row in gemstone.get("avoid") or []],
    }


def book_prefix(chart: dict, facts: dict, language: str, as_of: str) -> dict:
    """The chart-wide facts, identical for every call of one report: the second cached prefix block.

    Deliberately WITHOUT the timeline. The engine's timeline is ~300 KB; putting it here would cost a
    ~₹22 cache write before a word is written and crowd every call's context. Windows travel in the
    per-call message instead (`windows_block`), so a call is charged only for the windows it writes.
    """
    names = Names()
    data = {
        "as_of": as_of,
        "house_meanings": {str(house): list(areas) for house, areas in HOUSE_AREAS.items()},
        "chart": compact_chart(chart, names, as_of),
        "dignity": compact_dignity(facts["dignity"], names),
        "aspects (whole-sign drishti)": compact_aspects(facts["aspects"], names),
        "navamsa (D9)": compact_navamsa(facts["navamsa"], names),
        "yogas": compact_yogas(facts["yogas"], names),
        "highlights": compact_highlights(facts["highlights"], names),
        "dhaiya": {"active": facts["dhaiya"]["active"], "kind": facts["dhaiya"].get("kind"),
                   "saturn_house_from_moon": facts["dhaiya"].get("saturn_house_from_moon"),
                   "period": facts["dhaiya"].get("period")},
    }
    if (facts.get("gemstone") or {}).get("recommended"):
        data["gemstone"] = compact_gemstone(facts["gemstone"], names)
    # Register every name the per-call window blocks will use, so the one glossary in this cached
    # block covers them and no per-call message has to repeat it.
    from .engine_facts import every_window
    for window in every_window(facts["timeline"]):
        compact_window(window, names, language)
    for row in facts["timeline"].get("year_table") or []:
        _year_row(row, names, language)
    data["names"] = names.glossary()
    return data


# ---- the per-call window blocks -------------------------------------------------------------------------


def _transit_rows(transits: list, names: Names) -> list:
    rows = []
    for t in transits or []:
        row = [t["date"], _gname(t["graha"], names), t["event"], names.sign(t["sign"]),
               t["house_from_lagna"], t["house_from_moon"]]
        if t.get("retrograde_entry"):
            row.append("retrograde re-entry: a temporary step back")
        rows.append(row)
    return rows


def _saturn_phase(phases: list, language: str) -> list:
    return [f"{phase['phase_label']} ({label_of(phase['range'], language)})" for phase in phases or []]


def compact_window(window: dict, names: Names, language: str) -> dict:
    """One dated window as the writer sees it.

    **THE WRITER NEVER SEES AN ISO DATE FOR THE WINDOW ITSELF, AND THAT IS A SAFETY PROPERTY.** The
    whole design rests on it: the model returns a `window_id`, `start`/`end` are filled in afterwards
    from the engine, and the model therefore *cannot* write a wrong date range because it was never
    shown one. `range` here is the engine's already-printed label, not a date the model composes.

    So do NOT "simplify" this by handing the writer `engine.timeline_windows(...)` instead. That view
    is genuinely leaner than the raw timeline and is the right thing for any caller that needs dates -
    but it carries `start` and `end` per window, and putting those in front of the writer quietly
    re-admits exactly the failure this layer exists to prevent. (It is also ~3x larger once compacted:
    97,681 chars against 33,600 for the same 45 windows. The size is the lesser reason.)

    Dropped as machinery or already-in-the-prefix: `days`, `start_ym`, `end_ym`, `why_it_starts_here`,
    and the `active_lords` natal profiles that every window repeats.
    """
    dasha = window.get("dasha") or {}
    row = {"id": window["id"], "range": label_of(window["range"], language)}
    if dasha:
        row["dasha"] = {level: _lord(dasha.get(level), names)
                        for level in ("mahadasha", "antardasha", "pratyantardasha") if dasha.get(level)}
    elif window.get("mahadasha_lord"):  # a past-strip entry
        row["mahadasha"] = _lord(window["mahadasha_lord"], names)
    if window.get("age_years"):
        row["age_years"] = window["age_years"]
    if window.get("houses_lit"):
        row["houses_active"] = window["houses_lit"]
    areas = window_areas(window)
    if areas:
        row["areas"] = areas
    if window.get("saturn_phases"):
        row["shani"] = _saturn_phase(window["saturn_phases"], language)
    if window.get("transits"):
        row[f"transits {BOOK_TRANSIT_COLUMNS}"] = _transit_rows(window["transits"], names)
    return row


def windows_block(windows: list, language: str, names: Names | None = None) -> list:
    """The windows one call may write about. Names are already in the cached prefix's glossary."""
    names = names or Names()
    return [compact_window(window, names, language) for window in windows]


def _year_row(row: dict, names: Names, language: str) -> dict:
    return {
        "year": row["year"],
        "range": label_of(row["range"], language),
        "age": row.get("age_at_year_start"),
        "dashas [mahadasha, antardasha, range]": [
            [_lord(d.get("mahadasha"), names), _lord(d.get("antardasha"), names),
             label_of(d["range"], language)]
            for d in row.get("dashas") or []],
        "areas": [a["area"] for a in row.get("areas") or [] if a.get("area") in AREAS],
        "shani": _saturn_phase(row.get("saturn_phases"), language),
    }


def compact_year_table(year_table: list, language: str, names: Names | None = None) -> list:
    """Part G's feed: one row per year, its dasha periods and the life areas that year lights up."""
    names = names or Names()
    return [_year_row(row, names, language) for row in year_table]

