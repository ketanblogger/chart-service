"""GST: ONE setting, read everywhere, and the exact integer arithmetic that splits a price.

The decision (owner, 2026-09-28, revised the same day): **the listed prices INCLUDE GST.** The price on the
page is the total the customer pays; the taxable value and the tax are contained within it. ₹299 is charged as
₹299, of which ₹253.39 is the taxable value and ₹45.61 is the tax.

| Env var | Default | Meaning |
|---|---|---|
| `GST_RATE_PERCENT` | `18` | The rate, in percent. Fractional rates are allowed (`GST_RATE_PERCENT=5.5`). |
| `GST_INCLUSIVE` | `1` | `1` = the listed price already contains GST. `0` = the listed price is the base and GST is ADDED on top. |
| `EXPORT_SALES_ENABLED` | `0` | `1` = the checkout offers "Outside India" and bills it as a zero-rated export. |

WHY THE DEFAULT IS INCLUSIVE, AND WHY IT IS NOT A PREFERENCE. `app/payments/catalogue.py`'s figures are
GST-INCLUSIVE TOTALS. That is a property of those numbers, not of the environment - so the code's idea of what
they mean has to match them without anyone remembering anything. With the default the other way round, a deploy
that forgets one line of `.env` does not fail and does not warn: it reads ₹59 as a pre-tax base and charges
₹69.62. A silent 18% overcharge to real customers is the worst outcome available in this file, and it was one
forgotten env var away. The default therefore lives here, in version control, next to the arithmetic, where it
moves in the same commit as the prices it describes rather than on a server nobody is looking at.

The inverse risk is real but smaller and self-announcing: if the catalogue is ever switched back to pre-tax
figures and this default is not, the site UNDERCHARGES - it absorbs the tax instead of collecting it, which
shows up in the first reconciliation rather than in a customer's complaint. **If you change what the catalogue's
numbers mean, change `DEFAULT_INCLUSIVE` in the same commit.**

WHY BASIS POINTS AND NOT A FLOAT RATE. Money here is paise (integers) and the one property every reader
downstream depends on is `base + gst == total`, exactly, always - the webhook refuses a payment whose
amount does not equal `amount_paise` to the paisa, and net revenue is computed by subtracting the stored
GST from the stored total. A float rate makes that property depend on binary rounding: 0.18 is not 18/100,
so `round(4900 * 0.18)` is a coin toss the moment a rate like 12.5% arrives. The rate is therefore carried
as an integer number of basis points (18% = 1800) and the split is integer arithmetic with ONE rounding,
half-up, on the derived side only. The other side is then defined as the difference, which is what makes
the sum exact by construction rather than by luck.

At the launch prices no rounding actually happens: 18% of a whole number of rupees is a whole number of
paise (rupees x 100 x 1800 / 10000 = rupees x 18). The rounding exists for the prices we do not have yet.
"""

import os
from dataclasses import dataclass, replace

DEFAULT_RATE_PERCENT = "18"
# See "WHY THE DEFAULT IS INCLUSIVE" above: this must agree with what app/payments/catalogue.py's prices mean.
DEFAULT_INCLUSIVE = True
BASIS_POINTS = 10000  # 100% ; 1800 bp = 18%
TRUE_WORDS = {"1", "true", "yes", "on"}
FALSE_WORDS = {"0", "false", "no", "off"}

# EXPORT SALES ARE OFF, AND OFF IS NOT A PREFERENCE. Two things have to be true before this may be a `1`, and
# neither is: the LUT (the Letter of Undertaking that lets a service be exported without paying integrated tax)
# is NOT FILED, and Razorpay international is NOT APPROVED on this account. With the flag on before then, the
# site would take a foreign card it cannot settle and issue an invoice claiming a zero rate it has no
# undertaking for - the second of those is a false statement on a tax document, not a missing feature.
#
# The default therefore lives here rather than in `.env`, for the same reason `DEFAULT_INCLUSIVE` does: a
# deploy that forgets a line of environment must land on the SAFE reading. Forgetting this one costs nothing;
# the other way round it offers every buyer on earth a 0% charge, which is the largest silent discount this
# file is capable of. `states.sells_to()` and `POST /api/payments/order` both consult it, so the option cannot
# be reached by editing the page either.
DEFAULT_EXPORT_SALES = False

# What a zero-rated export is CALLED on the invoice - one spelling, read by the document and by the tests, so
# the phrase that carries the legal basis for charging no tax cannot drift into a paraphrase of itself.
EXPORT_TREATMENT = "Export of service — zero rated under LUT"


