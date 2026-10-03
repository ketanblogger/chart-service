"""The book: cover, table of contents, and PARTS made of CHAPTERS.

The paid Kundali report is printed as a book, not as a web page dump. This module turns one report JSON
into that structure; app/pdf/blocks.py draws what goes inside a chapter and templates/report.html lays it out.

Two shapes are accepted, so the renderer never depends on when `ai-layer` lands the new one:

1. **The book shape** - `report["parts"]` (app/ai/book.py), a list of
   `{id, heading, chapters: [{id, heading, paragraphs, bullets, highlights, windows, table}]}`.
   Part ids, in order: `labels.PART_IDS` (the eight parts A-H). A chapter carries at most one of
   - `highlights`: `[{key, heading, lines}]`    - Part A only;
   - `windows`: `[{window_id, start, end, dasha, transits, headline, paragraphs, areas}]` - Part D and
     anything else dated. The model only ever names a window **id**; `app/ai/book_report.py` fills the
     engine's dates and dasha lords in around it (and if it ever hands us an unresolved id we look it up in
     `data["timeline"]` ourselves), so no date in this book was ever written by the model;
   - `table`: `{columns, rows}` - Part G.
2. **The Phase 3 shape** - `report["sections"]`, which the other three products still use. Those become one
   "Your reading" part with a chapter per section, so all four products print as the same kind of book.

Whatever the shape, the engine blocks (charts, graha table, dasha tables, dosha tables, gemstone) are OURS:
they are built from `report["data"]` and slotted next to the chapter they belong to. A chapter the model did
not write still gets its engine block, and engine data with no chapter is appended to the part, never dropped.

Every heading the book prints gets an id, in document order; render.py reads those ids back out of the
finished HTML to fill the table of contents with real page numbers (two-pass render, see browser.py).
"""

from . import blocks as B
from .labels import PART_IDS, Labels

# Part B: chapters we print ourselves, in this order, whether or not the model wrote text for them.
# (`what_your_chart_looks_like` and `navamsa` are the model's own chapter ids from app/ai/book.py.)
PART_B_CHAPTERS = ("what_your_chart_looks_like", "navamsa", "graha_positions")
PART_F_CHAPTERS = ("mangal_dosha", "sade_sati", "other_doshas", "gemstone", "remedies")
MAX_WINDOW_TRANSITS = 3  # a window prints its first few engine transit events, not all of them


class Anchors:
    """Sequential ids for headings - "hd-1", "hd-2" ... in the order the template prints them."""

    def __init__(self) -> None:
        self.count = 0

    def next(self) -> str:
        self.count += 1
        return f"hd-{self.count}"


def _window_facts(window: dict) -> dict:
    """One engine timeline window, flattened to the keys the book reads (`start`, `end`, `dasha`,
    `transits`). The engine nests the dates under `range`; `app/ai/book_report.py` publishes them flat."""
    if not isinstance(window, dict):
        return {}
    dates = window.get("range") if isinstance(window.get("range"), dict) else {}
    return {**window, "start": window.get("start") or dates.get("start"),
            "end": window.get("end") or dates.get("end")}


def timeline_headings(data: dict, lang: str) -> dict:
    """{chapter id: the engine's label for the span that chapter covers} for the timeline chapters
    ("year_2028", "block_2032"). Two uses: the heading fallback when the writer's is blank, and - since
    `app/ai/book_report.compose_heading` puts exactly this label in front of the writer's theme - telling
    the span apart from the theme again, so the page can set them as a kicker and a title instead of one
    long line that repeats the dates the first window underneath is about to print."""
    timeline = (data or {}).get("timeline") or {}
    out = {}
    for year in timeline.get("near_years") or timeline.get("years") or []:
        if isinstance(year, dict) and year.get("year"):
            out[f"year_{year['year']}"] = Labels(lang).label(year) or str(year["year"])
    for block in timeline.get("far_blocks") or timeline.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        dates = block.get("range") if isinstance(block.get("range"), dict) else {}
        start = dates.get("start") or block.get("start")
        # the engine labels every range it produces, in every language; we only print what it gives us
        out[f"block_{str(start or '')[:4]}"] = Labels(lang).label(block)
    return {key: value for key, value in out.items() if key and value}


