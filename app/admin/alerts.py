"""The alerts and the 9 a.m. digest. Delivery is injectable, so a test can prove one fires without sending.

WHAT RAISES AN ALERT (the owner's list, one rule per function below):

| key | when |
|---|---|
| `order_late` | a paid order is still not ready `ALERT_READY_MINUTES` after payment |
| `order_failed` | a paid order's fulfilment is `failed` |
| `cost_over` | a book cost more than `ALERT_COST_LIMIT_BOOK_INR`, or a report more than `ALERT_COST_LIMIT_REPORT_INR` |
| `spend_over` | today's AI spend passed `AI_DAILY_LIMIT_INR` |
| `rashifal_failed` | a rashifal run ended with failed pages |
| `errors_5xx` | more than `ALERT_5XX_IN_10_MIN` server errors in ten minutes |
| `health_fail` | the readiness check is failing |
| `email_refused` | Resend refused a send |
| `webhook_signature` | a Razorpay webhook or checkout signature was rejected |

**DELIVERY IS A PARAMETER, NOT A FACT ABOUT THIS MODULE.** `fire_due()` takes a `deliver` callable; the
default sends through app/mailer.py. Nothing here imports the mailer at module level and nothing calls it
unless asked, which is what lets tests/test_admin_alerts.py assert that a real alert fires by handing it a
list to append to. A test that has to be trusted not to send e-mail is a test somebody eventually runs
with a live key in the environment.

**EVERY ALERT IS SENT AT MOST ONCE PER SUBJECT.** `admin_alerts_sent` is keyed on (key, subject), so a late
order raises one alert for that order and not one per page load - and `ALERT_REPEAT_SECONDS` lets a
recurring condition speak again after a day rather than going quiet for ever. Without that the first
version of this file sent an e-mail on every refresh of the overview, which teaches the reader to filter
the alerts, which is the same as not having any.

The digest is a separate path with its own subject: one per IST day, keyed on the date, so running the
command twice cannot send two.

NO SCHEDULER IS ADDED. This runs in two ways and both are stated out loud:
  1. the overview page evaluates and fires when it is opened (in a daemon thread, like the payment path's
     own background work, so a page load never waits on a network call to Resend);
  2. `.venv/bin/python -m app.admin.alerts` for a cron line or systemd timer - `--digest` for the 9:00 IST
     digest, no argument to check the alerts. That is the entry point to schedule; nothing in this package
     starts a timer of its own, and `--dry-run` prints what would go out without recording it as sent.

     The 9:00 IST digest has NO scheduler in the app, so it does not send until something calls it. Two
     lines on the server, whose timezone must be IST for these to mean 9 a.m. (the production box is, and
     `timedatectl` says so):

         */5 * * * *  cd /srv/astrology && .venv/bin/python -m app.admin.alerts        # the alerts
         0 9   * * *  cd /srv/astrology && .venv/bin/python -m app.admin.alerts --digest

     Five minutes is cheap - a handful of indexed SQLite reads - and the deduplication is what keeps it
     quiet. Running it more often does not send more e-mail; it only shortens the delay on the first one.
"""

import datetime as dt
import logging
import time
from dataclasses import dataclass

from app import db

from . import errors, health, ledger, metrics, orders, rashifal_ops
from .config import get_admin_settings

log = logging.getLogger(__name__)

ALERT_REPEAT_SECONDS = 86400   # the same condition on the same subject may speak again after a day
DIGEST_HOUR_IST = 9

db.register_schema("admin_alerts", """
CREATE TABLE IF NOT EXISTS admin_alerts_sent (
    key     TEXT NOT NULL,
    subject TEXT NOT NULL,
    at      REAL NOT NULL,
    title   TEXT NOT NULL,
    PRIMARY KEY (key, subject)
);
""")


@dataclass(frozen=True)
class Alert:
    """One thing worth waking up for. `subject` is what makes it the SAME alert on the next evaluation -
    an order id, a date, a run id - so it is deduplicated per thing rather than per kind."""

    key: str
    subject: str
    title: str
    detail: str
    severity: str = "warning"   # warning | critical

    @property
    def dedupe_key(self) -> tuple[str, str]:
        return self.key, self.subject


# ---- the rules ---------------------------------------------------------------------------------------


def late_and_failed_orders(now: float | None = None) -> list[Alert]:
    settings = get_admin_settings()
    now = now or time.time()
    found = []
    for order in orders.unfinished_paid(settings.ready_minutes * 60, now):
        waited = metrics.elapsed(order.get("paid_at"), now)
        if order.get("fulfilment") == "failed":
            found.append(Alert("order_failed", order["id"], f"Paid order {order['id']} FAILED",
                               f"{order.get('product')} in {order.get('language')}, paid {waited} ago, "
                               f"{order.get('attempts')} attempt(s). Last error: {(order.get('error') or '-')[:200]}",
                               "critical"))
        else:
            found.append(Alert("order_late", order["id"],
                               f"Paid order {order['id']} not ready after {waited}",
                               f"{order.get('product')} in {order.get('language')}, fulfilment "
                               f"{order.get('fulfilment')!r} after {order.get('attempts')} attempt(s). "
                               f"The limit is {settings.ready_minutes:g} min.", "critical"))
    return found


