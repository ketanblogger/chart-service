"""The /admin dashboard (Workstream B, Phase 1): server-rendered, read-only, behind HTTP basic auth.

    app/main.py:  from app.admin import router as admin_router ; app.include_router(admin_router)

| module | what it owns |
|---|---|
| `config.py` | every setting, as an env var with a default |
| `metrics.py` | **the one definition of every number**, NULL-aware. Nothing else computes a metric |
| `auth.py` | basic auth, the 12-hour session, the failed-login lockout (reusing `rate_events`) |
| `audit.py` | `admin_audit`: every single-order view and every export |
| `errors.py` | a log handler that keeps 5xx / Resend / signature failures where a page can read them |
| `orders.py` | order reads, with the privacy boundary as a column list rather than as a convention |
| `quality.py` | generation time, attempts, pass rate, what the checker cut |
| `ledger.py` | daily AI spend by bucket, model and language, and the month-end projection |
| `rashifal_ops.py` | the run reports on disk, and which of the 60 pages are stale |
| `health.py` | readiness, disk, database size, the smoke check, the licence clock |
| `alerts.py` | the alert rules and the 9 a.m. digest. Delivery is injectable |
| `charts.py` | inline SVG. No library, no script, no new CSP host |

Nothing in here writes to a table it does not own, and nothing starts a scheduler: the alerts run when the
overview is opened and from `python -m app.admin.alerts` (see that module for the cron line).
"""

from .routes import router

__all__ = ["router"]
