"""Rashifal ops: the last refresh runs, what each one produced, and which of the 60 pages are stale.

The run reports in `var/rashifal/runs/*.json` are the only record of a refresh - the refresh script writes
one per run and nothing else keeps a history - so this page is a reader of those files plus the stored pages
themselves. Parsing is in app/admin/ledger.py, because the cost ledger needs the same files and there is no
version of "read the run reports" that should exist twice.

"Stale" is not a judgement made here either. A page is stale when its stored window does not contain the
CURRENT window's start for its period, and `window_for` in app/rashifal/periods.py owns what the current
window is - the same function the refresh itself uses to decide whether to regenerate. So this page cannot
disagree with the job about what needs doing, which is the whole point of showing it: a list of stale pages
that the next run will not actually touch would send somebody hunting for a bug that is in the dashboard.

The next scheduled window is read from the same place, and it is described as the next window BOUNDARY, not
as a job time: the production refresh is a systemd timer this process cannot see, and the in-process
scheduler is off unless `RASHIFAL_SCHEDULER=1`. So the page states which of the two is running, and gives
the boundary, rather than inventing a "next run at" it has no way to know.
"""

import datetime as dt

from . import metrics
from .ledger import rashifal_runs

LANGUAGES = ("en", "hi", "mr")


def stored_pages() -> dict:
    from app.rashifal import store

    try:
        return store.list_pages()
    except Exception:  # noqa: BLE001 - an empty rashifal store must not take the admin page down
        return {}


def page_state(now=None) -> dict:
    """Per period: how many of the 12 pages cover the current window, how many are stale, which languages
    are missing, and the window itself."""
    from app.rashifal.config import get_rashifal_settings
    from app.rashifal.periods import PERIOD_SLUGS, RASHI_SLUGS, window_for

    moment = now or metrics.now_ist()
    stored = stored_pages()
    wanted = tuple(get_rashifal_settings().languages)
    state = {}
    for period in PERIOD_SLUGS:
        current = window_for(period, moment)
        fresh, stale, missing, incomplete = 0, [], [], []
        for rashi in RASHI_SLUGS:
            page = stored.get((rashi, period))
            if page is None:
                missing.append(rashi)
                continue
            # The stored window is recorded as ISO dates; a page covers the current window when its own
            # start is the current start. Comparing ends would call a page fresh on the last day of a
            # window it was written for two windows ago, because two windows can share an end date.
            if page["period_start"] != current.start.date().isoformat():
                stale.append(rashi)
                continue
            absent = [code for code in wanted if code not in page["languages"]]
            if absent:
                incomplete.append({"rashi": rashi, "missing": absent})
            fresh += 1
        state[period] = {
            "period": period,
            "window_start": current.start.date().isoformat(),
            "window_end": current.end.date().isoformat(),
            "next_boundary": current.end,
            "fresh": fresh,
            "stale": stale,
            "missing": missing,
            "incomplete": incomplete,
            "total": len(RASHI_SLUGS),
        }
    return state


def next_boundary(now=None) -> dict | None:
    """The soonest window boundary across all five periods - what the refresh will react to next.

    TIES ARE BROKEN BY FREQUENCY, not alphabetically, and the difference is visible one day in thirty. On the
    last day of a month the daily and the monthly window turn over at the SAME instant, and sorting by
    (boundary, period) then picked "monthly" because m sorts before t - so the page announced the rarest of
    the two windows that were about to move, on the one day it mattered. `PERIOD_SLUGS` is in frequency order,
    so its index is the tie-break: when several windows turn over together, name the one that always does.
    """
    from app.rashifal.periods import PERIOD_SLUGS

    state = page_state(now)
    rank = {period: index for index, period in enumerate(PERIOD_SLUGS)}
    upcoming = sorted((entry["next_boundary"], rank.get(period, len(rank)), period)
                      for period, entry in state.items())
    if not upcoming:
        return None
    when, _, period = upcoming[0]
    return {"period": period, "at": when, "in": _until(when, now or metrics.now_ist())}


