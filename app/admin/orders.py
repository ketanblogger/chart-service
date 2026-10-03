"""Reading orders for the dashboard. Read-only, and birth details cannot reach a list from here.

**Every query below names its columns.** Not `SELECT *`, and not `app.payments.store`'s own readers, which
return the whole row including `request_json` - the resolved birth date, time and place of a real customer.
A list template that was handed the whole row would only be one `{{ order.request }}` away from publishing
it, and that is the sort of mistake that is made while fixing something else. Naming the columns makes the
privacy rule structural: the data is not in the object, so no template can print it.

`LIST_COLUMNS` is therefore the privacy boundary, and tests/test_admin_web.py asserts that a birth date
placed on an order never appears in the orders list HTML.

The e-mail address is masked by `metrics.mask_email` everywhere except the single-order detail page, and
that page is written to `admin_audit` before it renders. The detail page reads the birth PLACE and nothing
else about the birth - a support conversation is about "the Pune chart, bought Tuesday", and the date and
time of birth are never needed to answer one.
"""

import json
import time

from app import db

from . import metrics
from .metrics import ai_cost_inr, mask_email

# The only columns a list is allowed to know about. See the module docstring.
LIST_COLUMNS = ("id", "product", "kind", "language", "amount_paise", "base_paise", "gst_paise", "status",
                "fulfilment", "attempts", "error", "cost_inr", "usage_json", "email", "report_id",
                "created_at", "paid_at", "updated_at")
_LIST_SELECT = ", ".join(LIST_COLUMNS)

STATUSES = ("paid", "created", "failed")
FULFILMENTS = ("ready", "pending", "generating", "failed", "none")


def _available(columns: tuple[str, ...]) -> list[str]:
    """Drop the columns this database does not have yet. The GST columns arrive by `register_columns`, and
    a dashboard that 500s between a deploy and a migration is a dashboard nobody trusts afterwards."""
    present = metrics.order_columns()
    return [name for name in columns if name in present]


def _rows(where: str = "", params: tuple | list = (), limit: int | None = None, columns=LIST_COLUMNS) -> list[dict]:
    names = _available(tuple(columns))
    query = f"SELECT {', '.join(names)} FROM orders"
    if where:
        query += f" WHERE {where}"
    query += " ORDER BY COALESCE(paid_at, created_at) DESC"
    if limit:
        query += f" LIMIT {int(limit)}"
    with db.transaction(write=False) as conn:
        return [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]


def paid_between(start: float, end: float) -> list[dict]:
    """Paid orders whose PAYMENT falls in [start, end).

    Bucketed on `paid_at`, not `created_at`: revenue belongs to the day the money arrived, and a checkout
    started at 23:58 and paid at 00:01 belongs to the second day in every report anyone will reconcile
    against. Unpaid rows have no `paid_at` at all, which is also why they cannot leak into a revenue window.
    """
    return _rows("status = 'paid' AND paid_at >= ? AND paid_at < ?", (start, end))


def recent(limit: int = 200, status: str = "", product: str = "", language: str = "",
           fulfilment: str = "", days: int = 0) -> list[dict]:
    """The orders list, filtered. Unknown filter values are ignored rather than trusted into the SQL."""
    clauses, params = [], []
    if status in STATUSES:
        clauses.append("status = ?")
        params.append(status)
    if fulfilment in FULFILMENTS:
        clauses.append("fulfilment = ?")
        params.append(fulfilment)
    if product:
        clauses.append("product = ?")
        params.append(product)
    if language in ("en", "hi", "mr"):
        clauses.append("language = ?")
        params.append(language)
    if days:
        start, end = metrics.window(days)
        clauses.append("COALESCE(paid_at, created_at) >= ?")
        params.append(start)
    return _rows(" AND ".join(clauses), params, limit)


def products() -> list[str]:
    with db.transaction(write=False) as conn:
        return [row["product"] for row in conn.execute("SELECT DISTINCT product FROM orders ORDER BY product")]


def one(order_id: str) -> dict | None:
    """One order, for the detail page. Still not `SELECT *`: the birth date and time are not fetched at all.

    `city` is pulled out of `request_json` here and nothing else is, which is why this reads that column
    rather than being handed the parsed row - the place is what identifies a chart in a support
    conversation, and the date and time never leave the database."""
    columns = (*LIST_COLUMNS, "razorpay_order_id", "payment_id", "paid_via", "user_id", "session_id",
               "as_of", "messages", "next_retry_at", "lease_until", "token", "gst_rate_bp", "invoice_no",
               "request_json", "names_json")
    found = _rows("id = ?", (order_id,), 1, columns)
    if not found:
        return None
    order = found[0]
    order["birth_places"] = _places(order.pop("request_json", None))
    # The cover names are a customer's own name: not shown, only counted, so the page can say whether the
    # PDF was personalised without putting the name on a screen that does not need it.
    try:
        order["named_cover"] = bool(json.loads(order.pop("names_json", None) or "{}"))
    except ValueError:
        order["named_cover"] = False
    order.pop("token", None)  # fetched only to know it exists; a token in admin HTML is a bearer credential
    return order


def _places(request_json: str | None) -> list[str]:
    try:
        request = json.loads(request_json or "null") or {}
    except ValueError:
        return []
    return [str(birth.get("city") or "-") for birth in (request.get("births") or []) if isinstance(birth, dict)]


# ---- view models -------------------------------------------------------------------------------------