def timeline_index(data: dict) -> dict:
    """{window id: window facts} over the engine timeline. Only a fallback: the report JSON normally
    carries each window already resolved (app/ai/book_report.py), and then nothing is looked up here."""
    timeline = (data or {}).get("timeline") or {}
    past = timeline.get("past")
    groups = [timeline.get("windows"), timeline.get("current_year"),
              (past or {}).get("entries") if isinstance(past, dict) else past]
    for group in (timeline.get("near_years") or []) + (timeline.get("far_blocks") or []):
        if isinstance(group, dict):
            groups.append(group.get("windows"))
    index = {}
    for group in groups:
        for window in group or []:
            if isinstance(window, dict) and window.get("id"):
                index[window["id"]] = _window_facts(window)
    return index


# ---- chapters ------------------------------------------------------------------------------------


def _transit_lines(L: Labels, window: dict) -> list[str]:
    lines = []
    for event in (window.get("transits") or [])[:MAX_WINDOW_TRANSITS]:
        graha = L.graha_short(event["graha"]) if event.get("graha") else ""
        sign = L.sign(event.get("to_sign") or event.get("sign"), short=True)
        # the engine writes the event in English ("enters", "turns retrograde in"); pick our own wording
        kind = str(event.get("event") or "")
        key = "station_retro_fmt" if "retrograde" in kind else "station_direct_fmt" if "direct" in kind else "ingress_fmt"
        text = L[key].format(graha=graha, sign=sign) if sign else f"{graha} {kind}".strip()
        if event.get("house_from_moon"):
            text += f" ({L['from_moon'].format(n=L.nth(event['house_from_moon']))})"
        lines.append(f"{L.date(event.get('date'))}: {text}")
    return lines


def _saturn_lines(L: Labels, window: dict) -> list[str]:
    """The Shani phase running inside this window (sade sati or a dhaiya), with the engine's own dates."""
    lines = []
    for phase in window.get("saturn_phases") or []:
        if not isinstance(phase, dict):
            continue
        name = L.phase_name(str(phase.get("phase") or ""))
        if not name:
            continue  # a phase key we have no name for is left out rather than printed in English
        dates = L.label(phase, fallback_start=phase.get("start"), fallback_end=phase.get("end"))
        lines.append(f"{L['saturn_phase']}: {name}" + (f" ({dates})" if dates else ""))
    return lines


def _area_items(L: Labels, entries) -> tuple[list[str], list[dict]]:
    """The life areas of one window, as (bare tags, {label, text} lines).

    Two shapes reach here, and for a long time only one of them worked. A stored report carries the
    published contract, [{area, text}], which app/ai/schema.py `pair_areas` builds from the model's
    parallel `areas` / `area_lines`; the two book fixtures carry the older plain-string shape. The dict
    was being handed to AREA_LABELS.get as a key - `unhashable type: dict` - which took down the render
    of every paid report PDF, while every test passed because no fixture had the shape production writes.

    The sentences are printed rather than discarded. Only the tag row was ever rendered, so the per-area
    line the model writes (and the customer pays for) was dropped, which is also why labels.py has carried
    an `areas_heading` string in all three languages that nothing ever used.
    """
    tags, lines = [], []
    for entry in entries or []:
        label = L.area(entry)
        if not label:
            continue
        text = ""
        if isinstance(entry, dict):
            text = str(entry.get("text") or "").strip()
        elif isinstance(entry, (list, tuple)) and len(entry) == 2:
            text = str(entry[1] or "").strip()
        (lines if text else tags).append({"label": label, "text": text} if text else label)
    return tags, lines


def _windows_block(L: Labels, entries: list, index: dict, anchors: Anchors) -> dict | None:
    """The dated sub-sections of a timeline chapter. The model supplies `window_id` and prose; the date
    range, the dasha lords and the transits all come from the engine window it names."""
    items = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        # the resolved shape (book_report._resolve_windows) carries the dates itself; an unresolved one
        # names a window id, which we look up in the engine timeline. Either way the dates are the engine's.
        window = {**(index.get(entry.get("window_id")) or {}), **entry}
        # the engine formatted this range, in this language, at the precision it chose - print it verbatim
        label = L.label(window)
        paragraphs = [p.strip() for p in (entry.get("paragraphs") or []) if p and p.strip()]
        if not label or not paragraphs:
            continue  # a window we cannot date, or with nothing in it, is not printed
        dasha = window.get("dasha") if isinstance(window.get("dasha"), dict) else window
        lords = [L.graha_short(dasha[key]) for key in ("mahadasha", "antardasha", "pratyantardasha")
                 if isinstance(dasha.get(key), dict) and dasha[key].get("name")]
        tags, area_lines = _area_items(L, entry.get("areas"))
        items.append({
            "id": anchors.next(), "label": label, "headline": (entry.get("headline") or "").strip(),
            "sub": " – ".join(lords), "paragraphs": paragraphs,
            "areas": tags, "area_lines": area_lines,
            "areas_heading": L["areas_heading"] if area_lines else "",
            "transits": _saturn_lines(L, window) + _transit_lines(L, window),
        })
    return {"type": "windows", "items": items} if items else None