@dataclass(frozen=True)
class GstSettings:
    """The rate and whether the listed prices already contain it."""

    rate_bp: int      # basis points: 1800 = 18%
    inclusive: bool   # True = the listed prices already contain GST; False = GST is added on top

    @property
    def rate_text(self) -> str:
        """The rate as it is printed and spoken: "18", or "12.5" for a fractional one. No percent sign -
        every language puts that differently and the sign belongs to the label, not to the number."""
        return f"{self.rate_bp / 100:g}"

    @property
    def charged(self) -> bool:
        """False for a zero rate, i.e. GST switched off entirely. A zero-rate order must not print a GST
        line or an invoice claiming tax was collected, so every caller asks this rather than testing 0."""
        return self.rate_bp > 0


def get_settings() -> GstSettings:
    """Read at call time, not import time, so tests and scripts can change the environment (app/ai/config.py
    does the same, for the same reason). An unparseable value is a loud failure, not a silent 18%: a typo in
    `GST_RATE_PERCENT` that fell back to a default would charge a rate nobody chose."""
    percent = os.getenv("GST_RATE_PERCENT", "").strip() or DEFAULT_RATE_PERCENT
    rate_bp = round(float(percent) * 100)
    if rate_bp < 0:
        raise ValueError(f"GST_RATE_PERCENT={percent!r} is negative")
    return GstSettings(rate_bp=rate_bp, inclusive=_flag("GST_INCLUSIVE", DEFAULT_INCLUSIVE))


def export_sales_enabled() -> bool:
    """Whether this site may sell outside India at all - see DEFAULT_EXPORT_SALES for why it is off.

    Read at call time like the rate, and parsed by the same strict `_flag`: `EXPORT_SALES_ENABLED="ture"` is
    refused rather than read as a no, because a typo that silently means "off" here is indistinguishable from
    the deliberate off, and the day this is switched on somebody has to be able to tell that it worked.
    """
    return _flag("EXPORT_SALES_ENABLED", DEFAULT_EXPORT_SALES)


def zero_rated(settings: GstSettings | None = None) -> GstSettings:
    """The current setting with the rate forced to zero: an export of service, zero rated under LUT.

    `inclusive` is carried through UNTOUCHED, and that is what keeps the charge the same. The listed price is
    the total in either treatment - ₹299 is charged as ₹299 to Pune and to Toronto - so zero-rating raises the
    taxable value to the whole of it instead of lowering the price. A customer who reached this by picking a
    different dropdown entry therefore pays exactly what the page said, which is the only version of this that
    is honest; `base + gst == total` still holds, with gst == 0.
    """
    return replace(settings or get_settings(), rate_bp=0)


def _flag(name: str, default: bool) -> bool:
    """A yes/no env var, parsed STRICTLY. Unset means the default; unrecognised is a failure, not a no.

    The usual `value.lower() in {"1", "true", "yes", "on"}` idiom answers False for anything it does not
    recognise, which makes `GST_INCLUSIVE="yes please"` and `GST_INCLUSIVE="ture"` mean *exclusive* - silently
    flipping the meaning of every price on the site to the more expensive reading. That is the same class of
    failure as a wrong default and it is a typo away, so a value that is neither a yes nor a no is refused.
    """
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    if raw.lower() in TRUE_WORDS:
        return True
    if raw.lower() in FALSE_WORDS:
        return False
    raise ValueError(f"{name}={raw!r} is neither a yes ({'/'.join(sorted(TRUE_WORDS))}) nor a no "
                     f"({'/'.join(sorted(FALSE_WORDS))}) - refusing to guess which way round the prices are")


@dataclass(frozen=True)
class Amounts:
    """One price, split. All three are paise and `base + gst == total` is guaranteed by construction.

    `rate_bp` travels with the numbers because an invoice has to print the rate that was CHARGED, which is
    not necessarily the rate configured today - the setting can change, and a reprinted invoice for last
    month's sale must still show last month's rate."""

    base_paise: int
    gst_paise: int
    total_paise: int
    rate_bp: int

    def __post_init__(self):
        # Not a defensive check: this is the property the webhook amount comparison and the net-revenue
        # figure both rest on, asserted where it is created rather than trusted at every reader.
        if self.base_paise + self.gst_paise != self.total_paise:
            raise ValueError(f"{self.base_paise} + {self.gst_paise} != {self.total_paise}")

    @property
    def base_inr(self) -> float:
        return self.base_paise / 100

    @property
    def gst_inr(self) -> float:
        return self.gst_paise / 100

    @property
    def total_inr(self) -> float:
        return self.total_paise / 100

    @property
    def rate_text(self) -> str:
        return f"{self.rate_bp / 100:g}"


def _round_half_up(numerator: int, denominator: int) -> int:
    """Integer division rounding halves UP. Both arguments are positive here (paise and basis points).

    `round()` is deliberately not used: it rounds halves to EVEN, so half a paisa of tax would land up or
    down depending on the neighbouring digit. A tax figure that moves with its neighbour is impossible to
    explain to the person who paid it, and impossible to reconcile against a return."""
    return (numerator * 2 + denominator) // (denominator * 2)


