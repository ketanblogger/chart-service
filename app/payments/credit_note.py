"""The GST credit note for a refund: its own number series, and everything the document prints.

WHY A CREDIT NOTE AND NOT A CORRECTED INVOICE. The invoice records what was charged, and it was. A refund
reverses part or all of that supply, and section 34 of the CGST Act deals with it as a SEPARATE document -
its own consecutive series, issued by the supplier, reducing the taxable value and the tax proportionally,
naming the invoice it relates to. Editing the invoice would change a document somebody already has, and the
return it was reported in has already been filed.

ONE NOTE PER REFUND, not per order. Razorpay allows several partial refunds against one payment and retries
every webhook delivery, so the refund id is the unit that is unique, dated and idempotent - and a credit note
has to state one amount on one date. Several credit notes against one invoice is ordinary.

THE SPLIT. The refunded amount is money that went back to a card, so it is always a GROSS figure, whichever
way the price was quoted: under inclusive pricing the charge WAS the total, and under exclusive pricing the
charge was base + tax. So the gross is split back out at the rate the invoice carries, never at today's
setting - `gst.split` with `inclusive=True` and the ORDER'S OWN `rate_bp`.

Several partial refunds are credited against the RUNNING TOTAL rather than each on its own, and the
difference matters. Two refunds of ₹28.80 on a ₹59.00 order split independently give bases of 2441 + 2441 =
4882 paise, while the invoice's taxable value is 5000 - and a fully refunded invoice whose credit notes do not
add back to it is a reconciliation somebody has to explain. Credited against the running total, note two
states exactly what is left: `split(cumulative).base - already_credited`. Same discipline as `gst.heads`,
where CGST is computed and SGST is what remains: round one figure, make the rest a difference.

THE NUMBER SERIES is `RK-CN/2627/00001` - prefix, `-CN` so it can never be mistaken for an invoice number,
the Indian financial year, and a counter that restarts each year. Sixteen characters exactly, which is the
limit Rule 46(b) sets for an invoice number and the limit this follows: a credit note carries a reference to
the invoice, and a number that does not fit the same field is a number somebody has to shorten by hand. The
`-CN` is why the counter is padded to five digits and not six.

The document is ENGLISH ONLY and rendered by the same template environment as the invoice, for the reasons in
app/payments/invoice.py: it is a document for a tax authority and an accountant, and one authoritative
wording is worth more there than three.
"""

import datetime as dt
import os

from app.web import site

from . import gst, invoice, states, store

IST = invoice.IST

# "RK-CN/2627/00001" is 16 characters, exactly the limit. Asserted on every allocation by
# `store.assign_credit_note` rather than trusted, because an over-long number is a valid string and an
# invalid document, and nobody finds out until it is on a note somebody else is holding.
MAX_NUMBER_LENGTH = 16
NUMBER_TEMPLATE = "{prefix}-CN/{series}/{n:05d}"
# A series key of its own, so credit notes are consecutive among THEMSELVES. Sharing the invoice counter
# would make both series full of holes, and "consecutive" is the whole property being claimed.
SERIES_PREFIX = "CN"


def prefix() -> str:
    """Same prefix as the invoice: one business, one mark. Overridable for the same reason."""
    return os.getenv("INVOICE_PREFIX", "").strip() or invoice.DEFAULT_PREFIX


def counter_for(at: float) -> str:
    """The COUNTER this note is numbered in: "CN2627" for a refund between 1 Apr 2026 and 31 Mar 2027, IST.

    Not the same string as the financial year printed on the document. The counter has to be its own row in
    `invoice_numbers` or credit notes and invoices would share one sequence and both would have holes in it;
    the printed number says "-CN" already, so repeating it as "RK-CN/CN2627/00001" would be both a stutter and
    18 characters against a 16-character limit."""
    return SERIES_PREFIX + invoice.series_for(at)


def credited(order: dict, refund_paise: int, cumulative_refunded: int,
             already_credited_base: int) -> gst.Amounts | None:
    """Split one refund into taxable value and tax at the rate the ORDER was charged at.

    `cumulative_refunded` is everything refunded on this order UP TO AND INCLUDING this refund, and
    `already_credited_base` the taxable value the earlier notes credited. The returned `base_paise` is what is
    left once those are accounted for, so the notes on a fully refunded invoice add back to exactly the
    invoiced taxable value - two refunds of half a Rs 299 order split independently credit 12669 + 12669 =
    25338 against an invoiced 25339, and an invoice whose credit notes do not add back to it is a
    reconciliation somebody has to explain. Same discipline as `gst.heads`: round one figure, make the rest a
    difference.

    The cumulative figure is passed IN rather than read from `order["refunded_paise"]`, and that is not a
    style choice. The order's field is the total refunded NOW, which equals the cumulative only when notes are
    issued as the refunds arrive. Backfilling an old refund after a newer one had already been recorded would
    then split the newer total across the older note and produce a negative tax figure - which is what it did.

    Returns None when the order carries no recorded GST (a sale from before the GST columns existed has no tax
    to reverse, and a note claiming to reduce a tax that was never recorded would be a false statement), or
    when the arithmetic does not come out - more refunded than charged is a bookkeeping error upstream, and
    guessing a split for it would put the guess on a tax document.
    """
    invoiced = gst.recorded(order)
    if invoiced is None or refund_paise <= 0:
        return None
    if cumulative_refunded <= 0 or cumulative_refunded > invoiced.total_paise:
        return None
    settings = gst.GstSettings(rate_bp=invoiced.rate_bp, inclusive=True)
    running = gst.split(cumulative_refunded, settings)
    base = running.base_paise - already_credited_base
    gst_paise = refund_paise - base
    if base < 0 or gst_paise < 0:
        return None
    return gst.Amounts(base_paise=base, gst_paise=gst_paise, total_paise=refund_paise,
                       rate_bp=invoiced.rate_bp)


