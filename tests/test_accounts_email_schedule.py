"""The month-end accounts e-mail: it existed, nothing ran it.

THE MESSAGE, THE SENDER AND THE DEDUPE WERE ALL BUILT - app/admin/accounting.py composes it, sends it
to ADMIN_EMAILS and records that the month has gone out, and `python -m app.admin.accounting --email`
is the entry point. What was missing was anything that would ever call it. The module's own docstring
offers a cron line and says plainly "no scheduler is added".

So this item is a timer, and these tests pin the two things that make it fire correctly rather than
nearly correctly: the right day and hour in the right timezone, and the right command.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

SERVICE = Path("deploy/systemd/accounts-email.service").read_text(encoding="utf-8")
TIMER = Path("deploy/systemd/accounts-email.timer").read_text(encoding="utf-8")


def test_it_fires_on_the_first_at_nine_india_time():
    """IST is stated in the unit rather than inherited from the server. A timer that depends on the
    host's timezone is a timer that moves when somebody fixes the host's timezone."""
    assert "OnCalendar=*-*-01 09:00:00 Asia/Kolkata" in TIMER


def test_a_missed_month_is_caught_up():
    """This one genuinely must not be skipped: a server down over midnight on the 1st would lose the
    month's message, and the next is thirty days away. Safe only because the send is deduplicated."""
    assert "Persistent=true" in TIMER


def test_the_command_takes_no_month():
    """With no argument the job reports the month that just ENDED, which is the whole point of running
    it on the 1st. A --month baked into the unit would report the same month forever."""
    exec_line = [line for line in SERVICE.splitlines() if line.startswith("ExecStart=")]
    assert len(exec_line) == 1
    command = exec_line[0][len("ExecStart="):]
    assert command.endswith("-m app.admin.accounting --email")
    assert "--month" not in command
    assert "--dry-run" not in command, "the unit would print and never send"


def test_the_month_it_reports_is_the_one_that_ended():
    from app.admin import accounting

    for moment in (dt.datetime(2026, 11, 1, 9, 0), dt.datetime(2027, 1, 1, 9, 0)):
        first = accounting.due_month(moment)
        assert first.day == 1
        assert (first.year, first.month) == ((moment.year, moment.month - 1) if moment.month > 1
                                             else (moment.year - 1, 12))


def test_sending_twice_in_one_month_is_impossible():
    """A manual run, a retry after a timeout, or a timer that fires twice must not mean two messages."""
    from app.admin import accounting

    sent = []
    first = dt.date(2026, 9, 1)
    now = dt.datetime(2026, 10, 1, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))

    def deliver(subject, body):
        sent.append(subject)
        return True

    assert accounting.send_month_email(first, now=now, deliver=deliver) is True
    assert accounting.send_month_email(first, now=now, deliver=deliver) is False
    assert len(sent) == 1


def test_the_message_carries_a_link_and_no_attachment():
    """The spreadsheet names every customer of the month and what they bought. Mail is not where that
    should sit, and the page behind the link needs a sign-in, which an attachment does not."""
    from app.admin import accounting

    subject, body, figures = accounting.compose(dt.date(2026, 10, 1))
    assert re.match(r"October 2026 accounts ready: \d+ invoices, Rs ", subject), subject
    assert "/admin/accounting?month=2026-10" in body
    assert "signed in" in body
    assert figures["month"] == "2026-10"


def test_a_month_that_has_not_ended_is_never_sent():
    """THE COST OF GETTING THIS WRONG IS A MISSING E-MAIL, NOT A WRONG ONE.

    The send is deduplicated per month. Mail October's figures on the 30th and that month is marked
    done, so the real message on the 1st never goes - the partial figures become the only ones anybody
    receives, and nothing looks broken anywhere.

    The timer itself cannot reach here early: due_month() reports the month containing YESTERDAY, so a
    run on the 30th asks for the month that genuinely ended. The way in is an explicit
    `--email --month <this month>`, which is exactly the thing somebody does by hand while checking.
    """
    import datetime as dt

    from app.admin import accounting

    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    on_the_thirtieth = dt.datetime(2026, 10, 30, 9, 0, tzinfo=ist)
    sent = []

    def deliver(subject, body):
        sent.append(subject)
        return True

    # the month in progress, and one that has not started
    assert accounting.send_month_email(dt.date(2026, 10, 1), now=on_the_thirtieth, deliver=deliver) is False
    assert accounting.send_month_email(dt.date(2026, 11, 1), now=on_the_thirtieth, deliver=deliver) is False
    assert sent == [], "a month in progress was mailed"

    # and the refusal must not have consumed October: the real run still sends it
    on_the_first = dt.datetime(2026, 11, 1, 9, 0, tzinfo=ist)
    assert accounting.send_month_email(dt.date(2026, 10, 1), now=on_the_first, deliver=deliver) is True
    assert len(sent) == 1 and sent[0].startswith("October 2026 accounts ready")


def test_the_guard_is_on_the_send_and_not_on_the_command():
    """Every caller gets it - the timer, the CLI, and anything added later. A check inside main() would
    protect only the way in that existed when it was written."""
    import inspect

    from app.admin import accounting

    source = inspect.getsource(accounting.send_month_email)
    assert "has not ended" in source


def test_printing_a_month_in_progress_is_still_allowed():
    """Inspecting the month so far is the useful thing to do on the 30th. Only SENDING is refused."""
    import datetime as dt

    from app.admin import accounting

    subject, body, figures = accounting.compose(dt.date(2026, 10, 1))
    assert subject and figures["month"] == "2026-10"
