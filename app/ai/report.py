"""Paid report generator: engine data -> Claude (interpret only) -> checked, structured report JSON.

Flow: compute engine data with a pinned `as_of` -> build prompt -> call the model -> check structure,
safety and facts -> regenerate with the checker's feedback if needed -> on the last attempt remove
any paragraph that still fails -> cache on disk. The report carries the engine data alongside the AI
text so the PDF draws charts and tables from the engine, never from AI prose.
"""

import copy
import datetime as dt
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass

from app import engine

from . import book_report, engine_facts
from .client import AIBadOutput, ClaudeClient, LLMClient
from .compact import Names, compact_chart, lordships, mangal_for_model
from .config import estimate_cost_usd, get_settings
from .products import LANGUAGES, PRODUCTS, Product
from .prompts import DISCLAIMERS, SYSTEM_PROMPT, build_user_prompt
from .safety import screen_text
from .schema import report_schema, structure_problems
from .validator import REDACT_KINDS, allow_range, check_text, collect_facts

log = logging.getLogger(__name__)

NO_REGENERATION_KINDS = {"wording"}  # e.g. dosha "cancelled" vs "mitigated": reported in meta.checks.warnings
CACHE_VERSION = 6  # bump when the prompt or report shape changes, so old cached reports are not reused
# Both Kundali tiers are written part by part (app/ai/book_report.py); `product.tier` picks the
# scope. Everything else - facts, checks, safety, the report envelope - is shared.
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

_FALLBACK_TEXT = {
    "en": ("Your {name}", "A personal reading of your chart, based on exact Swiss Ephemeris positions."),
    "hi": ("आपकी {name}", "आपकी कुंडली का व्यक्तिगत विवेचन, स्विस एफेमेरिस की सटीक ग्रह स्थितियों पर आधारित।"),
    "mr": ("तुमचा {name}", "तुमच्या कुंडलीचे वैयक्तिक विवेचन, स्विस एफेमेरिसच्या अचूक ग्रहस्थितींवर आधारित."),
}


@dataclass(frozen=True)
class Birth:
    """One person's resolved birth details (the API resolves `city` to lat/lon/timezone first)."""

    date: dt.date
    time: dt.time
    lat: float
    lon: float
    timezone: str | None = None
    city: str | None = None

    def key(self) -> dict:
        return {"date": self.date.isoformat(), "time": self.time.isoformat(timespec="seconds"),
                "lat": round(self.lat, 4), "lon": round(self.lon, 4), "tz": self.timezone or ""}


# ---- engine data ---------------------------------------------------------------------------------


def today_ist() -> dt.date:
    return dt.datetime.now(IST).date()


def _as_of_moment(as_of: dt.date) -> dt.datetime:
    return dt.datetime.combine(as_of, dt.time(12, 0), tzinfo=IST)


def _chart(birth: Birth, as_of: dt.date) -> dict:
    chart = engine.compute_chart(birth.date, birth.time, birth.lat, birth.lon, birth.timezone,
                                 as_of=_as_of_moment(as_of))
    if birth.city:
        chart["input"]["city"] = birth.city
    return chart


def _slim_chart(chart: dict) -> dict:
    """Raw-JSON mode, pair prompts: drop the 120-year dasha table (not needed for matching; halves the input)."""
    slim = copy.deepcopy(chart)
    slim["dasha"].pop("mahadashas", None)
    return slim


def _raw_for_model(chart: dict) -> dict:
    """Raw-JSON mode: the engine chart as is, except that the Mangal dosha block uses the model-facing wording
    ("softens", not the engine's "ineffective" / "cancel" - the dosha stays present)."""
    shown = copy.deepcopy(chart)
    shown["mangal_dosha"] = mangal_for_model(chart["mangal_dosha"])
    return shown


