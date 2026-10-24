"""The month's GST records: every invoice, every credit note, one spreadsheet, one ZIP.

WHAT THIS IS FOR. At the end of a month somebody has to file GSTR-1 and somebody has to hand a CA a folder.
Both want the same two things: the documents themselves, and a sheet whose totals reconcile against them.
So `/admin/accounting` answers one question per month - "what did we issue, and what does it add up to" -
and the download is that answer as files.

**EVERY ISSUED INVOICE IS IN IT. THERE IS NO FILTER.** An invoice number is allocated once, at payment, out
of a gap-free consecutive series (app/payments/invoice.py), and from that moment the document is a GST
record whatever this business later decides the sale *meant*. So this module's queries do not exclude the
proprietor's own orders, they do not exclude test-mode rows, and they do not exclude a refunded sale:

  - `internal` is a COLUMN in the sheet (and `internal_reason` beside it), never a `WHERE` clause. The
    dashboard's revenue figures are right to leave those orders out - see app/payments/internal.py - and a
    GST return is right to keep them in, and both can be true because one of them says which rows they are.
  - `orders.paid_between()` IS DELIBERATELY NOT USED. It filters `COALESCE(live, 1) = 1`, which is correct
    for revenue and wrong here: a test-mode order that was given an invoice number consumed a number out of
    the series, and a return reconciled against a series with an unexplained hole in it is a return
    somebody has to explain. `_invoiced_between` below reads `invoice_no IS NOT NULL` and nothing else.
  - a refund does not remove an invoice from the month it was issued in. It adds a CREDIT NOTE, in the
    month THAT was issued in, which is frequently a different month. Both are listed, and the Summary
    carries invoices, credit notes and the net of the two rather than one pre-netted column.

WHICH MONTH A DOCUMENT BELONGS TO is the date printed on it, in IST. For an invoice that is `paid_at` (the
number is allocated at payment and the document prints the payment date); for a credit note it is
`issued_at`, falling back to the refund's own timestamp exactly as app/payments/credit_note.py's `context`
does. IST and not UTC, for the reason `invoice.series_for` gives: a sale at 03:00 IST on 1 November read in
UTC lands on 31 October and in the previous return.

THE PAISA IS THE POINT. Every figure here is an integer number of paise from first read to last write, and
`Document.__post_init__` refuses a row whose parts do not add up to its total - the same assertion
`gst.Amounts` makes, for the same reason. The tax heads come from `gst.heads`, which guarantees
`sum(heads) == gst_paise`; where it cannot classify (no recorded place of supply) the tax lands in a
`not classified` column rather than being dropped, so a column total can never quietly lose a rupee.
`app/admin/xlsx.py`'s `Rupees` then writes the decimal from the integer. Nothing in this path is a float.

THE MONTHLY E-MAIL AND ITS SCHEDULE. No scheduler is added, exactly as app/admin/alerts.py adds none. One
cron line on the server, whose timezone must be IST:

    0 9 1 * *  cd /srv/astrology && .venv/bin/python -m app.admin.accounting --email

On the 1st that reports the month that just ENDED, which is why `due_month` subtracts a day rather than
reading today's month. The message carries a LINK and no attachment: the file names a customer and what
they bought, mail is not a place to keep that, and the page behind the link requires a sign-in. Sending is
deduplicated in `admin_alerts_sent`, the table app/admin/alerts.py already owns, so running the command
twice cannot send twice.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import logging
from dataclasses import dataclass, field

from app import db
from app.payments import credit_note, gst, internal, invoice, states, store
from app.payments.order_page import PRODUCT_NAMES

from . import audit, metrics
from .xlsx import Bold, Rupees, Sheet, when, workbook

log = logging.getLogger(__name__)

IST = invoice.IST
ALERT_KEY = "accounting_month"   # the dedupe key in `admin_alerts_sent`; one row per month
NOT_RECORDED = "(not recorded)"

# The columns this module is allowed to read, named for the same reason app/admin/orders.py names its own:
# the privacy boundary is the column list, not a convention. `request_json` - the resolved birth date, time
# and place of a real customer - IS NOT HERE and cannot reach any of this.
#
# `names_json` and `email` ARE, and they are the only place in app/admin that reads a customer's name. A tax
# invoice is issued to a named buyer at an address; a sheet of invoices with the buyer column blanked is not
# a record of anything. They reach the DOWNLOAD, which is written to the audit log, and never the page - see
# `month_page` and the route that calls it.
DOCUMENT_COLUMNS = (
    "id", "product", "kind", "language", "messages", "status", "currency",
    "amount_paise", "base_paise", "gst_paise", "gst_rate_bp", "place_of_supply",
    "invoice_no", "razorpay_order_id", "payment_id", "paid_at", "created_at",
    "email", "names_json", "internal", "internal_reason", "live",
    "refunded_paise", "refund_state", "refund_id", "refunded_at",
)

INVOICE_HEADER = ("Invoice no", "Date (IST)", "Order id", "Razorpay payment id", "Customer name",
                  "Customer e-mail", "Place of supply", "State", "State source", "Product", "Description",
                  "SAC code",
                  "Taxable value", "CGST", "SGST", "IGST", "Tax not classified", "Total",
                  "Status", "Credit notes", "Internal", "Internal reason")
INVOICE_WIDTHS = (17, 17, 24, 22, 24, 30, 14, 26, 22, 34, 10, 13, 11, 11, 11, 17, 12, 22, 20, 9, 24)

CREDIT_NOTE_HEADER = ("Credit note no", "Date (IST)", "Invoice no", "Invoice date (IST)", "Order id",
                      "Razorpay payment id", "Razorpay refund id", "Customer name", "Customer e-mail",
                      "Place of supply", "State", "State source", "Product", "Description", "SAC code",
                      "Taxable value credited", "CGST", "SGST", "IGST", "Tax not classified",
                      "Total credited", "Refund", "Internal", "Internal reason")
CREDIT_NOTE_WIDTHS = (18, 17, 17, 18, 24, 22, 22, 24, 30, 14, 26, 22, 34, 10, 22, 11, 11, 11, 17, 14, 9,
                      9, 24)

INVOICES_SHEET = "Invoices"
CREDIT_NOTES_SHEET = "Credit notes"
SUMMARY_SHEET = "Summary"


# ---- the month itself --------------------------------------------------------------------------------


def parse_month(text: str | None, now: dt.datetime | None = None) -> dt.date:
    """"2026-10" -> 1 October 2026. Anything unreadable falls back to the CURRENT IST month.

    A bad `?month=` is a typo or a crawler, not a reason for a 500 or a 422: the page shows a month either
    way and the one it shows is named on it, so a fallback cannot be mistaken for the month that was asked
    for. `<input type="month">` is what normally produces this value.
    """
    moment = now or metrics.now_ist()
    raw = (text or "").strip()
    parts = raw.split("-")
    try:
        return dt.date(int(parts[0]), int(parts[1]), 1)
    except (IndexError, ValueError, TypeError):
        return moment.date().replace(day=1)


def month_key(first: dt.date) -> str:
    return f"{first:%Y-%m}"


def month_label(first: dt.date) -> str:
    return f"{first:%B %Y}"


def month_bounds(first: dt.date) -> tuple[float, float]:
    """[start, end) of one IST calendar month, as unix timestamps."""
    days = calendar.monthrange(first.year, first.month)[1]
    return metrics.day_start(first), metrics.day_start(first + dt.timedelta(days=days))


def due_month(now: dt.datetime | None = None) -> dt.date:
    """The month the 1st-of-the-month e-mail is about: the one that just ended.

    Taken as "the first of the month containing yesterday" rather than as arithmetic on the month number,
    so January reports December of the previous year without a special case.
    """
    moment = now or metrics.now_ist()
    return (moment.date() - dt.timedelta(days=moment.date().day)).replace(day=1)


def months_with_documents(limit: int = 36) -> list[str]:
    """The months that actually hold an invoice or a credit note, newest first - what the picker offers.

    Built from the data rather than from a date range so the list cannot offer a month that has nothing in
    it, and so the first month of trading is the end of the list rather than a guess about when that was.
    """
    found: set[str] = set()
    with db.transaction(write=False) as conn:
        for row in conn.execute("SELECT paid_at FROM orders WHERE invoice_no IS NOT NULL AND paid_at IS NOT NULL"):
            found.add(metrics.ist_day(row["paid_at"])[:7])
        for row in conn.execute("SELECT COALESCE(issued_at, at) AS at FROM webhook_refunds "
                                "WHERE credit_no IS NOT NULL"):
            found.add(metrics.ist_day(row["at"])[:7])
    return sorted((key for key in found if key), reverse=True)[:limit]


# ---- one row of either sheet -------------------------------------------------------------------------


@dataclass
class Document:
    """One issued document - an invoice or a credit note - as both sheets and the ZIP need it.

    Money is paise throughout. `unclassified_paise` is tax that was charged and collected but cannot be
    attributed to a head because the order carries no recorded place of supply; it exists so that the row
    adds up and so that the hole is a figure on a page rather than a silent shortfall in a column total.
    """

    kind: str                  # "invoice" | "credit-note"
    number: str
    at: float
    order_id: str
    payment_id: str
    name: str
    email: str
    state_code: str
    state_name: str
    product: str
    description: str
    sac: str
    base_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    unclassified_paise: int
    total_paise: int
    status: str
    reference: str             # an invoice's credit notes; a credit note's invoice number
    internal: bool
    internal_reason: str
    rate_bp: int
    invoice_date: float | None = None
    refund_id: str = ""
    #: Empty when the buyer's own state is on the order; DEFAULTED_NOTE when this file supplied it.
    #: Placed among the defaulted fields rather than beside state_name, because a dataclass cannot have
    #: a field with a default before one without.
    state_note: str = ""
    # Carried for the ZIP, which has to render the document itself. `compare=False` so two Documents are
    # equal on the figures, which is what a test asserts about.
    order: dict = field(default_factory=dict, repr=False, compare=False)
    refund: dict | None = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        # The same assertion `gst.Amounts` makes, in the same spirit: a row whose parts do not add up to its
        # total would put a reconciliation error into a tax return, and it is cheaper to refuse to build it
        # than to find out which of twenty columns moved. Asserted on every row, not sampled.
        parts = self.base_paise + self.cgst_paise + self.sgst_paise + self.igst_paise + self.unclassified_paise
        if parts != self.total_paise:
            raise ValueError(f"{self.kind} {self.number}: taxable value and tax add up to {parts} paise, "
                             f"not the document's {self.total_paise}")

    @property
    def tax_paise(self) -> int:
        return self.cgst_paise + self.sgst_paise + self.igst_paise + self.unclassified_paise


def _order_rows(where: str, params: tuple) -> list[dict]:
    """Orders by this clause, with `names` parsed - the shape app/payments's own readers hand round."""
    present = metrics.order_columns()
    names = [name for name in DOCUMENT_COLUMNS if name in present]
    with db.transaction(write=False) as conn:
        rows = conn.execute(f"SELECT {', '.join(names)} FROM orders WHERE {where}", params).fetchall()
    orders = []
    for row in rows:
        order = dict(row)
        try:
            order["names"] = json.loads(order.pop("names_json", None) or "{}") or {}
        except ValueError:
            order["names"] = {}
        orders.append(order)
    return orders


