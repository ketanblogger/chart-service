"""The building blocks of a printed report: small dicts the Jinja template knows how to draw.

Two sources, never mixed:
- charts, graha / dasha / koota / dosha tables are built here **from `report["data"]`** (engine output);
- prose blocks (`prose`, `bullets`, `subsections`, `windows`, `remedies` ...) only carry the AI's plain text,
  which Jinja autoescapes and which is never trusted as HTML.

Nothing is calculated here and NO DATE IS EVER FORMATTED HERE: a range the engine has already labelled is
printed through `Labels.label()` exactly as the engine wrote it, in the reader's language and at the
precision the engine chose; one it has not labelled (a dasha period, a sade-sati cycle) goes through
`Labels.range()`, which is a call into the engine's own `format_range`. An engine `end` is exclusive, so
the printed label always names the last day actually covered.

Block types and the keys the template reads:

| type | keys |
|---|---|
| `facts` | items: [(label, value, sub)] |
| `table` | title, columns, rows, cls, keep, note |
| `chart` | title, svg, legend, retro, note, small |
| `columns` | title, blocks |
| `banner` | tone, title, text |
| `score` | total, max, unit, percent, percent_text, verdict |
| `note` | text |
| `trust` | title, paragraphs |
| `caveats` | title, paragraphs |
| `excluded` | title, items, note |
| `prose` | paragraphs |
| `bullets` | title, items |
| `subsections` | items: [{id, heading, paragraphs}] (h3) |
| `windows` | items: [{id, label, paragraphs, areas: [label], area_lines: [{label, text}], areas_heading}] (h3) |
| `remedies` | items: [{id, type, title, description, how_to, frequency}] (h3) |
| `dasha_grid` | title, cards |
| `pagebreak` | - |
"""

from markupsafe import Markup

from .chart_svg import chart_legend, chart_svg
from .labels import Labels, fmt_num

IST_OFFSET_SECONDS = 19800  # +05:30, today's Indian Standard Time

GRAHA_ORDER = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]


# ---- small block constructors --------------------------------------------------------------------


def facts(items: list) -> dict:
    return {"type": "facts", "items": [item for item in items if item]}


def table(columns: list[str], rows: list, *, title: str = "", cls: str = "", keep: bool = True, note: str = "") -> dict:
    """rows: list of cells or {"cells": [...], "cls": "..."}; a cell is a string or (main, sub)."""
    norm = [row if isinstance(row, dict) else {"cells": row, "cls": ""} for row in rows]
    return {"type": "table", "title": title, "columns": columns, "rows": norm, "cls": cls, "keep": keep, "note": note}


def note(text: str) -> dict:
    return {"type": "note", "text": text}


def prose(paragraphs: list[str] | None) -> dict | None:
    kept = [p.strip() for p in (paragraphs or []) if p and p.strip()]
    return {"type": "prose", "paragraphs": kept} if kept else None


def bullets(items: list[str] | None, title: str = "") -> dict | None:
    kept = [b.strip() for b in (items or []) if b and b.strip()]
    return {"type": "bullets", "title": title, "items": kept} if kept else None


def pagebreak() -> dict:
    return {"type": "pagebreak"}


def time_of_day(hms: str | None) -> str:
    parts = (hms or "").split(":")
    if len(parts) == 3 and parts[2] == "00":
        parts = parts[:2]
    return ":".join(parts)


def coords(inp: dict) -> str:
    lat, lon = inp.get("lat"), inp.get("lon")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return ""
    return f"{abs(lat):.4f}° {'N' if lat >= 0 else 'S'}, {abs(lon):.4f}° {'E' if lon >= 0 else 'W'}"


def birth_rows(L: Labels, inp: dict, name: str = "") -> list[tuple[str, str]]:
    place = inp.get("city") or coords(inp)
    rows = [(L["name"], name)] if name else []
    rows += [(L["dob"], L.date(inp.get("date"))), (L["tob"], time_of_day(inp.get("time"))), (L["pob"], place)]
    if inp.get("city") and coords(inp):
        rows.append((L["coordinates"], coords(inp)))
    if inp.get("timezone"):
        rows.append((L["timezone"], inp["timezone"]))
    return rows


# ---- engine-data blocks --------------------------------------------------------------------------