def _compact_prompt(product: Product, full: dict, as_of: dt.date) -> dict:
    """What the model reads when REPORT_COMPACT_DATA=1: the same facts as `full`, about a third of the tokens."""
    names, today = Names(), as_of.isoformat()
    if product.kind == "pair":
        matching = copy.deepcopy(full["matching"])
        for who in ("boy", "girl"):
            matching["mangal_dosha"][who] = mangal_for_model(full["matching"]["mangal_dosha"][who])
        prompt = {"as_of": today,
                  "boy_chart": compact_chart(full["boy_chart"], names, today, antardasha_mahadashas=None),
                  "girl_chart": compact_chart(full["girl_chart"], names, today, antardasha_mahadashas=None),
                  "matching": matching}
    else:
        prompt = {"as_of": today, "chart": compact_chart(full["chart"], names, today)}
    prompt["names"] = names.glossary()
    return prompt


def build_data(product: Product, births: list[Birth], as_of: dt.date) -> tuple[dict, dict]:
    """(engine data for the PDF / API response, data shown to the model) for the three flat-section
    products. The flagship Kundali book takes a different path entirely - see app/ai/book_report.py.

    The fact validator always works from the first (a superset of the second), so both prompt encodings
    are checked against the same engine facts."""
    if product.kind == "pair":
        boy, girl = (_chart(birth, as_of) for birth in births)
        full = {"boy_chart": boy, "girl_chart": girl, "matching": engine.match_charts(boy, girl)}
    else:
        chart = _chart(births[0], as_of)
        full = {"chart": chart, "lordships": lordships(chart)}
    if get_settings().compact_data:
        return full, _compact_prompt(product, full, as_of)
    if product.kind == "pair":
        matching = copy.deepcopy(full["matching"])
        for who in ("boy", "girl"):
            matching["mangal_dosha"][who] = mangal_for_model(full["matching"]["mangal_dosha"][who])
        return full, {"boy_chart": _raw_for_model(_slim_chart(full["boy_chart"])), "girl_chart": _raw_for_model(_slim_chart(full["girl_chart"])),
                      "matching": matching, "boy_lordships": lordships(full["boy_chart"]), "girl_lordships": lordships(full["girl_chart"])}
    return full, {**full, "chart": _raw_for_model(full["chart"])}


# ---- tidying -------------------------------------------------------------------------------------

_RE_MARKUP = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^<>]*)?>|\*\*|__|^#{1,6}\s+", re.MULTILINE)


def strip_markup(node):
    """The contract is plain text. A live run ended a summary with a stray "</p>", so HTML tags and markdown
    emphasis / heading marks are removed from every AI-written string before checking and saving."""
    if isinstance(node, str):
        return _RE_MARKUP.sub("", node).strip()
    if isinstance(node, list):
        return [strip_markup(item) for item in node]
    if isinstance(node, dict):
        return {key: (value if key in ("id", "type") else strip_markup(value)) for key, value in node.items()}
    return node


# ---- checking and redaction ----------------------------------------------------------------------


def _text_slots(content: dict):
    """Yield (location, container, key_or_index, text) for every AI-written string."""
    yield "title", content, "title", content.get("title", "")
    yield "summary", content, "summary", content.get("summary", "")
    for section in content.get("sections", []):
        where = f"section {section.get('id')}"
        yield f"{where} heading", section, "heading", section.get("heading", "")
        for i, text in enumerate(section.get("paragraphs", [])):
            yield f"{where} paragraph {i + 1}", section["paragraphs"], i, text
        for i, text in enumerate(section.get("bullets", [])):
            yield f"{where} bullet {i + 1}", section["bullets"], i, text
        for n, sub in enumerate(section.get("subsections", []), 1):
            yield f"{where} subsection {n} heading", sub, "heading", sub.get("heading", "")
            for i, text in enumerate(sub.get("paragraphs", [])):
                yield f"{where} subsection {n} paragraph {i + 1}", sub["paragraphs"], i, text
        table = section.get("table")
        if table:
            # a bad header drops the whole table (removing one column would misalign the rows)
            yield f"{where} table header", section, "table", " | ".join(table.get("columns", []))
            for r, row in enumerate(table.get("rows", [])):
                yield f"{where} table row {r + 1}", table["rows"], r, " | ".join(row)
    for n, remedy in enumerate(content.get("remedies", [])):
        text = " ".join(str(remedy.get(k, "")) for k in ("title", "description", "how_to", "frequency"))
        yield f"remedy {n + 1}", content["remedies"], n, text