def _invoiced_between(start: float, end: float) -> list[dict]:
    """Every order carrying an invoice number whose PAYMENT falls in the window. No other condition.

    Not `orders.paid_between`, and not `status = 'paid'` either: `invoice.assign` only ever numbers a paid
    order, so the invoice number IS the condition, and adding a second one here could only ever drop a
    document somebody has already been sent. See the module docstring.
    """
    return _order_rows("invoice_no IS NOT NULL AND paid_at IS NOT NULL AND paid_at >= ? AND paid_at < ?",
                       (start, end))


def _credited_between(start: float, end: float) -> tuple[list[tuple[dict, dict]], int]:
    """(refund row, its order) for every credit note ISSUED in the window, oldest first.

    The window is on `COALESCE(issued_at, at)`, which is the date the document prints - a note issued in
    November against October's invoice belongs to November's return, and listing it under the invoice's
    month is the mistake this ordering exists to prevent.
    """
    with db.transaction(write=False) as conn:
        rows = conn.execute(
            "SELECT * FROM webhook_refunds WHERE credit_no IS NOT NULL "
            "AND COALESCE(issued_at, at) >= ? AND COALESCE(issued_at, at) < ? "
            "ORDER BY COALESCE(issued_at, at), refund_id", (start, end)).fetchall()
    refunds = [dict(row) for row in rows]
    if not refunds:
        return [], 0
    wanted = sorted({refund["order_id"] for refund in refunds})
    placeholders = ", ".join("?" * len(wanted))
    by_id = {order["id"]: order for order in _order_rows(f"id IN ({placeholders})", tuple(wanted))}
    pairs, orphans = [], 0
    for refund in refunds:
        order = by_id.get(refund["order_id"])
        if order is None:
            # A credit note whose order has gone is not something to swallow: the note is a document
            # somebody holds, and the only honest thing a monthly export can do is say it cannot describe
            # one. Logged at ERROR; the count reaches the page through `view["orphans"]`.
            log.error("credit note %s references order %s, which is not in the database",
                      refund.get("credit_no"), refund.get("order_id"))
            orphans += 1
            continue
        pairs.append((refund, order))
    return pairs, orphans


