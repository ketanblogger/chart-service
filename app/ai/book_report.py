"""The flagship Kundali book (the Detailed tier): engine facts -> one Sonnet call per part -> a
checked, assembled book. Prices live in app/payments/catalogue.py, never in a docstring.

Why sectioned: the book is 30-60 pages and its length is decided by the
chart, not by a page target. One giant call cannot do that - it runs out of room and thins the timeline,
which is the part people paid for. So each part is generated on its own, all of them sharing one cached
prefix, and a part that fails its checks is regenerated alone instead of taking the whole book with it.

    system = [ BOOK_SYSTEM_PROMPT  frozen; caches across every customer          ~3.0k tokens
               this chart's facts  app/ai/compact.py `book_prefix`, identical
                                   for every call of this report                 ~5.2k tokens ] <- cached
    messages = [ user: which parts and chapters to write now, and ONLY the windows this call needs ]
    output_config.format = CALL_SCHEMA   one schema for every call - it is part of the cache key

Every date in the finished book comes from the engine. The model only ever names a window by `id`;
`_resolve_windows` fills the printed range in afterwards, so a hallucinated date cannot reach the page.

Two execution paths, sharing every check (`judge_draft` / `finish_call`) so a rule can never apply to
only one of them: threaded (default, ~4-10 minutes) and batched (`REPORT_BATCH=1`, the Message Batches
API at 50% of the token price, minutes to an hour).
"""

import copy
import datetime as dt
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from .book import FILLER_EXEMPT_CHAPTERS, WINDOWS, build_book, highlights_brief, plan
from .client import AIBadOutput, AIError
from .compact import Names, book_prefix, compact_year_table, windows_block
from .engine_facts import all_windows, report_facts, supplied, window_public
from .prompts import (
    BOOK_SYSTEM_PROMPT,
    FRONT_MATTER_NOTE,
    REMEDIES_NOTE,
    build_call_prompt,
    compact_json,
    gemstone_note,
    highlights_note,
)
from .safety import screen_text
from .schema import CALL_SCHEMA, call_problems, heading_problems, nest_highlights, pair_areas
from .validator import (
    REDACT_KINDS,
    REGENERATE_ONLY_KINDS,
    check_text,
    filler_issues,
    narrow_to_window,
    near_horizon,
    untranslated_heading,
    untraceable_issues,
    written_range_issues,
)

log = logging.getLogger(__name__)

MIN_REMEDIES = 5
DEFAULT_CONCURRENCY = 3
# Cosmetic findings reported as warnings rather than paid for with a regeneration. Same rule the flat
# reports use: a lone "cancelled" instead of "mitigated" is not worth re-writing a part.
# `heading_length` joins it for the reason in schema.heading_problems: one word over cost a part.
NO_REGENERATION_KINDS = {"wording", "heading_length"}
# Where a gemstone may be named, and only when the engine supplied one: the gemstone
# chapter, the top-level `gemstone` object, and the heading of the part that contains them - a live
# run had "Doshas, Remedies and Gemstones" rejected as a hard sell, which is silly and cost a retry.
GEMSTONE_CHAPTERS = {"gemstone"}
GEMSTONE_PART = "doshas_remedies"
HEADING_JOIN = " — "


def concurrency() -> int:
    """How many part calls run at once after the first one has written the prompt cache."""
    return max(1, int(os.getenv("REPORT_CONCURRENCY", str(DEFAULT_CONCURRENCY))))


def batched() -> bool:
    """`REPORT_BATCH=1`: send the book through the Message Batches API at half the token price."""
    return os.getenv("REPORT_BATCH", "0").strip() == "1"


class SectionFailed(AIBadOutput):
    """One part could not be produced cleanly. The book is not sold half-written."""


# ---- data -------------------------------------------------------------------------------------------


def build_book_data(chart: dict, language: str, as_of: dt.date,
                    tier: str = "detailed") -> tuple[dict, dict, tuple]:
    """(engine data for the PDF and the fact checker, the cached prefix the model reads, the parts).

    The prefix holds the chart-wide facts only and is IDENTICAL for both tiers - the engine computes
    everything once, and a Simple report is a selection from it, never a second computation. The
    timeline does not go in the prefix at all; see `book_prefix`.
    """
    facts = report_facts(chart, as_of)
    full = {"chart": chart, **facts}
    return full, book_prefix(chart, facts, language, as_of.isoformat()), build_book(facts, tier)


