"""The GST tax invoice for one paid order: its number series, and everything the document prints.

WHY HTML AND NOT PDF. The obvious move was app/pdf/, which already renders documents with Chromium - and
the reason not to is written in 37e5e62: Chromium's PDF text layer is lossy for Devanagari because it
writes ToUnicode by reverse cmap lookup and shaped glyphs have no reverse entry. An invoice is the one
document on this site whose entire value is that its text can be COPIED - a number read off it into a GST
return, a figure pasted into an accountant's sheet, a buyer's Ctrl-F for the invoice number. The product
names on it are Devanagari (`order_page.PRODUCT_NAMES`), so a PDF invoice would ship with exactly the
defect that decision was taken to stop needing to fix.

Three more things pushed the same way, in order of weight:

  - the PDF path needs a browser. `app/pdf/browser.py` raises `PdfBusy` under load and the book render is
    minutes of Chromium; an invoice must be there the instant it is asked for, on a page the customer is
    already looking at. HTML is a template render with no subprocess at all.
  - print-to-PDF is one keystroke in every browser, and this template carries an `@media print` block so
    that keystroke produces the document rather than a web page with navigation round it. The customer who
    wants a file gets a file; the one who wants to read it does not pay for a render.
  - the PDF path's stylesheet is A5/A4 with ~40 @page rules for a book. An invoice is one page of a table
    and would have needed its own stylesheet either way, so "reuse the PDF pipeline" was reuse of the
    subprocess, not of the design.

The document is ENGLISH ONLY, like every other legal page on this site (/terms, /privacy, /refund-policy
are English by decision). The link TO it on the order page is in the order's language, because that is a
label on a page the customer is reading; the invoice itself is a document for a tax authority and an
accountant, and one authoritative wording is worth more there than three.

THE NUMBER SERIES. Rule 46(b) wants a consecutive serial number, unique within a financial year, at most
16 characters, from alphanumerics plus "-" and "/". This series is `RK/2627/00001`: prefix, the Indian
financial year (1 April - 31 March) as two two-digit years, and a zero-padded counter that restarts each
year. Thirteen characters, three under the limit, with room for the counter to reach 99999.

The number is allocated ONCE, at payment, inside the same SQLite transaction that bumps the counter (see
`store.assign_invoice_number`) - not when an invoice is first viewed. Viewing order is not payment order:
allocating lazily would number a sale from Monday after a sale from Friday because Monday's buyer opened
their invoice first, and "consecutive" in a series that a return is reconciled against means consecutive
in the thing being numbered. Once written it is never recomputed, so a change to the format below cannot
renumber an invoice that has already been sent to somebody.
"""

import datetime as dt
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.web import site

from . import gst, states, store
from .order_page import PRODUCT_NAMES

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# A package-local template directory and a plain environment, like app/pdf: the document is standalone and
# must not inherit the site layout, so it has no business in the web templates the pages extend. Autoescaped,
# because a product name and a buyer's e-mail arrive from a form and end up inside a document we sign our
# GSTIN to.
_env = Environment(loader=FileSystemLoader(Path(__file__).resolve().parent / "templates"),
                   autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)

# Rule 46(b): at most 16 characters, and only alphanumerics, "-" and "/". Asserted on every allocation
# rather than trusted, because the failure is silent - an over-long number is a valid string and an
# invalid invoice, and nobody finds out until the number is on a document somebody else has.
MAX_NUMBER_LENGTH = 16
NUMBER_TEMPLATE = "{prefix}/{series}/{n:05d}"

# SAC 998439, "other on-line contents n.e.c.", under heading 9984 (telecommunications, broadcasting and
# information supply services): an AI-written astrology report delivered as a download is online
# information supplied electronically, not a consultancy service rendered in person. Env-overridable
# because a classification is the operator's call and his accountant's, not this file's.
DEFAULT_SAC = "998439"
DEFAULT_PREFIX = "RK"