def issue(order: dict, refund_id: str) -> str | None:
    """Give a processed refund its credit note number and freeze its split. Idempotent.

    Refunds are numbered in the order they happened, which is the order `store.refunds_for` returns, so this
    refuses to issue a note while an EARLIER refund on the same order still has none: the split of this one is
    defined against what the earlier notes already credited, and skipping one would make this note too large
    and leave the series in an order nothing explains. `scripts/issue_credit_notes.py` backfills oldest first
    for that reason.

    None when there is nothing to issue: no such refund, an order with no invoice (there is nothing for a note
    to reference), no recorded GST, or the case above. All of them mean the same thing to the customer - this
    refund has no credit note - and the order page then offers no link rather than a link to an incomplete
    document.
    """
    rows = store.refunds_for(order.get("id") or "")
    position = next((i for i, row in enumerate(rows) if row["refund_id"] == refund_id), None)
    if position is None:
        return None
    this = rows[position]
    if this.get("credit_no"):
        return this["credit_no"]
    if not order.get("invoice_no"):
        return None
    earlier = rows[:position]
    if any(not row.get("credit_no") for row in earlier):
        return None
    cumulative = sum(int(row.get("amount_paise") or 0) for row in rows[:position + 1])
    already = sum(int(row.get("base_paise") or 0) for row in earlier)
    amounts = credited(order, int(this.get("amount_paise") or 0), cumulative, already)
    if amounts is None:
        return None
    at = float(this.get("at") or dt.datetime.now(tz=IST).timestamp())
    return store.assign_credit_note(
        refund_id, counter_for(at), invoice.series_for(at), prefix(), NUMBER_TEMPLATE, MAX_NUMBER_LENGTH,
        base_paise=amounts.base_paise, gst_paise=amounts.gst_paise, rate_bp=amounts.rate_bp,
        invoice_no=order["invoice_no"], issued_at=at)


def context(order: dict, refund: dict) -> dict | None:
    """Everything templates/credit_note.html prints, or None when this refund has no credit note.

    Read entirely from the FROZEN columns on the refund row - the number, the split and the rate as they were
    when the note was issued - and never recomputed from today's setting. A reprint of a credit note must be
    the same document it was the first time, or it is not a credit note.
    """
    if not refund.get("credit_no") or refund.get("base_paise") is None:
        return None
    amounts = gst.Amounts(base_paise=int(refund["base_paise"]), gst_paise=int(refund["gst_paise"]),
                          total_paise=int(refund["base_paise"]) + int(refund["gst_paise"]),
                          rate_bp=int(refund.get("rate_bp") or 0))
    issued = dt.datetime.fromtimestamp(float(refund.get("issued_at") or refund["at"]), IST)
    supply = order.get("place_of_supply")
    known = states.is_known(supply)
    export = states.is_export(supply)
    return {
        "number": refund["credit_no"],
        "date": f"{issued:%d %B %Y}",
        "invoice_no": refund.get("invoice_no") or order.get("invoice_no") or "",
        "invoice_date": "" if not order.get("paid_at") else
                        f"{dt.datetime.fromtimestamp(order['paid_at'], IST):%d %B %Y}",
        "reason": "Refund of payment",
        "refund_id": refund["refund_id"],
        # Full or partial against the ORDER, which is what the customer and the accountant both ask first.
        "state": order.get("refund_state") or "partial",
        "seller": {"name": site.LEGAL_ENTITY, "address": site.LEGAL_ADDRESS, "gstin": site.GSTIN,
                   "email": site.SUPPORT_EMAIL, "site": site.SITE_NAME},
        "buyer_email": (order.get("email") or "").strip(),
        "buyer_name": (order.get("names") or {}).get("self", "").strip(),
        "line": {"description": invoice._product_name(order), "sac": invoice.sac_code(),
                 "base": gst.money(amounts.base_paise), "gst": gst.money(amounts.gst_paise),
                 "total": gst.money(amounts.total_paise), "rate": amounts.rate_text},
        "place_of_supply": f"{states.name(supply, 'en')} ({supply})" if known or export else "",
        "intra_state": states.is_intra_state(supply),
        "export": export,
        "treatment": gst.EXPORT_TREATMENT if export else "",
        "heads": [{"name": head.name, "rate": head.rate_text, "amount": gst.money(head.paise)}
                  for head in (gst.heads(amounts, states.is_intra_state(supply)) if known else ())],
        "charged": gst.money(order.get("amount_paise")),
        "refunded_total": gst.money(order.get("refunded_paise")),
        "reference": order["razorpay_order_id"],
        "payment_id": order.get("payment_id") or "",
        "currency": order["currency"],
    }


def render(order: dict, refund: dict, *, for_print: bool = False) -> str | None:
    """The credit note as a complete HTML document, or None when this refund has no note (see `context`).

    `for_print` adds the bundled font faces and nothing else - see invoice.render."""
    data = context(order, refund)
    if not data:
        return None
    return invoice._env.get_template("credit_note.html").render(
        **data, print_css=invoice.print_css() if for_print else "")


def for_order(order: dict) -> list[dict]:
    """Every credit note on this order, oldest first: (refund row, context) pairs the order page renders."""
    notes = []
    for refund in store.refunds_for(order.get("id") or ""):
        data = context(order, refund)
        if data:
            notes.append({"refund": refund, "note": data})
    return notes
