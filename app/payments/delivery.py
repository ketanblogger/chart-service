"""Did the customer ever open what they paid for - and one reminder if not.

A report paid for and never downloaded is the worst outcome this service has: the money is taken, the work
is done, and the person has nothing. It was invisible until the order started recording its first
download, and this module is what acts on that.

ONE REMINDER, EVER. Not "one a day until they open it": somebody who has not downloaded their report after
a day may be busy, may have changed their mind, may simply read it on a laptop next week. A second nudge is
us needing something, not them. The single send is enforced by a stamp on the order row - `mark_reminded`
only succeeds when nothing has set it - rather than by a schedule, because a reminder that CAN fire twice
is a reminder that eventually will.
"""
from __future__ import annotations

import datetime as _dt

import logging

log = logging.getLogger(__name__)

AFTER_HOURS = 24


#: What we can honestly say about whether a customer got their report.
DOWNLOADED, UNKNOWN, NEVER = "downloaded", "unknown", "never"


#: When download tracking actually shipped: commit 3a74c1e, "Did the e-mail arrive, and did they ever
#: open what they paid for", 2026-10-19 21:12 UTC. Before this moment `orders.downloaded_at` did not
#: exist and nothing was writing it, so a blank on an order paid earlier says nothing whatever.
#: Written as a date rather than a number so it can be read and checked - a hand-typed timestamp in this
#: same batch turned out to be a year and twenty minutes wrong and classified nothing while looking fine.
TRACKING_SINCE = _dt.datetime(2026, 10, 19, 21, 12, tzinfo=_dt.timezone.utc).timestamp()


def tracking_started() -> float:
    """The moment from which a blank `downloaded_at` is real evidence that nobody collected the report.

    THE FIRST VERSION OF THIS ASKED THE WRONG QUESTION. It returned MIN(downloaded_at) - the earliest
    download anyone had ever made - and None when there was none. But "nobody has downloaded anything
    yet" is not the same as "we were not recording", and treating it as such made every order unknown
    forever: a site that has recorded faithfully for a month and simply has no downloads would never
    chase a single one. The boundary is when the CODE started recording, which is a fact about this
    repository, not about the data.

    The earliest recorded download still wins if it somehow predates the constant, because data that
    exists beats a date written in a comment.
    """
    from app import db

    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT MIN(downloaded_at) AS first FROM orders "
                           "WHERE downloaded_at IS NOT NULL").fetchone()
    earliest = float(row["first"]) if row and row["first"] else None
    return min(earliest, TRACKING_SINCE) if earliest else TRACKING_SINCE


def cached_pdf_at(order: dict) -> float | None:
    """When this report's PDF was first rendered, from the cache file app/pdf/service.py writes.

    THIS IS THE OTHER HALF OF THE TRUTH, and it is why the two screens disagreed. The PDF is rendered on
    the first download REQUEST and cached under var/pdfs/<report id>-*.pdf, so the file existing means
    somebody asked for it. The four real orders were downloaded before `mark_downloaded` was written, so
    the file is there and the column is not. Reading only the column calls that "never downloaded"; the
    admin Orders page reads the file and calls it delivered. Both screens now ask this function.
    """
    report_id = order.get("report_id")
    if not report_id:
        return None
    try:
        from app.pdf.service import pdfs_dir

        matches = sorted(pdfs_dir().glob(f"{report_id}-*.pdf"), key=lambda path: path.stat().st_mtime)
    except (OSError, ValueError):
        return None
    return matches[0].stat().st_mtime if matches else None


def download_state(order: dict, *, started: float | None = None) -> tuple[str, float | None]:
    """-> (DOWNLOADED | UNKNOWN | NEVER, when) for one order, from every source there is.

    The order of evidence is what makes this honest:

      the column is set            -> DOWNLOADED, and we know when
      a cached PDF exists          -> DOWNLOADED, at the file's mtime: somebody asked for it
      nothing, and tracking was    -> NEVER: the machinery was working and recorded nothing for them
        demonstrably running then
      nothing else                 -> UNKNOWN: paid before any of this was written down, or the column has
                                      never recorded anything at all, and a blank is not a no

    `started` is passed in by callers listing many orders so the database is asked once rather than once
    per row.
    """
    if order.get("downloaded_at"):
        return DOWNLOADED, float(order["downloaded_at"])
    rendered = cached_pdf_at(order)
    if rendered:
        return DOWNLOADED, rendered
    began = tracking_started() if started is None else started
    paid = order.get("paid_at")
    if began and paid and float(paid) >= began:
        return NEVER, None
    return UNKNOWN, None


def should_remind(order: dict, *, now: float, after_hours: int = AFTER_HOURS,
                  paid_at: float | None = None, state: str | None = None) -> bool:
    """Whether this order is owed its one reminder. Every reason to say no is its own line."""
    # NEVER NUDGE ON A BLANK. The column alone used to decide this, and the column is empty for every
    # order paid before it was written - including four that demonstrably have their PDF. Only an order we
    # can positively say was never downloaded is owed a reminder; "we do not know" is not a yes, and the
    # cost of getting it wrong is an e-mail telling a paying customer they never collected something they
    # have had for weeks.
    #
    # `state` IS PASSED IN BY THE LOOP. This function used to be a pure predicate over a dict, and the
    # first version of this guard called download_state() here - which opens a database transaction and
    # reads the filesystem, so a caller holding a plain dict (every direct test of the once-only logic)
    # suddenly needed a schema. The loop already knows the state for each order and computes
    # tracking_started() once for all of them; deriving it here is the fallback, not the path.
    if (state if state is not None else download_state(order)[0]) != NEVER:
        return False
    if order.get("reminded_at"):
        return False                      # already nudged, once, which is all there is
    if not (order.get("email") and order.get("token")):
        return False                      # nowhere to send it, or no link to send
    paid = paid_at if paid_at is not None else order.get("paid_at")
    if not paid:
        return False
    return (now - float(paid)) >= after_hours * 3600


def _send_reminder(order: dict) -> bool:
    """The nudge itself: the same order link they were sent when they paid."""
    from app.payments.order_email import compose_reminder

    to, subject, body = compose_reminder(order)
    if not to:
        return False
    from app import mailer

    return mailer.send_recorded(to, subject, body).ok


def remind_undownloaded(after_hours: int = AFTER_HOURS, now: float | None = None,
                        limit: int = 50) -> dict:
    """Send the one reminder to everybody owed one. -> a small summary, for a log line or a script."""
    import time

    from app.payments import store

    now = now or time.time()
    candidates = store.paid_but_not_downloaded(after_hours=after_hours, now=now)
    started = tracking_started()          # once, not once per order
    sent, skipped = 0, 0
    for order in candidates[:limit]:
        if not should_remind(order, now=now, after_hours=after_hours,
                             state=download_state(order, started=started)[0]):
            skipped += 1
            continue
        # The stamp is taken FIRST. If the send then fails, this customer does not get a reminder - which
        # is the safer way round: a missing nudge costs one e-mail, a duplicated one costs trust.
        if not store.mark_reminded(order["id"]):
            skipped += 1
            continue
        if _send_reminder(order):
            sent += 1
        else:
            log.warning("reminder for %s could not be sent", order["id"][:12])
    return {"considered": len(candidates), "sent": sent, "skipped": skipped}


__all__ = ["AFTER_HOURS", "remind_undownloaded", "should_remind"]
