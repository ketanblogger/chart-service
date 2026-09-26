"""JSON schemas the model must fill (structured outputs). The PDF renders these shapes, never prose.

Two schemas live here:

- `report_schema(product)` - the original flat section list, still used by matching-report,
  mangal-dosha-remedy and sade-sati-guide.
- `CALL_SCHEMA` - the flagship Kundali book (app/ai/book.py). **One schema for every call of every
  report in every language**, so the structured-output format never varies between the calls that
  share a prompt-cache prefix. Which parts and chapters a given call must fill is said in the user
  message and checked by `call_problems`.

Structured-output limits respected in both: every object has additionalProperties false and all keys
required; no min/max or length constraints; no recursion.
"""

from .book import PLAIN, TABLE, WINDOWS
from .engine_facts import AREAS
from .products import Product

REMEDY_TYPES = ["mantra", "charity", "service", "habit", "worship", "meditation"]


# A heading lands in an auto-generated contents page with a leader-dot column and a page number, in a
# TOC that runs to ~97 entries. A heading that runs to a sentence wraps there and pushes the layout
# around. Structured outputs forbid `maxLength`, so the cap is enforced in `call_problems` instead.
MAX_HEADING_CHARS = 64
MAX_HEADING_WORDS = 9
# A timeline chapter's printed heading is the engine's span label PLUS the model's theme, so the theme
# it writes has to leave room for the label (about 24 characters, "जानेवारी 2032 – डिसेंबर 2036").
# Measured: "जानेवारी 2032 – डिसेंबर 2036" is 28 characters, so a 38-char theme cap rejected honest
# English themes at 40. 46 keeps the composed line under ~78.
MAX_THEME_CHARS = 46
MAX_THEME_WORDS = 7
# What the contents page actually prints for a span chapter: the engine's label plus that theme.
# "Jan 2028 – Dec 2028" is 5 words / 19 chars; the Devanagari form is 4 words / 28 chars.
MAX_COMPOSED_HEADING_CHARS = MAX_THEME_CHARS + 34
MAX_COMPOSED_HEADING_WORDS = MAX_THEME_WORDS + 6