def key_facts(L: Labels, chart: dict) -> dict:
    nak = chart["janma_nakshatra"]
    return facts([
        (L["lagna"], L.sign(chart["lagna"]["sign"]), chart["lagna"].get("degree_dms", "")),
        (L["rashi"], L.sign(chart["moon_rashi"]), f"{L['lord']}: {L.graha_short_key(chart['moon_rashi'].get('lord'))}"),
        (L["nakshatra"], L.nakshatra(nak), f"{L['pada']} {nak.get('pada', '')} · {L['lord']}: {L.graha_short_key(nak.get('lord'))}"),
    ])


def chart_block(L: Labels, chart: dict, script: str, title: str, *, small: bool = False, note_text: str | None = None) -> dict:
    names = {"Lagna": L["legend_lagna"], **{key: L.graha_short_key(key) for key in GRAHA_ORDER}}
    return {"type": "chart", "title": title, "svg": Markup(chart_svg(chart, script)), "small": small,
            "legend": chart_legend(script, names), "retro": L["retrograde"],
            "note": L["chart_note"] if note_text is None else note_text}


def navamsa(data: dict) -> dict | None:
    """The D9 chart from the engine (`data["navamsa"]`, or inside the chart). It has the same lagna /
    houses / grahas shape as the lagna chart, so app/pdf/chart_svg.py draws it with the same code.
    None when the engine did not supply one - then the book simply has no D9 page."""
    chart = data.get("chart") or {}
    for candidate in (data.get("navamsa"), chart.get("navamsa"), data.get("d9"), chart.get("d9")):
        if isinstance(candidate, dict) and candidate.get("houses") and candidate.get("grahas"):
            return candidate
    return None


def vargottama_note(L: Labels, d9: dict) -> dict | None:
    """Grahas in the same sign in D1 and D9 - the engine marks them; tradition reads them as strengthened."""
    names = [L.graha_short_key(key) for key in d9.get("vargottama") or [] if isinstance(key, str)]
    if d9.get("lagna_vargottama"):
        names.insert(0, L["legend_lagna"])
    return note(f"{L['vargottama']}: {', '.join(names)}") if names else None


def _combustion(chart: dict, dignity: dict | None) -> dict:
    """{graha key: True / False / None} - the engine's combustion verdict per graha.

    It ships two ways: as `combust` on every graha of the chart, and inside the `dignity` block as
    `combustion.applicable/combust`. Either is read; **None means "does not apply"** (Surya, Rahu, Ketu),
    which the table prints as a dash, never as "no". {} - no verdict anywhere - prints no column at all."""
    out: dict = {}
    for key, entry in (dignity or {}).items():
        block = (entry or {}).get("combustion")
        if isinstance(block, dict):
            out[key] = None if not block.get("applicable") else bool(block.get("combust"))
    for key, position in (chart.get("grahas") or {}).items():
        if key not in out and isinstance(position, dict) and "combust" in position:
            out[key] = None if position["combust"] is None else bool(position["combust"])
    return out if any(value is not None for value in out.values()) else {}


def graha_table(L: Labels, chart: dict, *, title: str | None = None, dignity: dict | None = None) -> dict:
    """Planet table: sign, degree, nakshatra + pada, house, retrograde and - when the engine supplies the
    dignity block - combust. `dignity` is `data["dignity"]`: {graha key: {..., "combustion": {...}}}."""
    burnt = _combustion(chart, dignity)
    combust = bool(burnt)
    lagna = chart["lagna"]
    dash = "–"
    first = [L["lagna_row"], L.sign(lagna["sign"]), lagna.get("degree_dms", ""), L.nakshatra(lagna.get("nakshatra")),
             str(lagna.get("pada", "")), "1", dash]
    rows = [{"cells": [*first, dash] if combust else first, "cls": "is-lagna"}]
    for key in GRAHA_ORDER:
        pos = chart["grahas"].get(key)
        if not pos:
            continue
        retro = L["always"] if key in ("Rahu", "Ketu") else L["yes"] if pos.get("retrograde") else L["no"]
        cells = [L.graha(pos.get("graha") or key), L.sign(pos["sign"]), pos.get("degree_dms", ""),
                 L.nakshatra(pos.get("nakshatra")), str(pos.get("pada", "")), str(pos.get("house", "")), retro]
        state = burnt.get(key)  # None = the rule does not apply to this graha (Surya, Rahu, Ketu)
        if combust:
            cells.append(dash if state is None else (L["yes"] if state else L["no"]))
        rows.append({"cells": cells, "cls": "is-flagged" if state else ""})
    columns = [L["col_graha"], L["col_sign"], L["col_degree"], L["col_nakshatra"], L["col_pada"], L["col_house"],
               L["col_retro"]]
    if combust:
        columns.append(L["col_combust"])
    return table(columns, rows, title=L["grahas_heading"] if title is None else title, cls="t-grahas", keep=False,
                 note=L["combust_note"] if combust else "")


