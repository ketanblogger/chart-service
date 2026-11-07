"""ONE definition of every number the dashboard shows. Nothing else computes a metric.

Every page, every export and every alert reads its figures from this module, so "net revenue" on the
overview, in the CSV and in the 9 a.m. digest cannot disagree. tests/test_admin_metrics.py pins each
definition below, including what happens when the underlying column is NULL.

THE RULE THAT SHAPES ALL OF THIS: **NULL is "not recorded", never zero.**

`orders.cost_inr` is NULL for a cache hit and for every order paid before the column existed. A reader
that treats those as 0 reports a 100% margin on a real sale, which is the most flattering possible lie and
the easiest one to believe. So every aggregate here is a pair - the figure AND how many rows had nothing
to contribute - and margin is `None` rather than a number when the cost of a sale is unknown. The
templates print "not recorded" for a None and never a dash that could be read as a zero.

| metric | definition |
|---|---|
| gross revenue | sum of `amount_paise` over paid, non-refunded orders |
| net revenue | the same sum with GST excluded (see `net_revenue_paise`) |
| payment fee | modelled: `PAYMENT_FEE_PERCENT` of the gross + GST on that fee (app/admin/config.py) |
| AI cost | `orders.cost_inr`, in rupees, NULL-aware |
| contribution margin | net revenue - payment fee - AI cost, in rupees and as a % of net revenue |
| average order value | net revenue / paid orders |
| generation time | `ready_at - paid_at` in seconds; p50, p90, max |
| first-attempt pass rate | AI calls that needed one attempt / all AI calls |

`ready_at` DOES NOT EXIST as a column, and this module does not add one to someone else's table. What
exists is `updated_at`, and `finish_fulfilment` is the last thing that writes it on a successful order -
so for `fulfilment = 'ready'` that timestamp IS when the report became ready. `ready_at` below says this
out loud and returns None for every other state, because on a failed or generating order `updated_at` is
the time of the last attempt and a duration built on it would be measuring the wrong thing.

Times: every window is an IST calendar boundary (Asia/Kolkata), taken from app/rashifal/periods.py so the
dashboard's "today" is the same day the rashifal windows use. Stored timestamps are POSIX seconds.
"""

import datetime as dt
import json
import re
import time
from dataclasses import dataclass, field

from app import db
from app.masking import mask_email  # re-exported: `metrics.mask_email` is how the dashboard spells it
from app.rashifal.periods import IST

from .config import get_admin_settings

# ---- time --------------------------------------------------------------------------------------------


def now_ist() -> dt.datetime:
    return dt.datetime.now(IST)


def to_ist(stamp: float | None) -> dt.datetime | None:
    return None if stamp is None else dt.datetime.fromtimestamp(float(stamp), IST)


def ist_day(stamp: float | None) -> str:
    """The IST calendar date a timestamp falls in, as an ISO string - the key every daily series is grouped by."""
    moment = to_ist(stamp)
    return "" if moment is None else moment.date().isoformat()


def day_start(day: dt.date) -> float:
    return dt.datetime.combine(day, dt.time(0, 0), IST).timestamp()


def window(days: int, now: dt.datetime | None = None) -> tuple[float, float]:
    """[start, end) covering the last `days` IST calendar days INCLUDING today. days=1 is today."""
    now = now or now_ist()
    end = day_start(now.date() + dt.timedelta(days=1))
    return day_start(now.date() - dt.timedelta(days=days - 1)), end


def day_labels(days: int, now: dt.datetime | None = None) -> list[str]:
    """The ISO dates of that window, oldest first - so a series has a row for a day with no sales."""
    now = now or now_ist()
    first = now.date() - dt.timedelta(days=days - 1)
    return [(first + dt.timedelta(days=offset)).isoformat() for offset in range(days)]


# ---- net revenue, and the GST columns that may not be there yet ---------------------------------------

# The GST split is being added to `orders` by another hand, as `base_paise` / `gst_paise` / `gst_rate_bp`,
# with app/payments/gst.py owning the arithmetic and `gst.recorded(order)` owning the question "was it
# recorded for this order?". This module asks THAT function rather than reading the columns itself, so
# there is one definition of a recorded split and not a second one here that could drift from it - and it
# imports inside the function, so an admin page still renders if that module moves or is not there yet.
GST_COLUMNS = ("base_paise", "gst_paise", "gst_rate_bp")
# A refund is not recorded as a column yet either; when it is, these are the names that will exclude the
# order from revenue. Until then `is_refunded` is always False and says so in one place, not in six queries.
REFUND_COLUMNS = ("refunded_at", "refund_id", "refunded")


