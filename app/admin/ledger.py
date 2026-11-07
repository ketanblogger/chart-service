"""The cost ledger: every rupee of AI spend, per IST day, split by where it went.

Four buckets, and one of them is a hole that this module refuses to paper over.

| bucket | source | complete? |
|---|---|---|
| paid reports | `orders.cost_inr` | yes, for orders fulfilled since the column existed |
| rashifal | `cost_estimate_inr` in each `var/rashifal/runs/<run>.json` | yes |
| consultation | `cost_usd` in the assistant message's `chat_messages.meta_json`, converted at `USD_INR` | yes for delivered AI replies |
| failed work | **nothing records it** | NO - see below |

**THE FAILED-WORK HOLE.** `store.finish_fulfilment` writes `cost_inr` only on success, deliberately: a
re-fulfilment must not overwrite what the sale really cost. The consequence is that a generation which
burned tokens and then failed leaves no cost behind anywhere. So this module does not estimate it. It
reports the SIZE of the blind spot instead - how many failed attempts happened in the window, and how many
orders have no recorded cost at all - because a bucket labelled "failed work: ₹0" in a month with nine
failed books is worse than an empty bucket, and an estimate multiplied by an average would be a number
somebody reconciles against a real invoice.

The same care applies to the day a cost is counted on. Report spend is bucketed on the day the order was
PAID, not the day the file was written. Generation follows payment by minutes, and it is the sale's day
that makes "cost per rupee of revenue" a ratio of two figures from the same day; an order retried at 2 a.m.
the next morning would otherwise put its cost on a day with no revenue to divide by.
"""

import calendar
import datetime as dt
import json
import os
from collections import Counter
from pathlib import Path

from app import db

from . import metrics, orders

REPORTS = "paid reports"
RASHIFAL = "rashifal"
CONSULTATION = "consultation"
FAILED = "failed work"
BUCKETS = (REPORTS, RASHIFAL, CONSULTATION, FAILED)


def usd_inr() -> float:
    from app.ai.config import get_settings

    return get_settings().usd_inr


# ---- the three buckets that have a source ------------------------------------------------------------


def report_spend(start: float, end: float, paid=None) -> tuple[dict[str, float], dict]:
    """({IST day: rupees}, blind-spot counts) from `orders.cost_inr`.

    `paid` lets the caller hand in the window's rows it has already fetched. `daily()` needs the same rows
    four times over - spend, revenue, by model, by language - and querying `orders` once per view of them
    was four scans of a table with no index on `paid_at`."""
    by_day: dict[str, float] = {}
    unknown, failed_attempts, failed_orders = 0, 0, 0
    for order in (orders.paid_between(start, end) if paid is None else paid):
        cost = metrics.ai_cost_inr(order)
        if cost is None:
            unknown += 1
        else:
            day = metrics.ist_day(order.get("paid_at"))
            by_day[day] = by_day.get(day, 0.0) + cost
        attempts = int(order.get("attempts") or 0)
        if attempts > 1:
            failed_attempts += attempts - 1
        if order.get("fulfilment") == "failed":
            failed_orders += 1
    return by_day, {"orders_without_cost": unknown, "retried_attempts": failed_attempts,
                    "orders_failed": failed_orders}


def runs_dir() -> Path:
    from app.ai.config import ROOT

    path = Path(os.getenv("RASHIFAL_RUNS_DIR", ROOT / "var" / "rashifal" / "runs"))
    return path if path.is_absolute() else ROOT / path