def _same_period(a: dict | None, b: dict | None) -> bool:
    return bool(a and b and a.get("start") == b.get("start") and a["lord"]["key"] == b["lord"]["key"])


def dasha_cycle(dasha: dict) -> int:
    """Which round of the 120-year Vimshottari cycle the CURRENT period is in: 1 normally, 2 or more for a
    chart older than one cycle (the engine repeats the sequence, as the texts imply). 1 when not said."""
    current = (dasha.get("current") or {}).get("mahadasha") or {}
    for value in (current.get("cycle"), dasha.get("cycles_to_reach_as_of")):
        if isinstance(value, int) and value > 0:
            return value
    return 1


def dasha_now(L: Labels, dasha: dict) -> dict:
    """Current mahadasha / antardasha + the balance at birth, as fact tiles. Past the first 120 years the
    running period is in a later round, and the tile says so - otherwise it silently contradicts the
    complete Vimshottari table, which lists the first cycle only."""
    current = dasha.get("current") or {}
    maha_now, antar_now = current.get("mahadasha"), current.get("antardasha")
    balance = dasha.get("balance_at_birth")
    cycle = dasha_cycle(dasha)
    round_note = f" \u00b7 {L['round'].format(n=cycle)}" if cycle > 1 else ""
    return facts([
        maha_now and (L["current_maha"], L.graha(maha_now["lord"]),
                      L.label(maha_now, fallback_start=maha_now["start"], fallback_end=maha_now["end"]) + round_note),
        antar_now and (L["current_antar"], L.graha(antar_now["lord"]), L.label(antar_now, fallback_start=antar_now["start"], fallback_end=antar_now["end"])),
        balance and (L["balance"], L.graha(balance["lord"]),
                     L["balance_fmt"].format(y=balance["years"], m=balance["months"], d=balance["days"])),
    ])


def dasha_tables(L: Labels, dasha: dict) -> list[dict]:
    """Mahadasha timeline + the antardashas of the running mahadasha, side by side.

    Past the first 120 years the running mahadasha is in a later round, so it is NOT one of the nine rows
    here and the antardasha table beside them would be the wrong century's. It is left out and the caption
    says why; the reader's own dated periods are in Part D either way."""
    current = dasha.get("current") or {}
    maha_now, antar_now = current.get("mahadasha"), current.get("antardasha")
    maha_rows, antar_rows, antar_title = [], [], ""
    for maha in dasha.get("mahadashas") or []:
        is_now = _same_period(maha, maha_now)
        maha_rows.append({"cells": [L.graha(maha["lord"]) + (f" ({L['now']})" if is_now else ""), fmt_num(maha.get("years")),
                                    L.date(maha["start"]), L.date(maha["end"])], "cls": "is-current" if is_now else ""})
        if is_now:
            antar_title = L["antar_in_current"].format(lord=L.graha_short(maha["lord"]))
            for antar in maha.get("antardashas") or []:
                running = _same_period(antar, antar_now)
                antar_rows.append({"cells": [L.graha(antar["lord"]) + (f" ({L['now']})" if running else ""),
                                             L.date(antar["start"]), L.date(antar["end"])],
                                   "cls": "is-current" if running else ""})
    pair = [table([L["col_maha"], L["col_years"], L["col_from"], L["col_to"]], maha_rows, title=L["maha_timeline"], cls="t-compact")]
    if antar_rows:
        pair.append(table([L["col_antar"], L["col_from"], L["col_to"]], antar_rows, title=antar_title, cls="t-compact"))
    cycle = dasha_cycle(dasha)
    footnote = L["dasha_note"].format(date=L.date(dasha.get("as_of")))
    if cycle > 1:
        footnote = f"{L['cycle_note'].format(n=cycle)} {footnote}"
    return [{"type": "columns", "title": "", "blocks": pair}, note(footnote)]


