"""Generation and quality: how long reports take, how often the first draft passes, and what the checker cut.

Two sources, and they answer different questions:

- **`orders.usage_json`** - written per SALE at fulfilment. It has the per-call record for the book (one
  entry per PART, each with its attempts, repairs, redactions and cost) and an attempt count for a flat
  report. This is the source for everything that has to be attributable to a sale: pass rate, attempts,
  redactions per chapter, the most expensive calls.
- **the report files in `REPORTS_DIR`** - `meta.checks.rejected_drafts`, which is the checker's own
  findings with the sentence that triggered each one. That text is NOT copied onto the order (it would
  double the row), so failure KINDS with examples can only come from here.

WHAT IS READ OUT OF A REPORT FILE, AND WHAT IS NOT. Only `meta`. A report file also holds `data` - the
whole engine chart of a real customer - and the report text itself. `_meta_of` parses the file and keeps
the meta, and the cache below keeps only that, so a customer's chart never lives in the dashboard's
memory. Files are parsed at most once per (path, mtime, size): the book is a megabyte of JSON and the
quality page asks for every one of them, which at thirteen files is 4 MB per page load and at four hundred
is a page nobody opens twice.
"""

import json
import os
from collections import Counter

from . import metrics, orders

_meta_cache: dict[str, tuple[tuple, dict]] = {}
MAX_EXAMPLES = 3
EXAMPLE_CHARS = 220


def _report_paths() -> list:
    from app.ai.config import get_settings

    directory = get_settings().reports_dir
    try:
        return sorted(directory.glob("*.json"))
    except OSError:
        return []


def _meta_of(path) -> dict:
    """`meta` of one report file, cached on (mtime, size). Never the chart, never the text."""
    try:
        stamp = path.stat()
    except OSError:
        return {}
    key = (stamp.st_mtime_ns, stamp.st_size)
    cached = _meta_cache.get(str(path))
    if cached and cached[0] == key:
        return cached[1]
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    meta = document.get("meta") or {}
    kept = {"product": document.get("product"), "language": document.get("language"),
            "model": meta.get("model"), "attempts": meta.get("attempts"),
            "cost_estimate_inr": meta.get("cost_estimate_inr"),
            "generated_at": meta.get("generated_at"),
            "rejected_drafts": (meta.get("checks") or {}).get("rejected_drafts") or [],
            "redactions": (meta.get("checks") or {}).get("redactions") or [],
            "clean": (meta.get("checks") or {}).get("clean")}
    _meta_cache[str(path)] = (key, kept)
    return kept


# ---- generation time by product x language ----------------------------------------------------------


def durations_by_product_language(paid) -> list[dict]:
    """p50 / p90 / max per (product, language). One row per pair that has at least one paid order."""
    groups: dict[tuple[str, str], list] = {}
    for order in paid:
        groups.setdefault((order.get("product") or "?", order.get("language") or "-"), []).append(order)
    rows = []
    for (product, language), group in sorted(groups.items()):
        spread = metrics.durations(group)
        rows.append({"product": product, "language": language, "orders": len(group),
                     "measured": spread.count, "missing": spread.missing,
                     "p50": spread.p50, "p90": spread.p90, "longest": spread.longest})
    return rows


# ---- attempts and the first-attempt pass rate -------------------------------------------------------


def calls_of_orders(paid) -> list[dict]:
    calls = []
    for order in paid:
        calls.extend(metrics.calls_of(order))
    return calls


def attempts_histogram(calls) -> list[dict]:
    """How many calls needed 1, 2, 3 ... attempts. A distribution, not a mean: the mean of a bimodal
    "almost always 1, occasionally 3" is a number no call ever took."""
    counter = Counter(call["attempts"] for call in calls)
    total = sum(counter.values()) or 1
    return [{"attempts": attempts, "calls": count, "share": count / total * 100}
            for attempts, count in sorted(counter.items())]


def pass_rate_by_day(days: int = 30, now=None, paid=None) -> list[dict]:
    """First-attempt pass rate per IST day, oldest first, with the day's call count beside it.

    The count travels with the rate because a 100% pass rate over one call and over forty are the same
    number and not the same fact, and a sparkline of the first would otherwise look like good news.

    `paid` is the window's rows when the caller already has them, so the page runs one query and not two."""
    if paid is None:
        start, end = metrics.window(days, now)
        paid = orders.paid_between(start, end)
    by_day: dict[str, list] = {label: [] for label in metrics.day_labels(days, now)}
    for order in paid:
        by_day.setdefault(metrics.ist_day(order.get("paid_at")), []).extend(metrics.calls_of(order))
    series = []
    for day in sorted(by_day):
        rate, first, total = metrics.first_attempt_pass_rate(by_day[day])
        series.append({"day": day, "rate": rate, "first": first, "calls": total})
    return series


