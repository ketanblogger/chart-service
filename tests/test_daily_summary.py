"""The daily summary: what the digest could not say, and the day it says it about.

THE DIGEST ONLY KNEW WHAT THE ORDERS SAID - how many, what they earned, what they cost, how long they
took. On a day with two orders that is a message about almost nobody. It now also carries visitors,
where those visits STARTED, refunds, orders left unpaid, new ratings, and any rashifal page that
failed.

ONE IST CALENDAR DAY, the same window every other number on the admin uses. Not "the last 24 hours":
two figures measured over different windows cannot be compared, and somebody will compare them anyway.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from app.admin import daily

SERVICE = Path("deploy/systemd/daily-summary.service").read_text(encoding="utf-8")
TIMER = Path("deploy/systemd/daily-summary.timer").read_text(encoding="utf-8")
DAY = dt.date(2026, 10, 22)


def test_every_figure_asked_for_is_in_the_message():
    """Built on a day with visits in it, because "Arrived on:" is correctly absent when nobody arrived -
    the first version of this test asserted it on an empty day and failed on the right behaviour."""
    from app import db

    day = dt.date(2031, 7, 7)
    with db.transaction() as conn:
        for visitor, path in (("v1", "/hi/rashifal/tula/aaj"), ("v2", "/hi/rashifal/tula/aaj"),
                              ("v3", "/kundli")):
            conn.execute(
                "INSERT INTO site_visits (ts, day, visitor, path, lang, is_admin, suspect) "
                "VALUES (?, ?, ?, ?, 'hi', 0, 0)", (0, day.isoformat(), visitor, path))

    lines = "\n".join(daily.lines_for(day))
    for label in ("Visitors", "Refunds", "Unpaid orders", "New ratings", "Rashifal", "Arrived on:"):
        assert label in lines, f"the summary has no {label} line"
    assert "3 (3 page views)" in lines
    # ranked by arrivals, most first
    assert lines.index("/hi/rashifal/tula/aaj") < lines.index("/kundli")


def test_the_arrivals_block_is_absent_when_nobody_arrived():
    """A heading over an empty list reads as a broken report."""
    assert "Arrived on:" not in "\n".join(daily.lines_for(dt.date(1999, 1, 1)))


def test_entry_pages_are_where_visits_started():
    """Not the busiest pages. The busiest is almost always the one everybody passes through; the page
    somebody ARRIVED on is the one that earned the visit."""
    import inspect

    source = inspect.getsource(daily.top_entry_pages)
    assert "MIN(ts)" in source and "GROUP BY visitor" in source


@pytest.mark.parametrize("figure", [daily.visitors, daily.refunds, daily.unpaid_orders,
                                    daily.new_ratings, daily.failed_rashifal])
def test_each_figure_answers_for_a_day_with_nothing_in_it(figure):
    """A quiet day is the normal case at this size, and a summary that errors on one is a summary
    nobody receives."""
    assert figure(dt.date(1999, 1, 1)) is not None


def test_a_broken_figure_does_not_cost_the_whole_message(monkeypatch):
    """A digest that does not arrive is worse than one missing a line."""
    def explode(day):
        raise RuntimeError("the table is locked")

    monkeypatch.setattr(daily, "refunds", explode)
    lines = daily.lines_for(DAY)
    assert any("not computed" in line for line in lines), "the failure is not reported"
    assert any("Visitors" in line for line in lines), "one broken figure took the others with it"


def test_the_digest_still_carries_the_order_figures():
    """The extras are an addition. Losing what the orders say would be a worse message, not a better."""
    from app.admin import alerts

    subject, body, figures = alerts.digest_body(DAY)
    for label in ("Paid orders", "Net revenue", "AI cost", "Margin"):
        assert label in body
    assert "Visitors" in body, "the extras did not reach the digest"


def test_the_timer_fires_at_eight_india_time():
    assert "OnCalendar=*-*-* 08:00:00 Asia/Kolkata" in TIMER
    assert "Persistent=true" in TIMER


def test_the_command_reports_yesterday_and_actually_sends():
    exec_line = [line for line in SERVICE.splitlines() if line.startswith("ExecStart=")]
    assert len(exec_line) == 1
    command = exec_line[0]
    assert command.endswith("-m app.admin.alerts --digest")
    assert "--dry-run" not in command, "the unit would print and never send"


def test_sending_twice_in_one_day_is_impossible():
    from app.admin import alerts

    sent = []
    now = dt.datetime(2026, 10, 23, 8, 0,
                      tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))

    def deliver(subject, body):
        sent.append(subject)
        return True

    assert alerts.send_digest(dt.date(2026, 10, 21), now=now, deliver=deliver) is True
    assert alerts.send_digest(dt.date(2026, 10, 21), now=now, deliver=deliver) is False
    assert len(sent) == 1