# Part A - the seven highlight cards, in the order the book prints them. The engine's verdict for an item
# sits with the writer's lines for it. `mangal` is the key app/ai/schema.py uses; `mangal_dosha` is older.
HIGHLIGHT_KEYS = ("basics", "mangal", "sade_sati", "dasha", "strengths", "cautions", "yogas")
HIGHLIGHT_ALIASES = {"mangal_dosha": "mangal"}


def _highlight_lines(L: Labels, key: str, value) -> list[str]:
    """One Part A item as the lines the book prints. Shapes come from `CALL_SCHEMA["highlights"]`."""
    if isinstance(value, list):  # strengths, cautions (three strings), yogas ({name, text})
        lines = []
        for item in value:
            if isinstance(item, dict):
                name, text = (item.get("name") or "").strip(), (item.get("text") or "").strip()
                item = f"{name} \u2014 {text}".strip(" \u2014") if name or text else ""
            if str(item or "").strip():
                lines.append(str(item).strip())
        return lines
    if not isinstance(value, dict):
        return [str(value).strip()] if str(value or "").strip() else []
    labelled = {"remedy": L["hl_remedy"], "guidance": L["hl_guidance"]}
    lines = []
    for field in ("verdict", "mood", "remedy", "guidance"):
        text = str(value.get(field) or "").strip()
        if text:
            lines.append(f"{labelled[field]}: {text}" if field in labelled else text)
    return lines


def _highlights_block(L: Labels, written, engine_cards: dict, chapter_heading: str = "") -> dict | None:
    """Part A: the engine's verdict for each item, with the writer's lines under it.

    `written` is the report's top-level `highlights` object (`{mangal: {...}, strengths: [...], ...}`), or -
    older shape - a chapter's list of `{key, heading, lines}`. Either way an item the writer did not fill
    still prints its engine verdict, and an item with neither is left out."""
    lines_by_key: dict[str, list[str]] = {}
    headings: dict[str, str] = {}
    order: list[str] = []
    if isinstance(written, dict):
        for key, value in written.items():
            key = HIGHLIGHT_ALIASES.get(key, key)
            lines_by_key[key] = _highlight_lines(L, key, value)
            order.append(key)
    else:
        for entry in written or []:
            if not isinstance(entry, dict):
                continue
            key = HIGHLIGHT_ALIASES.get((entry.get("key") or "").strip(), (entry.get("key") or "").strip())
            lines_by_key[key] = [line.strip() for line in entry.get("lines") or [] if line and line.strip()]
            headings[key] = (entry.get("heading") or "").strip()
            order.append(key)

    keys = [key for key in HIGHLIGHT_KEYS if key in lines_by_key or key in engine_cards]
    keys += [key for key in order if key not in keys]
    items = []
    for key in keys:
        lines, blocks = lines_by_key.get(key) or [], engine_cards.get(key) or []
        if not lines and not blocks:
            continue
        heading = headings.get(key) or L.chapter(key)
        items.append({"key": key, "heading": "" if heading == chapter_heading else heading,
                      "lines": lines, "blocks": blocks})
    return {"type": "highlights", "items": items} if items else None


def _ai_table(chapter: dict) -> dict | None:
    table = chapter.get("table")
    if not table or not (table.get("columns") and table.get("rows")):
        return None
    rows = [row for row in table["rows"] if any((cell or "").strip() for cell in row)]
    if not rows:
        return None
    return B.table(list(table["columns"]), rows, cls="t-ai", keep=False)


