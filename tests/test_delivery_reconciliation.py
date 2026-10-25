"""The delivery report and the admin Orders page must answer "did they get it" the same way.

THE BUG THIS EXISTS FOR, as it appeared on production on 21 October: scripts/delivery_report.py listed all
fourteen orders as "NEVER downloaded" while the admin Orders page showed the PDF delivered for the four
real ones. Neither screen was lying; they were reading different evidence.

  the report      read orders.downloaded_at, a column written only since mark_downloaded() was added
  the Orders page read var/pdfs/<report id>-*.pdf, which exists because the PDF is rendered on the first
                  download REQUEST

The four real orders were collected before the column existed, so the file is there and the column is not.
On top of that the report's "is this from before tracking" helper returned 0.0 when NO row had ever been
stamped, so every paid_at compared as later and every order printed NEVER - a blank column turned into a
confident accusation against fourteen customers, four of whom demonstrably had their report.

The consequence was not cosmetic: --remind reads the same state, so running it would have e-mailed paying
customers to say they had never collected something they had had for weeks.
"""
from __future__ import annotations

import time
import uuid

import pytest

from app import db
from app.payments import delivery, store  # store imported for its schema registration, not its API

from .test_order_delivery import seed_paid_order

HOUR = 3600.0


def _pdf_for(report_id: str):
    """A cached PDF, exactly where app/pdf/service.py would have left one."""
    from app.pdf.service import pdfs_dir

    directory = pdfs_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report_id}-kundali.pdf"
    path.write_bytes(b"%PDF-1.4 not a real report, but a real file\n")
    return path


@pytest.fixture
def production_shape(tmp_path, monkeypatch):
    """Production as it actually was: fourteen paid orders, four of them with a cached PDF and no column.

    Built through the same INSERT the payment path uses and the same schema registration, so the columns
    are the ones production has rather than ones a test invented.
    """
    from app.pdf import service as pdf_service

    monkeypatch.setattr(pdf_service, "pdfs_dir", lambda: tmp_path / "pdfs")
    collected, uncollected = [], []
    for index in range(14):
        order = seed_paid_order(paid_hours_ago=600 + index)
        if index < 4:
            _pdf_for(order["report_id"])
            collected.append(order["id"])
        else:
            uncollected.append(order["id"])
    return {"collected": collected, "uncollected": uncollected}


def test_nothing_reads_as_never_when_the_column_has_never_recorded_anything(production_shape):
    """The exact production state. An empty column is no evidence, not evidence of absence."""
    # The boundary is when the recording code shipped, not when somebody first downloaded something.
    # These orders were all paid well before it, so none of them can be called "never collected".
    started = delivery.tracking_started()
    assert started == delivery.TRACKING_SINCE
    from app.payments import store

    states = []
    for order_id in production_shape["collected"] + production_shape["uncollected"]:
        order = store.get_order(order_id)
        states.append(delivery.download_state(order, started=started)[0])
    assert states.count(delivery.NEVER) == 0, "a blank column must never read as NEVER"
    assert states.count(delivery.DOWNLOADED) == 4, "the four with a cached PDF were collected"
    assert states.count(delivery.UNKNOWN) == 10


def test_the_two_screens_agree_order_by_order(production_shape):
    """The whole point. Every order, both screens, same answer - not just the totals."""
    from app.admin import orders as admin_orders
    from app.payments import store

    started = delivery.tracking_started()
    for order_id in production_shape["collected"] + production_shape["uncollected"]:
        order = store.get_order(order_id)
        state, when = delivery.download_state(order, started=started)
        page = admin_orders.downloaded_at(order)
        if state == delivery.DOWNLOADED:
            assert page is not None, f"{order_id}: report says collected, Orders page says nothing"
            assert abs(page - when) < 1.0
        else:
            assert page is None, f"{order_id}: Orders page claims a download the report cannot see"


def test_remind_never_emails_an_order_whose_state_is_unknown(production_shape):
    """--remind is the dangerous half: it writes to customers.

    An unknown state must never produce an e-mail telling somebody they did not collect a report they may
    well have. Checked through should_remind, which is the gate every send passes.
    """
    from app.payments import store

    now = time.time()
    for order_id in production_shape["collected"] + production_shape["uncollected"]:
        order = store.get_order(order_id)
        assert delivery.should_remind(order, now=now, after_hours=24) is False, (
            f"{order_id}: would be e-mailed, state is "
            f"{delivery.download_state(order)[0]}")


def test_an_order_that_really_was_never_collected_is_still_chased(production_shape):
    """The guard must not become "never remind anybody", which would pass every test above.

    Once the column HAS recorded a download, tracking is demonstrably working, and an order paid after
    that moment with nothing to show for it genuinely was never collected.
    """
    from app.payments import store

    # The download has to be OLD, not an hour ago: tracking_started() is the earliest stamp there is, and
    # an order paid before that moment is correctly unknown rather than never. The first version of this
    # test stamped a download an hour ago and expected NEVER for an order paid 48 hours ago - which the
    # classifier rightly called unknown, because at the time it was paid nothing was being recorded.
    collected = seed_paid_order(paid_hours_ago=400)
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET downloaded_at = ? WHERE id = ?",
                     (time.time() - 300 * HOUR, collected["id"]))
    assert delivery.tracking_started() is not None
    missed = seed_paid_order(paid_hours_ago=48)
    order = store.get_order(missed["id"])
    assert delivery.download_state(order)[0] == delivery.NEVER
    assert delivery.should_remind(order, now=time.time(), after_hours=24) is True
    assert collected["id"]


def test_a_second_download_does_not_move_the_answer(production_shape):
    """The question is "did they ever get it"."""
    from app.payments import store

    order = seed_paid_order(paid_hours_ago=50)
    assert store.mark_downloaded(order["report_id"]) is True
    first = store.get_order(order["id"])["downloaded_at"]
    assert store.mark_downloaded(order["report_id"]) is False
    assert store.get_order(order["id"])["downloaded_at"] == first