def expensive_orders(days: int = 2, now=None) -> list[Alert]:
    """A sale that cost more of the AI budget than its price allows for.

    Two limits, because the two products have nothing in common: the book sells for ₹249 and the concise
    report for ₹49, so one rupee figure would either never fire on a book or fire on every report."""
    settings = get_admin_settings()
    start, end = metrics.window(days, now)
    found = []
    for order in orders.paid_between(start, end):
        cost = metrics.ai_cost_inr(order)
        if cost is None:
            continue
        gross = int(order.get("amount_paise") or 0)
        limit = settings.cost_limit_book_inr if gross >= 20000 else settings.cost_limit_report_inr
        if cost > limit:
            found.append(Alert("cost_over", order["id"],
                               f"Order {order['id']} cost Rs {cost:.2f} in AI",
                               f"{order.get('product')} in {order.get('language')} sold for Rs {gross / 100:g}; "
                               f"the limit for it is Rs {limit:g}. {order.get('attempts')} attempt(s), "
                               f"model {metrics.model_of(order) or 'not recorded'}."))
    return found


def daily_spend(now=None) -> list[Alert]:
    settings = get_admin_settings()
    moment = now or metrics.now_ist()
    spent = ledger.spend_today(moment)
    if spent <= settings.ai_daily_limit_inr:
        return []
    return [Alert("spend_over", moment.date().isoformat(),
                  f"AI spend today is Rs {spent:.0f}",
                  f"The daily limit AI_DAILY_LIMIT_INR is Rs {settings.ai_daily_limit_inr:g}. "
                  f"Paid reports, rashifal and the consultation together.", "critical")]


def rashifal_failures(hours: float = 26, now: float | None = None) -> list[Alert]:
    """A run that ended with failed pages. 26 hours, not 24: the daily refresh runs at 00:05 IST and a
    24-hour window checked at 00:04 the next day misses it by a minute."""
    since = (now or time.time()) - hours * 3600
    found = []
    for run in rashifal_ops.runs_with_failures(since):
        by_language = ", ".join(f"{code}:{count}" for code, count in sorted(run["failed_by_language"].items())) or "-"
        found.append(Alert("rashifal_failed", run["run_id"],
                           f"Rashifal run {run['run_id']} left {run['failed']} page(s) failed",
                           f"{run['generated']} generated, {run['partial']} partial, {run['skipped']} skipped, "
                           f"{run['failed']} FAILED. Checker rejections by language: {by_language}. "
                           f"The old content was kept, so nothing is blank."))
    return found