def _subsections_block(L: Labels, subsections: list, anchors: Anchors) -> dict | None:
    """Phase 3 shape only (the other three products); the book shape uses `windows` instead."""
    items = []
    for sub in subsections or []:
        paragraphs = [p.strip() for p in (sub.get("paragraphs") or []) if p and p.strip()]
        if not paragraphs:
            continue
        items.append({"id": anchors.next(), "heading": (sub.get("heading") or "").strip(), "paragraphs": paragraphs})
    return {"type": "subsections", "items": items} if items else None


def _text_blocks(L: Labels, chapter: dict, anchors: Anchors, index: dict, engine_cards: dict | None,
                 heading: str = "", highlights=None) -> list[dict]:
    """Everything the model wrote for one chapter, in reading order."""
    out = [B.prose(chapter.get("paragraphs")),
           B.bullets(chapter.get("bullets")) if chapter.get("bullets") else None,
           _highlights_block(L, highlights if highlights is not None else chapter.get("highlights"),
                             dict(engine_cards or {}), heading)
           if engine_cards is not None or chapter.get("highlights") else None,
           _windows_block(L, chapter.get("windows"), index, anchors),
           _subsections_block(L, chapter.get("subsections"), anchors),
           _ai_table(chapter)]
    return [block for block in out if block]


def _split_span(heading: str, span: str) -> tuple[str, str]:
    """("Jan 2032 - Dec 2036", "the theme") out of the one composed heading, when it starts with that
    span. The contents page still prints the whole thing; only the chapter opener sets them apart."""
    # our label carries non-breaking spaces (a date must not wrap) and the composed heading does not,
    # so the two are compared with those flattened - and the kicker keeps ours
    flat = heading.replace("\u00a0", " ")
    plain = span.replace("\u00a0", " ")
    if not plain or not flat.startswith(plain):
        return "", heading
    rest = flat[len(plain):].lstrip().lstrip("\u2014\u2013-").strip()
    return (span, rest) if rest else ("", heading)


def _chapter(L: Labels, chapter: dict, anchors: Anchors, index: dict, *, before: list | None = None,
             after: list | None = None, engine_cards: dict | None = None, fallback: str = "",
             highlights=None) -> dict:
    """One chapter = one h2, its engine blocks and its text."""
    chapter_id = (chapter.get("id") or "").strip()
    heading = (chapter.get("heading") or "").strip() or fallback or L.chapter(chapter_id)
    kicker, title = _split_span(heading, fallback)
    anchor = anchors.next()  # ids are handed out in print order: the h2, then the text, then `after`
    blocks = [block for block in (before or []) if block]
    blocks += _text_blocks(L, chapter, anchors, index, engine_cards, heading, highlights)
    tail = after() if callable(after) else after  # a callable builds its blocks (and their ids) last
    return {"anchor": anchor, "id": chapter_id,
            "heading": heading,   # the whole composed string: what the contents page prints
            "kicker": kicker, "title": title,   # ... and how the chapter opener sets it
            "blocks": blocks + [block for block in (tail or []) if block]}


# ---- the engine blocks that belong to each part ----------------------------------------------------


def _highlight_cards(L: Labels, chart: dict) -> dict:
    """Part A: the engine's own verdict for the three items that have one."""
    cards: dict[str, list] = {"basics": [B.key_facts(L, chart)]}
    dosha = chart.get("mangal_dosha") or {}
    if dosha:
        cards["mangal"] = [{
            "type": "banner",
            "tone": "ok" if not dosha.get("present") else "info" if dosha.get("cancellation_applies") else "warn",
            "title": L.mangal_status(dosha),
            "text": f"{L['intensity']}: {L.intensity(dosha.get('intensity'))}" if dosha.get("present") else ""}]
    sade = chart.get("sade_sati") or {}
    if sade:
        cycle = sade.get("cycle") or {}
        status = L.sade_status("active" if sade.get("active") else
                               "paused" if cycle.get("which") == "current" else "inactive")
        if cycle.get("start"):
            which = L["cycle_current"] if cycle.get("which") == "current" else L["cycle_next"]
            status += (f" · {which}: "
                       f"{L.label(cycle, fallback_start=cycle['start'], fallback_end=cycle['end'])}")
        cards["sade_sati"] = [{"type": "banner", "tone": "ok" if not sade.get("active") else "info",
                               "title": status, "text": ""}]
    if chart.get("dasha"):
        cards["dasha"] = [B.dasha_now(L, chart["dasha"])]
    return cards


