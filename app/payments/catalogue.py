"""The price list. **The only place an amount to charge ever comes from** - a client never sends one.

The prices (re-set 2026-09-28 when GST became inclusive), two tiers of the Kundali reading and two of the
consultation. **EVERY NUMBER HERE IS WHAT THE CUSTOMER PAYS**, tax included:

| Product | id | Price | Of which GST | What the buyer gets |
|---|---|---|---|---|
| Simple Kundali report | `kundali-report-simple` | ₹59 | ₹9.00 | a concise ~8-12 page PDF |
| Detailed Kundali report | `kundali-report` | ₹299 | ₹45.61 | the full 35-45 page print-and-bind book |
| Kundali matching | `matching-report` | ₹119 | ₹18.15 | matching PDF |
| Mangal dosha / Sade sati guides | ... | ₹59 each | ₹9.00 | guide PDF |
| Consultation Basic | `consultation-basic` | ₹119 | ₹18.15 | 10 questions **+ the simple report** |
| Consultation Premium | `consultation-premium` | ₹349 | ₹53.24 | 10 questions **+ the detailed book** |

The previous prices were ₹49 / ₹249 / ₹99 / ₹49 / ₹99 / ₹299 and were GST-EXCLUSIVE, so ₹249 was charged as
₹293.82. Every listed price ending in .82 is what that produced, and it is why these numbers moved: round
totals are worth more than round bases, because the total is the number the customer agrees to.

Rashifal is free, and the first two consultation questions are free.

**A consultation order records which report it includes in its own product id** - that is the whole of the
tier machinery. `report_product(order)` reads the bundled report off the catalogue entry for that id, so an
order can never drift to the other tier: ids are never reused and an id's bundled report never changes.
`consultation-pack` is the id sold before the tiers existed; it is still honoured (10 questions + the
detailed book, which is what those buyers paid for) but is no longer sellable.

A product may be priced here before `app/ai/products.py` can generate it (that is how a new report lands:
price first, generator next). `item()` returns None for such a product, so it cannot be bought, and
`app/hardening.py` warns while that is the case.

Page copy must not hard-code prices: templates / page config should read them from `prices_inr()` (or
GET /api/payments/config). tests/test_payments.py fails if a page shows a number that differs from this file.

**THESE PRICES INCLUDE GST** (owner's decision, 2026-09-28, to be confirmed with his CA before live keys).
Every number above is the TOTAL. 18% is taken out of it for the invoice, so ₹299 is ₹253.39 of taxable value
plus ₹45.61 of tax. `price_inr` and `prices_inr()` are the LISTED price, which is now also the charge:
`Item.amount_paise` equals `price_inr * 100` in this mode, and `Item.gst` is the split.

**NET REVENUE IS NO LONGER THE LISTED PRICE.** It is `Item.gst.base_paise` - the taxable value - and under
the previous exclusive mode those two were the same number, which is why anything that reads the listed price
as a net figure will now be wrong by 18% without looking wrong. `app/payments/gst.py` carries the mode as
`DEFAULT_INCLUSIVE`, in version control rather than in an environment file, because what these numbers MEAN
is a property of these numbers: the two have to move in the same commit or a deploy that forgot an env var
would charge ₹69.62 for the ₹59 product and say nothing.
"""

from dataclasses import dataclass

from app.ai.config import get_chat_settings
from app.ai.products import PRODUCTS

from . import gst

CURRENCY = "INR"

SIMPLE_REPORT = "kundali-report-simple"   # the ₹49 concise reading
DETAILED_REPORT = "kundali-report"        # the ₹249 book. Unchanged id: old orders, caches and entitlements hold
BASIC_PACK = "consultation-basic"         # ₹99: questions + the simple report
PREMIUM_PACK = "consultation-premium"     # ₹299: questions + the book
PACK = "consultation-pack"                # retired id, still honoured for anyone who bought one
MINI_PACK = "consultation-mini"           # a few questions, no report, behind the MINI_PACK flag
PACKS = (MINI_PACK, BASIC_PACK, PREMIUM_PACK)
PACK_REPORT = DETAILED_REPORT             # what the retired pack included

_REPORT_PRICES_INR = {
    SIMPLE_REPORT: 59,
    DETAILED_REPORT: 299,
    "matching-report": 119,
    "mangal-dosha-remedy": 59,
    "sade-sati-guide": 59,
    # RS 199, the proprietor's. I proposed 99 by comparison with the Rs 59 single-topic guides; he
    # set it against what the section people actually buy is worth - the spelling alternatives,
    # worked out for their own name - and against what comparable reports sell for elsewhere.
    "numerology-report": 199,
}
# id -> (price, bundled report, sold now?). The prices of the two tiers live here, not in the chat settings:
# there are two of them now, and one setting cannot describe two offers.
_PACKS = {
    BASIC_PACK: (119, SIMPLE_REPORT, True),
    PREMIUM_PACK: (349, DETAILED_REPORT, True),
    # The retired id keeps its old figure ON PURPOSE. It cannot be bought, its existing orders are frozen with
    # the rate that was stored on them, and `gst.recorded()` reads what was stored rather than recomputing - so
    # re-pricing it would change nothing except to suggest it was once sold at a price it never was.
    PACK: (99, DETAILED_REPORT, False),
}
_PACK_NAMES = {
    MINI_PACK: "AI consultation: {n} questions",
    BASIC_PACK: "AI consultation: {n} questions + Kundali PDF report",
    PREMIUM_PACK: "AI consultation: {n} questions + the detailed Kundali book",
    PACK: "AI consultation: {n} questions + Kundali PDF report",
}