def order_columns() -> set[str]:
    """The columns `orders` actually has right now. Read, never altered - the table belongs to app/payments."""
    with db.transaction(write=False) as conn:
        return {row[1] for row in conn.execute("pragma table_info(orders)")}


def _recorded_split(order):
    """app/payments/gst.py's view of this order's split, or None. Never raises."""
    try:
        from app.payments import gst
    except ImportError:      # the GST module is not in this tree yet
        return None
    try:
        return gst.recorded(dict(order))
    except Exception:        # noqa: BLE001 - a dashboard reports on the sale, it never fails because of one
        return None


def gst_status() -> dict:
    """What the dashboard can honestly say about GST today: that it has the split, or that it does not.

    Shown as a banner on the overview and in the CSV header. An operator reading "net revenue" has to know
    whether it is net of anything, and a dashboard that quietly prints the gross under a net label is how
    a tax liability gets spent."""
    missing = [name for name in GST_COLUMNS if name not in order_columns()]
    if missing:
        return {"recorded": False, "columns": missing,
                "how": "`orders` has no " + ", ".join(missing) + " column yet, so NET REVENUE BELOW EQUALS "
                       "GROSS: nothing has been excluded. It starts excluding GST by itself once the "
                       "payments layer records the split - no change is needed here."}
    return {"recorded": True, "columns": [],
            "how": "net revenue is each order's recorded GST-exclusive base (app/payments/gst.py)"}


def net_revenue_paise(order) -> tuple[int, bool]:
    """(net paise, was the GST split actually recorded for this order).

    Two cases, and the second is the one that matters. If the order carries a recorded split, the net is
    its GST-exclusive base. If it does not - no columns yet, or a NULL on an order paid before the split
    was being recorded - the gross is returned with `False`.

    That fallback is deliberate and it is a FALLBACK, not a default: NULL means nobody wrote the figure,
    and the only defensible reading of an unrecorded tax split is that the whole amount is what we know.
    Returning 0, or skipping the order, would both understate a real sale; applying today's rate to it
    would invent a tax nobody was charged. The boolean is what stops the guess being invisible: every
    total carries the count of the orders it could not split, and the page prints it.
    """
    row = dict(order)
    gross = int(row.get("amount_paise") or 0)
    split = _recorded_split(row)
    if split is not None:
        return int(split.base_paise), True
    return gross, False


def is_refunded(order) -> bool:
    """Refunds are manual in the Razorpay dashboard for the MVP and nothing writes them back here, so this
    is False for everyone today. It exists as the single place revenue asks the question, so the day a
    refund column appears one edit removes refunds from every figure at once."""
    row = dict(order)
    return any(row.get(name) for name in REFUND_COLUMNS)


# ---- per-order figures --------------------------------------------------------------------------------


def payment_fee_paise(gross_paise: int) -> int:
    """MODELLED gateway fee, not a measured one - see the WHY in app/admin/config.py.

    Charged on the GROSS, i.e. on the whole amount that moved through Razorpay including GST, because that
    is what the gateway takes its percentage of. Handing this the net would understate the fee by the fee
    on the tax - small per order (about 1.06 paise in the rupee of GST at the default rate) and exactly the
    kind of quiet shortfall that makes a modelled margin drift away from the settlement report."""
    return int(round(gross_paise * get_admin_settings().fee_rate))


def ai_cost_inr(order) -> float | None:
    """Rupees of AI spend recorded against this sale, or None for "not recorded" (cache hit, or pre-column)."""
    value = dict(order).get("cost_inr")
    return None if value is None else float(value)


def ready_at(order) -> float | None:
    """When the report became ready, or None if it is not ready. See the module docstring: this is
    `updated_at` READ ONLY for `fulfilment = 'ready'`, because that is the state in which the last write
    to it was the one that finished the job."""
    row = dict(order)
    if row.get("fulfilment") != "ready":
        return None
    # THE REAL MOMENT, when the row has one. `updated_at` is the row's LAST-MODIFIED time and anything
    # that touches the order afterwards - an invoice number, a retried e-mail, a refund, a credit note -
    # moves it forward, so a report that was ready in four minutes could read as ten hours. Orders that
    # predate the `ready_at` column have no honest answer here, so they are counted as UNMEASURED rather
    # than measured wrongly: `durations` already reports how many it could not measure.
    return float(row["ready_at"]) if row.get("ready_at") else None