def _yoga_table(L: Labels, yogas: list) -> dict | None:
    """The yogas the engine found in this chart (`data["yogas"]`): name, how strong, and the rule that
    produced it. The rule is engine text, not interpretation - the writer's chapter does the interpreting."""
    rows = []
    for yoga in yogas or []:
        if not isinstance(yoga, dict) or yoga.get("present") is False:
            continue
        english, devanagari = str(yoga.get("name") or "").strip(), str(yoga.get("devanagari") or "").strip()
        name = english if L.lang == "en" else (devanagari or english)
        if not name:
            continue
        # the engine's `rule` / `combination` text is English and model-facing: the writer's own chapter
        # explains each yoga in the report language, so the table stays to what the engine classified.
        rows.append([name, L.yoga_term(yoga.get("category")), L.yoga_term(yoga.get("nature")),
                     L.yoga_term(yoga.get("strength"))])
    return B.table([L["hl_yogas"], L["col_kind"], L["col_nature"], L["col_strength"]], rows,
                   cls="t-compact", keep=False) if rows else None


def _part_engine_blocks(L: Labels, part_id: str, report: dict, script: str) -> tuple[dict[str, list], list]:
    """(engine blocks per chapter id, engine blocks for the end of the part) for one part of the book."""
    data = report.get("data") or {}
    chart = data.get("chart") or {}
    per_chapter: dict[str, list] = {}
    tail: list = []
    if part_id == "chart_basics" and chart:
        per_chapter["what_your_chart_looks_like"] = [B.chart_block(L, chart, script, ""), B.key_facts(L, chart)]
        navamsa = B.navamsa(data)
        if navamsa:
            per_chapter["navamsa"] = [B.chart_block(L, navamsa, script, "", note_text=L["navamsa_note"]),
                                      B.vargottama_note(L, navamsa)]
        per_chapter["graha_positions"] = [B.graha_table(L, chart, title="", dignity=data.get("dignity"))]
    elif part_id == "timeline" and chart.get("dasha"):
        tail = [B.dasha_now(L, chart["dasha"]), *B.dasha_tables(L, chart["dasha"]), B.full_dasha(L, chart["dasha"])]
    elif part_id in ("doshas_remedies", "remedies") and chart:
        per_chapter["mangal_dosha"] = [*B.mangal_blocks(L, chart), B.cancellations(L, chart["mangal_dosha"])]
        per_chapter["sade_sati"] = [*B.sade_blocks(L, chart["sade_sati"]), B.sade_periods(L, chart["sade_sati"])]
        per_chapter["other_doshas"] = [_yoga_table(L, data.get("yogas"))]
        per_chapter["gemstone"] = B.gemstone(L, data.get("gemstone"), report.get("gemstone"))
    elif part_id == "year_table":
        if data.get("outlook_windows"):  # the Phase 3 shape
            per_chapter["year_by_year"] = [B.outlook_table(L, data["outlook_windows"])]
        elif (data.get("timeline") or {}).get("year_table"):
            per_chapter["year_by_year"] = [B.year_table(L, data["timeline"]["year_table"])]
    return {key: [block for block in value if block] for key, value in per_chapter.items()}, tail


def _remedy_block(L: Labels, report: dict, anchors: Anchors) -> dict | None:
    items = []
    for remedy in report.get("remedies") or []:
        title = (remedy.get("title") or "").strip()
        if not title:
            continue
        items.append({"id": anchors.next(), "type": L.remedy_type(remedy.get("type", "")), "title": title,
                      "description": (remedy.get("description") or "").strip(),
                      "how_to": (remedy.get("how_to") or "").strip(),
                      "frequency": (remedy.get("frequency") or "").strip()})
    return {"type": "remedies", "items": items} if items else None


# ---- parts ---------------------------------------------------------------------------------------


def _ordered_chapters(part_id: str, written: dict) -> list[str]:
    """Which chapter ids this part prints, in print order: ours first where the book fixes an order,
    then everything the model wrote that has not been placed yet."""
    fixed = {"chart_basics": PART_B_CHAPTERS, "doshas_remedies": PART_F_CHAPTERS,
             "remedies": PART_F_CHAPTERS}.get(part_id, ())
    return [*fixed, *[key for key in written if key not in fixed]]