#: What the service IS, in the words a GST line wants. SAC 998439 is "other on-line contents n.e.c.",
#: and a description column that says only "kundali-report-simple" tells a reader nothing about what was
#: supplied - which is the one thing the description is for.
SERVICE_PHRASE = "online astrology service"


def description(order: dict) -> str:
    """The line as a human reads it: "Janam Kundali Report - online astrology service".

    The catalogue's own name is used where the product is in the catalogue. Where it is NOT - a row
    written by hand, or a slug retired since - the slug is made readable rather than printed raw, and
    marked, because "kundali-simple" in a description column is an internal identifier leaking into a tax
    document and a reader cannot tell whether it is a product or a typo.
    """
    from app.payments import catalogue

    slug = (order.get("product") or "").strip()
    name = invoice._product_name(order)  # noqa: SLF001 - the invoice's own wording, so the two agree
    if slug and name == slug:
        known = slug in getattr(catalogue, "PRODUCTS", {})
        readable = slug.replace("-", " ").strip().capitalize()
        name = readable if known else f"{readable} (not in the catalogue)"
    return f"{name} - {SERVICE_PHRASE}" if name else SERVICE_PHRASE


def state_label(code: str | None) -> str:
    """The place of supply as a column reads it: "27 - Maharashtra", and the ways it can fail to be one.

    THE CODE IS NORMALISED FIRST, so a row carrying the two-letter "MH" reads as Maharashtra and its tax
    goes to CGST and SGST. It used to read "(not a GST state code: MH)" and put the whole tax in the
    unattributed column - correct about the data, wrong in a return, and wrong by the amount of the tax.
    The checkout API cannot produce a letter code, so such a row was written by hand; that is a reason to
    recognise it, not a reason to file its tax nowhere.

    Anything that is still not a state is NAMED rather than folded into "not recorded": a gap in history
    and a junk value need different repairs, and a column that calls them the same thing hides one.
    """
    resolved = states.normalise(code)
    if resolved:
        return f"{resolved} - {states.name(resolved, 'en')}"
    if states.is_export(code):
        return f"{states.name(code, 'en')} (zero-rated export)"
    raw = (code or "").strip()
    return NOT_RECORDED if not raw else f"(not a GST state code: {raw})"


def product_label(product: str) -> str:
    """The product's ENGLISH name, for the Summary's by-product rows.

    English and not the buyer's language, unlike the description on each document line: a summary row is
    one row for every sale of that product, and those sales were made in three languages - labelling the
    group with whichever language happened to come first would make the same product read differently from
    month to month. The per-document `Description` column keeps the wording the buyer actually saw.
    """
    names = PRODUCT_NAMES.get(product, {})
    return (names.get("en") or product).replace("{n}", "n")


#: What a row says when its state was supplied by this file rather than by the buyer.
DEFAULTED_NOTE = "state defaulted: recipient address not on record"


def _defaulted(order: dict) -> bool:
    """Is this a sale from before checkout asked for a state?

    Only those. An order that HAS a code - even an unusable one - is never defaulted, because the fix
    there is to find out what the code should have been, not to overwrite it.
    """
    return not (order.get("place_of_supply") or "").strip()


def _heads(amounts: gst.Amounts, code: str | None) -> tuple[int, int, int, int]:
    """(CGST, SGST, IGST, not classified) in paise. Their sum is always `amounts.gst_paise`.

    `gst.heads` is asked only when the place of supply is one of the 36 codes a return is filed for, which
    is the same condition app/payments/invoice.py prints a split under. Anything else keeps its tax in the
    fourth figure: an export's tax is zero so it lands there as a zero, and a code that is not a GST state
    lands there as the real amount.

    THE ONE EXCEPTION, AND IT IS A DELIBERATE DISAGREEMENT. An order from before 28 September 2026 has no
    place of supply at all, and the owner's instruction (to be confirmed with his CA) is to file those to
    the supplier's own state - Maharashtra, so CGST 9% + SGST 9%. The customer's ISSUED INVOICE for those
    sales still shows no state and a single composite GST line, and it is not reissued: a tax document
    that has already gone to a buyer is not rewritten months later to make a spreadsheet tidier.

    So for those rows the sheet and the document DO disagree, which this file otherwise promises they
    never do. That is why every such row carries DEFAULTED_NOTE in its own column and why the Summary
    counts them separately - the disagreement is stated on the face of the export rather than discovered
    by whoever reconciles it.
    """
    if code is None and amounts.gst_paise:
        code = states.seller_code()
    # NORMALISED, so the figures agree with the label the column prints. A row that reads "27 -
    # Maharashtra" and files its tax as unattributed would be the worst of both.
    code = states.normalise(code) or code
    if not states.is_known(code):
        return 0, 0, 0, amounts.gst_paise
    cgst = sgst = igst = 0
    for head in gst.heads(amounts, states.is_intra_state(code)):
        if head.name == "CGST":
            cgst = head.paise
        elif head.name == "SGST":
            sgst = head.paise
        else:
            igst = head.paise
    return cgst, sgst, igst, 0


def _status(order: dict) -> str:
    """The order's status with the refund stated, because that is the first thing asked of an invoice row."""
    status = order.get("status") or "?"
    refunded = int(order.get("refunded_paise") or 0)
    if not refunded:
        return status
    state = order.get("refund_state") or "partial"
    return f"{status}, refunded in {'full' if state == 'full' else 'part'}"


def _internal(order: dict, admins) -> tuple[bool, str]:
    """(is it ours, why) - `app/payments/internal.py`'s answer, never a second opinion.

    The reason is carried beside the flag because a classification with no reason is one nobody can check
    or reverse (the words are `register_columns`' own, in app/payments/store.py). A stored reason wins; where
    there is none the evidence is re-derived so the column is never blank behind a "yes".
    """
    flag = internal.is_internal(order, admins)
    reason = (order.get("internal_reason") or "").strip()
    if not reason and flag:
        reason = internal.reason_for(order, admins) or ""
    return flag, reason