def system_blocks(prompt_data: dict) -> list[dict]:
    """The two cached prefix blocks. Nothing per-call goes in here, ever."""
    return [
        {"type": "text", "text": BOOK_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "Chart facts - the only source of astrological facts for the whole "
                                 "book. The dated windows for each part arrive with that part's "
                                 "instructions.\n<chart>\n" + compact_json(prompt_data) + "\n</chart>",
         "cache_control": {"type": "ephemeral"}},
    ]


def call_message(call, language: str, as_of: str, facts: dict, feedback=None) -> str:
    """The user message for one call: its briefs, and only the windows it needs."""
    windows = call.windows()
    extra = {}
    if call.wants_highlights:
        extra["highlights"] = highlights_note(highlights_brief(facts))
    if call.wants_gemstone:
        extra["gemstone"] = gemstone_note()
    if call.wants_remedies:
        extra["remedies"] = REMEDIES_NOTE
    if call.wants_front_matter:
        extra["front_matter"] = FRONT_MATTER_NOTE
        extra["year_table"] = ("The year table feed, one row per year:\n<year_table>\n"
                               + compact_json(compact_year_table(facts["timeline"]["year_table"], language))
                               + "\n</year_table>")
    encoded = compact_json(windows_block(windows, language, Names())) if windows else ""
    return build_call_prompt(call, language, as_of, encoded, extra, feedback)


# ---- checking -----------------------------------------------------------------------------------------


def text_slots(call, data: dict):
    """Yield (where, container, key, text, kind, window_id) for every AI-written string in a call.

    `kind` is "prose" (the filler check applies), "heading" (the language check applies) or "line".
    `window_id` is set for text written inside a timeline window, so it is checked against that
    window's own transits and months rather than against the whole twenty-year span.
    """
    if data.get("title"):
        yield "title", data, "title", data["title"], "heading", None
    if data.get("summary"):
        yield "summary", data, "summary", data["summary"], "prose", None

    highlights = data.get("highlights") or {}
    for key in ("mangal_verdict", "mangal_remedy", "sade_sati_verdict", "sade_sati_guidance",
                "dasha_mood"):
        if highlights.get(key):
            yield f"highlights {key}", highlights, key, highlights[key], "line", None
    for key in ("strengths", "cautions", "yoga_names", "yoga_lines"):
        for i, text in enumerate(highlights.get(key) or []):
            yield f"highlights {key} {i + 1}", highlights[key], i, text, "line", None

    gemstone = data.get("gemstone") or {}
    for field, text in gemstone.items():
        if text:
            yield f"chapter gemstone {field}", gemstone, field, text, "line", None

    for part in data.get("parts") or []:
        pid = part.get("id")
        yield f"part {pid} heading", part, "heading", part.get("heading", ""), "heading", None
        if part.get("intro"):
            yield f"part {pid} intro", part, "intro", part["intro"], "line", None
        for chapter in part.get("chapters") or []:
            where = f"part {pid} chapter {chapter.get('id')}"
            yield f"{where} heading", chapter, "heading", chapter.get("heading", ""), "heading", None
            for i, text in enumerate(chapter.get("paragraphs") or []):
                yield f"{where} paragraph {i + 1}", chapter["paragraphs"], i, text, "prose", None
            for i, text in enumerate(chapter.get("bullets") or []):
                yield f"{where} bullet {i + 1}", chapter["bullets"], i, text, "line", None
            for n, sub in enumerate(chapter.get("subsections") or [], 1):
                yield f"{where} subsection {n} heading", sub, "heading", sub.get("heading", ""), "heading", None
                for i, text in enumerate(sub.get("paragraphs") or []):
                    yield f"{where} subsection {n} paragraph {i + 1}", sub["paragraphs"], i, text, "prose", None
            for window in chapter.get("windows") or []:
                wid = window.get("window_id")
                yield f"{where} window {wid} headline", window, "headline", window.get("headline", ""), \
                    "line", wid
                for i, text in enumerate(window.get("paragraphs") or []):
                    yield f"{where} window {wid} paragraph {i + 1}", window["paragraphs"], i, text, "prose", wid
                # `areas` and `area_lines` are paired by index and the model does NOT always return
                # them the same length - a live batch round crashed here on a window with more lines
                # than areas. Every consumer zips defensively (`pair_areas`, `redact`); so does this.
                areas = window.get("areas") or []
                for i, text in enumerate(window.get("area_lines") or []):
                    area = areas[i] if i < len(areas) else "?"
                    yield f"{where} window {wid} area {area}", window["area_lines"], i, text, "prose", wid
            table = chapter.get("table")
            if table:
                # a bad header drops the whole table (removing one column would misalign every row)
                yield f"{where} table header", chapter, "table", " | ".join(table.get("columns") or []), \
                    "heading", None
                for r, row in enumerate(table.get("rows") or []):
                    yield f"{where} table row {r + 1}", table["rows"], r, " | ".join(row), "line", None
    for n, remedy in enumerate(data.get("remedies") or []):
        text = " ".join(str(remedy.get(k, "")) for k in ("title", "description", "how_to", "frequency"))
        yield f"remedy {n + 1}", data["remedies"], n, text, "line", None