def full_dasha(L: Labels, dasha: dict) -> dict:
    """The complete Vimshottari table: the nine mahadashas of the FIRST 120-year cycle from birth, which is
    the classical object a reader recognises. For a chart older than that the running period is in a later
    round and therefore after the last row here, so the table is captioned to say exactly that rather than
    leaving the reader to find a contradiction between this grid and the "current period" tile."""
    current = (dasha.get("current") or {}).get("mahadasha")
    cards = []
    for maha in dasha.get("mahadashas") or []:
        cards.append({
            "title": L.graha(maha["lord"]), "dates": L.label(maha, fallback_start=maha["start"], fallback_end=maha["end"]),
            "current": _same_period(maha, current),
            "rows": [(L.graha_short(antar["lord"]), L.date(antar["start"]), L.date(antar["end"]))
                     for antar in maha.get("antardashas") or []],
        })
    cycle = dasha_cycle(dasha)
    return {"type": "dasha_grid", "title": L["full_dasha"], "cards": cards,
            "note": L["cycle_note"].format(n=cycle) if cycle > 1 else ""}


def outlook_table(L: Labels, windows: list[dict]) -> dict:
    rows = []
    for window in windows:
        periods = [f"{L.graha_short(p['mahadasha'])} – {L.graha_short(p['antardasha'])}: {L.label(p, fallback_start=p['start'], fallback_end=p['end'])}"
                   for p in window.get("dasha_periods") or []]
        ingresses = []
        for item in window.get("slow_graha_ingresses") or []:
            text = f"{L.date(item['date'])}: " + L["ingress_fmt"].format(graha=L.graha_short(item["graha"]),
                                                                        sign=L.sign(item["to_sign"], short=True))
            if item.get("house_from_moon"):
                text += f" ({L['from_moon'].format(n=L.nth(item['house_from_moon']))})"
            if item.get("retrograde_entry") and item["graha"]["key"] not in ("Rahu", "Ketu"):
                text += f" [{L['retrograde']}]"
            ingresses.append(text)
        rows.append({"cells": [str(window["year"]), {"lines": periods or [L["none"]]}, {"lines": ingresses or [L["none"]]}], "cls": ""})
    return table([L["col_year"], L["col_dasha_periods"], L["col_ingresses"]], rows,
                 title=L["outlook_table"], cls="t-outlook", keep=False)


def mangal_refs(L: Labels, dosha: dict, title: str = "") -> dict:
    refs = [("from_lagna", "from_lagna"), ("from_moon_ref", "from_moon"), ("from_venus", "from_venus")]
    rows = []
    for label_key, data_key in refs:
        info = dosha.get(data_key) or {}
        rows.append({"cells": [L[label_key], L.house(info.get("mars_house")), L["yes"] if info.get("dosha") else L["no"]],
                     "cls": "is-flagged" if info.get("dosha") else ""})
    return table([L["col_counted"], L["col_mars_in"], L["col_triggers"]], rows, title=title, cls="t-compact")


def cancellations(L: Labels, dosha: dict) -> dict | None:
    if not dosha.get("present") or not dosha.get("cancellations"):
        return None  # "applies" with no dosha would only confuse
    rows = [{"cells": [L.cancellation(rule), L["applies"] if rule.get("applies") else L["not_applies"]],
             "cls": "is-ok" if rule.get("applies") else "is-muted"} for rule in dosha["cancellations"]]
    return table([L["col_rule"], L["col_applies"]], rows, title=L["cancellations"], cls="t-rules")