def invoice_document(order: dict, admins=None) -> Document | None:
    """One invoice row, or None when this order has no invoice this module can describe.

    None happens for a row with a number but no recorded GST split, which `invoice.assign` cannot produce -
    it is reachable only by a hand-written row, and a line with a number and no figures would be worse in a
    return than a loud absence. The count reaches the page as `view["unreadable"]`.
    """
    amounts = gst.recorded(order)
    if amounts is None or not order.get("invoice_no"):
        return None
    code = order.get("place_of_supply")
    defaulted = _defaulted(order)
    if defaulted:
        code = states.seller_code()
    cgst, sgst, igst, unclassified = _heads(amounts, code)
    notes = [row["credit_no"] for row in store.refunds_for(order["id"]) if row.get("credit_no")]
    flag, reason = _internal(order, admins)
    return Document(
        kind="invoice", number=order["invoice_no"], at=float(order["paid_at"]), order_id=order["id"],
        payment_id=order.get("payment_id") or "", name=(order.get("names") or {}).get("self", "").strip(),
        email=(order.get("email") or "").strip(), state_code=(states.normalise(code) or code or ""), state_name=state_label(code),
        state_note=(DEFAULTED_NOTE if defaulted else ""),
        product=order.get("product") or "", description=description(order),
        sac=invoice.sac_code(), base_paise=amounts.base_paise, cgst_paise=cgst, sgst_paise=sgst,
        igst_paise=igst, unclassified_paise=unclassified, total_paise=amounts.total_paise,
        status=_status(order), reference=" ".join(notes), internal=flag, internal_reason=reason,
        rate_bp=amounts.rate_bp, order=order)


def credit_note_document(refund: dict, order: dict, admins=None) -> Document | None:
    """One credit-note row, read from the FROZEN split on the refund - never recomputed.

    The reason is app/payments/credit_note.py's: a reprint of a credit note must be the document it was the
    first time. A monthly export recomputing the split at today's rate would print a figure that disagrees
    with the note in the accountant's folder, which is the one thing this file exists to make impossible.
    """
    if not refund.get("credit_no") or refund.get("base_paise") is None:
        return None
    base, tax = int(refund["base_paise"]), int(refund.get("gst_paise") or 0)
    amounts = gst.Amounts(base_paise=base, gst_paise=tax, total_paise=base + tax,
                          rate_bp=int(refund.get("rate_bp") or 0))
    code = order.get("place_of_supply")
    # A credit note reverses an invoice, so it is attributed to the same state that invoice was -
    # including when this file supplied that state. A note filed under a different head from its own
    # invoice is a reconciliation somebody has to do by hand.
    defaulted = _defaulted(order)
    if defaulted:
        code = states.seller_code()
    cgst, sgst, igst, unclassified = _heads(amounts, code)
    flag, reason = _internal(order, admins)
    return Document(
        kind="credit-note", number=refund["credit_no"],
        at=float(refund.get("issued_at") or refund["at"]), order_id=order["id"],
        payment_id=order.get("payment_id") or "", name=(order.get("names") or {}).get("self", "").strip(),
        email=(order.get("email") or "").strip(), state_code=(states.normalise(code) or code or ""), state_name=state_label(code),
        state_note=(DEFAULTED_NOTE if defaulted else ""),
        product=order.get("product") or "", description=description(order),
        sac=invoice.sac_code(), base_paise=amounts.base_paise, cgst_paise=cgst, sgst_paise=sgst,
        igst_paise=igst, unclassified_paise=unclassified, total_paise=amounts.total_paise,
        status=order.get("refund_state") or "partial",
        reference=refund.get("invoice_no") or order.get("invoice_no") or "",
        internal=flag, internal_reason=reason, rate_bp=amounts.rate_bp,
        invoice_date=order.get("paid_at"), refund_id=refund.get("refund_id") or "",
        order=order, refund=refund)


# ---- totals ------------------------------------------------------------------------------------------

TOTAL_FIELDS = ("base_paise", "cgst_paise", "sgst_paise", "igst_paise", "unclassified_paise", "total_paise")


def totals(documents) -> dict:
    """Column sums, in paise, plus the count. Integer addition only - see the module docstring."""
    added = {name: 0 for name in TOTAL_FIELDS}
    count = 0
    for document in documents:
        count += 1
        for name in TOTAL_FIELDS:
            added[name] += getattr(document, name)
    return {**added, "count": count, "tax_paise": added["cgst_paise"] + added["sgst_paise"]
            + added["igst_paise"] + added["unclassified_paise"]}


def _net(left: dict, right: dict) -> dict:
    """Invoices minus credit notes.

    `count` is deliberately ADDED rather than subtracted: an invoice reversed by a credit note is two
    documents issued, not zero, and a return is filed on both of them. Only the money nets off.
    """
    return {**{name: left[name] - right[name] for name in (*TOTAL_FIELDS, "tax_paise")},
            "count": left["count"] + right["count"]}


def _grouped(invoices, notes, key, label) -> list[dict]:
    """One row per group, with the invoice side, the credit-note side and the net of the two.

    Both sides share the key space, so a group whose only document this month is a credit note still gets a
    row - a month in which a state's whole invoice was reversed must not read as a month that state did not
    appear in.
    """
    keys: dict = {}
    for document in (*invoices, *notes):
        keys.setdefault(key(document), label(document))
    rows = []
    for group in sorted(keys):
        mine = [document for document in invoices if key(document) == group]
        theirs = [document for document in notes if key(document) == group]
        issued, credited = totals(mine), totals(theirs)
        rows.append({"key": group, "label": keys[group], "invoices": issued, "credit_notes": credited,
                     "net": _net(issued, credited)})
    return rows


def month_view(first: dt.date, admins=None) -> dict:
    """Everything the page, the spreadsheet and the e-mail read. One pass over the month, shared by all three."""
    start, end = month_bounds(first)
    admins = internal.admin_emails() if admins is None else admins
    orders = sorted(_invoiced_between(start, end), key=lambda order: (order["paid_at"], order["id"]))
    invoices, unreadable = [], 0
    for order in orders:
        document = invoice_document(order, admins)
        if document is None:
            log.error("order %s carries invoice number %r with no recorded GST split - left out of the "
                      "%s export", order.get("id"), order.get("invoice_no"), month_key(first))
            unreadable += 1
            continue
        invoices.append(document)
    pairs, orphans = _credited_between(start, end)
    notes = [document for document in
             (credit_note_document(refund, order, admins) for refund, order in pairs)
             if document is not None]
    issued, credited = totals(invoices), totals(notes)
    return {
        "month": first,
        "key": month_key(first),
        "label": month_label(first),
        "start": start,
        "end": end,
        "invoices": invoices,
        "credit_notes": notes,
        "totals": {"invoices": issued, "credit_notes": credited, "net": _net(issued, credited)},
        "by_state": _grouped(invoices, notes, lambda d: d.state_code, lambda d: d.state_name),
        "by_product": _grouped(invoices, notes, lambda d: d.product, lambda d: product_label(d.product)),
        # Honest counts rather than silence: how many of this month's documents are OURS (included and
        # flagged, never dropped), and anything this export could not describe.
        "internal_invoices": sum(1 for document in invoices if document.internal),
        "internal_credit_notes": sum(1 for document in notes if document.internal),
        "unreadable": unreadable,
        # A credit note this export could not describe: its order is gone, or its frozen split is not on the
        # row. Counted and printed rather than skipped - a document somebody holds that no monthly file
        # mentions is the one failure this page cannot be allowed to hide.
        "orphans": orphans + (len(pairs) - len(notes)),
        "generated_at": dt.datetime.now(IST),
    }