def server_errors(now: float | None = None) -> list[Alert]:
    settings = get_admin_settings()
    now = now or time.time()
    count = errors.count_since(errors.SERVER_ERROR, now - 600)
    if count <= settings.errors_in_10_min:
        return []
    # The subject is the ten-minute bucket, so a sustained outage speaks once per bucket rather than on
    # every page load, and a second burst an hour later is a new alert rather than a suppressed one.
    bucket = int(now // 600)
    return [Alert("errors_5xx", str(bucket), f"{count} server errors in ten minutes",
                  f"The threshold ALERT_5XX_IN_10_MIN is {settings.errors_in_10_min}. "
                  f"The system health page lists them.", "critical")]


def provider_errors(now: float | None = None) -> list[Alert]:
    """Resend refusing a send, and a rejected payment signature. Both are already logged precisely; this
    turns the log line into a message, and both are bucketed per hour so a storm is one alert."""
    now = now or time.time()
    bucket = str(int(now // 3600))
    found = []
    counts = errors.counts_since(now - 3600)
    refused = counts.get(errors.EMAIL_REFUSED, 0)
    if refused:
        found.append(Alert("email_refused", bucket, f"Resend refused {refused} send(s) in the last hour",
                           "A customer who closed the tab has no order link. The order page itself is "
                           "permanent, so nothing is lost, but the e-mail is the route back to it."))
    rejected = counts.get(errors.WEBHOOK_SIGNATURE, 0)
    if rejected:
        found.append(Alert("webhook_signature", bucket,
                           f"{rejected} rejected payment or webhook signature(s) in the last hour",
                           "Either RAZORPAY_WEBHOOK_SECRET does not match the one in the Razorpay dashboard, "
                           "or somebody is posting to the webhook. Neither fulfils an order.", "critical"))
    return found


def health_failure(now: float | None = None) -> list[Alert]:
    result = health.readiness(check_chromium=False)
    if result.get("status") == "ok":
        return []
    broken = ", ".join(f"{name}: {check['detail']}" for name, check in (result.get("checks") or {}).items()
                       if not check.get("ok"))
    day = metrics.to_ist(now or time.time())
    return [Alert("health_fail", day.strftime("%Y-%m-%dT%H"), "The readiness check is FAILING",
                  broken or "readiness reported a failure with no detail", "critical")]


def evaluate(now: float | None = None) -> list[Alert]:
    """Every rule, in one list. Each rule catches its own failures: one unreadable run report must not stop
    the late-order alert, which is the one that costs money."""
    moment_ts = now or time.time()
    moment_ist = metrics.to_ist(moment_ts)
    found: list[Alert] = []
    rules = (("late/failed orders", lambda: late_and_failed_orders(moment_ts)),
             ("expensive orders", lambda: expensive_orders(2, moment_ist)),
             ("daily spend", lambda: daily_spend(moment_ist)),
             ("rashifal failures", lambda: rashifal_failures(26, moment_ts)),
             ("server errors", lambda: server_errors(moment_ts)),
             ("provider errors", lambda: provider_errors(moment_ts)),
             ("health", lambda: health_failure(moment_ts)))
    for label, rule in rules:
        try:
            found.extend(rule())
        except Exception:  # noqa: BLE001
            log.exception("admin alert rule %r failed", label)
    return found


# ---- delivery ----------------------------------------------------------------------------------------


def email_delivery(subject: str, body: str) -> bool:
    """The default: one plain-text message to `ALERT_EMAIL_TO` through app/mailer.py, which never raises and
    which sends nothing at all unless `REPORT_EMAIL_ENABLED` is on."""
    from app import mailer

    settings = get_admin_settings()
    if not settings.alert_email_to:
        log.warning("admin alert not sent (ALERT_EMAIL_TO is empty): %s", subject)
        return False
    return mailer.send(settings.alert_email_to, subject, body)


def _already_sent(alert: Alert, now: float) -> bool:
    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT at FROM admin_alerts_sent WHERE key = ? AND subject = ?",
                           (alert.key, alert.subject)).fetchone()
    return bool(row) and (now - float(row["at"])) < ALERT_REPEAT_SECONDS


def _mark_sent(alert: Alert, now: float) -> None:
    with db.transaction() as conn:
        conn.execute("INSERT INTO admin_alerts_sent (key, subject, at, title) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT(key, subject) DO UPDATE SET at = excluded.at, title = excluded.title",
                     (alert.key, alert.subject, now, alert.title[:200]))


def compose(alert: Alert) -> tuple[str, str]:
    from app.web import site

    prefix = "CRITICAL" if alert.severity == "critical" else "Alert"
    subject = f"[{site.SITE_NAME} {prefix}] {alert.title}"
    body = (f"{alert.title}\n\n{alert.detail}\n\n"
            f"Raised at {metrics.now_ist():%Y-%m-%d %H:%M} IST.\n"
            f"Dashboard: {site.base_url().rstrip('/')}/admin\n")
    return subject, body


def fire_due(now: float | None = None, deliver=None, alerts=None) -> list[Alert]:
    """Evaluate, drop the ones already sent, deliver the rest, record what went out. Returns what was sent.

    `deliver(subject, body) -> bool` is the injection point. A delivery that returns False is NOT recorded
    as sent, so a Resend outage does not swallow the alert - the next evaluation tries again. That is the
    opposite of the usual "mark it done and move on", and it is deliberate: the whole value of these
    messages is that the first one arrives."""
    now = now or time.time()
    deliver = deliver or email_delivery
    sent = []
    for alert in (evaluate(now) if alerts is None else alerts):
        if _already_sent(alert, now):
            continue
        subject, body = compose(alert)
        try:
            ok = bool(deliver(subject, body))
        except Exception:  # noqa: BLE001 - a delivery failure must not stop the remaining alerts
            log.exception("delivering admin alert %s/%s failed", alert.key, alert.subject)
            ok = False
        if ok:
            _mark_sent(alert, now)
            sent.append(alert)
        else:
            log.warning("admin alert NOT delivered, will be retried: %s", alert.title)
    return sent


def fire_in_background(now: float | None = None, deliver=None) -> None:
    """What the overview page calls. A daemon thread, for the same reason app/payments/service.py spawns one
    for the order e-mail: a page must never wait on a third party's HTTP request."""
    import threading

    def run():
        try:
            fire_due(now, deliver)
        except Exception:  # noqa: BLE001
            log.exception("admin alert evaluation failed")

    threading.Thread(target=run, daemon=True, name="admin-alerts").start()


# ---- the daily digest --------------------------------------------------------------------------------


def digest_body(day: dt.date | None = None, now=None) -> tuple[str, str, dict]:
    """(subject, body, the figures) for YESTERDAY - which is what a 9 a.m. digest is about.

    Yesterday and not the last 24 hours: the digest is read against a calendar day, reconciled against a
    calendar day, and "since 9 a.m. yesterday" is a window nobody else's numbers use."""
    from app.web import site

    moment = now or metrics.now_ist()
    day = day or (moment.date() - dt.timedelta(days=1))
    start = metrics.day_start(day)
    end = metrics.day_start(day + dt.timedelta(days=1))
    paid = orders.paid_between(start, end)
    totals = metrics.summarise(paid)
    spread = totals.durations
    figures = {"day": day.isoformat(), "orders": totals.orders, "net_inr": totals.net_inr,
               "gross_inr": totals.gross_inr, "ai_cost_inr": totals.ai_cost_inr,
               "cost_unknown": totals.cost_unknown, "margin_inr": totals.margin_inr,
               "margin_percent": totals.margin_percent, "p50_seconds": spread.p50, "failed": totals.failed}
    margin = ("not computable: "
              f"{totals.cost_unknown} of {totals.orders} orders have no recorded AI cost"
              if totals.margin_inr is None else
              f"Rs {totals.margin_inr:.2f}"
              + (f" ({totals.margin_percent:.0f}% of net)" if totals.margin_percent is not None else ""))
    p50 = "no order became ready" if spread.p50 is None else f"{spread.p50 / 60:.1f} min"
    body = "\n".join([
        f"{site.SITE_NAME}: {day:%A %-d %B %Y} (IST)",
        "",
        f"Paid orders        {totals.orders}",
        f"Net revenue        Rs {totals.net_inr:.2f}"
        + ("" if not totals.gst_unknown else f"  ({totals.gst_unknown} order(s) have no recorded GST split, "
                                            f"so their gross is counted)"),
        f"Gross charged      Rs {totals.gross_inr:.2f}",
        f"AI cost            Rs {totals.ai_cost_inr:.2f}"
        + ("" if not totals.cost_unknown else f"  ({totals.cost_unknown} order(s) not recorded)"),
        f"Payment fee        Rs {totals.fee_inr:.2f}  (modelled, not from a settlement report)",
        f"Margin             {margin}",
        f"p50 generation     {p50}",
        f"Failed orders      {totals.failed}",
        "",
        f"{site.base_url().rstrip('/')}/admin",
    ])
    return f"[{site.SITE_NAME}] Yesterday: {totals.orders} order(s), Rs {totals.net_inr:.0f} net", body, figures


def send_digest(day: dt.date | None = None, now=None, deliver=None) -> bool:
    """Send the digest once per day. Keyed in the same table as the alerts, so twice is impossible."""
    moment = now or metrics.now_ist()
    day = day or (moment.date() - dt.timedelta(days=1))
    subject, body, figures = digest_body(day, moment)
    marker = Alert("digest", day.isoformat(), subject, body)
    stamp = moment.timestamp()
    if _already_sent(marker, stamp):
        log.info("digest for %s has already been sent", day)
        return False
    ok = bool((deliver or email_delivery)(subject, body))
    if ok:
        _mark_sent(marker, stamp)
    return ok


def main(argv=None) -> int:
    """`.venv/bin/python -m app.admin.alerts [--digest] [--dry-run]` - the cron entry point. The module
    docstring has the two crontab lines."""
    import argparse

    from app.ai import config as _config  # noqa: F401  (loads .env)

    parser = argparse.ArgumentParser(description="RashiKundli admin alerts and the daily digest")
    parser.add_argument("--digest", action="store_true", help="send yesterday's digest instead of checking alerts")
    parser.add_argument("--dry-run", action="store_true", help="print what would be sent; send nothing")
    args = parser.parse_args(argv)

    printed: list[str] = []

    def dry(subject: str, body: str) -> bool:
        printed.append(subject)
        print(f"--- would send ---\n{subject}\n\n{body}")
        return False   # False, so a dry run never records it as sent

    deliver = dry if args.dry_run else None
    if args.digest:
        subject, body, _ = digest_body()
        if args.dry_run:
            dry(subject, body)
            return 0
        print("digest sent" if send_digest() else "digest NOT sent (already sent today, or the mailer is off)")
        return 0
    if args.dry_run:
        for alert in evaluate():
            dry(*compose(alert))
        print(f"{len(printed)} alert(s) would be considered (deduplication is not applied in a dry run)")
        return 0
    sent = fire_due(deliver=deliver)
    print(f"{len(sent)} alert(s) sent")
    for alert in sent:
        print(f"  {alert.severity:8s} {alert.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