def find_problems(content: dict, facts) -> list[dict]:
    """Safety hits and fact issues, each with where it was found."""
    problems = []
    for where, container, key, text in _text_slots(content):
        for hit in screen_text(text):
            problems.append({"type": "safety", "kind": hit.category, "where": where, "found": hit.term,
                             "message": f"forbidden topic ({hit.category}): '{hit.term}'",
                             "slot": (container, key)})
        for issue in check_text(text, facts):
            problems.append({"type": "fact", "kind": issue.kind, "where": where, "found": issue.found,
                             "message": issue.message, "slot": (container, key)})
    return problems


def _must_redact(problem: dict) -> bool:
    return problem["type"] == "safety" or problem["kind"] in REDACT_KINDS


def redact(content: dict, problems: list[dict], product: Product, language: str) -> list[dict]:
    """Remove every paragraph / bullet / row / remedy with a blocking problem. Returns what was removed."""
    removed, list_removals = [], {}
    title, summary = _FALLBACK_TEXT[language]
    for problem in problems:
        if not _must_redact(problem):
            continue
        container, key = problem["slot"]
        if isinstance(container, list):
            list_removals.setdefault(id(container), (container, set()))[1].add(key)
        elif key == "title":
            container[key] = title.format(name=product.name)
        elif key == "summary":
            container[key] = summary
        else:  # a heading: blank it; the PDF template falls back to its own section label
            container[key] = ""
        removed.append({k: problem[k] for k in ("type", "kind", "where", "found")})
    for container, indexes in list_removals.values():
        for index in sorted(indexes, reverse=True):
            del container[index]
    for section in content.get("sections", []):
        section["subsections"] = [sub for sub in section.get("subsections", []) if sub.get("paragraphs")]
        if not section.get("table") or not section["table"].get("rows"):
            section["table"] = None
    return removed


def _public(problem: dict) -> dict:
    return {k: problem[k] for k in ("type", "kind", "where", "found", "message")}


# ---- cache ---------------------------------------------------------------------------------------


def report_id(product: str, language: str, births: list[Birth], as_of: dt.date) -> str:
    payload = {"v": CACHE_VERSION, "product": product, "language": language, "as_of": as_of.isoformat(),
               "births": [birth.key() for birth in births]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:32]


def _cache_path(rid: str):
    return get_settings().reports_dir / f"{rid}.json"


def load_report(rid: str) -> dict | None:
    """A previously generated report by id, or None. Never calls the AI."""
    if not (rid.isalnum() and len(rid) == 32):
        return None
    path = _cache_path(rid)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("unreadable cached report %s; ignoring", path)
        return None