# ---- the spreadsheet ---------------------------------------------------------------------------------


def _invoice_row(document: Document) -> list:
    return [document.number, when(document.at, IST), document.order_id, document.payment_id,
            document.name, document.email, document.state_code, document.state_name,
            document.state_note,
            document.product, document.description, document.sac,
            Rupees(document.base_paise), Rupees(document.cgst_paise), Rupees(document.sgst_paise),
            Rupees(document.igst_paise), Rupees(document.unclassified_paise), Rupees(document.total_paise),
            document.status, document.reference, "yes" if document.internal else "no",
            document.internal_reason]


def _credit_note_row(document: Document) -> list:
    return [document.number, when(document.at, IST), document.reference, when(document.invoice_date, IST),
            document.order_id, document.payment_id, document.refund_id, document.name, document.email,
            document.state_code, document.state_name, document.state_note,
            document.product, document.description, document.sac,
            Rupees(document.base_paise), Rupees(document.cgst_paise), Rupees(document.sgst_paise),
            Rupees(document.igst_paise), Rupees(document.unclassified_paise), Rupees(document.total_paise),
            document.status, "yes" if document.internal else "no", document.internal_reason]


def _figures(block: dict) -> list:
    return [Rupees(block["base_paise"]), Rupees(block["cgst_paise"]), Rupees(block["sgst_paise"]),
            Rupees(block["igst_paise"]), Rupees(block["unclassified_paise"]), Rupees(block["total_paise"])]


_MONEY_HEADS = ("Taxable value", "CGST", "SGST", "IGST", "Tax not classified", "Total")


def summary_sheet(view: dict) -> Sheet:
    """Totals by tax head, by state (what GSTR-1 B2C is filed on) and by product.

    THE TOTALS ARE SUMS OF THE ROWS ABOVE, not a second computation of them. Every figure on this sheet is
    produced by `totals()` adding integer paise over the very Documents written into the other two sheets,
    so the sheet cannot disagree with its own detail - which is the failure that makes a reconciliation
    sheet worse than none.
    """
    from app.web import site

    settings = gst.get_settings()
    rows: list[list] = [
        [Bold(f"{view['label']} - GST records")],
        ["Seller", site.LEGAL_ENTITY],
        ["GSTIN", site.GSTIN],
        ["Month (IST)", view["label"]],
        ["Generated", view["generated_at"].strftime("%Y-%m-%d %H:%M")],
        ["Pricing", f"listed prices {'INCLUDE' if settings.inclusive else 'EXCLUDE'} GST "
                    f"at {settings.rate_text}% (app/payments/gst.py)"],
        ["Invoices issued", view["totals"]["invoices"]["count"]],
        ["Credit notes issued", view["totals"]["credit_notes"]["count"]],
        ["Internal", f"{view['internal_invoices']} invoice(s) and {view['internal_credit_notes']} credit "
                     f"note(s) in this file are OURS, not a customer's. They are INCLUDED and flagged in "
                     f"the Internal column: an issued invoice is a GST record either way."],
        ["Not classified", "tax collected on an order with no recorded place of supply. It is real tax in a "
                           "column of its own because it cannot be filed under CGST/SGST or IGST."],
        [],
        [Bold("Totals by tax head")],
        ["", *(Bold(head) for head in _MONEY_HEADS), Bold("Documents")],
        ["Invoices", *_figures(view["totals"]["invoices"]), view["totals"]["invoices"]["count"]],
        ["Credit notes", *_figures(view["totals"]["credit_notes"]), view["totals"]["credit_notes"]["count"]],
        ["Net", *_figures(view["totals"]["net"]), view["totals"]["net"]["count"]],
        [],
        [Bold("By state (place of supply) - for GSTR-1 B2C")],
        [Bold("Code"), Bold("State"), Bold("Invoices"), Bold("Taxable value"), Bold("Tax"), Bold("Total"),
         Bold("Credit notes"), Bold("Taxable credited"), Bold("Tax credited"), Bold("Total credited"),
         Bold("Net taxable"), Bold("Net tax"), Bold("Net total")],
    ]
    for row in view["by_state"]:
        rows.append(_group_row(row))
    rows.extend([[], [Bold("By product")],
                 [Bold("Product"), Bold("Description"), Bold("Invoices"), Bold("Taxable value"), Bold("Tax"),
                  Bold("Total"), Bold("Credit notes"), Bold("Taxable credited"), Bold("Tax credited"),
                  Bold("Total credited"), Bold("Net taxable"), Bold("Net tax"), Bold("Net total")]])
    for row in view["by_product"]:
        rows.append(_group_row(row))
    if view["unreadable"] or view["orphans"]:
        rows.extend([[], [Bold("Left out of this file")],
                     ["Invoice numbers with no recorded GST split", view["unreadable"]],
                     ["Credit notes whose order is missing", view["orphans"]]])
    return Sheet(SUMMARY_SHEET, rows,
                 widths=(30, 34, 10, 15, 13, 13, 13, 17, 14, 15, 13, 11, 12), freeze_header=False)


def _group_row(row: dict) -> list:
    return [row["key"] or NOT_RECORDED, row["label"],
            row["invoices"]["count"], Rupees(row["invoices"]["base_paise"]),
            Rupees(row["invoices"]["tax_paise"]), Rupees(row["invoices"]["total_paise"]),
            row["credit_notes"]["count"], Rupees(row["credit_notes"]["base_paise"]),
            Rupees(row["credit_notes"]["tax_paise"]), Rupees(row["credit_notes"]["total_paise"]),
            Rupees(row["net"]["base_paise"]), Rupees(row["net"]["tax_paise"]),
            Rupees(row["net"]["total_paise"])]


def month_workbook(view: dict) -> bytes:
    """The three sheets as one .xlsx. A month with nothing in it still has all three, with their headers.

    A zero-sale month is a real month and an empty file is a real answer to it: a workbook that was not
    written, or one sheet short, reads as a failed export rather than as a quiet month, and somebody then
    spends an evening finding out which it was.
    """
    invoices = Sheet(INVOICES_SHEET, [[Bold(head) for head in INVOICE_HEADER]]
                     + [_invoice_row(document) for document in view["invoices"]], widths=INVOICE_WIDTHS)
    notes = Sheet(CREDIT_NOTES_SHEET, [[Bold(head) for head in CREDIT_NOTE_HEADER]]
                  + [_credit_note_row(document) for document in view["credit_notes"]],
                  widths=CREDIT_NOTE_WIDTHS)
    return workbook([invoices, notes, summary_sheet(view)])