def sac_code() -> str:
    return os.getenv("INVOICE_SAC", "").strip() or DEFAULT_SAC


def prefix() -> str:
    return os.getenv("INVOICE_PREFIX", "").strip() or DEFAULT_PREFIX


def financial_year(moment: dt.datetime) -> tuple[int, int]:
    """The Indian financial year containing `moment`: 1 April to 31 March, as (start year, end year)."""
    start = moment.year if moment.month >= 4 else moment.year - 1
    return start, start + 1


def series_for(paid_at: float) -> str:
    """The series key of a payment timestamp: "2627" for a sale between 1 Apr 2026 and 31 Mar 2027.

    IST, not UTC. A sale at 03:00 IST on 1 April is in the new financial year; read in UTC it is 21:30 on
    31 March and lands in the old one, which is the wrong return."""
    start, end = financial_year(dt.datetime.fromtimestamp(paid_at, IST))
    return f"{start % 100:02d}{end % 100:02d}"


def assign(order: dict) -> str | None:
    """Give a newly paid order its invoice number. Idempotent; returns the number the order now carries.

    None when the order has no GST recorded: an order paid before the GST columns existed has no tax to
    invoice, and issuing it a number would put a gap-free series behind a document that cannot state a
    rate. Those sales are invoiced by hand if anyone asks, which is what happened before this file existed.
    """
    if order.get("status") != "paid" or gst.recorded(order) is None:
        return None
    series = series_for(order.get("paid_at") or dt.datetime.now(tz=IST).timestamp())
    return store.assign_invoice_number(order["id"], series, prefix(), NUMBER_TEMPLATE, MAX_NUMBER_LENGTH)


def _product_name(order: dict) -> str:
    """The product as the BUYER saw it, in the language they bought in - the one place this English-only
    document speaks another language, because an invoice line has to match what was on the page."""
    names = PRODUCT_NAMES.get(order["product"], {})
    lang = order.get("language") if order.get("language") in names else "en"
    return (names.get(lang) or order["product"]).replace("{n}", str(order.get("messages") or 0))