@dataclass(frozen=True)
class Item:
    product: str
    kind: str  # "report" | "pack" | "download"
    name: str  # shown in Razorpay Checkout and on the order page
    price_inr: int
    messages: int = 0  # pack only
    bundled_report: str | None = None  # pack only: the report product that comes with it
    sold: bool = True  # False = honoured for existing orders, not offered any more

    @property
    def base_paise(self) -> int:
        """The LISTED price in paise - which under inclusive pricing is the CHARGE, not the taxable value.

        The name is now misleading and is kept only because `gst.split()` takes this as its input; the taxable
        value is `Item.gst.base_paise`, and NET REVENUE IS THAT, not this. Under the previous exclusive mode
        the two were the same number, so nothing distinguished them and nothing had to. Retiring this name in
        favour of `listed_paise` is queued - see the checklist - and is deliberately not bundled with a price
        change, because a rename and a repricing in one commit is how the wrong number ships quietly.
        """
        return self.price_inr * 100

    @property
    def gst(self) -> gst.Amounts:
        """base / GST / total for this item under the current GST setting (app/payments/gst.py)."""
        return gst.split(self.base_paise)

    @property
    def amount_paise(self) -> int:
        """WHAT IS CHARGED: the total including GST. Deliberately still called `amount_paise`, because that
        is the name every caller already uses for the number it hands to Razorpay and stores on the order -
        `razorpay.create_order`, `store.insert_order`, the webhook's amount comparison, and both live-check
        scripts. Renaming it would have left the same name meaning the pre-tax figure in some places and the
        charge in others, which is the one mistake in tax arithmetic nobody notices until a return is filed.
        The pre-tax figure has its own name (`base_paise`) precisely so this one can keep meaning the charge.
        """
        return self.gst.total_paise


def pending_products() -> list[str]:
    """Priced here, but `app/ai/products.py` cannot generate them yet, so they are not for sale."""
    return [product for product in _REPORT_PRICES_INR if product not in PRODUCTS]


def _mini() -> tuple[int, None, bool]:
    """(price, bundled report, sold?) for the small pack, read at call time.

    Read HERE rather than baked into `_PACKS` at import: the price and the size are settings, and a module
    constant would freeze whatever they were when the process started - which is a trap for exactly the
    person who changes a price in .env, restarts, and finds the old one still on the page.
    """
    from app.web import site

    return site.MINI_PACK_PRICE_INR, None, bool(site.MINI_PACK)


# A THIRD KIND. A report is generated and is about one chart; a pack is a number of messages. A
# DOWNLOAD is neither: it is bought once and unlocks something the buyer then makes as often as they
# like, with nothing generated and nothing stored. The biodata premium designs are the first of
# these - keying them to a report id would mean keeping the sheet, which is exactly what that page
# promises not to do.
BIODATA_PREMIUM = "biodata-premium"
_DOWNLOADS = {BIODATA_PREMIUM: (99, "Biodata premium designs")}


def item(product: str) -> Item | None:
    """The catalogue entry, or None for an unknown product or one that cannot be generated yet."""
    if product == MINI_PACK:
        price, report, sold = _mini()
        from app.web import site

        size = site.MINI_PACK_MESSAGES
        return Item(product, "pack", _PACK_NAMES[product].format(n=size), price, size, report, sold)
    if product in _PACKS:
        price, report, sold = _PACKS[product]
        settings = get_chat_settings()
        return Item(product, "pack", _PACK_NAMES[product].format(n=settings.pack_messages), price,
                    settings.pack_messages, report, sold)
    if product in _REPORT_PRICES_INR and product in PRODUCTS:
        return Item(product, "report", PRODUCTS[product].name, _REPORT_PRICES_INR[product])
    if product in _DOWNLOADS:
        price, name = _DOWNLOADS[product]
        return Item(product, "download", name, price)
    return None


def sellable(product: str) -> Item | None:
    """The entry only if it may be bought right now. Retired ids resolve through `item()` but never here."""
    entry = item(product)
    return entry if entry and entry.sold else None


def report_product(order: dict) -> str | None:
    """Which report an order entitles its buyer to: the product itself for a report order, the bundled report
    for a consultation purchase that carries one, else None. For a pack the id IS the record of the tier."""
    if not order.get("report_id"):
        return None
    if order.get("kind") != "pack":
        return order["product"]
    entry = item(order["product"])
    if entry and entry.bundled_report:
        return entry.bundled_report
    # THE FALLBACK IS FOR THE RETIRED ID ONLY. `or PACK_REPORT` here meant any pack without a bundled
    # report entitled its buyer to the detailed book - so the Rs 49 questions-only pack would have bought
    # the Rs 299 one. A pack that carries no report entitles its buyer to no report.
    return PACK_REPORT if order["product"] == PACK else None


def all_items() -> list[Item]:
    """Everything that may be bought today: reports, then the consultation tiers, then downloads.

    THE DOWNLOADS BELONG HERE even though they are bought from inside a tool rather than from a
    product page. This list is what builds the pricing page, and a charge a reader can meet while
    using the site has to be on the page that lists what things cost - "it is only ninety-nine
    rupees and it is written on the button" is not the same as published.
    """
    entries = [item(product) for product in (*_REPORT_PRICES_INR, *PACKS, *_DOWNLOADS)]
    return [entry for entry in entries if entry and entry.sold]


def prices_inr() -> dict[str, int]:
    """{product: rupees} - for templates, page config and GET /api/payments/config."""
    return {entry.product: entry.price_inr for entry in all_items()}