def rashifal_runs() -> list[dict]:
    """Every run report on disk, newest first. The run id starts with the run's IST timestamp, but the file
    mtime is what is used for the day: a run id is written when the run STARTS and a batch run finishes up
    to an hour later, so the mtime is when the money was actually spent."""
    found = []
    try:
        paths = sorted(runs_dir().glob("*.json"))
    except OSError:
        return []
    for path in paths:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            stamp = path.stat().st_mtime
        except (OSError, ValueError):
            continue
        if not isinstance(report, dict):
            continue
        counts = report.get("counts") or {}
        found.append({
            "run_id": report.get("run_id") or path.stem,
            "at": stamp,
            "when": metrics.to_ist(stamp),
            "day": metrics.ist_day(stamp),
            "periods": report.get("periods") or [],
            "languages": report.get("languages") or [],
            "model": report.get("model"),
            "batch": bool(report.get("batch")),
            "calls": int(report.get("calls") or 0),
            "seconds": float(report.get("wall_clock_seconds") or 0.0),
            "cost_inr": report.get("cost_estimate_inr"),
            "generated": int(counts.get("generated") or 0),
            "partial": int(counts.get("partial") or 0),
            "skipped": int(counts.get("skipped") or 0),
            "failed": int(counts.get("failed") or 0),
            "failed_by_language": report.get("failed_checks_by_language") or {},
            "rejections": report.get("rejections") or [],
        })
    found.sort(key=lambda run: run["at"], reverse=True)
    return found


def rashifal_spend(start: float, end: float, runs=None) -> dict[str, float]:
    by_day: dict[str, float] = {}
    for run in runs if runs is not None else rashifal_runs():
        if not (start <= run["at"] < end) or run["cost_inr"] is None:
            continue
        by_day[run["day"]] = by_day.get(run["day"], 0.0) + float(run["cost_inr"])
    return by_day


def consultation_spend(start: float, end: float) -> tuple[dict[str, float], int]:
    """({IST day: rupees}, replies with no cost recorded) from the chat's own per-message meta.

    `cost_usd` is stored in DOLLARS by app/ai/chat.py and converted here at the CURRENT `USD_INR`, which is
    an approximation for an old message and is said so on the page. A reply that fell back to canned text
    records no cost (no successful call was billed for it) and is counted, not assumed free."""
    # Imported for its SIDE EFFECT as well as for nothing else: `chat_store` registers the `chat_messages`
    # schema at import time, and app/db.py only applies the schemas registered before a connection opens. A
    # process that has served an admin page but never touched the consultation had no such table, and this
    # query raised "no such table: chat_messages" - which took the whole cost ledger down with it.
    from app.ai import chat_store  # noqa: F401

    rate = usd_inr()
    by_day: dict[str, float] = {}
    missing = 0
    with db.transaction(write=False) as conn:
        rows = conn.execute(
            "SELECT created_at, meta_json FROM chat_messages WHERE role = 'assistant' AND kind = 'ai' "
            "AND created_at >= ? AND created_at < ?", (start, end)).fetchall()
    for row in rows:
        try:
            meta = json.loads(row["meta_json"] or "null") or {}
        except ValueError:
            meta = {}
        cost_usd = meta.get("cost_usd") if isinstance(meta, dict) else None
        if cost_usd is None:
            missing += 1
            continue
        day = metrics.ist_day(row["created_at"])
        by_day[day] = by_day.get(day, 0.0) + float(cost_usd) * rate
    return by_day, missing


# ---- by model and by language ------------------------------------------------------------------------


def by_model(start: float, end: float, runs=None, paid=None) -> list[dict]:
    """Rupees per model, over reports and rashifal together. The consultation's model is in its message
    meta too, but its spend is per reply rather than per sale, so it is listed separately below."""
    totals: Counter = Counter()
    for order in (orders.paid_between(start, end) if paid is None else paid):
        cost = metrics.ai_cost_inr(order)
        if cost is not None:
            totals[metrics.model_of(order) or "not recorded"] += cost
    for run in runs if runs is not None else rashifal_runs():
        if start <= run["at"] < end and run["cost_inr"] is not None:
            totals[run["model"] or "not recorded"] += float(run["cost_inr"])
    return [{"model": model, "cost_inr": cost} for model, cost in totals.most_common()]


def by_language(start: float, end: float, paid=None) -> list[dict]:
    """Rupees per language of the SALE. Rashifal is written in all three languages in one run and its cost
    is not split per language in the run report, so it is left out of this table rather than divided by
    three - a third of a batch is not what Marathi cost, and the run report says `failed_checks_by_language`
    but not `cost_by_language`."""
    totals: Counter = Counter()
    counts: Counter = Counter()
    for order in (orders.paid_between(start, end) if paid is None else paid):
        language = order.get("language") or "-"
        counts[language] += 1
        cost = metrics.ai_cost_inr(order)
        if cost is not None:
            totals[language] += cost
    return [{"language": language, "orders": counts[language], "cost_inr": totals.get(language, 0.0)}
            for language in sorted(counts)]