def mangal_blocks(L: Labels, chart: dict) -> list[dict]:
    dosha, mars = chart["mangal_dosha"], chart["grahas"]["Mars"]
    mars_sub = f"{mars.get('degree_dms', '')} · {L.nakshatra(mars.get('nakshatra'))} · {L.house(mars.get('house'))}"
    if mars.get("retrograde"):
        mars_sub += f" · {L['retrograde']}"
    return [
        {"type": "banner", "tone": "ok" if not dosha.get("present") else "info" if dosha.get("cancellation_applies") else "warn",
         "title": L.mangal_status(dosha), "text": ""},
        facts([(L["intensity"], L.intensity(dosha.get("intensity")), ""),
               (L["mars"], L.sign(mars["sign"]), mars_sub),
               (L["lagna"], L.sign(chart["lagna"]["sign"]), ""),
               (L["rashi"], L.sign(chart["moon_rashi"]), "")]),
        mangal_refs(L, dosha, L["mars_refs"]),
        note(L["mangal_rule"]),
    ]


def _sade_status_key(sade: dict) -> str:
    if sade.get("active"):
        return "active"
    return "paused" if (sade.get("cycle") or {}).get("which") == "current" else "inactive"


def sade_blocks(L: Labels, sade: dict) -> list[dict]:
    cycle = sade.get("cycle") or {}
    status = _sade_status_key(sade)
    phase_label, phase_note, _ = L.phase(sade.get("phase")) if sade.get("phase") else ("", "", 0)
    cycle_label = L["cycle_current"] if cycle.get("which") == "current" else L["cycle_next"]
    return [
        # Brand rule: an ACTIVE sade sati is a caution period and takes Warning, the
        # same tone as an active mangal dosha. "Paused" (the cycle has begun but Shani is out of range
        # just now) is information, not caution, so it stays neutral - and an absent one is Success.
        {"type": "banner", "tone": "ok" if status == "inactive" else "warn" if status == "active" else "info",
         "title": L.sade_status(status) + (f": {phase_label}" if status == "active" and phase_label else ""),
         "text": phase_note if status == "active" else ""},
        facts([(L["moon_sign"], L.sign(sade.get("moon_sign")), ""),
               (L["saturn_now"], L.sign(sade.get("saturn_sign")),
                L["from_moon"].format(n=L.nth(sade["saturn_house_from_moon"])) if sade.get("saturn_house_from_moon") else ""),
               cycle.get("start") and (cycle_label, L.label(cycle, fallback_start=cycle["start"], fallback_end=cycle["end"]), ""),
               (L["as_of"], L.date(sade.get("as_of")), "")]),
    ]


def sade_periods(L: Labels, sade: dict) -> dict | None:
    cycle = sade.get("cycle") or {}
    if not cycle.get("periods"):
        return None
    as_of, moon_index = sade.get("as_of") or "", (sade.get("moon_sign") or {}).get("index", 1)
    rows = []
    for period in cycle["periods"]:
        label, _, offset = L.phase(period.get("phase"))
        running = period["start"] <= as_of < period["end"]
        rows.append({"cells": [label + (f" ({L['now']})" if running else ""), L.sign_by_index(moon_index + offset),
                               L.date(period["start"]), L.date(period["end"])], "cls": "is-current" if running else ""})
    title = L["cycle_current"] if cycle.get("which") == "current" else L["cycle_next"]
    return table([L["col_phase"], L["col_saturn_in"], L["col_from"], L["col_to"]], rows,
                 title=f"{title}: {L.label(cycle, fallback_start=cycle['start'], fallback_end=cycle['end'])}", cls="t-compact", note=L["sade_note"])


def koota_table(L: Labels, matching: dict) -> dict:
    rows = []
    for item in matching.get("kootas") or []:
        name, meaning = L.koota(item["koota"])
        rows.append({"cells": [(name, meaning), L.koota_value(item["koota"], item.get("boy")),
                               L.koota_value(item["koota"], item.get("girl")),
                               f"{fmt_num(item.get('score'))} / {fmt_num(item.get('max'))}"],
                     "cls": "is-flagged" if item.get("score") == 0 else ""})
    rows.append({"cells": [L["total"], "", "", f"{fmt_num(matching.get('total'))} / {fmt_num(matching.get('max_total'))}"],
                 "cls": "is-total"})
    return table([L["col_koota"], L["boy"], L["girl"], L["col_points"]], rows, title=L["guna_heading"], cls="t-kootas")


def _dosha_status(L: Labels, dosha: dict | None) -> str:
    if not dosha or not dosha.get("present"):
        return L["dosha_absent"]
    return L["dosha_cancelled"] if dosha.get("cancellation_applies") else L["dosha_present"]