def _until(when: dt.datetime, now: dt.datetime) -> str:
    seconds = (when - now).total_seconds()
    if seconds < 0:
        return "now (the window has already turned over)"
    if seconds < 5400:
        return f"in {seconds / 60:.0f} min"
    if seconds < 172800:
        return f"in {seconds / 3600:.1f} h"
    return f"in {seconds / 86400:.1f} days"


def how_it_runs() -> str:
    """Which refresh is actually driving this install - not a guess at a cron line we cannot see."""
    from app.rashifal.config import scheduler_enabled

    if scheduler_enabled():
        return ("RASHIFAL_SCHEDULER=1: this process runs the refresh itself, daily at 00:05 IST with a "
                "05:30 retry and one run shortly after start-up")
    return ("RASHIFAL_SCHEDULER is off, so the refresh is whatever calls scripts/rashifal_refresh.py "
            "(the production set-up is a systemd timer, which this process cannot see)")


def runs_by_period_language(runs, limit: int = 12) -> list[dict]:
    """Pages generated / failed / kept per period and per language, over the most recent runs.

    Per LANGUAGE the only per-language figure a run report carries is `failed_checks_by_language`: how many
    language versions the checker rejected. Generated and skipped counts are per PAGE across all languages,
    so they are reported per period only. Presenting a per-language "generated" by dividing would be an
    invention, and the Marathi column is exactly where somebody would act on it."""
    rows = []
    for run in runs[:limit]:
        rows.append({
            "run_id": run["run_id"],
            "when": run["when"],
            "periods": ", ".join(run["periods"]) or "-",
            "languages": ", ".join(run["languages"]) or "-",
            "model": run["model"] or "-",
            "batch": run["batch"],
            "generated": run["generated"],
            "partial": run["partial"],
            "skipped": run["skipped"],
            "failed": run["failed"],
            "failed_by_language": run["failed_by_language"],
            "calls": run["calls"],
            "cost_inr": run["cost_inr"],
            "minutes": run["seconds"] / 60,
            # Cost per page actually produced, which is the figure that answers "can we afford to run this
            # daily?". A run that generated nothing (everything already covered its window) has no cost per
            # page - it is a run that correctly did nothing, not an infinitely expensive one.
            "cost_per_page": None if not run["generated"] or run["cost_inr"] is None
            else float(run["cost_inr"]) / run["generated"],
        })
    return rows


def recent_rejections(runs, limit: int = 12) -> list[dict]:
    """The checker's most recent rejections, newest run first - the text of what it refused.

    These are the messages that caught the Marathi spelling and the "own sign" claims, so they are shown in
    full rather than counted: a count tells you the checker is working, and the message tells you whether
    the brief is wrong."""
    found = []
    for run in runs:
        for rejection in run["rejections"]:
            if not isinstance(rejection, dict):
                continue
            found.append({"run_id": run["run_id"], "when": run["when"],
                          "rashi": rejection.get("rashi"), "period": rejection.get("period"),
                          "language": rejection.get("language"), "attempt": rejection.get("attempt"),
                          "message": str(rejection.get("message") or "")[:300]})
            if len(found) >= limit:
                return found
    return found


def overview(now=None) -> dict:
    runs = rashifal_runs()
    state = page_state(now)
    return {
        "runs": runs_by_period_language(runs),
        "run_count": len(runs),
        "last_run": runs[0] if runs else None,
        "periods": [state[period] for period in state],
        "stale_total": sum(len(entry["stale"]) for entry in state.values()),
        "missing_total": sum(len(entry["missing"]) for entry in state.values()),
        "incomplete_total": sum(len(entry["incomplete"]) for entry in state.values()),
        "next": next_boundary(now),
        "how_it_runs": how_it_runs(),
        "rejections": recent_rejections(runs),
    }


def runs_with_failures(since: float) -> list[dict]:
    """Runs since a timestamp that ended with failed pages - the rashifal alert's query."""
    return [run for run in rashifal_runs() if run["at"] >= since and run["failed"]]