def workbook_name(view: dict) -> str:
    return f"accounts-{view['key']}.xlsx"


# ---- the ZIP -----------------------------------------------------------------------------------------


def _render_html(document: Document) -> str | None:
    """The document itself, print-ready, from the module that OWNS it - never re-templated here.

    `for_print=True` is the copy with the bundled font faces, which is what app/pdf must have: headless
    Chromium has no system font for Devanagari and refuses to print a page with no loaded face.
    """
    if document.kind == "invoice":
        return invoice.render(document.order, for_print=True)
    return credit_note.render(document.order, document.refund or {}, for_print=True)


#: How long one document may queue for a render slot before the archive takes its HTML instead.
#:
#: BOUNDED, AND NOT `wait=True`. app/pdf/browser.py allows `PDF_MAX_CONCURRENT` renders on the whole
#: machine and an unbounded waiter parks a FastAPI threadpool thread for as long as it queues - the module
#: says so, and threadpool starvation takes every route on the site down, not only the PDF ones. This is a
#: sync route, so the operator's month-end download is one of those waiters. A minute is many times the
#: measured render of a one-page document and still a bound; past it the HTML goes into the archive and
#: README.txt names it, which is a slower reader rather than a missing record.
PDF_WAIT_SECONDS = 60


def _default_pdf(html: str) -> bytes:
    from app.pdf.service import ensure_document_pdf

    return ensure_document_pdf(html, wait=PDF_WAIT_SECONDS).read_bytes()


def month_zip(view: dict, *, render_pdf=None) -> tuple[bytes, dict]:
    """(the ZIP, what went into it) - one spreadsheet, one README and every document of the month.

    `render_pdf(html) -> bytes` is the injection point, for the same reason app/admin/alerts.py's delivery
    is one: it runs Chromium, and a test that proves this archive is built must not need a browser.

    A DOCUMENT THAT WILL NOT PRINT IS STILL IN THE ARCHIVE, as the HTML it is rendered from. Chromium can
    be absent, busy (`PdfBusy` - app/pdf/browser.py bounds concurrent renders machine-wide) or broken, and
    none of those are a reason for a month's records to be short a document: the HTML is the source the PDF
    is printed from, it is what the customer was linked to, and it opens in any browser. README.txt names
    every one that fell back, so the gap is stated rather than discovered.
    """
    import io
    import zipfile

    from app.pdf.service import document_download_name

    render_pdf = render_pdf or _default_pdf
    folders = {"invoice": "invoices", "credit-note": "credit-notes"}
    written, fallbacks, failed = [], [], []
    buffer = io.BytesIO()
    seen_members: set[str] = set()
    collisions: list[str] = []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for document in (*view["invoices"], *view["credit_notes"]):
            html = _render_html(document)
            if html is None:
                # The document module declined to render it (see its `context`): there is nothing to put in
                # the archive, and inventing a placeholder would be worse than a named absence.
                log.error("%s %s could not be rendered for the %s export", document.kind, document.number,
                          view["key"])
                failed.append(document.number)
                continue
            name = document_download_name(document.kind, document.number)
            at = dt.datetime.fromtimestamp(document.at, IST)
            try:
                body = render_pdf(html)
            except Exception as exc:  # noqa: BLE001 - see the docstring: never lose a record over a browser
                log.warning("%s %s: no PDF (%s: %s) - the HTML goes into the archive instead",
                            document.kind, document.number, type(exc).__name__, exc)
                fallbacks.append(name)
                body, name = html.encode("utf-8"), f"{name.removesuffix('.pdf')}.html"
            # The document's own issue date as the member's timestamp, so an extracted folder sorts by when
            # each document was issued. Clamped to 1980 because that is the earliest a ZIP can express and
            # an older date RAISES - which on a hand-written row with no timestamp would take the whole
            # month's export down over one member's metadata.
            stamp = (max(1980, at.year), at.month, at.day, at.hour, at.minute, at.second)
            member = f"{folders[document.kind]}/{name}"
            # TWO DOCUMENTS CANNOT SHARE A MEMBER NAME. A member name is the invoice number, so a series
            # that has repeated one - which must never happen, and did on a developer's database - wrote
            # the same path twice. A ZIP permits that; every tool that reads one shows the last and
            # discards the other, so an invoice would vanish from an archive whose entire promise is that
            # none ever does. The order id disambiguates, and the README names the collision, so the
            # bookkeeping fault is visible rather than absorbed.
            if member in seen_members:
                collisions.append(f"{member} (also {document.order_id})")
                member = (f"{folders[document.kind]}/{name.removesuffix('.pdf').removesuffix('.html')}"
                          f"--{document.order_id}{'.html' if name.endswith('.html') else '.pdf'}")
            seen_members.add(member)
            info = zipfile.ZipInfo(member, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, body)
            written.append(member)
        archive.writestr(workbook_name(view), month_workbook(view))
        archive.writestr("README.txt", _readme(view, written, fallbacks, failed, collisions))
    return buffer.getvalue(), {"written": written, "html_instead_of_pdf": fallbacks, "not_rendered": failed}


def zip_name(view: dict) -> str:
    return f"accounts-{view['key']}.zip"


