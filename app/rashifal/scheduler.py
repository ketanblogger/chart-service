"""Optional in-process scheduler (APScheduler), enabled with RASHIFAL_SCHEDULER=1.

The recommended production set-up is the systemd timer in deploy/systemd/ calling
scripts/rashifal_refresh.py; this is the no-extra-moving-parts alternative for a single box.

Cadence (IST): one job, daily at 00:05, plus 05:30 as a retry, plus once shortly after start-up.
Every run asks for ALL periods; `refresh` regenerates only pages whose stored content does not cover the
current window, so the effective cadence is exactly: today daily, weekly on Monday, 3/6/12-month pages on
the 1st - and anything that failed (or a server that was down at midnight) heals on the next run instead
of waiting a week or a month.

Several uvicorn workers may each start a scheduler; the lease in the database (store.acquire_lease) lets
only one of them run a refresh at a time, and the others find nothing left to do.
"""

import logging

from app.ai.client import AIError

from .config import scheduler_enabled
from .generate import RefreshBusy, refresh

log = logging.getLogger(__name__)
_scheduler = None


def run_once() -> None:
    try:
        summary = refresh()
    except RefreshBusy as exc:
        log.info("rashifal refresh skipped: %s", exc)
    except AIError as exc:
        log.error("rashifal refresh did not run: %s", exc)
    except Exception:  # a scheduler thread must never die silently
        log.exception("rashifal refresh crashed")
    else:
        log.info("rashifal refresh: %d generated, %d partial, %d skipped, %d failed (est. $%.2f)",
                 summary.count("generated"), summary.count("partial"), summary.count("skipped"),
                 summary.count("failed"), summary.cost_usd)


def start_if_enabled():
    """FastAPI start-up hook. Returns the scheduler, or None when RASHIFAL_SCHEDULER is off."""
    global _scheduler
    if not scheduler_enabled() or _scheduler is not None:
        return _scheduler
    import datetime as dt

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger

    from .periods import IST

    scheduler = BackgroundScheduler(timezone=IST, job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600})
    scheduler.add_job(run_once, CronTrigger(hour=0, minute=5, timezone=IST), id="rashifal-midnight")
    scheduler.add_job(run_once, CronTrigger(hour=5, minute=30, timezone=IST), id="rashifal-retry")
    scheduler.add_job(run_once, DateTrigger(run_date=dt.datetime.now(IST) + dt.timedelta(seconds=90)), id="rashifal-startup")
    scheduler.start()
    _scheduler = scheduler
    log.info("rashifal scheduler started (00:05 and 05:30 IST)")
    return scheduler


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