# ---- the page ----------------------------------------------------------------------------------------


def daily(days: int = 30, now=None) -> dict:
    """The ledger: one row per IST day with the four buckets, plus the totals and the projection."""
    start, end = metrics.window(days, now)
    labels = metrics.day_labels(days, now)
    runs = rashifal_runs()
    paid = orders.paid_between(start, end)
    reports, blind = report_spend(start, end, paid)
    rashifal = rashifal_spend(start, end, runs)
    consultation, consultation_missing = consultation_spend(start, end)

    revenue_by_day: dict[str, float] = {}
    for order in paid:
        net, _ = metrics.net_revenue_paise(order)
        day = metrics.ist_day(order.get("paid_at"))
        revenue_by_day[day] = revenue_by_day.get(day, 0.0) + net / 100

    rows = []
    for day in labels:
        spend = {REPORTS: reports.get(day, 0.0), RASHIFAL: rashifal.get(day, 0.0),
                 CONSULTATION: consultation.get(day, 0.0), FAILED: None}
        total = sum(value for value in spend.values() if value is not None)
        revenue = revenue_by_day.get(day, 0.0)
        rows.append({"day": day, "spend": spend, "total": total, "net_revenue_inr": revenue,
                     # Paise of AI cost per rupee of net revenue. None on a day with no revenue: spend with
                     # no sales is not an infinite ratio, it is a day the ratio does not describe.
                     "cost_per_rupee": None if revenue <= 0 else total / revenue})
    spent = sum(row["total"] for row in rows)
    revenue = sum(row["net_revenue_inr"] for row in rows)
    return {
        "days": days,
        "rows": rows,
        "totals": {REPORTS: sum(reports.values()), RASHIFAL: sum(rashifal.values()),
                   CONSULTATION: sum(consultation.values()), FAILED: None},
        "spent_inr": spent,
        "net_revenue_inr": revenue,
        "cost_per_rupee": None if revenue <= 0 else spent / revenue,
        "by_model": by_model(start, end, runs, paid),
        "by_language": by_language(start, end, paid),
        "blind_spot": {**blind, "consultation_replies_without_cost": consultation_missing},
        "projection": month_projection(now),
        "usd_inr": usd_inr(),
    }


def month_projection(now=None) -> dict:
    """Spend so far this IST month, and where it lands at this rate.

    Straight-line on days ELAPSED INCLUDING TODAY, which makes the first of the month a projection from a
    partial day and therefore noisy - the page prints the elapsed days beside it so that is visible rather
    than being a surprise. No seasonality is modelled: there is not a year of data to model one from."""
    moment = now or metrics.now_ist()
    first = moment.date().replace(day=1)
    start = metrics.day_start(first)
    end = metrics.day_start(moment.date() + dt.timedelta(days=1))
    runs = rashifal_runs()
    reports, _ = report_spend(start, end)
    rashifal = rashifal_spend(start, end, runs)
    consultation, _ = consultation_spend(start, end)
    spent = sum(reports.values()) + sum(rashifal.values()) + sum(consultation.values())
    elapsed_days = moment.day
    days_in_month = calendar.monthrange(moment.year, moment.month)[1]
    return {"month": moment.strftime("%B %Y"), "spent_inr": spent, "elapsed_days": elapsed_days,
            "days_in_month": days_in_month,
            "projected_inr": spent / elapsed_days * days_in_month if elapsed_days else None}


def spend_today(now=None) -> float:
    """Total AI spend on the current IST day - the figure the daily-limit alert compares."""
    start, end = metrics.window(1, now)
    reports, _ = report_spend(start, end)
    consultation, _ = consultation_spend(start, end)
    return sum(reports.values()) + sum(rashifal_spend(start, end).values()) + sum(consultation.values())