# ---- what the checker found --------------------------------------------------------------------------


def failure_kinds(limit: int = 8) -> list[dict]:
    """The checker's most common findings across every cached report, with example sentences.

    Grouped on `kind` (the validator's own classification) and, within a kind, the distinct messages are
    kept so an example is a real line the checker wrote rather than a paraphrase. An example is a sentence
    from GENERATED astrology prose plus the checker's reason - never a customer's data - and it is
    truncated, because these messages quote a whole paragraph when the paragraph is what was wrong.
    """
    counter: Counter = Counter()
    examples: dict[str, list[str]] = {}
    languages: dict[str, Counter] = {}
    for path in _report_paths():
        meta = _meta_of(path)
        for draft in meta.get("rejected_drafts") or []:
            for problem in _problems_of(draft):
                kind = str(problem.get("kind") or "unclassified")
                counter[kind] += 1
                languages.setdefault(kind, Counter())[meta.get("language") or "?"] += 1
                message = str(problem.get("message") or "").strip()
                where = str(problem.get("where") or "").strip()
                text = f"{where}: {message}" if where else message
                bucket = examples.setdefault(kind, [])
                if text and text not in bucket and len(bucket) < MAX_EXAMPLES:
                    bucket.append(text[:EXAMPLE_CHARS])
    return [{"kind": kind, "count": count, "examples": examples.get(kind, []),
             "languages": dict(languages.get(kind, {}))}
            for kind, count in counter.most_common(limit)]


def _problems_of(draft) -> list[dict]:
    """A rejected-draft entry, flattened to problem dicts.

    The flat report and the book write this differently - the flat one is
    `{"attempt", "structure", "problems"}` while the book's parts append their own records - so both shapes
    are accepted rather than one of them being silently skipped, which would make whichever product is
    quieter look like the clean one."""
    if not isinstance(draft, dict):
        return []
    found = [problem for problem in (draft.get("problems") or []) if isinstance(problem, dict)]
    # `structure` is a list of plain strings: a shape the checker uses for "this is not a report at all".
    found += [{"kind": "structure", "message": str(text)} for text in (draft.get("structure") or [])]
    if not found and draft.get("kind"):
        found = [draft]
    return found


def redactions_by_chapter(paid, limit: int = 15) -> list[dict]:
    """Paragraphs the checker cut, per chapter, summed over the sales in the window.

    From `usage_json`, not from the report files: a chapter that is cut on every sale of one product
    matters more than one cut once, and only the order rows know how many sales there were."""
    counter: Counter = Counter()
    for order in paid:
        for call in metrics.calls_of(order):
            for chapter, count in (call["cut_by_chapter"] or {}).items():
                counter[str(chapter)] += int(count)
    return [{"chapter": chapter, "cut": count} for chapter, count in counter.most_common(limit)]


def most_expensive_calls(paid, limit: int = 12) -> list[dict]:
    """The calls that cost the most rupees. A cost of None sorts out, not to the bottom as a zero."""
    calls = [call for call in calls_of_orders(paid) if call.get("cost_inr") is not None]
    calls.sort(key=lambda call: float(call["cost_inr"]), reverse=True)
    return calls[:limit]


def overview(days: int = 30, now=None) -> dict:
    """Everything the generation-and-quality page shows, for a window of IST days."""
    start, end = metrics.window(days, now)
    paid = orders.paid_between(start, end)
    calls = calls_of_orders(paid)
    rate, first, total = metrics.first_attempt_pass_rate(calls)
    return {
        "days": days,
        "orders": len(paid),
        "durations": metrics.durations(paid),
        "by_product_language": durations_by_product_language(paid),
        "attempts": attempts_histogram(calls),
        "pass_rate": rate,
        "pass_first": first,
        "calls": total,
        "pass_rate_series": pass_rate_by_day(days, now, paid),
        "failure_kinds": failure_kinds(),
        "redactions": redactions_by_chapter(paid),
        "expensive": most_expensive_calls(paid),
        "reports_cached": len(_report_paths()),
        "reports_dir_note": os.getenv("REPORTS_DIR", "var/reports"),
    }