def matching_doshas(L: Labels, matching: dict) -> dict:
    doshas = matching.get("doshas") or {}
    bhakoot = doshas.get("bhakoot_dosha") or {}
    distance = bhakoot.get("sign_distance") or []
    text = L["moon_distance"].format(a=distance[0], b=distance[1]) if len(distance) == 2 else ""
    rows = [[L["nadi_dosha"], _dosha_status(L, doshas.get("nadi_dosha"))],
            [L["bhakoot_dosha"], (_dosha_status(L, bhakoot), text) if text else _dosha_status(L, bhakoot)]]
    return table([L["doshas_heading"], L["status"]], rows, cls="t-compact")


def mangal_compare(L: Labels, matching: dict) -> list[dict]:
    mangal = matching.get("mangal_dosha") or {}
    boy, girl = mangal.get("boy") or {}, mangal.get("girl") or {}
    if mangal.get("compatible"):
        text = L["mangal_compatible_both"] if boy.get("present") else L["mangal_compatible_none"]
    else:
        text = L["mangal_one_sided"]
    pair = []
    for who, dosha in ((L["boy"], boy), (L["girl"], girl)):
        title = f"{who}: {L.mangal_status(dosha)}"
        if dosha.get("present"):
            title += f" ({L['intensity']}: {L.intensity(dosha.get('intensity'))})"
        pair.append(mangal_refs(L, dosha, title))
    return [{"type": "banner", "tone": "ok" if mangal.get("compatible") else "info", "title": L["mangal_compare"], "text": text},
            {"type": "columns", "title": "", "blocks": pair}]


def score_block(L: Labels, matching: dict) -> dict:
    return {"type": "score", "total": fmt_num(matching.get("total")), "max": fmt_num(matching.get("max_total")),
            "unit": L["gunas"], "percent": max(0.0, min(100.0, float(matching.get("percentage") or 0))),
            "percent_text": f"{fmt_num(matching.get('percentage'))}%", "verdict": L.verdict(matching.get("verdict"))}


# ---- AI-text blocks ------------------------------------------------------------------------------


def _stone_name(L: Labels, entry: dict) -> str:
    """"Ruby (Manikya)" / "माणिक्य (Ruby)" - the engine gives the English name, the Sanskrit one and its
    Devanagari spelling; we never translate a stone name ourselves."""
    english, devanagari = str(entry.get("stone") or "").strip(), str(entry.get("devanagari") or "").strip()
    sanskrit = str(entry.get("sanskrit") or "").strip()
    if L.lang == "en":
        return f"{english} ({sanskrit})" if sanskrit else english
    return f"{devanagari or sanskrit} ({english})" if english else (devanagari or sanskrit)


def gemstone(L: Labels, gem: dict | None, written: dict | None = None) -> list[dict]:
    """PART F: the engine's gemstone table - one row per recommended stone, then what to avoid, then the
    writer's own note about it (`report["gemstone"]`, which is in the reader's language).

    The engine's `weight` guidance is deliberately NOT printed: the book never names a weight, a carat or
    a price, so nobody can read it as a shopping list (app/ai/book.py holds the writer to the same line)."""
    written = written if isinstance(written, dict) else {}
    recommended = [entry for entry in (gem or {}).get("recommended") or [] if isinstance(entry, dict)]
    if not recommended:  # no engine table: print the writer's own card, if there is one
        rows = [(L["gem_stone"], written.get("stone")), (L["gem_metal"], written.get("metal")),
                (L["gem_finger"], written.get("finger")), (L["gem_day"], written.get("day"))]
        tiles = [(label, str(value).strip(), "") for label, value in rows if str(value or "").strip()]
        if not tiles:
            return []
        out = [facts(tiles), prose([str(written.get("note") or "").strip()])]
        if str(written.get("avoid") or "").strip():
            out.append(note(f"{L['gem_avoid']}: {written['avoid'].strip()}"))
        return [block for block in out if block]
    rows = []
    for entry in recommended:
        rows.append([(_stone_name(L, entry), L.gem_role(entry)), L.graha(entry.get("graha")),
                     L.gem_term(entry.get("metal")), L.gem_term(entry.get("finger")), L.gem_term(entry.get("day"))])
    out = [table([L["gem_stone"], L["col_graha"], L["gem_metal"], L["gem_finger"], L["gem_day"]], rows,
                 cls="t-gems", keep=False)]
    avoid = [_stone_name(L, entry) for entry in (gem or {}).get("avoid") or [] if isinstance(entry, dict)]
    if avoid:
        out.append(note(f"{L['gem_avoid']}: {', '.join(name for name in avoid if name)}"))
    elif str(written.get("avoid") or "").strip():
        out.append(note(f"{L['gem_avoid']}: {written['avoid'].strip()}"))
    out.append(prose([str(written.get("note") or "").strip()]))
    # `wearing_note` / `presentation` in the engine block are written for the model, in English; the
    # reader gets the writer's own gemstone chapter in their language instead.
    return [block for block in out if block]