def _part(L: Labels, index: int, part: dict, report: dict, script: str, anchors: Anchors, windows: dict,
          headings: dict) -> dict:
    part_id = (part.get("id") or "").strip()
    anchor = anchors.next()  # the part heading prints before its chapters, so it takes the first id
    per_chapter, tail = _part_engine_blocks(L, part_id, report, script)
    written: dict[str, dict] = {}
    for position, chapter in enumerate(part.get("chapters") or []):
        written.setdefault((chapter.get("id") or "").strip() or f"chapter_{position}", chapter)

    chart = (report.get("data") or {}).get("chart") or {}
    highlight_cards = _highlight_cards(L, chart) if part_id == "highlights" and chart else None

    chapters = []
    for chapter_id in _ordered_chapters(part_id, written):
        text = written.pop(chapter_id, None)
        before = per_chapter.pop(chapter_id, [])
        if part_id == "year_table" and (text or {}).get("table"):
            before = []  # the writer's year table IS Part G; ours is only the fallback
        # a callable, not a list: the remedy cards take their heading ids when the book prints them
        after = ((lambda: [_remedy_block(L, report, anchors)])
                 if chapter_id == "remedies" and part_id in ("doshas_remedies", "remedies")
                 and report.get("remedies") else [])
        if text is None and not before and not after:
            continue  # nothing written and nothing computed: the book simply has no such chapter
        chapters.append(_chapter(L, text or {"id": chapter_id}, anchors, windows, before=before, after=after,
                                 engine_cards=highlight_cards if chapter_id in ("at_a_glance",) else None,
                                 highlights=report.get("highlights") if chapter_id == "at_a_glance" else None,
                                 fallback=headings.get(chapter_id, "")))
        if chapter_id == "at_a_glance":
            highlight_cards = None
    lead: list = []
    if highlight_cards:  # Part A without its chapter: the engine verdicts still get their page
        block = _highlights_block(L, report.get("highlights"), highlight_cards)
        if block:
            lead.append(block)
    for leftover in per_chapter.values():  # engine data whose chapter was never written: never dropped
        tail = [*leftover, *tail]

    return {"anchor": anchor, "id": part_id,
            # the part knows its own letter (app/ai/book_report.py); the position is only the fallback
            "letter": str(part.get("label") or "").strip() or L.part_letter(index),
            "heading": L.part(index, part_id, part.get("heading", "")),
            "intro": (part.get("intro") or "").strip(),
            # `blocks` print before the chapters, `after_blocks` after them: the complete Vimshottari tables
            # are reference material and belong at the END of Part D, not in front of the reading.
            "blocks": [block for block in lead if block],
            "after_blocks": [block for block in tail if block], "chapters": chapters}


