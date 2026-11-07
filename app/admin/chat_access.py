"""Reading what somebody actually asked the astrologer: the guard and the trail, and nothing else.

THERE IS NO VIEWER HERE ON PURPOSE. The dashboard counts consultations and never shows one, because the
two are different acts: counting is operating a business, and reading a stranger's question about their
marriage is not. If that ever has to happen - a refund dispute, a safety report, a court order - it should
be a deliberate act with a named reason, recorded where it cannot be quietly undone.

So this module provides what such an act would have to pass through, and no way to perform it. A future
viewer must call `authorise` and must be given a reason; without one it cannot start. The authorisation is
written to the admin audit log BEFORE anything is read, so the record exists even if the read fails.
"""

from __future__ import annotations

import logging

from app.admin import audit

log = logging.getLogger(__name__)

MIN_REASON = 20     # a reason shorter than this is not a reason, it is a keystroke


class NotAuthorised(Exception):
    """Raised instead of returning anything. There is no partial access to somebody's words."""


def authorise(actor: str, session_id: str, reason: str, *, request=None) -> None:
    """Record, in the audit log, that `actor` is about to read the contents of one consultation.

    Raises `NotAuthorised` unless the caller is an administrator by the allowlist AND has given a reason
    with something in it. The write happens first and is not conditional on what follows: a log that only
    records successful reads is a log that hides the interesting ones.
    """
    from app.web import accounts

    if not accounts.is_admin(actor):
        raise NotAuthorised("only an administrator on the allowlist may be authorised to read a chat")
    text = (reason or "").strip()
    if len(text) < MIN_REASON:
        raise NotAuthorised(f"a reason of at least {MIN_REASON} characters is required, in writing")
    if not session_id:
        raise NotAuthorised("a specific consultation must be named; there is no bulk access")

    audit.record(actor, "chat.read.authorised", subject=session_id, detail=text[:200],
                 request=request)
    log.warning("chat content authorised for reading: actor=%s session=%s", actor, session_id)


def read(*args, **kwargs):
    """Deliberately not implemented.

    The guard above exists so that building this later is a small, visible change rather than a quiet one.
    Nothing in the product needs it today, and an unused viewer is a door nobody is watching.
    """
    raise NotImplementedError(
        "reading chat content is not built. Add it deliberately, behind `authorise`, with a test that the "
        "audit row is written before anything is read.")