def normalise(call, data: dict) -> dict:
    """Re-nest a call's output into exactly the parts and chapters that were asked for.

    Seen live: asked for PART D with the two chapters `year_2030` and `year_2031`, the model returned
    three top-level parts - `timeline`, `year_2031`, `year_2031` - with the chapters promoted to
    parts. The writing was fine; only the nesting was wrong. Failing the part there would have thrown
    away nine other good parts, so chapters are re-bucketed by id and `call_problems` judges what is
    left. Only moves and de-duplicates: nothing is invented, and an id nobody asked for is dropped.
    """
    owner = {chapter.id: part.id for part in call.parts for chapter in part.chapters}
    wanted = {part.id: [chapter.id for chapter in part.chapters] for part in call.parts}
    headings, chapters = {}, {}

    def take(node: dict) -> None:
        cid = node.get("id")
        if cid in owner and (cid not in chapters or _chapter_is_empty(chapters[cid])):
            chapters[cid] = node

    nodes = data.get("parts") or []
    # A real part entry's heading always wins over one borrowed from a chapter promoted to a part.
    for node in nodes:
        if node.get("id") in wanted and (node.get("heading") or "").strip():
            headings.setdefault(node["id"], node["heading"])
    for node in nodes:
        if node.get("id") in owner and (node.get("heading") or "").strip():
            headings.setdefault(owner[node["id"]], node["heading"])
    for node in nodes:
        for child in node.get("chapters") or []:
            take(child)
        if node.get("id") in owner and not (node.get("chapters") or []):
            take(node)  # the stray part IS the chapter body

    intros = {node["id"]: node.get("intro", "") for node in nodes if node.get("id") in wanted}
    data["parts"] = [{"id": part_id,
                      "heading": headings.get(part_id, ""),
                      "intro": intros.get(part_id, ""),
                      "chapters": [chapters[cid] for cid in ids if cid in chapters]}
                     for part_id, ids in wanted.items()]
    return data


def _chapter_labels(call, where: str) -> dict:
    """The engine span label of the chapter a heading slot belongs to, if it has one."""
    for part in call.parts:
        for chapter in part.chapters:
            if where.endswith(f"chapter {chapter.id} heading"):
                return chapter.labels or {}
    return {}


def _gemstone_slot(where: str) -> bool:
    if where in (f"part {GEMSTONE_PART} heading", f"part {GEMSTONE_PART} intro"):
        return True
    return any(f"chapter {chapter}" in where for chapter in GEMSTONE_CHAPTERS)


