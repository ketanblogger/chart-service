"""The /admin pages. Server-rendered Jinja in this same app, read-only, behind HTTP basic auth.

SIX PAGES (Phase 1): overview, orders (+ one order), generation and quality, cost ledger, rashifal ops,
system health. Two CSV exports, both aggregates. Nothing here writes to a customer's data: the only tables
this package inserts into are its own (`admin_audit`, `admin_error_events`, `admin_alerts_sent`), and every
read of `orders` names its columns so a birth date cannot reach a template (see app/admin/orders.py).

NOT IN THE SITEMAP, NOT INDEXED, NOT IN robots.txt. The sitemap is built from the URL registry in
app/web/i18n.py and /admin is not a registered page, so it is excluded by construction rather than by a
rule somebody has to remember. Every response carries `X-Robots-Tag: noindex, nofollow`, `Cache-Control:
no-store` and `Referrer-Policy: no-referrer`, and the 401 carries them too. robots.txt is deliberately NOT
given a `Disallow: /admin` line: robots.txt is public, so a disallow there is an announcement that the path
exists, and it does nothing a 401 has not already done.

EVERY PAGE IS ONE QUERY PER WINDOW, NOT ONE PER DAY. Nothing is precomputed and no scheduler is added. A
page fetches the widest window it needs once and buckets it by IST day in Python (`metrics.by_ist_day`);
the quality page parses each cached report file at most once per (mtime, size); the ledger reads the
run-report JSONs. This matters because `orders` has no index on `paid_at`, so the first version's
thirty-three per-day queries were thirty-three scans of the whole table - a page that got slower with every
sale ever made rather than with the length of the window it was showing. The next thing to do, if the
report cache ever gets large enough to matter, is to cache the per-day `Totals`; `metrics.summarise` over a
day's rows is already the right unit for that.
"""

import csv
import io
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.web import site

from . import alerts, audit, charts, errors, health, ledger, metrics, orders, quality, rashifal_ops
from .auth import clear_session, insecure_transport, issue_session, require_admin
from .config import get_admin_settings

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)
router = APIRouter(prefix="/admin", include_in_schema=False)

# Attaching the error recorder here is the one side effect of importing this module, and it is deliberate:
# the single `include_router` line in app/main.py is the only hook this package has, so the import IS the
# installation. app/admin/errors.py explains what it keeps and why it is a log handler.
errors.install()

NAV = (("overview", "Overview", "/admin"), ("orders", "Orders", "/admin/orders"),
       ("quality", "Generation", "/admin/quality"), ("cost", "Cost ledger", "/admin/cost"),
       ("rashifal", "Rashifal ops", "/admin/rashifal"), ("system", "System", "/admin/system"))
SPEND_SERIES = ((ledger.REPORTS, ledger.REPORTS), (ledger.RASHIFAL, ledger.RASHIFAL),
                (ledger.CONSULTATION, ledger.CONSULTATION), (ledger.FAILED, ledger.FAILED))
