"""Which orders and usage events are OURS rather than a customer's, and why.

NOTHING IS DELETED. An internal order keeps its row, its invoice number, its credit note and its GST
figures: the 29 September Rs 59 order and its Rs 57.60 credit note are accounting records a CA and a GST
return both need. Marking them changes what the business metrics COUNT, not what the books contain.

WHY IT MATTERS. The proprietor buying his own report, a browser check in test mode, a rehearsal before
launch - each of those is a paid row with an amount on it, and a revenue figure that includes them is a
number nobody can act on. The AI those internal orders and chats consumed is the opposite case: it is
real money that left the account, so it is shown as its own line and never folded away.

THE CLASSIFICATION IS EVIDENCE-BASED AND NEVER GUESSES REVENUE AWAY. An order is internal when its email
belongs to an admin, or when it was made with test Razorpay keys. An order whose mode was never recorded
(`live IS NULL`, which means "made before that column existed") is NOT assumed to be either: the backfill
lists it for a person to decide, because the cost of wrongly marking a real sale internal is a revenue
figure that is quietly too low, and nobody notices a number that is missing.
"""
from __future__ import annotations

import datetime as _dt

ADMIN = "admin email"
TEST_MODE = "test-mode razorpay keys"
UNDECIDED = "mode not recorded"


def admin_emails() -> frozenset[str]:
    from app.web import site

    return frozenset(site.ADMIN_EMAILS)


#: The first real sale: 2026-09-29 10:22 IST, order ord_bb6c58802403dde9ecd3. Everything created before
#: that moment was a rehearsal - the site had never taken a rupee from anybody who was not us, so there
#: was nobody else for it to have come from. Four orders from 25-28 September sat as "cannot be judged"
#: because they carry no razorpay mode and were not placed from an admin address; this decides them on a
#: fact about the business rather than on a guess about an address.
FIRST_LIVE_SALE_ID = "ord_bb6c58802403dde9ecd3"
#: 2026-09-29 10:22:00 +05:30. WRITTEN AS A DATE, NOT A NUMBER. The first version of this line was a
#: hand-typed unix timestamp that resolved to 29 September 2025 at 10:02 - a year and twenty minutes
#: wrong, and silently so: every September 2026 order compared as "after the first sale" and the rule
#: classified nothing at all while appearing to work. A literal nobody can read is a literal nobody can
#: check.
FIRST_LIVE_SALE_AT = _dt.datetime(
    2026, 9, 29, 10, 22, tzinfo=_dt.timezone(_dt.timedelta(hours=5, minutes=30))).timestamp()
BEFORE_FIRST_SALE = "before the first live sale"


#: Every reason that means "this is ours". A caller deciding what to mark asks THIS, so adding a reason
#: above cannot leave a dispatch somewhere else still listing two of them by name.
INTERNAL_REASONS = frozenset({ADMIN, TEST_MODE, BEFORE_FIRST_SALE})


def before_first_sale(order: dict) -> bool:
    """Was this order created before the site's first real sale?

    The first sale's own order is not before itself, and nothing after it is caught - the four October
    orders that are real business stay business.
    """
    if order.get("id") == FIRST_LIVE_SALE_ID:
        return False
    created = order.get("created_at")
    return bool(created) and float(created) < FIRST_LIVE_SALE_AT


def reason_for(order: dict, admins: frozenset[str] | None = None) -> str | None:
    """Why this order is internal, or None if it is a customer's.

    Returns `UNDECIDED` for a row that cannot be judged either way - the caller decides whether to mark
    it, and the backfill's answer is to print it and leave it alone.
    """
    admins = admin_emails() if admins is None else admins
    email = (order.get("email") or "").strip().lower()
    if email and email in admins:
        return ADMIN
    live = order.get("live")
    if live == 0:
        return TEST_MODE
    # BEFORE ANY OF THIS WAS REAL. Checked after the two certain signals and before giving up, so an
    # admin address or a test-mode flag still reports the specific reason it is internal.
    if before_first_sale(order):
        return BEFORE_FIRST_SALE
    if live is None:
        return UNDECIDED
    return None


def is_internal(order: dict, admins: frozenset[str] | None = None) -> bool:
    """What the metrics ask. A stored classification wins; otherwise the evidence decides, and an
    undecided row counts as BUSINESS so that a real sale is never hidden by a missing column.

    `admins` is injectable because otherwise this reads the live environment on every call, and a test
    could not state the case it is testing - the first version of this classified an admin order as
    business whenever ADMIN_EMAILS happened to be unset, which is precisely the configuration in which
    the classification matters most.
    """
    stored = order.get("internal")
    if stored is not None:
        return bool(stored)
    return reason_for(order, admins) in (ADMIN, TEST_MODE)


def split(orders, admins: frozenset[str] | None = None) -> tuple[list[dict], list[dict]]:
    """(business, internal) - the one place that divides them, so no page can disagree with another."""
    admins = admin_emails() if admins is None else admins
    business, internal = [], []
    for order in orders:
        (internal if is_internal(dict(order), admins) else business).append(order)
    return business, internal


class NoAdminsConfigured(RuntimeError):
    """ADMIN_EMAILS is empty, so no order can be recognised as the proprietor's.

    A backfill that runs in this state marks nothing, finds nothing to mark, and reports success - which
    reads exactly like "there was nothing internal" and is the one wrong conclusion available. Raised
    rather than returned so it cannot be ignored by a caller that does not check.
    """


def require_admins() -> frozenset[str]:
    """The admin set, or a refusal. For anything that WRITES a classification."""
    admins = admin_emails()
    if not admins:
        raise NoAdminsConfigured(
            "ADMIN_EMAILS is empty, so no order can be recognised as internal by address. "
            "Set it in /srv/astrology/.env - the same addresses the admin dashboard allows - "
            "and run this again.")
    return admins


def mask(email: str | None) -> str:
    """"m***" - enough to recognise a row without putting an address in a report or a log."""
    address = (email or "").strip()
    return f"{address[0]}***" if address else "(no email)"