def year_table(L: Labels, rows: list) -> dict | None:
    """PART G from the engine's own year table: year, its dasha periods, and the transits that define it.
    Printed only when the writer's own year table is missing, so the part is never two tables of one thing."""
    out = []
    for year in rows or []:
        if not isinstance(year, dict) or not year.get("year"):
            continue
        periods = [f"{L.graha_short(period['mahadasha'])} \u2013 {L.graha_short(period['antardasha'])}: "
                   f"{L.label(period)}"
                   for period in year.get("dashas") or []
                   if period.get("mahadasha") and period.get("antardasha") and period.get("range")]
        moves = []
        for event in year.get("transits") or []:
            sign = L.sign(event.get("sign") or event.get("to_sign"), short=True)
            kind = str(event.get("event") or "")
            key = "station_retro_fmt" if "retrograde" in kind else "station_direct_fmt" if "direct" in kind else "ingress_fmt"
            moves.append(f"{L.date(event.get('date'))}: " + L[key].format(graha=L.graha_short(event["graha"]), sign=sign))
        out.append({"cells": [str(year["year"]), {"lines": periods or [L["none"]]}, {"lines": moves or [L["none"]]}],
                    "cls": ""})
    if not out:
        return None
    return table([L["col_year"], L["col_dasha_periods"], L["col_ingresses"]], out,
                 title=L["outlook_table"], cls="t-outlook", keep=False)


# ---- the trust box and the accuracy caveats (every PDF, paid and free) -----------------------------


def trust_block(L: Labels, *, ai: bool) -> dict:
    """"How this report was made" - a trust requirement, on the first page of every PDF we produce.

    It is not a sales pitch. Its job is to answer the one question an AI-flavoured astrology product has
    to answer before anything else: were these DATES computed, or invented? So the first paragraph names
    Swiss Ephemeris and what came out of it, and only the second one mentions AI at all.

    `ai=False` is the free chart PDF, which calls no model and contains no written interpretation. It
    still gets a second paragraph, because the site's other pages do mention AI and a reader arrives here
    carrying that: saying "nothing here was written by AI" outright is the honest answer, and it keeps the
    rule that AI is never named on a page without Swiss Ephemeris beside it in the same section."""
    return {"type": "trust", "title": L["trust_heading"] if ai else L["trust_heading_chart"],
            "paragraphs": [L["trust_calc"], L["trust_ai"] if ai else L["trust_no_ai"]]}