def _obj(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def heading_problems(where: str, text: str, themed: bool = False) -> list[str]:
    """Too long for the contents page. Devanagari words are counted the same way.

    **Reported, never retried.** A live run failed a whole part because one heading was 8 words
    against a limit of 7, and the regeneration then dropped the chapter altogether - a paid part lost
    to a cosmetic overflow. Layout is platform's to handle; this exists so we can see when the model
    is running long, not to refuse the book. See `heading_length` in NO_REGENERATION_KINDS.

    `themed=True` for a chapter whose printed heading will have the engine's span label prepended,
    so the model's part of it has to be shorter.
    """
    text = (text or "").strip()
    chars, words = (MAX_THEME_CHARS, MAX_THEME_WORDS) if themed else (MAX_HEADING_CHARS, MAX_HEADING_WORDS)
    tail = (" - the printed heading also gets this chapter's date span from the engine, so leave it room"
            if themed else " - a handful of words, not a sentence")
    if len(text) > chars:
        return [f"{where}: the heading is {len(text)} characters, over {chars}. It goes in the "
                f"contents page next to a page number{tail}"]
    if len(text.split()) > words:
        return [f"{where}: the heading is {len(text.split())} words, over {words}. It goes in the "
                f"contents page{tail}"]
    return []


# ---- the grammar limit, and what to do when it binds ----------------------------------------------
#
# The API compiles a structured-output schema into a grammar and refuses one that gets too big:
#   400 invalid_request_error "The compiled grammar is too large, which would cause performance issues."
#
# Read this before adding a field. ONE schema serves all ten calls of the book, so the failure mode is
# not "one section degrades" - it is "no Kundali report can be produced at all", which is what we hit.
# The error names nothing useful, so it is easy to lose an afternoon to.
#
# `schema_weight` is a cheap offline stand-in, calibrated against the live API on 2026-09-21 with
# claude-sonnet-5: weight 24 compiles, weight 27 (this schema plus `subsections`) is rejected. The real
# ceiling can only be found with a real request, so probe one before going over.
#
# WHY ONE SCHEMA: `output_config.format` participates in the prompt-cache key. Measured - same system
# blocks, different schema, `cache_read_input_tokens: 0` and a fresh cache write. So a schema
# specialised per call would destroy the shared prefix: ten cache writes of ~8.2k tokens instead of
# one, roughly ₹18 a report.
#
# THE ESCAPE HATCH, if this budget ever binds: do NOT trim fields, and do NOT go per call. Split into
# TWO cache groups - the calls that need `highlights` share schema A, the rest share schema B. That is
# two cache writes instead of one (~₹1.8 a report, trivial) against the ~₹18 of going per call, it puts
# each schema far below the ceiling, and a future field addition then affects one group instead of the
# whole product.
GRAMMAR_BUDGET = 25


def schema_weight(node) -> int:
    """How much structure the grammar has to encode: every object, array and enum alternative."""
    if isinstance(node, dict):
        weight = 1 if node.get("type") in ("object", "array") else 0
        weight += len(node.get("enum") or [])
        return weight + sum(schema_weight(value) for key, value in node.items() if key != "description")
    if isinstance(node, list):
        return sum(schema_weight(item) for item in node)
    return 0


_STRINGS = {"type": "array", "items": {"type": "string"}}

_TABLE = _obj({
    "columns": _STRINGS,
    "rows": {"type": "array", "items": _STRINGS},
})

_SUBSECTION = _obj({
    "heading": {"type": "string"},
    "paragraphs": _STRINGS,
})

_REMEDY = _obj({
    "title": {"type": "string"},
    "type": {"type": "string", "description": "One of: " + ", ".join(REMEDY_TYPES)},
    "description": {"type": "string", "description": "Why this suits this chart, naming the graha it relates to."},
    "how_to": {"type": "string", "description": "Exactly what to do, in one or two sentences."},
    "frequency": {"type": "string", "description": "When / how often, e.g. 'Saturday mornings'."},
})


# ---- the flagship book ---------------------------------------------------------------------------
#
# ONE schema for every call of every report in every language, so the structured-output format never
# varies between calls that share a prompt-cache prefix. Most fields are unused in any one call; which
# ones a call must fill is said in the user message and checked by `call_problems`.

_WINDOW = _obj({
    "window_id": {"type": "string", "description": "An id listed for this chapter, exactly as given."},
    "headline": {"type": "string", "description": "A few words. Never a date."},
    "paragraphs": _STRINGS,
    # Flat, paired by index, for the same grammar-size reason as `highlights` above: this is the
    # deepest point in the schema (parts -> chapters -> windows -> areas) and an object type here is
    # what the compiled grammar pays most for. `pair_areas` rebuilds [{area, text}] for the contract.
    "areas": {"type": "array", "items": {"type": "string"},
              "description": "Life areas this window is about. Each must be one of: " + ", ".join(AREAS)},
    "area_lines": {"type": "array", "items": {"type": "string"},
                   "description": "One sentence per `areas` entry, same order."},
})


def pair_areas(window: dict) -> list:
    """`areas` + `area_lines` -> the contract's [{area, text}]. Pure reshaping.

    The two are paired by index and the model does not always return them the same length, so a pair
    is emitted only when BOTH halves are there: an area tag with no sentence is an empty line in the
    rendered book, and a sentence with no tag has nowhere to go.
    """
    lines = window.get("area_lines") or []
    pairs = []
    for i, area in enumerate(window.get("areas") or []):
        text = (lines[i] if i < len(lines) else "").strip()
        if (area or "").strip() and text:
            pairs.append({"area": area, "text": text})
    return pairs

_CHAPTER = _obj({
    "id": {"type": "string", "description": "A chapter id listed for this call, exactly as given."},
    "heading": {"type": "string"},
    "paragraphs": _STRINGS,
    "bullets": _STRINGS,
    # NO `subsections` here, deliberately. It is in the published contract and every chapter carries
    # `subsections: []`, but the model is not offered it: the compiled structured-output grammar sits
    # right at the API's size limit (a measured 400 - see GRAMMAR_BUDGET below), and this is the field
    # the book misses least, since Part D's structure comes from `windows` and Part A's from `bullets`.
    "windows": {"type": "array", "items": _WINDOW},
    "table": {"anyOf": [_TABLE, {"type": "null"}]},
})

_BOOK_PART = _obj({
    "id": {"type": "string", "description": "A part id listed for this call, exactly as given."},
    "heading": {"type": "string"},
    "intro": {"type": "string", "description": "At most two sentences, or empty."},
    "chapters": {"type": "array", "items": _CHAPTER},
})

# Part A, items 2-7 - the highlight cards. Filled by the Part A call only; empty strings and empty
# lists otherwise.
#
# FLAT on purpose. The nested form platform reads - {mangal: {verdict, remedy}, ...} - is three more
# object types in the compiled structured-output grammar, and with parts -> chapters -> windows -> areas
# already four arrays deep that tipped the whole schema over the API's grammar-size limit (a real 400,
# measured). `nest_highlights` below rebuilds the contract shape in code, which costs nothing.
_HIGHLIGHTS = _obj({
    "mangal_verdict": {"type": "string"},
    "mangal_remedy": {"type": "string"},
    "sade_sati_verdict": {"type": "string"},
    "sade_sati_guidance": {"type": "string"},
    "dasha_mood": {"type": "string"},
    "strengths": {"type": "array", "items": {"type": "string"}, "description": "Exactly three, in order."},
    "cautions": {"type": "array", "items": {"type": "string"}, "description": "Exactly three, in order."},
    "yoga_names": {"type": "array", "items": {"type": "string"}},
    "yoga_lines": {"type": "array", "items": {"type": "string"},
                   "description": "One per `yoga_names` entry, same order."},
})

# The nested shape the report publishes and the PDF reads (docs/API.md).
HIGHLIGHT_GROUPS = (("mangal", ("verdict", "remedy")), ("sade_sati", ("verdict", "guidance")),
                    ("dasha", ("mood",)))


def nest_highlights(flat: dict) -> dict:
    """The flat schema shape -> the nested contract shape. Pure reshaping, nothing invented."""
    flat = flat or {}
    out = {}
    for group, fields in HIGHLIGHT_GROUPS:
        values = {field: (flat.get(f"{group}_{field}") or "").strip() for field in fields}
        if any(values.values()):
            out[group] = values
    for key in ("strengths", "cautions"):
        rows = [line.strip() for line in flat.get(key) or [] if (line or "").strip()]
        if rows:
            out[key] = rows
    names, lines = flat.get("yoga_names") or [], flat.get("yoga_lines") or []
    yogas = [{"name": name.strip(), "text": (lines[i] if i < len(lines) else "").strip()}
             for i, name in enumerate(names) if (name or "").strip()]
    if yogas:
        out["yogas"] = yogas
    return out

# Part F, the gemstone. Every value is copied from the engine's `gemstone` block; `note` is the writer's
# one-line framing of it. Filled by the Part F call only.
_GEMSTONE = _obj({
    "stone": {"type": "string"},
    "finger": {"type": "string"},
    "day": {"type": "string"},
    "metal": {"type": "string"},
    "avoid": {"type": "string"},
    "note": {"type": "string"},
})

CALL_SCHEMA = _obj({
    "title": {"type": "string", "description": "Empty unless asked."},
    "summary": {"type": "string", "description": "Empty unless asked."},
    "parts": {"type": "array", "items": _BOOK_PART,
              "description": "One entry per PART listed, in order. A chapter is never an entry here."},
    "highlights": _HIGHLIGHTS,
    "gemstone": _GEMSTONE,
    "remedies": {"type": "array", "items": _REMEDY},
})


def _filled(node) -> bool:
    """True when the model actually put something in an object or list."""
    if isinstance(node, dict):
        return any(_filled(value) for value in node.values())
    if isinstance(node, list):
        return any(_filled(item) for item in node)
    return bool(str(node or "").strip())


def call_problems(call, data: dict, min_remedies: int) -> tuple[list[str], list[str]]:
    """What the schema cannot enforce, split into (FATAL, REPAIRABLE).

    FATAL means the part cannot be used: wrong parts or chapters, a chapter with no content, a
    window id the engine never issued, missing remedies or highlights. These fail the book.

    REPAIRABLE means the text is fine and only its presentation is off - a blank chapter heading, or
    two chapters headed the same. Both drive a retry, because a real heading is better than a
    fallback one, but on the last attempt they are accepted and fixed deterministically at assembly
    (`compose_heading`, `repair_duplicate_headings`, and platform's own per-chapter fallback).

    The distinction exists because the alternative kept destroying paid books: a heading one word
    over the cap, then a chapter heading left blank, each cost a whole generation. A cosmetic flaw
    must never be more expensive than the content it decorates.
    """
    problems, repairable = [], []
    want_parts = [part.id for part in call.parts]
    got_parts = [part.get("id") for part in data.get("parts") or []]
    if got_parts != want_parts:
        return [f"parts must be exactly {want_parts} in this order; got {got_parts}"], []

    # Two headings reading the same in a contents page leave the reader no way to tell them apart.
    # Checked per call, which is where the realistic collisions are: the four year chapters and the
    # four block chapters each share one call, as do the chapters of any one part.
    seen_headings = {}

    def register(where: str, text: str, chapter=None) -> None:
        # For a chapter whose printed heading is the engine's span label plus this theme, uniqueness
        # is a property of the COMPOSED heading - two years may honestly share a theme, and the
        # labels are what tell them apart. Any one language works as the proxy; they all differ.
        label = (getattr(chapter, "labels", None) or {}).get("en", "")
        key = " ".join(f"{label} {text or ''}".split()).casefold()
        if not (text or "").strip():
            return
        if key in seen_headings:
            repairable.append(f"{where}: this heading is word for word the same as "
                              f"{seen_headings[key]}. Every heading in the book must be distinct - "
                              "they are the contents page")
        else:
            seen_headings[key] = where

    for part, written in zip(call.parts, data["parts"]):
        where = f"part {part.id}"
        # A PART heading may be empty: platform prints its own "PART A" and falls back. Only CHAPTER
        # headings are required, because those are the contents-page entries. Requiring it here cost
        # three attempts and a whole failed book on a live run.
        register(where, written.get("heading"))
        want = [chapter.id for chapter in part.chapters]
        got = [chapter.get("id") for chapter in written.get("chapters") or []]
        if got != want:
            problems.append(f"{where}: chapters must be exactly {want} in this order; got {got}")
            continue
        for chapter, body in zip(part.chapters, written["chapters"]):
            spot = f"{where} chapter {chapter.id}"
            fatal, soft = _chapter_problems(spot, chapter, body)
            problems += fatal
            repairable += soft
            register(spot, body.get("heading"), chapter)

    if call.wants_front_matter and not ((data.get("title") or "").strip() and (data.get("summary") or "").strip()):
        problems.append("this call must also fill `title` and `summary`")
    if call.wants_remedies and len(data.get("remedies") or []) < min_remedies:
        problems.append(f"this call must also give at least {min_remedies} remedies chosen for this chart")
    for n, remedy in enumerate(data.get("remedies") or [], 1):
        if remedy.get("type") not in REMEDY_TYPES:
            problems.append(f"remedy {n}: `type` must be one of {REMEDY_TYPES}; got {remedy.get('type')!r}")
    problems += _highlight_problems(call, data)
    if call.wants_gemstone:
        missing = [key for key in ("stone", "finger", "day", "metal")
                   if not (data.get("gemstone") or {}).get(key, "").strip()]
        if missing:
            problems.append(f"this call must also fill `gemstone` - missing {missing}")
    elif _filled(data.get("gemstone")):
        problems.append("`gemstone` belongs to the doshas and remedies call; leave it empty here")
    return problems, repairable


def _highlight_problems(call, data: dict) -> list[str]:
    highlights = data.get("highlights") or {}
    if not call.wants_highlights:
        return ["`highlights` belongs to the Part A call; leave it empty here"] if _filled(highlights) else []
    problems = []
    for group, fields in HIGHLIGHT_GROUPS:
        for field in fields:
            if not (highlights.get(f"{group}_{field}") or "").strip():
                problems.append(f"`highlights.{group}_{field}` is empty")
    for key in ("strengths", "cautions"):
        rows = highlights.get(key) or []
        if len(rows) != 3 or not all((row or "").strip() for row in rows):
            problems.append(f"`highlights.{key}` must be exactly three non-empty lines; got {len(rows)}")
    names, lines = highlights.get("yoga_names") or [], highlights.get("yoga_lines") or []
    if len(names) != len(lines):
        problems.append(f"`highlights.yoga_names` and `yoga_lines` must be the same length; "
                        f"got {len(names)} and {len(lines)}")
    return problems


def _chapter_problems(where: str, chapter, body: dict) -> tuple[list[str], list[str]]:
    problems, repairable = [], []
    # A chapter that covers a span may leave its theme empty: the printed heading falls back to the
    # engine's own range label, which is a perfectly good contents-page entry. For any other chapter
    # a blank heading is worth ONE retry but is not worth losing the book - platform's renderer
    # falls back to its own label per chapter id.
    if not (body.get("heading") or "").strip() and not chapter.labels:
        repairable.append(f"{where} has no heading")
    filled = {name for name in ("paragraphs", "bullets", "windows") if body.get(name)}
    if body.get("table"):
        filled.add("table")
    if not filled:
        problems.append(f"{where} is empty")

    if chapter.shape == WINDOWS:
        written = body.get("windows") or []
        if not written:
            problems.append(f"{where} must fill `windows`, one entry per dated window it covers")
        allowed, seen = set(chapter.window_ids), set()
        for entry in written:
            wid = entry.get("window_id")
            if wid not in allowed:
                problems.append(f"{where}: `{wid}` is not one of this chapter's window ids "
                                f"({', '.join(chapter.window_ids)}) - use only those, exactly as written")
            elif wid in seen:
                problems.append(f"{where}: window `{wid}` is used more than once")
            seen.add(wid)
            if not entry.get("paragraphs"):
                problems.append(f"{where}: window `{wid}` has no text")
            for area in entry.get("areas") or []:
                if area not in AREAS:
                    problems.append(f"{where}: window `{wid}` area {area!r} is not one of {list(AREAS)}")
            # A ragged `areas` / `area_lines` pair is NOT a structure failure. `pair_areas` zips them
            # and drops the remainder, so the worst case is a tag with no sentence - which is exactly
            # what an unpaired entry means anyway. Failing the part over it cost two real retries on
            # the past strip, where area tags are not even wanted.
        if body.get("paragraphs"):
            problems.append(f"{where}: put the reading inside the windows, not in `paragraphs`")
    elif body.get("windows"):
        problems.append(f"{where} is not a timeline chapter; leave `windows` empty")

    if chapter.shape == TABLE:
        table = body.get("table")
        if not (table and table.get("columns") and table.get("rows")):
            problems.append(f"{where} must fill `table` with columns and rows")
        elif any(len(row) != len(table["columns"]) for row in table["rows"]):
            problems.append(f"{where}: every table row must have {len(table['columns'])} cells")
        if body.get("paragraphs"):
            problems.append(f"{where}: this chapter is the table only; leave `paragraphs` empty")
    elif chapter.shape == PLAIN and not (body.get("paragraphs") or body.get("bullets")):
        problems.append(f"{where} must have paragraphs")
    return problems, repairable


# ---- the original flat report (matching / mangal / sade-sati) ---------------------------------------


def report_schema(product: Product) -> dict:
    section = _obj({
        "id": {"type": "string", "enum": [section_id for section_id, _ in product.sections]},
        "heading": {"type": "string"},
        "paragraphs": _STRINGS,
        "subsections": {"type": "array", "items": _SUBSECTION},
        "bullets": _STRINGS,
        "table": {"anyOf": [_TABLE, {"type": "null"}]},
    })
    return _obj({
        "title": {"type": "string"},
        "summary": {"type": "string", "description": "Three or four sentences: the essence of the report."},
        "sections": {"type": "array", "items": section},
        "remedies": {"type": "array", "items": _REMEDY},
    })


def structure_problems(product: Product, data: dict) -> list[str]:
    """What the schema cannot enforce: every section present once, in order, and none empty."""
    problems = []
    sections = data.get("sections") or []
    got = [section.get("id") for section in sections]
    want = [section_id for section_id, _ in product.sections]
    if got != want:
        problems.append(f"sections must be exactly {want} in this order; got {got}")
    for section in sections:
        if not section.get("paragraphs") and not section.get("subsections"):
            problems.append(f"section {section.get('id')!r} has no paragraphs or subsections")
    if len(data.get("remedies") or []) < product.min_remedies:
        problems.append(f"at least {product.min_remedies} remedies are required")
    if not (data.get("title") or "").strip() or not (data.get("summary") or "").strip():
        problems.append("title and summary must not be empty")
    return problems
