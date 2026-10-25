"""One e-mail, once, to somebody who opened checkout and did not finish. Never a second.

THE NUMBER THAT PROMPTED IT: of the orders created in the last ninety days, as many were abandoned at
checkout as were paid. Those are people who chose a product, typed their address and stopped - which is
the only step in the funnel where somebody has already decided to buy and then did not.

WHAT THIS IS NOT. It is not a campaign, a sequence, or a discount. One mail, with the same link they
already had, and the mail says it is the only one. The moment a second mail is justified by the first
one's numbers, this file stops being a service to the customer and becomes a reason to distrust every
other mail we send.

BOUNDED AT BOTH ENDS. Nobody is written to within `AFTER_HOURS` of creating the order, because they may
still be at the payment page or deciding. And nobody is written to after `BEFORE_HOURS`, because an
order abandoned a fortnight ago is not a sale waiting to be recovered - it is somebody who decided no,
and a mail about it reads as a company that has been watching.

EVERY REASON TO SAY NO IS ITS OWN LINE, as in app/payments/delivery.py, so that adding a reason later is
adding a line rather than editing a condition somebody has to re-derive.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

#: Not before this long after the order was created. Long enough that a slow payment, a bank page or a
#: second attempt has finished; short enough that the decision is still live.
AFTER_HOURS = 20

#: And not after this long. Two weeks.
BEFORE_HOURS = 14 * 24


def should_mail(order: dict, *, now: float, after_hours: int = AFTER_HOURS,
                before_hours: int = BEFORE_HOURS, created_after: float | None = None) -> bool:
    """Whether this abandoned order is owed its one mail.

    `created_after` is an ABSOLUTE floor and the rolling window cannot replace it: a window measured
    backwards from now says "still live", not "placed after we decided to write about these at all".
    The first live run reaches only orders created after it was switched on, and a fortnight later a
    rolling window alone would quietly sweep in everything that predates that decision.
    """
    if order.get("status") == "paid" or order.get("paid_at"):
        return False                      # they bought it; this would be a mail about nothing
    if order.get("unpaid_mailed_at"):
        return False                      # already written to, once, which is all there is
    if not (order.get("email") and order.get("token")):
        return False                      # nowhere to write, or no link to send
    # INTERNAL AND TEST ORDERS ARE NOT CUSTOMERS. The admin's own test purchases and anything created in
    # test mode would otherwise generate mail to the proprietor about orders he made deliberately.
    from app.payments import internal

    if order.get("reason") in internal.INTERNAL_REASONS or not order.get("live", 1):
        return False
    created = order.get("created_at")
    if not created:
        return False
    if created_after is not None and float(created) < float(created_after):
        return False                      # placed before the period we decided to write about
    age_hours = (now - float(created)) / 3600
    return after_hours <= age_hours <= before_hours


SUBJECT = {
    "en": "Your RashiKundli order is still open",
    "hi": "आपका RashiKundli ऑर्डर अभी खुला है",
    "mr": "तुमची RashiKundli ऑर्डर अजून उघडी आहे",
}

#: The whole message. It states what happened, gives the same link, and says it is the only one - and it
#: offers nothing extra to come back for. A discount here would tell everybody who paid on time that
#: they paid too much.
LEAD = {
    "en": ("You started an order on RashiKundli and it was not completed - no payment was taken.\n\n"
           "If you still want it, the same link finishes it:\n{link}\n\n"
           "If you have changed your mind, nothing is needed. This is the only e-mail we will send "
           "about it."),
    "hi": ("आपने RashiKundli पर ऑर्डर शुरू किया था जो पूरा नहीं हुआ - कोई भुगतान नहीं लिया गया।\n\n"
           "अगर अब भी चाहिए, तो इसी लिंक से पूरा हो जाएगा:\n{link}\n\n"
           "मन बदल गया हो तो कुछ करने की ज़रूरत नहीं। इस बारे में यही एकमात्र ई-मेल है।"),
    "mr": ("तुम्ही RashiKundli वर ऑर्डर सुरू केली होती, ती पूर्ण झाली नाही - कोणतेही पैसे घेतलेले नाहीत।\n\n"
           "अजूनही हवी असेल, तर याच दुव्याने पूर्ण होईल:\n{link}\n\n"
           "विचार बदलला असेल तर काही करायची गरज नाही. याबद्दलचा हा एकमेव ई-मेल आहे."),
}


def compose(order: dict) -> tuple[str, str, str]:
    """(to, subject, body) - the same order link they already have, never a new one.

    A mail that introduced a second way in would be a mail nobody could tell from a phishing attempt,
    which is the reasoning app/payments/order_email.py already follows.
    """
    from app.web import site

    language = order.get("language") if order.get("language") in SUBJECT else "en"
    link = f"{site.base_url().rstrip('/')}/order/{order['token']}"
    return order.get("email") or "", SUBJECT[language], LEAD[language].format(link=link)


def mail_abandoned(after_hours: int = AFTER_HOURS, before_hours: int = BEFORE_HOURS,
                   now: float | None = None, limit: int = 50, dry_run: bool = False,
                   created_after: float | None = None) -> dict:
    """Write once to everybody owed it. -> a small summary, for a log line or a script."""
    import time

    from app import mailer
    from app.payments import store

    now = now or time.time()
    candidates = store.unpaid_with_an_address(after_hours=after_hours, now=now,
                                              before_hours=before_hours, created_after=created_after)
    sent = skipped = 0
    for order in candidates[:limit]:
        if not should_mail(order, now=now, after_hours=after_hours, before_hours=before_hours,
                           created_after=created_after):
            skipped += 1
            continue
        if dry_run:
            sent += 1
            continue
        # THE STAMP IS TAKEN FIRST, the same way round as the delivery reminder: if the send then fails
        # this customer gets no mail, and a missing one costs an e-mail where a duplicated one costs
        # trust.
        if not store.mark_unpaid_mailed(order["id"]):
            skipped += 1
            continue
        to, subject, body = compose(order)
        if to and mailer.send_recorded(to, subject, body).ok:
            sent += 1
        else:
            log.warning("unpaid-order mail for %s could not be sent", order["id"][:12])
    return {"considered": len(candidates), "sent": sent, "skipped": skipped, "dry_run": dry_run,
            "created_after": created_after}


__all__ = ["AFTER_HOURS", "BEFORE_HOURS", "compose", "mail_abandoned", "should_mail"]