def _save_report(report: dict) -> None:
    path = _cache_path(report["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)  # atomic: a crash never leaves a half-written report


# ---- the generator -------------------------------------------------------------------------------


def generate_report(
    product_slug: str,
    language: str,
    births: list[Birth],
    *,
    as_of: dt.date | None = None,
    client: LLMClient | None = None,
    use_cache: bool = True,
) -> dict:
    """The full report JSON (see docs/API.md). Raises ValueError for bad arguments, AIError for AI trouble."""
    product = PRODUCTS.get(product_slug)
    if product is None:
        raise ValueError(f"unknown product {product_slug!r}; use one of {sorted(PRODUCTS)}")
    if language not in LANGUAGES:
        raise ValueError(f"unknown language {language!r}; use one of {sorted(LANGUAGES)}")
    expected = 2 if product.kind == "pair" else 1
    if len(births) != expected:
        raise ValueError(f"{product_slug} needs {expected} birth detail(s), got {len(births)}")

    as_of = as_of or today_ist()
    rid = report_id(product_slug, language, births, as_of)
    if use_cache:
        cached = load_report(rid)
        if cached is not None:
            cached["meta"]["cache_hit"] = True
            return cached

    settings = get_settings()
    client = client or ClaudeClient(settings)  # raises AINotConfigured before any engine work is wasted
    if product.book:
        report = _generate_book(product, language, births, as_of, rid, client, settings)
        _save_report(report)
        return report
    full_data, prompt_data = build_data(product, births, as_of)
    facts = collect_facts(full_data)
    schema = report_schema(product)

    calls, feedback, content, problems, regenerated_for = [], None, None, [], []
    for attempt in range(1, settings.max_attempts + 1):
        user = build_user_prompt(product, language, prompt_data, as_of.isoformat(), feedback)
        result = client.generate_json(system=SYSTEM_PROMPT, user=user, schema=schema)
        calls.append(result)
        content = strip_markup(result.data)
        structure = structure_problems(product, content)
        problems = find_problems(content, facts)
        log.info("report %s attempt %d: %d structure, %d content problems", rid, attempt, len(structure), len(problems))
        if not structure and not any(p["kind"] not in NO_REGENERATION_KINDS for p in problems):
            break  # clean, or only cosmetic findings that are not worth a second paid call (they become warnings)
        feedback = structure + [f"{p['where']}: {p['message']}" for p in problems]
        regenerated_for.append({"attempt": attempt, "structure": structure, "problems": [_public(p) for p in problems]})
    else:
        if structure:
            raise AIBadOutput(f"report structure still wrong after {settings.max_attempts} attempts: {structure}")

    redactions = redact(content, problems, product, language) if problems else []
    warnings = [_public(p) for p in problems if not _must_redact(p)]
    if redactions:
        still_wrong = structure_problems(product, content)
        if still_wrong:
            raise AIBadOutput(f"report unusable after removing unsafe/unverifiable text: {still_wrong}")

    usage = {key: sum(call.usage.get(key, 0) for call in calls)
             for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
    model = calls[-1].model
    cost_usd = estimate_cost_usd(model, usage)
    if cost_usd is None:
        cost_usd = estimate_cost_usd(settings.model, usage)
    report = {
        "id": rid,
        "product": product.slug,
        "product_name": product.name,
        "language": language,
        "title": content["title"],
        "summary": content["summary"],
        "sections": content["sections"],
        "remedies": content["remedies"],
        "disclaimer": DISCLAIMERS[language],
        "data": full_data,
        "meta": {
            "model": model,
            "requested_model": settings.model,
            "effort": settings.effort,
            "as_of": as_of.isoformat(),
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "attempts": len(calls),
            "usage": usage,
            "cost_estimate_usd": cost_usd,
            "cost_estimate_inr": None if cost_usd is None else round(cost_usd * settings.usd_inr, 2),
            "request_ids": [call.request_id for call in calls if call.request_id],
            # rejected_drafts: what the checker found in earlier attempts (the last entry matches `redactions` /
            # `warnings` when the final attempt was still not clean). Watch this for validator false positives.
            "checks": {"clean": not redactions and not warnings, "redactions": redactions, "warnings": warnings,
                       "rejected_drafts": regenerated_for},
            "cache_version": CACHE_VERSION,
            "cache_hit": False,
        },
    }
    _save_report(report)
    return report


# ---- the flagship book --------------------------------------------------------------------------


def book_facts(full_data: dict):
    """Fact checker for the book: every engine fact, widened to each month and year the supplied windows
    and dasha periods span (validator.allow_range), and told which fact types the engine gave us at all
    (validator.untraceable_issues)."""
    facts = collect_facts(full_data)
    timeline = full_data.get("timeline") or {}
    ranges = [window["range"] for window in timeline.get("windows", [])]
    ranges += [entry["range"] for entry in timeline.get("past", {}).get("entries", [])]
    ranges += [row["range"] for row in timeline.get("year_table", [])]
    ranges += [block["range"] for block in timeline.get("far_blocks", [])]
    ranges += [year["range"] for year in timeline.get("near_years", [])]
    # Deliberately NOT the whole 120-year dasha table: widening over that would accept any month up to
    # 2115 and gut the check. The timeline is what the book is allowed to talk about.
    for engine_range in ranges:
        allow_range(facts, engine_range["start"], engine_range["end"])
    for flag, value in engine_facts.supplied(full_data).items():
        if hasattr(facts, flag):
            setattr(facts, flag, value)
    return facts


def _generate_book(product: Product, language: str, births: list[Birth], as_of: dt.date, rid: str,
                   client: LLMClient, settings) -> dict:
    chart = _chart(births[0], as_of)
    # The checker needs every engine fact, including the windows, before the first call is made.
    probe, _, _ = book_report.build_book_data(chart, language, as_of, product.tier)
    written = book_report.generate_book(
        chart=chart, language=language, as_of=as_of, client=client,
        facts_for_checker=book_facts(probe), max_attempts=settings.book_part_attempts,
        strip=strip_markup, tier=product.tier)

    results = written["results"]
    usage = {key: sum(result.usage.get(key, 0) for result in results)
             for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
    model = results[-1].model
    cost_usd = estimate_cost_usd(model, usage) or estimate_cost_usd(settings.model, usage)
    per_call = [{"call": record["call"], "attempts": record["attempts"],
                 "redactions": len(record["redactions"]), "warnings": len(record["warnings"]),
                 "usage": record["usage"],
                 "cost_estimate_inr": None if estimate_cost_usd(model, record["usage"]) is None else
                 round(estimate_cost_usd(model, record["usage"]) * settings.usd_inr, 2)}
                for record in written["checks"]]
    redactions = [item for record in written["checks"] for item in record["redactions"]]
    warnings = [item for record in written["checks"] for item in record["warnings"]]
    rejected = [item for record in written["checks"] for item in record["rejected_drafts"]]
    fallback_title, fallback_summary = _FALLBACK_TEXT[language]
    return {
        "id": rid,
        "product": product.slug,
        "product_name": product.name,
        "language": language,
        "tier": product.tier,   # "simple" | "detailed" - platform renders both from `parts`
        "title": written["title"] or fallback_title.format(name=product.name),
        "summary": written["summary"] or fallback_summary,
        "parts": written["parts"],
        # The Part A cards and the Part F gemstone lines: top level, both optional, both degrade to {}
        "highlights": written["highlights"],
        "gemstone": written["gemstone"],
        # DEPRECATED flat view of the same text, so the Phase 4 PDF keeps working while the book
        # template is built. Read `parts`; see docs/API.md.
        "sections": written["sections"],
        "remedies": written["remedies"],
        "disclaimer": DISCLAIMERS[language],
        "data": written["data"],
        "meta": {
            "model": model,
            "requested_model": settings.model,
            "effort": settings.effort,
            "as_of": as_of.isoformat(),
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "attempts": len(results),
            "calls": per_call,
            "usage": usage,
            "cost_estimate_usd": cost_usd,
            "cost_estimate_inr": None if cost_usd is None else round(cost_usd * settings.usd_inr, 2),
            "request_ids": [r.request_id for r in results if r.request_id],
            "checks": {"clean": not redactions and not warnings, "redactions": redactions,
                       "warnings": warnings, "rejected_drafts": rejected},
            "cache_version": CACHE_VERSION,
            "cache_hit": False,
        },
    }