def _legacy_parts(L: Labels, report: dict, script: str, names: dict, anchors: Anchors) -> list[dict]:
    """The Phase 3 `sections` shape (matching / mangal-dosha / sade-sati, and any older cached report)."""
    product, data = report.get("product", ""), report.get("data") or {}
    front: list[dict] = []
    attached: dict[str, list] = {}

    if "matching" in data:
        matching, boy, girl = data["matching"], data["boy_chart"], data["girl_chart"]
        front.append(B.score_block(L, matching))
        front.append(B.koota_table(L, matching))
        front.append({"type": "columns", "title": L["charts_heading"], "blocks": [
            B.chart_block(L, boy, script, L["boy"] + (f": {names['boy']}" if names.get("boy") else ""), small=True, note_text=""),
            B.chart_block(L, girl, script, L["girl"] + (f": {names['girl']}" if names.get("girl") else ""), small=True, note_text="")]})
        front.append(B.note(L["chart_note"]))
        attached["growth_areas"] = [B.matching_doshas(L, matching)]
        attached["mangal_dosha"] = B.mangal_compare(L, matching)
    elif "chart" in data:
        chart = data["chart"]
        front.append(B.chart_block(L, chart, script, L["chart_heading"]))
        front.append(B.key_facts(L, chart))
        if product == "mangal-dosha-remedy":
            front += [*B.mangal_blocks(L, chart), B.graha_table(L, chart)]
            attached["mitigating_factors"] = [B.cancellations(L, chart["mangal_dosha"])]
        elif product == "sade-sati-guide":
            front += [*B.sade_blocks(L, chart["sade_sati"]), B.graha_table(L, chart)]
            attached["timeline"] = [B.sade_periods(L, chart["sade_sati"])]
        else:
            front += [B.graha_table(L, chart), B.dasha_now(L, chart["dasha"]), *B.dasha_tables(L, chart["dasha"]),
                      B.full_dasha(L, chart["dasha"])]
            if data.get("outlook_windows"):
                attached["yearly_outlook"] = [B.outlook_table(L, data["outlook_windows"])]
            attached["sade_sati"] = [*B.sade_blocks(L, chart["sade_sati"]), B.sade_periods(L, chart["sade_sati"])]

    front_anchor = anchors.next() if front else None
    reading_anchor = anchors.next()
    chapters = []
    for section in report.get("sections") or []:
        section_id = (section.get("id") or "").strip()
        heading = (section.get("heading") or "").strip() or L.section(product, section_id)
        chapters.append(_chapter(L, {**section, "heading": heading}, anchors, {}, before=attached.pop(section_id, [])))
    for blocks in attached.values():  # a section the contract promised is missing: still print the engine data
        front += [block for block in blocks if block]

    remedies = _remedy_block(L, report, anchors)
    if remedies:
        chapters.append({"anchor": anchors.next(), "id": "remedies", "heading": L["remedies"], "blocks": [remedies]})

    parts = []
    if front_anchor:
        parts.append({"anchor": front_anchor, "id": "chart_basics", "letter": L.part_letter(0),
                      "heading": L.part(0, "chart_basics"), "intro": "",
                      "blocks": [block for block in front if block], "after_blocks": [], "chapters": []})
    parts.append({"anchor": reading_anchor, "id": "reading", "letter": L.part_letter(len(parts)),
                  "heading": L.part(len(parts), "reading"), "intro": "", "blocks": [], "after_blocks": [],
                  "chapters": chapters})
    return parts


def build_parts(report: dict, L: Labels, script: str, names: dict, anchors: Anchors) -> list[dict]:
    """The whole body of the book, in print order."""
    written = [part for part in report.get("parts") or [] if isinstance(part, dict)]
    if not written:
        return _legacy_parts(L, report, script, names, anchors)
    windows = timeline_index(report.get("data") or {})
    headings = timeline_headings(report.get("data") or {}, L.lang)
    seen = {(part.get("id") or "").strip() for part in written}
    extra = []
    for part_id in PART_IDS:  # a part the model never wrote still prints its engine data
        if part_id not in seen:
            per_chapter, tail = _part_engine_blocks(L, part_id, report, script)
            if any(per_chapter.values()) or tail:
                extra.append({"id": part_id, "chapters": []})
    order = {part_id: index for index, part_id in enumerate(PART_IDS)}
    ordered = sorted(written + extra, key=lambda part: order.get((part.get("id") or "").strip(), len(PART_IDS)))
    return [_part(L, index, part, report, script, anchors, windows, headings)
            for index, part in enumerate(ordered)]


def build_toc(L: Labels, parts: list[dict], pages: dict[str, int] | None, *, closing: dict | None = None) -> dict:
    """Contents: every part, every chapter. `pages` maps a heading anchor to its printed page number;
    None (first pass) prints the placeholder, and a missing anchor prints nothing rather than a wrong number."""
    entries = []
    for part in parts:
        entries.append({"level": 1, "anchor": part["anchor"], "kicker": f"{L['part']} {part['letter']}",
                        "text": part["heading"], "page": _page(pages, part["anchor"])})
        for chapter in part["chapters"]:
            entries.append({"level": 2, "anchor": chapter["anchor"], "kicker": "", "text": chapter["heading"],
                            "page": _page(pages, chapter["anchor"])})
    if closing:
        entries.append({"level": 2, "anchor": closing["anchor"], "kicker": "", "text": closing["heading"],
                        "page": _page(pages, closing["anchor"])})
    return {"heading": L["contents"], "entries": entries, "note": L["toc_note"], "filled": pages is not None}


def _page(pages: dict[str, int] | None, anchor: str) -> str:
    if pages is None:
        return "00"  # first pass: a fixed-width placeholder, so filling in real digits cannot reflow the book
    number = pages.get(anchor)
    return str(number) if isinstance(number, int) and number > 0 else ""
