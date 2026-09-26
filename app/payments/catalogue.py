"""The price list. **The only place an amount to charge ever comes from** - a client never sends one.

The launch prices (decided 2026-09-22), two tiers of the Kundali reading and two of the consultation:

| Product | id | Price | What the buyer gets |
|---|---|---|---|
| Simple Kundali report | `kundali-report-simple` | ₹49 | a concise ~8-12 page PDF |
| Detailed Kundali report | `kundali-report` | ₹249 | the full 35-45 page print-and-bind book |
| Kundali matching | `matching-report` | ₹99 | matching PDF |
| Mangal dosha / Sade sati guides | ... | ₹49 each | guide PDF |
| Consultation Basic | `consultation-basic` | ₹99 | 10 questions **+ the simple report** |
| Consultation Premium | `consultation-premium` | ₹299 | 10 questions **+ the detailed book** |

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
"""

from dataclasses import dataclass

from app.ai.config import get_chat_settings
from app.ai.products import PRODUCTS

CURRENCY = "INR"

SIMPLE_REPORT = "kundali-report-simple"   # the ₹49 concise reading
DETAILED_REPORT = "kundali-report"        # the ₹249 book. Unchanged id: old orders, caches and entitlements hold
BASIC_PACK = "consultation-basic"         # ₹99: questions + the simple report
PREMIUM_PACK = "consultation-premium"     # ₹299: questions + the book
PACK = "consultation-pack"                # retired id, still honoured for anyone who bought one
PACKS = (BASIC_PACK, PREMIUM_PACK)
PACK_REPORT = DETAILED_REPORT             # what the retired pack included

_REPORT_PRICES_INR = {
    SIMPLE_REPORT: 49,
    DETAILED_REPORT: 249,
    "matching-report": 99,
    "mangal-dosha-remedy": 49,
    "sade-sati-guide": 49,
}
# id -> (price, bundled report, sold now?). The prices of the two tiers live here, not in the chat settings:
# there are two of them now, and one setting cannot describe two offers.
_PACKS = {
    BASIC_PACK: (99, SIMPLE_REPORT, True),
    PREMIUM_PACK: (299, DETAILED_REPORT, True),
    PACK: (99, DETAILED_REPORT, False),
}
_PACK_NAMES = {
    BASIC_PACK: "AI consultation: {n} questions + Kundali PDF report",
    PREMIUM_PACK: "AI consultation: {n} questions + the detailed Kundali book",
    PACK: "AI consultation: {n} questions + Kundali PDF report",
}


@dataclass(frozen=True)
class Item:
    product: str
    kind: str  # "report" | "pack"
    name: str  # shown in Razorpay Checkout and on the order page
    price_inr: int
    messages: int = 0  # pack only
    bundled_report: str | None = None  # pack only: the report product that comes with it
    sold: bool = True  # False = honoured for existing orders, not offered any more

    @property
    def amount_paise(self) -> int:
        return self.price_inr * 100


def pending_products() -> list[str]:
    """Priced here, but `app/ai/products.py` cannot generate them yet, so they are not for sale."""
    return [product for product in _REPORT_PRICES_INR if product not in PRODUCTS]


def item(product: str) -> Item | None:
    """The catalogue entry, or None for an unknown product or one that cannot be generated yet."""
    if product in _PACKS:
        price, report, sold = _PACKS[product]
        settings = get_chat_settings()
        return Item(product, "pack", _PACK_NAMES[product].format(n=settings.pack_messages), price,
                    settings.pack_messages, report, sold)
    if product in _REPORT_PRICES_INR and product in PRODUCTS:
        return Item(product, "report", PRODUCTS[product].name, _REPORT_PRICES_INR[product])
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
    return (entry.bundled_report if entry else None) or PACK_REPORT


def all_items() -> list[Item]:
    """Everything that may be bought today, reports first, then the consultation tiers."""
    entries = [item(product) for product in (*_REPORT_PRICES_INR, *PACKS)]
    return [entry for entry in entries if entry and entry.sold]


def prices_inr() -> dict[str, int]:
    """{product: rupees} - for templates, page config and GET /api/payments/config."""
    return {entry.product: entry.price_inr for entry in all_items()}