def context(order: dict) -> dict | None:
    """Everything templates/invoice.html prints, or None when this order cannot be invoiced.

    Cannot be invoiced means: not paid, no GST recorded (pre-GST sale), or no number allocated. All three
    are the same answer to the customer - there is no tax invoice for this order - and the order page
    simply does not offer the link, rather than offering one that renders an incomplete document.
    """
    amounts = gst.recorded(order)
    if order.get("status") != "paid" or amounts is None or not order.get("invoice_no"):
        return None
    paid = dt.datetime.fromtimestamp(order["paid_at"], IST)
    # The place of supply, and therefore which heads the tax is filed under. Intra-state is CGST+SGST, anywhere
    # else is IGST, and THE TOTAL IS THE SAME EITHER WAY - this changes how the tax is described, never how much
    # of it there is. An order with no recorded state (anything sold before the checkout asked) gets neither a
    # split nor an invented state: it keeps the single composite line and says the place of supply is not known.
    supply = order.get("place_of_supply")
    known = states.is_known(supply)
    # An export is described, not classified: it has a place of supply ("Outside India") and no tax head at all.
    # Read from `states.is_export`, which does not consult the flag - this document is frozen, and an order taken
    # while exports were on must keep reading as an export after they are switched off again.
    export = states.is_export(supply)
    return {
        "number": order["invoice_no"],
        "date": f"{paid:%d %B %Y}",
        # A refund does not alter this document. The invoice records what was charged, and it was; a reversal
        # is a CREDIT NOTE with its own consecutive series (app/payments/credit_note.py), and since 2026-09-29
        # those are issued automatically. The refund is still stated here, and the notes are NAMED: an invoice
        # that says nothing about a refund asserts by omission that the money was kept, and one that mentions a
        # reversal without naming the document that made it leaves the reader to go and look for it.
        "credit_notes": [row["credit_no"] for row in store.refunds_for(order["id"]) if row.get("credit_no")],
        "refund": None if not order.get("refunded_paise") else {
            "state": order.get("refund_state"),
            "amount": gst.money(order.get("refunded_paise")),
            "id": order.get("refund_id"),
            "on": "" if not order.get("refunded_at") else
                  f"{dt.datetime.fromtimestamp(float(order['refunded_at']), IST):%d %B %Y}",
        },
        "seller": {"name": site.LEGAL_ENTITY, "address": site.LEGAL_ADDRESS, "gstin": site.GSTIN,
                   "email": site.SUPPORT_EMAIL, "site": site.SITE_NAME},
        # The buyer's e-mail is all we hold. It is not a billing address and this document does not pretend
        # it is one: the row is labelled "Billed to (e-mail)" so nobody reads a blank address as an omission.
        "buyer_email": (order.get("email") or "").strip(),
        "buyer_name": (order.get("names") or {}).get("self", "").strip(),
        "line": {"description": _product_name(order), "sac": sac_code(),
                 "base": gst.money(amounts.base_paise), "gst": gst.money(amounts.gst_paise),
                 "total": gst.money(amounts.total_paise), "rate": amounts.rate_text},
        # English on this document, like the rest of it, plus the code - the code is what a return is filed
        # against and what makes the row unambiguous whatever language the buyer read the site in.
        "place_of_supply": f"{states.name(supply, 'en')} ({supply})" if known or export else "",
        "intra_state": states.is_intra_state(supply),
        # A zero-rated export of service. The template prints THIS instead of a CGST/SGST or IGST split, because
        # there is no split: the tax is nil and the reason it is nil is the LUT, which is the one thing on the
        # document an assessing officer needs to see. `gst.EXPORT_TREATMENT` is the single spelling of it.
        "export": export,
        "treatment": gst.EXPORT_TREATMENT if export else "",
        # ((name, rate, amount), ...): CGST+SGST, or IGST, or empty when there is no state to classify by.
        "heads": [{"name": head.name, "rate": head.rate_text, "amount": gst.money(head.paise)}
                  for head in (gst.heads(amounts, states.is_intra_state(supply)) if known else ())],
        # Which way round the price was quoted, so the document can SAY so. The figures are identical either
        # way (base + gst == total), but the sentence describing them is not, and a tax invoice asserting that
        # tax "was added" to a price that already contained it is a false statement on a legal document. The
        # stored rate tells us the rate; only the mode tells us the direction, and it is read from the setting
        # because an order paid under one mode is never reprinted under the other - the figures are frozen.
        "inclusive": gst.get_settings().inclusive,
        "reference": order["razorpay_order_id"],
        "payment_id": order.get("payment_id") or "",
        "currency": order["currency"],
    }


def print_css():
    """The bundled @font-face rules, for the copy of a document that is going to be printed to PDF.

    `Markup`, because this environment autoescapes - the document carries a buyer's e-mail and a product name
    from a form, and that must stay true. Without it the quotes in the CSS become &#34; and Chromium sees no
    valid @font-face rule at all, which app/pdf/browser.py then refuses to print: the same way app/pdf/render.py
    hands its stylesheet to its template."""
    from markupsafe import Markup

    from app.pdf.service import document_font_css

    return Markup(document_font_css())


def render(order: dict, *, for_print: bool = False) -> str | None:
    """The invoice as a complete HTML document, or None when this order has no invoice (see `context`).

    `for_print` adds the bundled font faces, and nothing else. The two copies are the same document - one is
    served over HTTP and read, the other is printed to a file - and keeping them one template is what stops
    the file a customer forwards to an accountant differing from the page they read it on.
    """
    data = context(order)
    if not data:
        return None
    return _env.get_template("invoice.html").render(**data, print_css=print_css() if for_print else "")