def row_view(order: dict) -> dict:
    """One line of the orders table: no birth details, a masked address, and margin that may be None."""
    gross = int(order.get("amount_paise") or 0)
    net, gst_recorded = metrics.net_revenue_paise(order)
    cost = ai_cost_inr(order)
    return {
        "id": order["id"],
        "when": metrics.to_ist(order.get("paid_at") or order.get("created_at")),
        "product": order.get("product"),
        "kind": order.get("kind"),
        "language": order.get("language") or "-",
        "gross_inr": gross / 100,
        "net_inr": net / 100,
        "gst_recorded": gst_recorded,
        "status": order.get("status"),
        "fulfilment": order.get("fulfilment"),
        "attempts": order.get("attempts"),
        "seconds": metrics.generation_seconds(order),
        "cost_inr": cost,
        "margin_inr": metrics.margin_inr(gross, net, cost),
        "margin_percent": metrics.margin_percent(gross, net, cost),
        "email": mask_email(order.get("email")),
        "has_email": bool((order.get("email") or "").strip()),
        "downloaded": downloaded_at(order) is not None,
        "error": (order.get("error") or "")[:120] or None,
    }


def downloaded_at(order: dict) -> float | None:
    """When the customer's PDF was first rendered, which is the closest thing to "downloaded" that exists.

    There is no download column on `orders` and this package does not add one to another module's table.
    What there IS: app/pdf/service.py renders a report's PDF ON THE FIRST DOWNLOAD REQUEST and caches the
    file under `var/pdfs/<report id>-...`. So the existence of that file means somebody asked for the PDF,
    and its mtime is when they first did. It cannot count a second download, and it says nothing about an
    order whose customer read the report on the web page instead - both stated on the page, because a
    column headed "downloaded" that silently means "a file exists" is a number that will be quoted.
    """
    report_id = order.get("report_id")
    if not report_id:
        return None
    try:
        from app.pdf.service import pdfs_dir

        matches = sorted(pdfs_dir().glob(f"{report_id}-*.pdf"), key=lambda path: path.stat().st_mtime)
    except (OSError, ValueError):
        return None
    return matches[0].stat().st_mtime if matches else None


def timeline(order: dict) -> list[dict]:
    """paid -> ready -> e-mail -> download, as far as each is actually recorded.

    The e-mail step is the honest gap in this: `send_order_link` is called once per payment and its result
    is logged, never stored, so there is no per-order "sent at". What the page can say is whether an
    address was captured and whether sending was even switched on, and that is what it says. A column on
    `orders` written by the payments layer is the fix, and it is not this package's column to add.
    """
    from app import mailer

    steps = [{"step": "paid", "at": order.get("paid_at"),
              "detail": f"via {order.get('paid_via') or '-'}, payment {order.get('payment_id') or '-'}"}]
    ready = metrics.ready_at(order)
    seconds = metrics.generation_seconds(order)
    steps.append({"step": "ready", "at": ready,
                  "detail": (f"{seconds / 60:.1f} min after payment, {order.get('attempts')} attempt(s)"
                             if seconds is not None else
                             f"not ready: fulfilment is {order.get('fulfilment')!r} after "
                             f"{order.get('attempts')} attempt(s)")})
    address = (order.get("email") or "").strip()
    steps.append({"step": "order-link e-mail", "at": None,
                  "detail": ("no address was captured at checkout" if not address else
                             f"sent to {mask_email(address)} at payment (per-order delivery is NOT recorded; "
                             f"sending is {'on' if mailer.configured() else 'OFF'})")})
    first_download = downloaded_at(order)
    steps.append({"step": "PDF download", "at": first_download,
                  "detail": ("the PDF has never been rendered, so it has not been downloaded"
                             if first_download is None else
                             "first render of the PDF, which happens on the first download request")})
    return steps


def detail_view(order: dict) -> dict:
    """Everything the order detail page shows, including per-call cost, retries, repairs and redactions."""
    gross = int(order.get("amount_paise") or 0)
    net, gst_recorded = metrics.net_revenue_paise(order)
    cost = ai_cost_inr(order)
    calls = metrics.calls_of(order)
    redactions = sum(call["redactions"] for call in calls)
    repairs = sum(call["repairs"] for call in calls)
    by_chapter: dict[str, int] = {}
    for call in calls:
        for chapter, count in (call["cut_by_chapter"] or {}).items():
            by_chapter[str(chapter)] = by_chapter.get(str(chapter), 0) + int(count)
    return {
        "order": order,
        "row": row_view(order),
        "timeline": timeline(order),
        "calls": calls,
        "model": metrics.model_of(order),
        "redactions": redactions,
        "repairs": repairs,
        "cut_by_chapter": sorted(by_chapter.items()),
        "gross_inr": gross / 100,
        "net_inr": net / 100,
        "gst_recorded": gst_recorded,
        "gst_inr": None if order.get("gst_paise") is None else int(order["gst_paise"]) / 100,
        "fee_inr": metrics.payment_fee_paise(gross) / 100,
        "cost_inr": cost,
        "margin_inr": metrics.margin_inr(gross, net, cost),
        "margin_percent": metrics.margin_percent(gross, net, cost),
        "age": metrics.elapsed(order.get("paid_at") or order.get("created_at")),
    }


def unfinished_paid(older_than_seconds: float, now: float | None = None) -> list[dict]:
    """Paid orders that are still not ready after `older_than_seconds`. The 15-minute alert's query."""
    cutoff = (now or time.time()) - older_than_seconds
    return _rows("status = 'paid' AND fulfilment != 'ready' AND paid_at IS NOT NULL AND paid_at <= ?", (cutoff,))