def generation_seconds(order) -> float | None:
    """ready_at - paid_at. None when either end is missing, or when the clock would run backwards.

    A negative duration is dropped rather than clamped to zero: it can only come from a row whose
    timestamps were written by different clocks or hands (a manual re-fulfilment, a restored backup), and
    a zero-second generation folded into a p50 makes the whole percentile quietly optimistic."""
    row = dict(order)
    finished, paid = ready_at(row), row.get("paid_at")
    if finished is None or paid is None:
        return None
    seconds = finished - float(paid)
    return seconds if seconds >= 0 else None


def margin_inr(gross_paise: int, net_paise: int, cost_inr: float | None) -> float | None:
    """Contribution margin in rupees: net revenue - payment fee - AI cost. None when the AI cost is unknown.

    Both amounts are needed and they are not the same number: the revenue we keep is the GST-exclusive
    base, while the fee is taken off the tax-inclusive charge. Passing one figure for both was the first
    version of this and it overstated every margin by the fee on the GST."""
    if cost_inr is None:
        return None
    return net_paise / 100 - payment_fee_paise(gross_paise) / 100 - cost_inr


def margin_percent(gross_paise: int, net_paise: int, cost_inr: float | None) -> float | None:
    """Margin as a percentage of NET revenue. None when the cost is unknown, and None on a zero sale -
    a percentage of nothing is not 0%, it is undefined, and 0% reads as "we made no money on this"."""
    rupees = margin_inr(gross_paise, net_paise, cost_inr)
    if rupees is None or net_paise <= 0:
        return None
    return rupees / (net_paise / 100) * 100


# ---- percentiles -------------------------------------------------------------------------------------


def percentile(values, fraction: float) -> float | None:
    """Nearest-rank percentile of a list of numbers; None for an empty list.

    Nearest rank, not interpolated: these are generation times measured on a handful of orders a day, and
    an interpolated p90 of four samples invents a duration no order ever had. With one sample, p50 and p90
    are both that sample, which is the honest answer."""
    ordered = sorted(value for value in values if value is not None)
    if not ordered:
        return None
    index = max(0, min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1)))))
    return float(ordered[index])


@dataclass(frozen=True)
class Durations:
    """p50 / p90 / max of a set of generation times, with how many orders had no usable duration."""

    count: int
    missing: int
    p50: float | None
    p90: float | None
    longest: float | None

    @property
    def measured(self) -> int:
        return self.count


def durations(orders) -> Durations:
    seconds = [generation_seconds(order) for order in orders]
    usable = [value for value in seconds if value is not None]
    return Durations(count=len(usable), missing=len(seconds) - len(usable), p50=percentile(usable, 0.5),
                     p90=percentile(usable, 0.9), longest=max(usable) if usable else None)


# ---- the summary every page and the digest share -----------------------------------------------------


@dataclass
class Totals:
    """One window's figures. `*_unknown` counters are why this is a dataclass and not a dict of numbers."""

    orders: int = 0
    gross_paise: int = 0
    net_paise: int = 0
    fee_paise: int = 0
    ai_cost_inr: float = 0.0
    cost_unknown: int = 0
    gst_unknown: int = 0
    failed: int = 0
    not_ready: int = 0
    durations: Durations = field(default_factory=lambda: Durations(0, 0, None, None, None))

    @property
    def gross_inr(self) -> float:
        return self.gross_paise / 100

    @property
    def net_inr(self) -> float:
        return self.net_paise / 100

    @property
    def fee_inr(self) -> float:
        return self.fee_paise / 100

    @property
    def average_order_inr(self) -> float | None:
        """Net revenue per paid order. None with no orders - an average of nothing is not zero."""
        return None if not self.orders else self.net_inr / self.orders

    @property
    def margin_inr(self) -> float | None:
        """None while ANY order in the window has no recorded AI cost.

        Deliberately all-or-nothing. A margin summed over the orders that happen to have a cost, presented
        as the window's margin, is a number with an unstated denominator, and the missing orders are
        exactly the ones that would pull it down. The page shows the count instead and says what to do."""
        if self.cost_unknown or not self.orders:
            return None
        return self.net_inr - self.fee_inr - self.ai_cost_inr
        # There is deliberately no "partial margin over the orders that do have a cost" alongside this. Such
        # a figure can only be built from the net revenue of ALL the orders minus the cost of SOME of them,
        # which is not a margin of anything - it is the full-margin number wearing a smaller label. The
        # count of unpriced orders is the honest thing to show, and it is what the page shows.

    @property
    def margin_percent(self) -> float | None:
        rupees = self.margin_inr
        return None if rupees is None or self.net_paise <= 0 else rupees / self.net_inr * 100