def accuracy_block(L: Labels, chart: dict, *, approximate_time: bool = False) -> dict | None:
    """The two caveats the engine flags on `chart["accuracy"]`, or None when it flags neither (~94% of charts).

    Word for word what the chart page prints (app/static/js/render.js, `accuracyHtml`), so a customer who
    reads the page and then the PDF is told the same thing twice rather than two different things once.
    Both are about the LAGNA - the only part of a chart that a few kilometres or a few minutes can move -
    and both end by naming what does NOT move, so they inform rather than alarm.

    `approximate_time` is the one caveat the ENGINE cannot raise, because nothing in the chart records that
    the time was guessed - the caller knows and the chart does not. It is deliberately NOT written into
    `chart["accuracy"]` on the way through: that block is the engine's verdict, and a caller-supplied flag
    dressed up as one would be the same blurring of computed and claimed that the rest of this file exists
    to avoid. It comes first, because it dominates the other two: a three-hour bucket moves the lagna every
    single time, where a near-cusp birthplace moves it rarely.

    The wording carries measured proportions rather than hedges, and `tests/test_pdf.py` re-measures every
    one of them against the engine so the sentence cannot drift away from the behaviour. The window is
    ninety minutes - the furthest the form's presets can put a reader from their real time - and over
    5000 random births compared against the same birth ninety minutes later:

        lagna 75%  ~  mangal dosha 9.5%  ~  nakshatra 6.6%  ~  mahadasha LORD 6.6%
        Moon sign 2.6%  ~  sade sati 0.4%  ~  dasha start, same lord: >1 y for 43%, >2 y IMPOSSIBLE

    That last one is a derivation, not a measurement: ninety minutes of Moon travel is at most 0.95 of a
    degree, 0.071 of a nakshatra, which over the 20-year Venus period is 1.44 years. The observed maximum
    is 1.44 years - the measurement rests ON the bound rather than inside it. So the copy says the dates
    can never move further, which is a stronger and truer claim than saying they rarely do.

    The window is a fact about the FORM, so it moves when the form does: it was three hours until an
    03:00 preset closed the six-hour gap from midnight, and every figure above halved.

    Two things this went through are worth keeping, because both would happen again. First, SADE SATI IS
    NOT IMMUNE: it follows the Moon sign, so the status flips for about one chart in a hundred. An earlier
    draft said it "does not depend on the birth time at all"; two independent 150-birth samples both saw
    zero and agreed with each other, and both were wrong. That absolute was the REASSURING half of the
    caveat - the half a reader leans on - which is the half worth measuring hardest.

    Second, every figure here was once about 50% too high, from a sweep that built the later time with
    `time(hour % 24)` - so a bucket starting at 21:00 compared 21:00 against 00:00 THE SAME MORNING, a
    21-hour gap sold as three. It inflated one sample in eight, survived three random seeds, and was only
    caught by noticing that some "shifts" exceeded what the Moon can physically do in three hours. The
    dates cannot move more than about 2.9 years (the Moon covers at most ~1.9 deg of a 13.3 deg nakshatra
    in three hours, times the 20-year Venus period), so anything past that was arithmetic, not astrology.
    A sanity bound the data cannot cross is worth more than another thousand samples.

    Nothing else is decided here: the engine sets `sensitive` and `non_standard`, and those caveats are
    printed if and only if it did. A caveat on a chart where it could not have mattered is noise that
    teaches people to skip the one that does matter."""
    accuracy = chart.get("accuracy") or {}
    boundary, clock = accuracy.get("lagna_boundary") or {}, accuracy.get("clock") or {}
    notes = [L["acc_approx_time"]] if approximate_time else []
    if boundary.get("sensitive"):
        city = (chart.get("input") or {}).get("city")
        # two templates, not one with a substituted phrase: Marathi attaches its postposition to the noun
        # ("ठिकाणापासून"), which a {place} slot cannot do for both a city name and "the place you entered"
        notes.append(L["acc_place" if city else "acc_place_here"].format(
            km=round(boundary.get("km_to_change_sign") or 0), unit=L["acc_km"], place=city or "",
            adjacent=L.sign(boundary.get("adjacent_sign"), short=True),
            lagna=L.sign((chart.get("lagna") or {}).get("sign"), short=True)))
    if clock.get("non_standard"):
        era = L.era(clock)
        offset = int(clock.get("offset_seconds") or 0)
        notes.append(L["acc_clock"].format(
            era=era, minutes=round(abs(offset - IST_OFFSET_SECONDS) / 60),
            direction=L["acc_ahead"] if offset > IST_OFFSET_SECONDS else L["acc_behind"])
            if era else L["acc_clock_plain"].format(offset=clock.get("offset") or ""))
    return {"type": "caveats", "title": L["acc_heading"], "paragraphs": notes} if notes else None


def excluded_block(L: Labels) -> dict:
    """"What this free chart does not include" - the free PDF only.

    The product rule is that the paid tiers' extra value has to be OBVIOUS, and the honest way to do that is
    to say what is missing rather than to cripple what is here. No price and no product id: a PDF outlives
    a price list, and app/payments/catalogue.py is the only place an amount may ever come from."""
    return {"type": "excluded", "title": L["excluded_heading"], "items": L.excluded(), "note": L["excluded_note"]}