def split(price_paise: int, settings: GstSettings | None = None) -> Amounts:
    """Split a LISTED price (paise) into base, GST and total according to the setting.

    Inclusive (the shipping decision): the listed price IS the total, the base is computed and rounded once,
    and the GST is the remainder - so the customer is charged exactly the round number on the page and the
    taxable value is the one carrying paise. Exclusive: the listed price IS the base, GST is computed from it
    and rounded once, and the total is the sum.
    Either way exactly one of the three is rounded and the third is a difference, never a second rounding.
    """
    if not isinstance(price_paise, int) or price_paise < 0:
        raise ValueError(f"price must be a whole number of paise, got {price_paise!r}")
    settings = settings or get_settings()
    rate_bp = settings.rate_bp
    if settings.inclusive:
        base = _round_half_up(price_paise * BASIS_POINTS, BASIS_POINTS + rate_bp)
        return Amounts(base_paise=base, gst_paise=price_paise - base, total_paise=price_paise, rate_bp=rate_bp)
    gst = _round_half_up(price_paise * rate_bp, BASIS_POINTS)
    return Amounts(base_paise=price_paise, gst_paise=gst, total_paise=price_paise + gst, rate_bp=rate_bp)


@dataclass(frozen=True)
class Head:
    """One tax head as an invoice prints it: CGST, SGST or IGST."""

    name: str
    rate_bp: int
    paise: int

    @property
    def rate_text(self) -> str:
        return f"{self.rate_bp / 100:g}"


def heads(amounts: Amounts, intra_state: bool) -> tuple[Head, ...]:
    """The tax on this sale, split into the heads it is filed under. THE MONEY DOES NOT MOVE.

    Intra-state (buyer's state == seller's) is CGST + SGST at half the rate each; inter-state is IGST at the
    whole rate. The customer pays the same total either way - this is classification, not arithmetic on the
    charge - and `sum(head.paise) == amounts.gst_paise` is guaranteed here rather than hoped for.

    How the halves are computed matters. CGST is the half rate applied to the taxable value, which is the
    lawful definition; SGST is then defined as WHAT IS LEFT of the tax already stored on the order. Computing
    both from the rate would let two roundings disagree with the recorded total by a paisa - and a paisa that
    does not reconcile is the entire problem with tax arithmetic, because the invoice, the return and the bank
    statement are then three different numbers. An odd paisa lands on SGST, which is a convention, not a
    rounding: 4561 splits as 2281 + 2280.
    """
    if not amounts.gst_paise:
        return ()
    if not intra_state:
        return (Head("IGST", amounts.rate_bp, amounts.gst_paise),)
    half = amounts.rate_bp // 2
    cgst = _round_half_up(amounts.base_paise * half, BASIS_POINTS)
    sgst = amounts.gst_paise - cgst
    if cgst < 0 or sgst < 0:
        raise ValueError(f"CGST/SGST split of {amounts.gst_paise} went negative ({cgst}, {sgst})")
    return (Head("CGST", half, cgst), Head("SGST", amounts.rate_bp - half, sgst))


def recorded(order: dict) -> Amounts | None:
    """What was actually charged on a stored order, or None when this order predates the GST columns.

    NULL means "not recorded" and never zero - see the `register_columns` docstring in app/db.py. Orders
    paid before 2026-09-28 were charged a price with no GST line behind it; reading their NULL as 0 would
    print a ₹0.00 GST row on their order page and claim, on a tax invoice, that tax was collected and was
    nil. So every reader goes through here and handles None, and nothing infers the split by applying
    today's rate to an old amount - today's rate is not what that customer paid.
    """
    base, gst, rate_bp = order.get("base_paise"), order.get("gst_paise"), order.get("gst_rate_bp")
    if base is None or gst is None:
        return None
    total = order.get("amount_paise")
    if total is None or base + gst != total:
        # A row whose parts do not add up to the charge is worse than a row with no parts: it would print a
        # breakdown that disagrees with the money. Treated as not recorded, loudly enough to find.
        return None
    return Amounts(base_paise=base, gst_paise=gst, total_paise=total, rate_bp=rate_bp or 0)


def money(paise: int | None) -> str:
    """Rupees as a customer reads them: "249" for a whole amount, "293.82" when there are paise.

    Trailing ".00" is dropped because the listed prices are whole rupees and printing ₹249.00 next to a
    page that says ₹249 invites the question "which is it?". An amount that really has paise keeps BOTH
    digits - it is the number on the bank statement, and "249.1" is not a number anybody's statement shows.
    """
    if paise is None:
        return ""
    return f"{paise // 100:d}" if paise % 100 == 0 else f"{paise / 100:.2f}"