def find_problems(call, data: dict, facts, gemstone_allowed: bool, windows: dict | None = None,
                  language: str = "en", timeline: dict | None = None) -> list[dict]:
    """Safety hits, invented facts and filler in one call's output, each with where it was found.

    Nothing is ever checked against the whole-book fact set: text inside a timeline window is scoped
    to that window's own transits, and everything else to the near horizon (validator.near_horizon).
    Over twenty years a slow graha visits every sign, so an unscoped check cannot fail.
    """
    problems, scoped = [], {}

    def facts_for(window_id):
        """The horizon this slot's text is judged against. DO NOT collapse this to `facts`.

        The book covers about twenty years, and over twenty years a slow graha visits every sign -
        so against the whole-book fact set a transit claim CANNOT fail, whatever house it names.
        That is not hypothetical: "Guru also enters your 9th house transit-wise around 31 October
        2026" reached a live customer-facing transcript (Simha is this chart's lagna, the 1st house;
        it is the 9th only counted from the Moon), and the unscoped set passes it silently.

        So text inside a timeline window is judged against THAT window's own transits, and every
        other slot against the near horizon - the birth chart plus the current year - which is the
        same 12-month horizon the consultation chat uses and why the chat layer never lost this
        check. Pinned in tests/test_historical_defects.py.
        """
        key = window_id if (window_id and windows and window_id in windows) else "_near"
        if key not in scoped:
            scoped[key] = (narrow_to_window(facts, windows[window_id]) if key != "_near"
                           else (near_horizon(facts, timeline) if timeline else facts))
        return scoped[key]

    for where, container, key, text, kind, window_id in text_slots(call, data):
        here = facts_for(window_id)
        allow_gemstone = gemstone_allowed and _gemstone_slot(where)
        for hit in screen_text(text, allow_gemstone=allow_gemstone):
            problems.append({"type": "safety", "kind": hit.category, "where": where, "found": hit.term,
                             "message": f"forbidden topic ({hit.category}): '{hit.term}'",
                             "slot": (container, key)})
        issues = list(check_text(text, here)) + list(untraceable_issues(text, here))
        if window_id or kind == "heading":
            # A date range the model typed. Inside a window the engine's label is printed above the
            # text; in a heading the span is composed from the engine's label at assembly.
            issues += written_range_issues(text)
        if kind == "prose" and not any(f"chapter {name}" in where for name in FILLER_EXEMPT_CHAPTERS):
            issues += filler_issues(text)
        if kind == "heading":
            issues += [issue for issue in [untranslated_heading(text, language)] if issue]
            themed = bool(_chapter_labels(call, where))
            problems += [{"type": "fact", "kind": "heading_length", "where": where,
                          "found": (text or "")[:60], "message": message, "slot": (container, key)}
                         for message in heading_problems(where, text, themed=themed)]
        for issue in issues:
            problems.append({"type": "fact", "kind": issue.kind, "where": where, "found": issue.found,
                             "message": issue.message, "slot": (container, key)})
    return problems


def must_redact(problem: dict) -> bool:
    """Blanking a heading would leave a hole in the contents page, so `untranslated` is regenerated
    rather than cut - see validator.REGENERATE_ONLY_KINDS."""
    if problem["kind"] in REGENERATE_ONLY_KINDS:
        return False
    return problem["type"] == "safety" or problem["kind"] in REDACT_KINDS


def redact(data: dict, problems: list[dict]) -> list[dict]:
    """Remove every paragraph / line / row / remedy with a blocking problem, then tidy what is left
    empty. Returns what was removed, for meta.checks.redactions."""
    removed, list_removals = [], {}
    for problem in problems:
        if not must_redact(problem):
            continue
        container, key = problem["slot"]
        if isinstance(container, list):
            list_removals.setdefault(id(container), (container, set()))[1].add(key)
        else:  # a heading or a table: blank it (the PDF falls back to its own label)
            container[key] = "" if key != "table" else None
        removed.append({k: problem[k] for k in ("type", "kind", "where", "found")})
    for container, indexes in list_removals.values():
        for index in sorted(indexes, reverse=True):
            del container[index]
    for part in data.get("parts") or []:
        for chapter in part.get("chapters") or []:
            chapter["subsections"] = [sub for sub in chapter.get("subsections") or [] if sub.get("paragraphs")]
            for window in chapter.get("windows") or []:
                areas, lines = window.get("areas") or [], window.get("area_lines") or []
                kept = [(a, lines[i]) for i, a in enumerate(areas)
                        if i < len(lines) and (lines[i] or "").strip()]
                window["areas"] = [a for a, _ in kept]
                window["area_lines"] = [line for _, line in kept]
            chapter["windows"] = [w for w in chapter.get("windows") or [] if w.get("paragraphs")]
            if not (chapter.get("table") or {}).get("rows"):
                chapter["table"] = None
    highlights = data.get("highlights") or {}
    for key in ("strengths", "cautions"):
        if key in highlights:
            highlights[key] = [row for row in highlights[key] if (row or "").strip()]
    # yoga names and lines are paired by index, so a cut on either side drops the whole pair
    names, lines = highlights.get("yoga_names"), highlights.get("yoga_lines")
    if names is not None and lines is not None:
        kept = [(n, lines[i]) for i, n in enumerate(names)
                if i < len(lines) and (n or "").strip() and (lines[i] or "").strip()]
        highlights["yoga_names"] = [n for n, _ in kept]
        highlights["yoga_lines"] = [line for _, line in kept]
    return removed