NO_STORE = {"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


# ---- template helpers: the rendering of "not recorded" lives here, once ------------------------------


def _rupees(value) -> str:
    """`Rs 249.00`, or the words "not recorded" for a None.

    A dash would be read as a zero and a zero is the one thing a NULL does not mean, so the filter spends
    the words. Every page uses it, which is why no template ever has to decide."""
    if value is None:
        return "not recorded"
    return f"Rs {float(value):,.2f}"


def _pct(value) -> str:
    return "not recorded" if value is None else f"{float(value):.0f}%"


def _minutes(seconds) -> str:
    """A duration as an operator reads it. Sub-minute in seconds, the rest in minutes: a generation is
    minutes long and "541 s" is a number you have to divide before it means anything."""
    if seconds is None:
        return "not recorded"
    seconds = float(seconds)
    return f"{seconds:.0f} s" if seconds < 90 else f"{seconds / 60:.1f} min"


def _ist(stamp) -> str:
    moment = metrics.to_ist(stamp)
    return "-" if moment is None else moment.strftime("%d %b %Y %H:%M")


templates.env.filters["rupees"] = _rupees
templates.env.filters["pct"] = _pct
templates.env.filters["minutes"] = _minutes
templates.env.filters["ist"] = _ist


def _page(request: Request, actor: str, page: str, template: str, context: dict) -> HTMLResponse:
    nav = [{"key": key, "label": label, "path": path, "current": key == page} for key, label, path in NAV]
    settings = get_admin_settings()
    full = {"site_name": site.SITE_NAME, "actor": actor, "admin_nav": nav, "now_ist": metrics.now_ist(),
            "insecure": insecure_transport(), "fee_percent": settings.fee_rate * 100,
            "bar": charts.bar_row, **context}
    response = templates.TemplateResponse(request, template, full)
    response.headers.update(NO_STORE)
    if getattr(request.state, "admin_new_session", False):
        issue_session(response, actor)
    return response


# ---- 1. overview -------------------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def overview(request: Request, actor: str = Depends(require_admin)) -> HTMLResponse:
    """Today / 7d / 30d, the 30-day trend, and the alerts strip.

    The alerts are EVALUATED for the strip and then delivered in a background thread. Opening the dashboard
    is exactly the moment an operator wants to know, and delivery is deduplicated per subject, so a refresh
    does not resend - but a page load must never wait on Resend, hence the thread (app/payments/service.py
    spawns one for the order e-mail for the same reason).

    `ADMIN_ALERTS_ON_VIEW=0` leaves the strip and stops the delivery, for an install that would rather have
    the timer be the only thing that sends. The tests set it, so no test can start a thread that outlives
    the environment it was configured in - a thread still running after a monkeypatch is undone would read
    the developer's real `.env`, and that is how a test suite sends a real e-mail."""
    now = metrics.now_ist()
    # ONE query for the widest window, then bucketed in Python. Three windows plus thirty days used to be
    # thirty-three queries, each a scan of `orders` (there is no index on `paid_at`), so the page got slower
    # with every sale ever made rather than with the length of the window it is showing.
    month_start, month_end = metrics.window(30, now)
    month = orders.paid_between(month_start, month_end)
    by_day = metrics.by_ist_day(month, 30, now)
    labels = metrics.day_labels(30, now)

    windows = []
    for days, label in ((1, "Today"), (7, "Last 7 days"), (30, "Last 30 days")):
        rows = [order for day in labels[-days:] for order in by_day[day]]
        windows.append({"days": days, "label": label, "totals": metrics.summarise(rows)})

    trend = [{"day": day, "totals": metrics.summarise(by_day[day])} for day in labels]

    raised = alerts.evaluate()
    if get_admin_settings().alerts_on_view:
        alerts.fire_in_background()
    return _page(request, actor, "overview", "overview.html", {
        "windows": windows,
        "trend": trend,
        "alerts": raised,
        "gst": metrics.gst_status(),
        "revenue_chart": charts.sparkline([day["totals"].net_inr for day in trend],
                                          [day["day"] for day in trend], colour=charts.SERIES[0],
                                          fmt="{:,.0f}"),
        "orders_chart": charts.sparkline([day["totals"].orders for day in trend],
                                         [day["day"] for day in trend], colour=charts.SERIES[1]),
    })


# ---- 2. orders ---------------------------------------------------------------------------------------


@router.get("/orders", response_class=HTMLResponse)
def orders_list(request: Request, actor: str = Depends(require_admin), days: int = 30, status: str = "",
                product: str = "", language: str = "", fulfilment: str = "") -> HTMLResponse:
    """The list. Not audited, because it holds nothing that needs auditing: no birth details and no full
    address. Auditing every list view would make the log a page counter and bury the views that matter."""
    rows = orders.recent(300, status=status, product=product, language=language, fulfilment=fulfilment, days=days)
    return _page(request, actor, "orders", "orders.html", {
        "rows": [orders.row_view(row) for row in rows],
        "filters": {"days": days, "status": status, "product": product, "language": language,
                    "fulfilment": fulfilment},
        "products": orders.products(), "statuses": orders.STATUSES, "fulfilments": orders.FULFILMENTS,
    })


@router.get("/orders/{order_id}", response_class=HTMLResponse)
def order_detail(request: Request, order_id: str, actor: str = Depends(require_admin)) -> HTMLResponse:
    """One order - the only page with a customer's full e-mail address on it, and therefore audited.

    The audit line is written BEFORE the page is built. If rendering then fails, the log still records that
    this order was opened, which is the direction the error has to fall: a view that happened without a
    record is the failure this log exists to prevent, and a record of a view that failed to render is noise."""
    order = orders.one(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="no such order")
    audit.record(actor, audit.ORDER_VIEW, order_id, f"{order.get('product')} / {order.get('status')}", request)
    return _page(request, actor, "orders", "order_detail.html", {
        "detail": orders.detail_view(order),
        "views": audit.views_of(order_id)[1:],   # skip the line this request just wrote
    })


# ---- 3. generation and quality -----------------------------------------------------------------------


@router.get("/quality", response_class=HTMLResponse)
def generation_quality(request: Request, actor: str = Depends(require_admin), days: int = 30) -> HTMLResponse:
    view = quality.overview(max(1, min(365, days)))
    series = view["pass_rate_series"]
    p50s = [row["p50"] for row in view["by_product_language"] if row["p50"] is not None]
    return _page(request, actor, "quality", "quality.html", {
        "view": view,
        "longest_p50": max(p50s) if p50s else 1,
        # A day with no calls is None, not 0: `sparkline` draws a gap, because a day nobody bought anything
        # is not a day the pass rate collapsed.
        "pass_chart": charts.sparkline([row["rate"] for row in series], [row["day"] for row in series],
                                       colour=charts.SERIES[1], unit="%"),
    })


# ---- 4. cost ledger ----------------------------------------------------------------------------------


@router.get("/cost", response_class=HTMLResponse)
def cost_ledger(request: Request, actor: str = Depends(require_admin), days: int = 30) -> HTMLResponse:
    view = ledger.daily(max(1, min(365, days)))
    return _page(request, actor, "cost", "cost.html", {
        "view": view, "series": SPEND_SERIES,
        "spend_chart": charts.stacked_bars(view["rows"], SPEND_SERIES),
        "spend_legend": charts.legend(SPEND_SERIES),
    })


# ---- 5. rashifal ops ---------------------------------------------------------------------------------


@router.get("/rashifal", response_class=HTMLResponse)
def rashifal(request: Request, actor: str = Depends(require_admin)) -> HTMLResponse:
    return _page(request, actor, "rashifal", "rashifal.html", {"view": rashifal_ops.overview()})


# ---- 6. system health --------------------------------------------------------------------------------


@router.get("/system", response_class=HTMLResponse)
def system(request: Request, actor: str = Depends(require_admin),
           chromium: bool = Query(default=False)) -> HTMLResponse:
    return _page(request, actor, "system", "system.html", {
        "view": health.overview(check_chromium=chromium),
        "audit_entries": audit.recent(60),
    })


# ---- exports: aggregates only ------------------------------------------------------------------------


def _csv(rows, header: list[str], note: str) -> str:
    """A CSV with a `#` comment line naming what it is and what its NULLs mean, then the header.

    The comment is there because these files get e-mailed and opened in a spreadsheet weeks later, where a
    blank margin cell is indistinguishable from a zero unless the file says so itself."""
    buffer = io.StringIO()
    buffer.write(f"# {note}\n")
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


@router.get("/export/daily-cost.csv", response_class=PlainTextResponse)
def export_daily_cost(request: Request, actor: str = Depends(require_admin), days: int = 30) -> Response:
    """Daily aggregates. There is deliberately NO export of customer rows: a CSV of orders would be a
    spreadsheet of who bought what, off the server and out of reach of the audit log that covers this one."""
    days = max(1, min(365, days))
    view = ledger.daily(days)
    audit.record(actor, audit.EXPORT, "daily-cost.csv", f"{days} days", request)
    gst = metrics.gst_status()
    rows = [[row["day"], f"{row['spend'][ledger.REPORTS]:.2f}", f"{row['spend'][ledger.RASHIFAL]:.2f}",
             f"{row['spend'][ledger.CONSULTATION]:.2f}", "", f"{row['total']:.2f}",
             f"{row['net_revenue_inr']:.2f}",
             "" if row["cost_per_rupee"] is None else f"{row['cost_per_rupee']:.4f}"]
            for row in view["rows"]]
    body = _csv(rows, ["day_ist", "paid_reports_inr", "rashifal_inr", "consultation_inr", "failed_work_inr",
                       "total_inr", "net_revenue_inr", "cost_per_rupee_of_revenue"],
                "RashiKundli daily AI cost, aggregates only. All days are IST. failed_work_inr is ALWAYS "
                "EMPTY: a failed generation's cost is not recorded anywhere (see /admin/cost). An empty "
                f"cell means not recorded, never zero. Net revenue: {gst['how']}")
    return Response(body, media_type="text/csv",
                    headers={**NO_STORE, "Content-Disposition": 'attachment; filename="daily-cost.csv"'})


@router.get("/export/daily-revenue.csv", response_class=PlainTextResponse)
def export_daily_revenue(request: Request, actor: str = Depends(require_admin), days: int = 30) -> Response:
    days = max(1, min(365, days))
    audit.record(actor, audit.EXPORT, "daily-revenue.csv", f"{days} days", request)
    now = metrics.now_ist()
    start, end = metrics.window(days, now)
    by_day = metrics.by_ist_day(orders.paid_between(start, end), days, now)
    rows = []
    for day in metrics.day_labels(days, now):
        totals = metrics.summarise(by_day[day])
        rows.append([day, totals.orders, f"{totals.gross_inr:.2f}", f"{totals.net_inr:.2f}",
                     totals.gst_unknown, f"{totals.fee_inr:.2f}", f"{totals.ai_cost_inr:.2f}",
                     totals.cost_unknown,
                     "" if totals.margin_inr is None else f"{totals.margin_inr:.2f}",
                     "" if totals.margin_percent is None else f"{totals.margin_percent:.1f}",
                     "" if totals.durations.p50 is None else f"{totals.durations.p50:.0f}",
                     "" if totals.durations.p90 is None else f"{totals.durations.p90:.0f}",
                     totals.failed])
    gst = metrics.gst_status()
    body = _csv(rows, ["day_ist", "paid_orders", "gross_inr", "net_inr", "orders_without_gst_split",
                       "payment_fee_inr_modelled", "ai_cost_inr", "orders_without_recorded_cost",
                       "margin_inr", "margin_percent", "p50_generation_seconds", "p90_generation_seconds",
                       "failed_orders"],
                "RashiKundli daily revenue, aggregates only - one row per IST day, no customer rows. "
                "margin_inr is EMPTY when any order that day has no recorded AI cost; an empty cell means "
                f"not recorded, never zero. The payment fee is modelled, not measured. Net revenue: {gst['how']}")
    return Response(body, media_type="text/csv",
                    headers={**NO_STORE, "Content-Disposition": 'attachment; filename="daily-revenue.csv"'})


@router.get("/export/audit.csv", response_class=PlainTextResponse)
def export_audit(request: Request, actor: str = Depends(require_admin), limit: int = 2000) -> Response:
    """The audit log itself. Exporting it is audited, which is not circular - it is the point: whoever takes
    a copy of the trail leaves a line in the trail."""
    audit.record(actor, audit.EXPORT, "audit.csv", f"{limit} rows", request)
    entries = audit.recent(max(1, min(20000, limit)))
    rows = [[_ist(entry["at"]), entry["actor"], entry["action"], entry["subject"] or "",
             entry["detail"] or "", (entry["ip_key"] or "")[:10]] for entry in entries]
    body = _csv(rows, ["when_ist", "actor", "action", "subject", "detail", "network_hmac"],
                "RashiKundli admin audit log. `subject` is an order id or an export name; no customer "
                "details are in this file, and `network_hmac` is a hash of a network block, not an address.")
    return Response(body, media_type="text/csv",
                    headers={**NO_STORE, "Content-Disposition": 'attachment; filename="audit.csv"'})


# ---- sign out ----------------------------------------------------------------------------------------


@router.get("/logout")
def logout(request: Request) -> RedirectResponse:
    """Drops the session cookie. Deliberately does NOT claim to sign you out: with HTTP basic auth the
    browser still holds the credentials and will offer them on the next request, so the honest description
    is "forget the session", and the page that follows re-authenticates. Closing the browser is what ends a
    basic-auth session, and that is a property of the scheme, not something this route can fix."""
    response = RedirectResponse("/admin", status_code=303)
    clear_session(response)
    response.headers.update(NO_STORE)
    return response