def _readme(view: dict, written: list[str], fallbacks: list[str], failed: list[str],
            collisions: list[str] | None = None) -> bytes:
    """What is in the archive and what the figures mean, in the archive.

    Here for the same reason app/admin/routes.py writes a `#` comment line into every CSV: this file is
    opened by somebody else, months later, and a column they have to guess at is a column they will guess
    wrong. The internal flag and the "not classified" column are both stated, because both look like
    mistakes to a reader who has not been told why they are there.
    """
    from app.web import site

    lines = [
        f"{site.SITE_NAME} - GST records for {view['label']} (all dates IST)",
        f"Generated {view['generated_at']:%Y-%m-%d %H:%M} IST. {site.LEGAL_ENTITY}, GSTIN {site.GSTIN}.",
        "",
        f"{workbook_name(view)}   invoices, credit notes and the totals by tax head, state and product",
        *( ["",
            "DUPLICATE INVOICE NUMBERS IN THIS MONTH - a tax series must never repeat one, and two",
            "documents under one number cannot both be filed. The second of each pair is saved with its",
            "order id appended so neither is lost; the underlying records still need fixing:",
            *(f"  {line}" for line in (collisions or [])),
           ] if collisions else [] ),
        f"invoices/            {view['totals']['invoices']['count']} tax invoice(s) issued this month",
        f"credit-notes/        {view['totals']['credit_notes']['count']} credit note(s) issued this month",
        "",
        "EVERY ISSUED INVOICE IS HERE. Orders that are ours rather than a customer's (the proprietor's own",
        "purchase, a test-mode rehearsal) are INCLUDED and marked in the spreadsheet's Internal column.",
        "An invoice number comes out of one gap-free consecutive series, so a document left out would show",
        "up as a hole in that series; the dashboard's revenue figures exclude those orders, a GST return",
        "does not, and the column is how both can be true.",
        "",
        "A credit note is filed in the month it was ISSUED, which can be a later month than its invoice.",
        "The Summary therefore carries invoices, credit notes and the net of the two, never one netted",
        "column. 'Tax not classified' is tax that was collected on an order with no recorded place of",
        "supply: it is real tax that cannot be put under CGST/SGST or IGST, and it is a column rather than",
        "a silent omission so that no total loses it.",
    ]
    if fallbacks:
        lines += ["", "NO PDF FOR THESE - the print-ready HTML is in the archive instead (same document,",
                  "same content; the PDF renderer was unavailable or busy):"] + [f"  {n}" for n in fallbacks]
    if failed:
        lines += ["", "NOT IN THIS ARCHIVE AT ALL - these documents could not be rendered. Report this:"] \
                 + [f"  {n}" for n in failed]
    if view["unreadable"] or view["orphans"]:
        lines += ["", f"{view['unreadable']} order(s) carry an invoice number with no recorded GST split and "
                      f"{view['orphans']} credit note(s) reference an order that is not in the database. "
                      f"Both are data repairs, not gaps in the month."]
    lines += ["", f"{len(written)} document file(s) in this archive."]
    return ("\n".join(lines) + "\n").encode("utf-8")


# ---- the page ----------------------------------------------------------------------------------------


def month_page(view: dict) -> dict:
    """What the HTML page shows, which is deliberately LESS than the download.

    NO CUSTOMER NAME AND NO FULL E-MAIL ADDRESS. The spreadsheet needs both - a tax invoice is issued to a
    named buyer - but a browser page does not, and app/admin's rule is that the only page with a full
    address on it is the single-order page, which is audited before it renders. So the page carries the
    figures and masked addresses, the ZIP carries the records, and taking the ZIP is what gets audited.
    """
    return {
        **{key: view[key] for key in ("key", "label", "totals", "by_state", "by_product", "unreadable",
                                      "orphans", "internal_invoices", "internal_credit_notes",
                                      "generated_at")},
        "invoices": [_page_row(document) for document in view["invoices"]],
        "credit_notes": [_page_row(document) for document in view["credit_notes"]],
    }


def _page_row(document: Document) -> dict:
    return {
        "number": document.number,
        "when": metrics.to_ist(document.at),
        "order_id": document.order_id,
        "state_code": document.state_code,
        "state_name": document.state_name,
        "product": document.product,
        "email": metrics.mask_email(document.email),
        "base_inr": document.base_paise / 100,
        "cgst_inr": document.cgst_paise / 100,
        "sgst_inr": document.sgst_paise / 100,
        "igst_inr": document.igst_paise / 100,
        "unclassified_inr": document.unclassified_paise / 100,
        "total_inr": document.total_paise / 100,
        "status": document.status,
        "reference": document.reference,
        "internal": document.internal,
        "internal_reason": document.internal_reason,
    }


# ---- the monthly e-mail ------------------------------------------------------------------------------


def page_url(first: dt.date) -> str:
    from app.web import site

    return f"{site.base_url().rstrip('/')}/admin/accounting?month={month_key(first)}"


def compose(first: dt.date, view: dict | None = None) -> tuple[str, str, dict]:
    """(subject, body, the figures) for one month's "accounts ready" message.

    NO ATTACHMENT, and a link instead. The spreadsheet names every customer of the month and what they
    bought; mail is not a place that data should sit, and the page behind the link needs a sign-in, which
    an e-mailed file does not. The subject carries the two numbers worth reading on a phone - how many
    invoices, and what was charged - so the message does not have to be opened to be useful.
    """
    from app.web import site

    view = view or month_view(first)
    issued = view["totals"]["invoices"]
    credited = view["totals"]["credit_notes"]
    gross_inr = issued["total_paise"] / 100
    subject = f"{view['label']} accounts ready: {issued['count']} invoices, Rs {gross_inr:,.0f}"
    lines = [
        f"{site.SITE_NAME} - {view['label']} (IST)",
        "",
        f"Invoices issued    {issued['count']}",
        f"Charged            Rs {gross_inr:,.2f}  (taxable Rs {issued['base_paise'] / 100:,.2f} "
        f"+ tax Rs {issued['tax_paise'] / 100:,.2f})",
        f"Credit notes       {credited['count']}"
        + ("" if not credited["count"] else f", Rs {credited['total_paise'] / 100:,.2f} credited back"),
        f"Net of both        Rs {view['totals']['net']['total_paise'] / 100:,.2f}  "
        f"(taxable Rs {view['totals']['net']['base_paise'] / 100:,.2f})",
        f"CGST / SGST / IGST Rs {issued['cgst_paise'] / 100:,.2f} / "
        f"Rs {issued['sgst_paise'] / 100:,.2f} / Rs {issued['igst_paise'] / 100:,.2f}",
    ]
    if issued["unclassified_paise"]:
        lines.append(f"Not classified     Rs {issued['unclassified_paise'] / 100:,.2f} of tax on order(s) "
                     f"with no recorded place of supply")
    if view["internal_invoices"] or view["internal_credit_notes"]:
        lines.append(f"Internal           {view['internal_invoices']} invoice(s) and "
                     f"{view['internal_credit_notes']} credit note(s) are ours, not a customer's. They are "
                     f"IN these figures and flagged in the sheet: an issued invoice is a GST record.")
    lines += [
        "",
        "The month's page has the invoices, the credit notes and the totals by tax head, by state and by",
        "product, and a Download month button that gives you one ZIP: every document as a PDF plus the",
        "spreadsheet. Nothing is attached to this message and the page needs you to be signed in.",
        "",
        page_url(first),
    ]
    figures = {"month": month_key(first), "invoices": issued["count"],
               "charged_inr": gross_inr, "credit_notes": credited["count"],
               "net_inr": view["totals"]["net"]["total_paise"] / 100}
    return subject, "\n".join(lines), figures


