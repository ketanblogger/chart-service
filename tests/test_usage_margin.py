"""The usage page's money: what we keep, and an estimate that says it is one.

TWO THINGS WERE WRONG WITH THE MARGIN ON THAT PAGE.

It counted GST as income. The revenue figure was the sum of the usage events, and those carry
`amount_paise` - the tax-INCLUSIVE charge. On a Rs 299 sale that is Rs 45.61 that was never ours: it is
collected on the government's behalf and remitted. Every margin on the page was over by the tax.

And it treated an unrecorded cost as no cost. Chat answers and reports went in for months with no cost
worked out, and a margin that reads unknown as zero is the most flattering possible lie - the page said
so in a note, but the number itself stayed wrong.

Both are fixed by publishing MORE numbers rather than quietly changing one: gross and net side by side,
measured margin and estimated margin side by side, each labelled.
"""
from __future__ import annotations

import pytest

from app import analytics, db
from app.payments import store  # noqa: F401 - registers the orders schema

RANGE = ("2000-01-01", "2099-12-31")


def test_revenue_is_split_into_what_we_keep_and_what_we_remit():
    money = analytics.revenue_ex_gst(*RANGE)
    assert money["gross_inr"] == pytest.approx(money["net_inr"] + money["gst_inr"], abs=0.01)


def test_the_margin_is_taken_on_the_net_and_not_the_gross():
    """THE WHOLE POINT. A margin on the gross is a margin on money that belongs to the government."""
    report = analytics.summary(3650)
    assert report["margin_inr"] == pytest.approx(
        report["revenue_net_inr"] - report["cost_inr"], abs=0.01)
    if report["gst_collected_inr"]:
        assert report["margin_inr"] < report["revenue_gross_inr"] - report["cost_inr"]


def test_a_paid_order_with_no_payment_date_is_reported_rather_than_lost():
    """FOUND BY COMPARING TWO FIGURES THAT SHOULD HAVE AGREED. The range filter is on paid_at, and some
    early rows are 'paid' with that column empty - so they fell out of every window silently and the
    revenue was short by their whole value. They cannot be put in a day they do not have, so they are
    counted and named instead."""
    money = analytics.revenue_ex_gst(*RANGE)
    assert "undated_orders" in money and "undated_inr" in money
    if money["undated_orders"]:
        assert money["undated_inr"] > 0


def test_the_estimate_is_a_median_and_not_a_mean(monkeypatch):
    """One retried report costing six times the usual would drag a mean up and inflate every estimate
    taken from it. Built here as rows rather than asserted on prose."""
    day = "2031-03-03"
    with db.transaction() as conn:
        for cost in (1.0, 1.0, 1.0, 60.0):          # mean 15.75, median 1.0
            conn.execute(
                "INSERT INTO site_events (ts, day, feature, action, ok, cost_inr, cost_known, is_admin) "
                "VALUES (?, ?, 'report', 'sold', 1, ?, 1, 0)", (0, day, cost))
        conn.execute(
            # NOT NULL, so an unrecorded cost is stored as 0.0 with cost_known = 0 - which is exactly
            # why a total that sums cost_inr reads "unknown" as "free".
            "INSERT INTO site_events (ts, day, feature, action, ok, cost_inr, cost_known, is_admin) "
            "VALUES (?, ?, 'report', 'sold', 1, 0.0, 0, 0)", (0, day))
    estimate = analytics.estimated_cost(day, day)
    assert estimate["events"] == 1
    assert estimate["inr"] == pytest.approx(1.0, abs=0.01), "a mean would have given 15.75"


def test_a_kind_with_nothing_to_estimate_from_gets_no_estimate():
    """Inventing a number for it would be the same mistake as calling it zero. It is counted instead."""
    day = "2031-04-04"
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO site_events (ts, day, feature, action, ok, cost_inr, cost_known, is_admin) "
            "VALUES (?, ?, 'chat', 'question', 1, 0.0, 0, 0)", (0, day))
    estimate = analytics.estimated_cost(day, day)
    assert estimate["inr"] == 0 and estimate["events"] == 0
    assert estimate["no_basis"] == 1


def test_the_estimate_is_never_folded_into_the_measured_margin():
    """An estimate presented as a measurement is how a page stops being worth reading."""
    report = analytics.summary(3650)
    assert report["margin_inr"] == pytest.approx(
        report["revenue_net_inr"] - report["cost_inr"], abs=0.01)
    assert report["margin_with_estimate_inr"] == pytest.approx(
        report["margin_inr"] - report["estimated_cost_inr"], abs=0.01)


def test_the_page_labels_every_estimated_number():
    """A reader must be able to tell, on the page, which figure was measured and which was modelled."""
    from pathlib import Path

    html = Path("app/admin/templates/usage.html").read_text(encoding="utf-8")
    block = html[html.index('<div class="k">Margin</div>'):]
    block = block[:block.index("</div>\n</section>")] if "</div>\n</section>" in block else block
    assert "margin_with_estimate_inr" in block
    assert "estimated" in block.lower()
    assert "Revenue (ex GST)" in html and "gst_collected_inr" in html