def by_ist_day(orders, days: int, now: dt.datetime | None = None) -> dict[str, list]:
    """{ISO day: the orders paid that day}, with an entry for every day in the window including empty ones.

    Here so that a page showing a 30-day trend runs ONE query and buckets it, rather than thirty queries -
    which is what the first version did. `orders` has no index on `paid_at`, so each of those thirty was a
    scan of the table, and the cost of that grows with every sale ever made rather than with the window.
    """
    buckets: dict[str, list] = {label: [] for label in day_labels(days, now)}
    for order in orders:
        buckets.setdefault(ist_day(dict(order).get("paid_at")), []).append(order)
    return buckets


def summarise(orders) -> Totals:
    """Totals for a list of PAID orders (the caller has already filtered the window and the status)."""
    totals = Totals()
    for order in orders:
        row = dict(order)
        if row.get("status") != "paid" or is_refunded(row):
            continue
        net, gst_recorded = net_revenue_paise(row)
        totals.orders += 1
        totals.gross_paise += int(row.get("amount_paise") or 0)
        totals.net_paise += net
        totals.fee_paise += payment_fee_paise(int(row.get("amount_paise") or 0))
        cost = ai_cost_inr(row)
        if cost is None:
            totals.cost_unknown += 1
        else:
            totals.ai_cost_inr += cost
        if not gst_recorded:
            totals.gst_unknown += 1
        if row.get("fulfilment") == "failed":
            totals.failed += 1
        if row.get("fulfilment") != "ready":
            totals.not_ready += 1
    totals.durations = durations(orders)
    return totals


# ---- AI calls behind one order -----------------------------------------------------------------------


def calls_of(order) -> list[dict]:
    """The per-call records stored in `orders.usage_json`, normalised to one shape.

    The book stores a list (one entry per PART of the book, each with its own attempts and cost); a flat
    report stores no list at all, only a total attempt count - so it is presented here as a single call.
    Without this both shapes end up spelled out at every call site, and the flat reports get dropped from
    the pass rate by whichever site forgets them, which silently raises it."""
    row = dict(order)
    try:
        usage = json.loads(row.get("usage_json") or "null") or {}
    except ValueError:
        return []
    if not isinstance(usage, dict):
        return []
    records = usage.get("calls")
    if isinstance(records, list) and records:
        return [{"call": str(record.get("call") or "?"), "attempts": int(record.get("attempts") or 1),
                 "redactions": int(record.get("redactions") or 0), "repairs": int(record.get("repairs") or 0),
                 "cut_by_chapter": record.get("cut_by_chapter") or {},
                 "cost_inr": record.get("cost_estimate_inr"),
                 "order_id": row.get("id"), "product": row.get("product"), "language": row.get("language")}
                for record in records if isinstance(record, dict)]
    attempts = usage.get("attempts")
    if attempts is None:
        return []
    return [{"call": "report", "attempts": int(attempts), "redactions": 0, "repairs": 0, "cut_by_chapter": {},
             "cost_inr": ai_cost_inr(row), "order_id": row.get("id"), "product": row.get("product"),
             "language": row.get("language")}]


def first_attempt_pass_rate(calls) -> tuple[float | None, int, int]:
    """(rate as a percentage, calls that passed first time, all calls). None when there are no calls -
    a pass rate over zero calls is not 100%."""
    records = list(calls)
    if not records:
        return None, 0, 0
    first = sum(1 for record in records if record["attempts"] == 1)
    return first / len(records) * 100, first, len(records)


def model_of(order) -> str | None:
    try:
        usage = json.loads(dict(order).get("usage_json") or "null") or {}
    except ValueError:
        return None
    return usage.get("model") if isinstance(usage, dict) else None


# ---- masking ------------------------------------------------------------------------------------------