def _chapter_is_empty(chapter: dict) -> bool:
    return not any(chapter.get(key) for key in ("paragraphs", "bullets", "subsections", "windows", "table"))


def _public(problem: dict) -> dict:
    return {k: problem[k] for k in ("type", "kind", "where", "found", "message")}


# ---- one part, checked --------------------------------------------------------------------------------


def judge_draft(call, result, *, facts, gemstone_allowed, windows, language, timeline, strip):
    """Check ONE draft of one part. Shared by the threaded and the batched paths, so a change to the
    rules can never apply to only one of them.

    Returns (content, fatal structure problems, repairable ones, content problems, the feedback to
    send on a retry).
    """
    content = normalise(call, strip(result.data))
    structure, repairable = call_problems(call, content, MIN_REMEDIES)
    problems = ([] if structure else
                find_problems(call, content, facts, gemstone_allowed, windows, language, timeline))
    worth_retrying = [p for p in problems if p["kind"] not in NO_REGENERATION_KINDS]
    # `repairable` earns a retry but never a refusal - see schema.call_problems.
    feedback = structure + repairable + [f"{p['where']}: {p['message']}" for p in worth_retrying]
    return content, structure, repairable, problems, feedback


def finish_call(call, content, structure, problems, results, rejected, *, language, max_attempts):
    """Redact what is left, refuse what cannot be shipped, and build the meta record. Shared."""
    if structure:
        raise SectionFailed(f"part {call.key} still malformed after {max_attempts} attempts: {structure}")
    # An untranslated heading can be neither cut (the contents page would have a hole) nor shipped
    # (page two of a Marathi book would be half English), so if a retry did not fix it the part fails.
    stubborn = [p for p in problems if p["kind"] in REGENERATE_ONLY_KINDS]
    if stubborn:
        raise SectionFailed(f"part {call.key} still has English headings in a {language} book after "
                            f"{max_attempts} attempts: {[p['found'] for p in stubborn]}")
    redactions = redact(content, problems) if problems else []
    warnings = [_public(p) for p in problems if not must_redact(p)]
    if redactions:
        emptied = [f"{part['id']}.{chapter['id']}"
                   for part in content["parts"] for chapter in part["chapters"] if _chapter_is_empty(chapter)]
        if emptied:
            raise SectionFailed(f"part {call.key} lost {emptied} entirely to unsafe or unverifiable text")
    usage = {key: sum(r.usage.get(key, 0) for r in results)
             for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
    return content, results, {"call": call.key, "attempts": len(results), "usage": usage,
                              "redactions": redactions, "warnings": warnings, "rejected_drafts": rejected}


def _log_draft(call, attempt, structure, problems, feedback):
    """The reasons, not just the counts: a retry is the cost lever, so a run has to be diagnosable
    from its log without re-running it."""
    log.info("book call %s attempt %d: %d structure, %d content%s", call.key, attempt,
             len(structure), len(problems),
             "".join(f"\n        - {reason[:190]}" for reason in feedback[:6]))


def run_call(call, *, client, system, language, as_of, facts, engine_facts_block, gemstone_allowed,
             windows, timeline, max_attempts, strip):
    """Generate one part, re-asking the model with the checker's feedback until it is clean."""
    results, feedback, rejected = [], None, []
    content, structure, problems = None, [], []
    for attempt in range(1, max_attempts + 1):
        user = call_message(call, language, as_of, engine_facts_block, feedback)
        result = client.generate_json(system=system, user=user, schema=CALL_SCHEMA)
        results.append(result)
        content, structure, repairable, problems, feedback = judge_draft(
            call, result, facts=facts, gemstone_allowed=gemstone_allowed, windows=windows,
            language=language, timeline=timeline, strip=strip)
        _log_draft(call, attempt, structure, problems, feedback)
        if not feedback:
            break
        rejected.append({"call": call.key, "attempt": attempt, "structure": structure,
                         "repairable": repairable,
                         "problems": [_public(p) for p in problems]})
    return finish_call(call, content, structure, problems, results, rejected,
                       language=language, max_attempts=max_attempts)


def run_batch_rounds(calls, *, client, system, language, as_of, facts, engine_facts_block,
                     gemstone_allowed, windows, timeline, max_attempts, strip):
    """Every part through the Message Batches API: one round per attempt, 50% of the token price.

    A batch is asynchronous (minutes to an hour), which the purchase flow already tolerates - it
    backgrounds generation behind a permanent order link. What it cannot do is the threaded path's
    trick of running one call first to write the prompt cache, because every request in a round is
    submitted together and some will miss the cache and write it themselves. That costs a few rupees;
    the halved token price more than pays for it.

    A retry is a whole extra round, so here latency scales with ROUNDS, not with calls - the opposite
    of the threaded path, and another reason reducing retries matters.

    THE WARM-UP IS NOT OPTIONAL. Measured on a real book: submitting all twelve together, eight
    missed the prefix cache and wrote it while only four read it - a 33% hit rate and ~Rs 10 of pure
    waste on a Rs 30 book, because every request starts before any of them has finished writing.
    Running the first call synchronously first costs one full-price call (~Rs 4) and turns the
    remaining eleven into cache reads.
    """
    state = {call.key: {"call": call, "feedback": None, "results": [], "rejected": [],
                        "content": None, "structure": [], "problems": []} for call in calls}
    done = []
    if len(calls) > 1:
        warm = min(calls, key=lambda call: len(call.windows()))  # the cheapest call warms the cache
        log.info("book batch: warming the prompt cache with %s before the batch", warm.key)
        done.append(run_call(warm, client=client, system=system, language=language, as_of=as_of,
                             facts=facts, engine_facts_block=engine_facts_block,
                             gemstone_allowed=gemstone_allowed, windows=windows, timeline=timeline,
                             max_attempts=max_attempts, strip=strip))
        state.pop(warm.key)
    pending = list(state)
    for round_number in range(1, max_attempts + 1):
        log.info("book batch round %d: %d part(s) - %s", round_number, len(pending), ", ".join(pending))
        outcomes = client.generate_json_batch([
            {"custom_id": key, "system": system, "schema": CALL_SCHEMA,
             "user": call_message(state[key]["call"], language, as_of, engine_facts_block,
                                  state[key]["feedback"])}
            for key in pending])
        still_pending = []
        for key in pending:
            entry, outcome = state[key], outcomes[key]
            if isinstance(outcome, AIError):
                log.warning("book batch %s: %s", key, outcome)
                if round_number == max_attempts:
                    raise SectionFailed(f"part {key} never came back from the batch: {outcome}")
                still_pending.append(key)
                continue
            entry["results"].append(outcome)
            content, structure, repairable, problems, feedback = judge_draft(
                entry["call"], outcome, facts=facts, gemstone_allowed=gemstone_allowed,
                windows=windows, language=language, timeline=timeline, strip=strip)
            entry.update(content=content, structure=structure, problems=problems, feedback=feedback)
            _log_draft(entry["call"], len(entry["results"]), structure, problems, feedback)
            if feedback:
                entry["rejected"].append({"call": key, "attempt": len(entry["results"]),
                                          "structure": structure, "repairable": repairable,
                                          "problems": [_public(p) for p in problems]})
                still_pending.append(key)
        pending = still_pending
        if not pending:
            break
    return done + [finish_call(entry["call"], entry["content"], entry["structure"], entry["problems"],
                               entry["results"], entry["rejected"],
                               language=language, max_attempts=max_attempts)
                   for entry in state.values()]


# ---- assembly -------------------------------------------------------------------------------------


def compose_heading(chapter, written: str, language: str) -> str:
    """The printed heading for a chapter that covers a span: the ENGINE's label plus the model's theme.

    The model is asked for the theme alone and never for the span, because a span it writes is a date
    it writes - the one thing this layer exists to prevent. A model-written "2032 – 2037" for a block
    the engine labels "2032 – 2036" would be wrong, would bypass the engine's formatter, and would sit
    on the contents page of a paid book.
    """
    label = (chapter.labels or {}).get(language, "")
    written = (written or "").strip()
    if not label:
        return written
    if not written:
        return label
    return f"{label}{HEADING_JOIN}{written}"


def repair_duplicate_headings(title: str, parts: list[dict]) -> list[dict]:
    """Make every heading in the book distinct, in document order, and say what was changed.

    A collision is repaired rather than shipped or hard-failed: the customer should never see two
    identical contents lines when we can tell them apart for free, and binning nine good parts over a
    blemish serves them worse. The discriminator is the chapter's own engine range label, which the
    engine guarantees is unique per window in every language, so the repair cannot itself collide.
    Anything still colliding afterwards is reported and left alone.
    """
    def fold(text):
        return " ".join((text or "").split()).casefold()

    seen, clashes = {}, []
    if fold(title):
        seen[fold(title)] = "title"
    for part in parts:
        for where, container in ([(f"part {part['id']}", part)]
                                 + [(f"part {part['id']} chapter {chapter['id']}", chapter)
                                    for chapter in part["chapters"]]):
            text = container.get("heading") or ""
            key = fold(text)
            if not key:
                continue
            if key not in seen:
                seen[key] = where
                continue
            clash = {"type": "fact", "kind": "duplicate_heading", "where": where,
                     "found": text.strip()[:60],
                     "message": f"'{text.strip()[:60]}' also heads {seen[key]}"}
            label = container.get("_label") or ""
            repaired = f"{label}{HEADING_JOIN}{text.strip()}" if label else ""
            if repaired and fold(repaired) not in seen:
                container["heading"] = repaired
                seen[fold(repaired)] = where
                clash["message"] += f"; repaired to '{repaired[:60]}' using the engine's range label"
            else:
                clash["message"] += ("; no engine range label to tell them apart, so the contents page "
                                     "will show the same line twice")
            clashes.append(clash)
    return clashes


def duplicate_headings(title: str, parts: list[dict]) -> list[dict]:
    """Report-only view of the same check, for tests and for inspecting a finished book."""
    seen, clashes = {}, []
    for where, text in ([("title", title)]
                        + [(f"part {part['id']}", part["heading"]) for part in parts]
                        + [(f"part {part['id']} chapter {chapter['id']}", chapter["heading"])
                           for part in parts for chapter in part["chapters"]]):
        key = " ".join((text or "").split()).casefold()
        if not key:
            continue
        if key in seen:
            clashes.append({"type": "fact", "kind": "duplicate_heading", "where": where,
                            "found": (text or "").strip()[:60],
                            "message": f"'{(text or '').strip()[:60]}' also heads {seen[key]}; the "
                                       "contents page will show the same line twice"})
        else:
            seen[key] = where
    return clashes


def _resolve_windows(chapter: dict, windows: dict, language: str) -> None:
    """Replace each `window_id` with the engine's own dates, label, dasha lords and transits.

    This is where the two-layer rule becomes structural rather than advisory: the model chose which
    window to write about, and nothing else about it.
    """
    resolved = []
    for written in chapter.get("windows") or []:
        window = windows.get(written.get("window_id"))
        if window is None:  # call_problems already rejected this; belt and braces
            continue
        resolved.append({**window_public(window, language),
                         "headline": written.get("headline", ""),
                         "paragraphs": written.get("paragraphs") or [],
                         "areas": pair_areas(written)})
    chapter["windows"] = resolved


def assemble(book: tuple, written: dict, windows: dict, language: str) -> list[dict]:
    """The `parts` array, in book order, from the per-call outputs."""
    parts = []
    for part in book:
        body = written.get(part.id)
        if body is None:
            continue
        chapters = {chapter["id"]: chapter for chapter in body["chapters"]}
        ordered = []
        for chapter in part.chapters:
            got = chapters.get(chapter.id)
            if got is None or _chapter_is_empty(got):
                continue
            if chapter.shape == WINDOWS:
                _resolve_windows(got, windows, language)
            got["heading"] = compose_heading(chapter, got.get("heading"), language)
            # kept only for `repair_duplicate_headings`, stripped before the report is published
            got["_label"] = (chapter.labels or {}).get(language, "")
            # `subsections` is in the published contract but not in the model's schema (see
            # schema.py); the key is always present so platform's renderer never has to guard for it.
            got["subsections"] = got.get("subsections") or []
            got.setdefault("table", None)
            got.pop("highlights", None)  # Part A's cards are a top-level object now, not a field
            ordered.append(got)
        if ordered:
            parts.append({"id": part.id, "label": part.label, "heading": body["heading"],
                          "intro": body.get("intro", ""), "chapters": ordered})
    return parts


def flat_sections(parts: list[dict]) -> list[dict]:
    """DEPRECATED compatibility view: one entry per chapter in the old flat `sections` shape, so the
    Phase 4 PDF template keeps rendering while the book template is built."""
    sections = []
    for part in parts:
        for chapter in part["chapters"]:
            subsections = list(chapter.get("subsections") or [])
            subsections += [{"heading": f"{window['label']} - {window['headline']}".strip(" -"),
                             "paragraphs": window["paragraphs"]
                             + [f"{area['area']}: {area['text']}" for area in window.get("areas") or []]}
                            for window in chapter.get("windows") or []]
            sections.append({
                "id": f"{part['id']}.{chapter['id']}",
                "heading": chapter.get("heading", ""),
                "paragraphs": chapter.get("paragraphs") or [],
                "subsections": subsections,
                "bullets": chapter.get("bullets") or [],
                "table": chapter.get("table"),
            })
    return sections


# ---- the generator ------------------------------------------------------------------------------------


def generate_book(*, chart: dict, language: str, as_of: dt.date, client, facts_for_checker,
                  max_attempts: int, strip, tier: str = "detailed") -> dict:
    """Write the book. Returns {title, summary, highlights, gemstone, parts, sections, remedies,
    data, results, checks}.

    `tier` selects which parts are written - "detailed" is the full Parts A-H book, "simple" the cheaper
    tier. EVERY check is the same for both; only the scope differs.
    """
    full_data, prompt_data, book = build_book_data(chart, language, as_of, tier)
    system = system_blocks(prompt_data)
    calls = plan(book, tier)
    if not calls:
        raise SectionFailed("this chart produced no parts to write")
    windows = all_windows(full_data["timeline"])
    shared = dict(client=client, system=system, language=language, as_of=as_of.isoformat(),
                  facts=facts_for_checker, engine_facts_block=full_data,
                  gemstone_allowed=supplied(full_data)["has_gemstone"], windows=windows,
                  timeline=full_data["timeline"], max_attempts=max_attempts, strip=strip)

    if batched():
        outputs = run_batch_rounds(calls, **shared)
    else:
        # The first call writes the ~8k-token prefix into the prompt cache; the rest read it. Running
        # them all at once would have every call miss the cache and pay the write premium.
        outputs = [run_call(calls[0], **shared)]
        rest = calls[1:]
        if rest:
            workers = min(concurrency(), len(rest))
            if workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    outputs += list(pool.map(lambda call: run_call(call, **shared), rest))
            else:
                outputs += [run_call(call, **shared) for call in rest]

    written, results, records, remedies = {}, [], [], []
    title = summary = ""
    highlights, gemstone = {}, {}
    for content, call_results, record in outputs:
        results += call_results
        records.append(record)
        for part in content["parts"]:
            if part["id"] in written:  # two calls writing the same part: merge their chapters
                written[part["id"]]["chapters"] += part["chapters"]
            else:
                written[part["id"]] = copy.deepcopy(part)
        remedies += content.get("remedies") or []
        title = title or (content.get("title") or "").strip()
        summary = summary or (content.get("summary") or "").strip()
        highlights = highlights or nest_highlights(content.get("highlights"))
        gemstone = gemstone or {k: v for k, v in (content.get("gemstone") or {}).items() if v}

    parts = assemble(book, written, windows, language)
    if not parts:
        raise SectionFailed("nothing survived the checks; the book was not written")

    # Every chapter the plan asked for must be present. The worst failure seen live was the model
    # returning later chapters EMPTY - no error, no truncation, no refusal - which is
    # indistinguishable from a chart with little to say, so it would have shipped as a quietly thin
    # book at full price. Sizing calls by window count fixed the cause; this makes a regression loud.
    wanted = {(part.id, chapter.id) for part in book for chapter in part.chapters}
    got = {(part["id"], chapter["id"]) for part in parts for chapter in part["chapters"]}
    if wanted - got:
        raise SectionFailed(f"the book is missing chapters the plan asked for: {sorted(wanted - got)}")

    clashes = repair_duplicate_headings(title, parts)
    for part in parts:
        for chapter in part["chapters"]:
            chapter.pop("_label", None)
    if clashes:
        log.warning("book had %d duplicate headings across calls: %s",
                    len(clashes), [c["found"] for c in clashes])
        records.append({"call": "assembly", "attempts": 0, "usage": {},
                        "redactions": [], "warnings": clashes, "rejected_drafts": []})

    return {
        "title": title,
        "summary": summary,
        "highlights": highlights,
        "gemstone": gemstone,
        "parts": parts,
        "sections": flat_sections(parts),
        "remedies": remedies,
        "data": full_data,
        "results": results,
        "checks": records,
    }
