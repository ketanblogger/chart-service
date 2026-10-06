"""System health: the readiness probe, error counts, disk, database size, the last smoke check, the licence clock.

Almost all of this already exists and is simply not visible anywhere: `hardening.readiness()` is what
`/health/ready` answers, `first_sale.summary()` is what the licence clock says, and the error counts come
from app/admin/errors.py. This module's job is to put them on one page with the two facts nobody has ever
been able to see from a browser - free space on `var/` and the size of the database - and to be honest
about the one that is not recorded at all.

**THE LAST SMOKE CHECK IS NOT RECORDED.** `scripts/smoke_check.py` prints its result and writes no file, so
there is no artefact to timestamp. Rather than leave a card saying "unknown" with nothing to do about it,
this reads the mtime of `ADMIN_SMOKE_MARKER` (default `var/smoke-check.log`) and the page says, in words,
that redirecting the script's output there is what makes the card true. That is a one-line change to a
deploy command, and it is stated where somebody will read it.

`readiness()` is called WITHOUT the Chromium check by default. That check launches headless Chromium and
takes about a second and a half; a dashboard page that starts a browser process on every load is a
dashboard that falls over on the box it is meant to be watching. `?chromium=1` asks for it explicitly.
"""

import os
import shutil
import time
from pathlib import Path

from . import errors, metrics
from .config import get_admin_settings


def readiness(check_chromium: bool = False) -> dict:
    from app import hardening

    return hardening.readiness(check_chromium=check_chromium)


def disk() -> dict:
    """Free space where `var/` lives: orders, the database, reports, PDFs and the run reports all land there.

    Reported as a percentage AND in gigabytes, because neither alone is actionable: 8% of a 20 GB disk is a
    weekend, and 8% of a 500 GB disk is a month."""
    from app.ai.config import ROOT

    path = ROOT / "var"
    try:
        path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(path)
    except OSError as exc:
        return {"ok": False, "detail": f"cannot read {path}: {exc}"}
    free_share = usage.free / usage.total * 100 if usage.total else 0
    return {"ok": free_share >= 10, "path": str(path.relative_to(ROOT)),
            "free_gb": usage.free / 1024 ** 3, "total_gb": usage.total / 1024 ** 3, "free_percent": free_share}


def database() -> dict:
    """Size of the SQLite file and of its write-ahead log.

    The WAL is listed separately on purpose: it grows between checkpoints and a big one is not a big
    database, so a single "database size" that silently included it would look like runaway growth after a
    busy hour and then shrink by itself."""
    from app import db

    path = db.db_path()
    def size(candidate: Path) -> int:
        try:
            return candidate.stat().st_size
        except OSError:
            return 0

    return {"path": path.name, "bytes": size(path), "wal_bytes": size(Path(str(path) + "-wal")),
            "mb": size(path) / 1024 ** 2, "wal_mb": size(Path(str(path) + "-wal")) / 1024 ** 2}


def directory_sizes() -> list[dict]:
    """What is actually using the space under `var/`: the report cache and the PDF cache are the two that grow
    without a ceiling as sales come in, and the free-chart PDF cache is the one that has one."""
    from app.ai.config import ROOT, get_settings
    from app.pdf.service import pdfs_dir

    entries = []
    for label, path in (("report cache", get_settings().reports_dir), ("PDF cache", pdfs_dir()),
                        ("rashifal run reports", ROOT / "var" / "rashifal" / "runs")):
        total, files = 0, 0
        try:
            for item in path.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
                    files += 1
        except OSError:
            pass
        entries.append({"label": label, "files": files, "mb": total / 1024 ** 2})
    return entries


def last_smoke_check() -> dict:
    from app.ai.config import ROOT

    configured = get_admin_settings().smoke_marker
    path = Path(configured)
    if not path.is_absolute():
        path = ROOT / path
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return {"recorded": False, "path": configured,
                "note": f"scripts/smoke_check.py writes no artefact, so nothing has timestamped it. Redirect "
                        f"its output to {configured} (or point ADMIN_SMOKE_MARKER elsewhere) and this becomes real."}
    return {"recorded": True, "path": configured, "at": stamp, "when": metrics.to_ist(stamp),
            "age": metrics.elapsed(stamp)}


def licence_clock() -> dict:
    """The first LIVE paid sale, and the Swiss Ephemeris licence position. NOT a countdown.

    It was one: it carried `deadline`, `days_left` and `overdue`, and the page showed a licence violation
    ticking down. There is no deadline. The Swiss Ephemeris is dual-licensed and the AGPL is one of the two -
    we comply by publishing the source of every deploy, which the publication procedure exists to do, and that
    is a licence in force rather than a grace period. The Professional licence is wanted to STOP publishing,
    for commercial reasons, and cannot help while `pyswisseph` is imported anyway.

    The keys stay in the payload with honest values rather than being deleted, because a dashboard that drops
    a key silently renders a blank where a number was and nobody notices which.
    """
    from app.payments import first_sale

    record = first_sale.status()
    return {"started": record is not None, "summary": first_sale.summary(),
            "licence": "pending; AGPL publishing in force", "overdue": False}


def error_counts(now: float | None = None) -> dict:
    now = now or time.time()
    return {
        "ten_minutes": errors.counts_since(now - 600),
        "day": errors.counts_since(now - 86400),
        "week": errors.counts_since(now - 7 * 86400),
        "recent": errors.recent(30),
        "capturing": get_admin_settings().error_capture,
        "dropped": errors.dropped(),
        "labels": errors.KIND_LABELS,
    }


def config_check() -> dict:
    """What a production start would refuse or warn about. Already written and already exact - it is the
    same function the process runs at boot, so this cannot drift from what would actually happen."""
    from app import hardening

    fatal, warnings = hardening.config_problems()
    return {"fatal": fatal, "warnings": warnings, "production": hardening.is_production()}


def overview(check_chromium: bool = False, now: float | None = None) -> dict:
    return {
        "readiness": readiness(check_chromium),
        "checked_chromium": check_chromium,
        "disk": disk(),
        "database": database(),
        "directories": directory_sizes(),
        "smoke": last_smoke_check(),
        "licence": licence_clock(),
        "errors": error_counts(now),
        "config": config_check(),
        "environment": os.getenv("APP_ENV", "development"),
        "mailer_configured": _mailer_configured(),
    }


def _mailer_configured() -> dict:
    from app import mailer

    return {"configured": mailer.configured(), "problems": mailer.problems()}