def email_delivery(subject: str, body: str) -> bool:
    """The default: one plain-text message to each address in ADMIN_EMAILS, through app/mailer.py.

    ADMIN_EMAILS and not `ALERT_EMAIL_TO`: this is the owner's own month-end paperwork and the allowlist is
    who is allowed to open the page the message links to, so a recipient who could not use the link cannot
    be on the list by construction.

    True when at least one address was accepted, and the accepted ones are not re-sent: a second attempt
    would put a duplicate in the inbox that worked in order to retry the one that did not. A refusal is
    logged by app/mailer.py with the address masked, and the alerts already raise `email_refused` on it.
    """
    from app import mailer
    from app.web import site

    if not site.ADMIN_EMAILS:
        log.warning("month-end accounting e-mail not sent: ADMIN_EMAILS is empty")
        return False
    accepted = [address for address in site.ADMIN_EMAILS if mailer.send(address, subject, body)]
    if len(accepted) != len(site.ADMIN_EMAILS):
        log.warning("month-end accounting e-mail: %d of %d address(es) accepted it",
                    len(accepted), len(site.ADMIN_EMAILS))
    return bool(accepted)


def send_month_email(first: dt.date | None = None, now: dt.datetime | None = None, deliver=None) -> bool:
    """Send one month's message, at most once per month. True if it went.

    Deduplicated in `admin_alerts_sent` through app/admin/alerts.py's own helpers rather than a second
    table or a second sliding window: one table, one implementation, and a cron line that fires twice (or a
    retry after a timeout) cannot send twice. `alerts.send_digest` does exactly this for the daily digest.
    """
    from . import alerts

    moment = now or metrics.now_ist()
    first = first or due_month(moment)

    # A MONTH THAT HAS NOT ENDED IS NEVER SENT, and the cost of getting this wrong is not a wrong
    # e-mail - it is a MISSING one. The send is deduplicated per month, so a figure mailed on the 30th
    # would mark that month done and the real message on the 1st would never go. The partial figures
    # would be the only ones anybody ever received, and nothing would look broken.
    #
    # `--email --month <this month>` is the way in; the timer itself cannot reach here early, because
    # due_month() reports the month containing YESTERDAY, so a run on the 30th asks for the month that
    # genuinely ended. The guard is on the send rather than on the command, so every caller gets it.
    #
    # Printing and --dry-run are untouched: inspecting a month in progress is the useful thing to do.
    if first >= due_month(moment) + dt.timedelta(days=1):
        log.error("refusing to send the %s accounting e-mail: that month has not ended. Sending it now "
                  "would mark the month done and the real message would never go.", month_key(first))
        return False

    view = month_view(first)
    subject, body, _ = compose(first, view)
    marker = alerts.Alert(ALERT_KEY, month_key(first), subject, body)
    stamp = moment.timestamp()
    # Private, deliberately: the dedupe table belongs to app/admin/alerts.py and has one reader and one
    # writer. app/admin/auth.py reaches into app/ai/chat_identity for its secret for the same reason - a
    # second copy of the logic is a second thing that can disagree.
    if alerts._already_sent(marker, stamp):  # noqa: SLF001
        log.info("the %s accounting e-mail has already been sent", month_key(first))
        return False
    ok = bool((deliver or email_delivery)(subject, body))
    if ok:
        alerts._mark_sent(marker, stamp)  # noqa: SLF001
    return ok


# ---- the cron entry point ----------------------------------------------------------------------------


def main(argv=None) -> int:
    """`.venv/bin/python -m app.admin.accounting [--month YYYY-MM] [--email] [--dry-run] [--zip PATH]`.

    The module docstring has the crontab line. With no argument it PRINTS the month's totals, which is the
    thing to run when a figure is being questioned; `--email` is what cron runs; `--zip` writes the archive
    to a file, for the month a browser download is not the way it is being collected.
    """
    import argparse

    from app.ai import config as _config  # noqa: F401  (loads .env)

    parser = argparse.ArgumentParser(description="RashiKundli month-end GST records")
    parser.add_argument("--month", default="", help="YYYY-MM (default: the month that just ended)")
    parser.add_argument("--email", action="store_true", help="send the month's 'accounts ready' message")
    parser.add_argument("--dry-run", action="store_true", help="print what would be sent; send nothing")
    parser.add_argument("--zip", default="", help="write the month's ZIP to this path")
    args = parser.parse_args(argv)

    first = parse_month(args.month) if args.month else due_month()
    view = month_view(first)
    issued, credited = view["totals"]["invoices"], view["totals"]["credit_notes"]

    if args.email:
        if args.dry_run:
            # Printed, never recorded as sent: a dry run that marked the month done would silence the real
            # message. Same rule as `python -m app.admin.alerts --dry-run`.
            subject, body, _ = compose(first, view)
            print(f"--- would send ---\n{subject}\n\n{body}")
            return 0
        print("sent" if send_month_email(first) else
              "NOT sent (already sent for this month, ADMIN_EMAILS is empty, or the mailer is off)")
        return 0

    print(f"{view['label']}: {issued['count']} invoice(s), {credited['count']} credit note(s)")
    for name, block in (("invoices", issued), ("credit notes", credited), ("net", view["totals"]["net"])):
        print(f"  {name:13s} taxable Rs {block['base_paise'] / 100:>12,.2f}   "
              f"tax Rs {block['tax_paise'] / 100:>10,.2f}   total Rs {block['total_paise'] / 100:>12,.2f}")
    if view["internal_invoices"] or view["internal_credit_notes"]:
        print(f"  {view['internal_invoices']} invoice(s) and {view['internal_credit_notes']} credit note(s) "
              f"are internal - INCLUDED above and flagged in the sheet")
    if view["unreadable"] or view["orphans"]:
        print(f"  LEFT OUT: {view['unreadable']} invoice number(s) with no GST split, "
              f"{view['orphans']} credit note(s) with no order")
    if args.zip:
        from pathlib import Path

        body, notes = month_zip(view)
        path = Path(args.zip)
        path.write_bytes(body)
        print(f"  wrote {path} ({len(body):,} bytes, {len(notes['written'])} document file(s))")
        if notes["html_instead_of_pdf"]:
            print(f"  NO PDF for {len(notes['html_instead_of_pdf'])} document(s); the HTML is in the archive")
    return 0


def record_download(actor: str, view: dict, request=None) -> None:
    """Audit one month's download. The archive carries customer names and full addresses, so it is an
    export in exactly the sense app/admin/audit.py means - the files leave the building."""
    audit.record(actor, audit.EXPORT, zip_name(view),
                 f"{view['totals']['invoices']['count']} invoice(s), "
                 f"{view['totals']['credit_notes']['count']} credit note(s)", request)


if __name__ == "__main__":
    raise SystemExit(main())