_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# The order-page token, wherever it appears. app/web/routes.py mints it with `secrets.token_urlsafe(24)` and
# treats 20-80 characters as a candidate, so the same range is matched here. Case-insensitive on the path
# literal: a mismatched-case request 404s and never reaches the unhandled-error log, so `/ORDER/` is not a
# live vector - but the flag costs nothing and removes the question. NOT handled: a percent-encoded
# `%2Forder%2F`, deliberately - Starlette decodes `request.url.path` before any handler sees it, so that form
# cannot arrive through the path this scrub exists for, and a pattern for an unreachable shape is a pattern
# nobody can test.
_ORDER_PATH = re.compile(r"(/order/)[A-Za-z0-9_-]{20,80}", re.IGNORECASE)
# A token named in the text rather than sitting in a path: `token=x`, `token: x`, `"token": "x"`, `token x`.
#
# KEYED ON THE WORD, NOT ON THE VALUE'S SHAPE, and that is the whole design. A token is 32 characters of
# `[A-Za-z0-9_-]`, and so is a report id (32 hex), a brief hash and a dozen other things this log legitimately
# names. A rule that redacted everything of that shape would blank the report id out of every line on the
# health page - and the report id is how an operator finds the failing report. A scrub that destroys the
# diagnostic it is protecting gets turned off, which leaves the token exposed again.
#
# Two forms, with different length floors. After an `=` or a `:` anything of 8+ characters is the value, since
# nothing but a value goes there. After a bare space the floor is 20, because "token generation failed" and
# "token expired" are English and their next word is short; a 20-character word following "token" in a log
# line is not prose. No line in the app prints a token this way today - `grep` finds none - so this is for the
# `log.warning("order %s token %s", ...)` that gets added later, which is exactly the case this module exists
# to survive.
_TOKEN_ASSIGNED = re.compile(r"""(\b(?:access_token|order_token|token)\b["']?\s*[=:]\s*["']?)([A-Za-z0-9_-]{8,})""",
                             re.IGNORECASE)
_TOKEN_SPACED = re.compile(r"""(\b(?:access_token|order_token|token)\b\s+)([A-Za-z0-9_-]{20,80})""", re.IGNORECASE)


def scrub(text: str) -> str:
    """Take the credentials and the personal data out of a free-text string on its way into OUR tables.

    E-mail addresses are masked, and the ORDER TOKEN is removed wherever it appears - in a path, as a query
    parameter, or named in the text. The token is a bearer credential: anyone holding it can open the
    customer's order page and download their report, and that page is reachable without a login, permanently,
    by design.

    THE THREAT IS NOT A CRAFTED PATH. An attacker does not know a customer's token. It is the customer's OWN
    real token travelling through a 500 into a table that a page renders and a CSV exports - which is why the
    canonical `/order/{token}` form matters most, and why the full URL the order-link e-mail carries
    (`https://.../mr/order/{token}`) is covered by the same pattern. `app/hardening.py` logs the request path of every unhandled error -
    `log.exception("unhandled error on %s %s", request.method, request.url.path)` - so a 500 anywhere under
    `/order/{token}` puts a live token into the application log, and this module's whole job is to keep what
    the app logs somewhere a web page and a CSV can read it. Without this scrub the system-health page would
    print working credentials for a real customer's purchase.
    """
    text = _EMAIL.sub(lambda match: mask_email(match.group(0)), text or "")
    text = _ORDER_PATH.sub(r"\1<token redacted>", text)
    text = _TOKEN_ASSIGNED.sub(r"\1<redacted>", text)
    return _TOKEN_SPACED.sub(r"\1<redacted>", text)


def mask_emails_in(text: str) -> str:
    """Mask every address inside a free-text string. `scrub` is what callers want; this is one part of it."""
    return _EMAIL.sub(lambda match: mask_email(match.group(0)), text or "")


def elapsed(since: float | None, now: float | None = None) -> str:
    """"7 min", "3 h 20 min", "4 days" - for an age, never for a precise duration."""
    if since is None:
        return "-"
    seconds = max(0.0, (now if now is not None else time.time()) - float(since))
    if seconds < 90:
        return f"{seconds:.0f} s"
    if seconds < 5400:
        return f"{seconds / 60:.0f} min"
    if seconds < 172800:
        hours, minutes = divmod(int(seconds // 60), 60)
        return f"{hours} h {minutes} min"
    return f"{seconds / 86400:.1f} days"
