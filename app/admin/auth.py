"""Who may open /admin: HTTP basic auth over HTTPS, a 12-hour session, and a lockout on failed sign-ins.

E-mail OTP is explicitly a later phase. This is the whole gate for now:

1. **HTTP basic auth.** `ADMIN_USER` / `ADMIN_PASSWORD` from `.env`. An unset password means /admin answers
   401 to everybody, including the owner - a dashboard with a default password is worse than no dashboard.
   Both halves are compared with `hmac.compare_digest`, the user name included: comparing a name with `==`
   leaks its length and its prefix through timing, and there is no reason to hand that away.
2. **Over HTTPS.** Basic auth sends the password on every request, in a header, reversibly encoded. On
   http:// that is a password on the wire, so `insecure_transport()` says so and the page prints the
   warning; `BASE_URL` decides, exactly as the Secure cookie flag does elsewhere in this codebase.
3. **A 12-hour session.** A signed cookie (`SESSION_SECRET`, like the public uid cookie) carries the moment
   the credentials were last actually checked. Past `ADMIN_SESSION_HOURS` it is refused and the credentials
   are checked again.

   BE CLEAR ABOUT WHAT THAT BUYS, because basic auth makes it easy to overstate: the browser holds the
   credentials and will re-send them, so this cannot log a live browser out. What it bounds is how long a
   stolen cookie alone is worth anything, and how long a CHANGED OR REMOVED PASSWORD takes to take effect -
   without it, a password pulled out of `.env` after a leak would keep working in every open browser until
   the tab was closed. Twelve hours is the owner's figure.
4. **Lockout on failed sign-ins**, through the limiter that already exists: `rate_events`, written only by
   `app.ai.chat_store.check_rate`. Two keys are counted, because one is not enough. A per-network key
   (`ADMIN_LOGIN_MAX_FAILURES` in `ADMIN_LOGIN_WINDOW_MINUTES`) stops the obvious attack; a global key
   (`ADMIN_LOGIN_MAX_FAILURES_ALL`) still trips when the attempts are spread across many networks, which
   is what a per-IP limit is blind to by construction. Whichever trips, the password is not even compared,
   and both the refusal and the lockout are written to `admin_audit`.

The lock is READ here and WRITTEN only by `check_rate`, so there is one writer to that table and one
sliding-window implementation. `check_rate` prunes non-`free:` keys older than an hour, which is why the
window is documented in minutes: a lockout window longer than an hour would be pruned out from under it.
"""

import hashlib
import hmac
import logging
import os
import time
from base64 import b64decode

from fastapi import HTTPException, Request, Response

from app import db

from . import audit
from .config import get_admin_settings

log = logging.getLogger(__name__)

COOKIE_NAME = "admin_session"
REALM = "RashiKundli admin"
_PER_NETWORK_KEY = "admin-login:%s"
_GLOBAL_KEY = "admin-login:all"


class Locked(HTTPException):
    """Too many failed sign-ins. 429 with Retry-After, and never a hint about the password."""

    def __init__(self, retry_after: int):
        super().__init__(status_code=429, detail="too many failed sign-ins", headers={"Retry-After": str(max(1, retry_after))})
        self.retry_after = retry_after


def insecure_transport() -> bool:
    """True when the site is not on https, i.e. basic auth would send the password in clear."""
    return not os.getenv("BASE_URL", "").strip().lower().startswith("https://")


# ---- the signed session cookie -----------------------------------------------------------------------


def _secret() -> bytes:
    """The same secret the public uid cookie is signed with (app/ai/chat_identity), including its dev
    fallback - so /admin is never the one place that quietly has no secret to sign with."""
    from app.ai import chat_identity

    return chat_identity._secret()  # noqa: SLF001 - one secret, one place that resolves it


def _sign(issued_at: int, user: str) -> str:
    """The signature covers the USER NAME and the password's own hash as well as the timestamp, so a cookie
    stops being valid the moment either is changed - that is what makes "revoke by editing .env" true."""
    settings = get_admin_settings()
    password_hash = hashlib.sha256(settings.password.encode()).hexdigest()
    payload = f"admin\x1f{user}\x1f{password_hash}\x1f{issued_at}"
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]


def issue_session(response: Response, user: str) -> None:
    issued_at = int(time.time())
    settings = get_admin_settings()
    response.set_cookie(COOKIE_NAME, f"{issued_at}.{_sign(issued_at, user)}",
                        max_age=int(settings.session_hours * 3600), httponly=True, samesite="strict",
                        secure=not insecure_transport(), path="/admin")


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/admin")


def session_user(request: Request) -> str | None:
    """The admin user this request's cookie proves, or None (missing, tampered, or older than the session)."""
    value = request.cookies.get(COOKIE_NAME) or ""
    issued, _, signature = value.partition(".")
    if not issued.isdigit() or not signature:
        return None
    settings = get_admin_settings()
    if not settings.configured:
        return None
    age = time.time() - int(issued)
    if age < 0 or age > settings.session_hours * 3600:
        return None
    return settings.user if hmac.compare_digest(signature, _sign(int(issued), settings.user)) else None


# ---- the lockout -------------------------------------------------------------------------------------


def _failures_in_window(key: str, seconds: float) -> list[float]:
    """Timestamps of the recent failures under one key. A READ of app/ai/chat_store's table: every write to
    it goes through `check_rate` there, so the sliding window has exactly one implementation."""
    with db.transaction(write=False) as conn:
        rows = conn.execute("SELECT ts FROM rate_events WHERE key = ? AND ts > ? ORDER BY ts",
                            (key, time.time() - seconds)).fetchall()
    return [float(row["ts"]) for row in rows]


def lock_state(ip_key: str) -> int:
    """Seconds this caller must wait, or 0 when it may try. Checked BEFORE the password is compared, so a
    locked-out caller gets no timing signal about whether its guess was close."""
    settings = get_admin_settings()
    window = settings.login_window_minutes * 60
    for key, limit in ((_PER_NETWORK_KEY % ip_key, settings.login_max_failures),
                       (_GLOBAL_KEY, settings.login_max_failures_all)):
        failures = _failures_in_window(key, window)
        if len(failures) >= limit:
            return max(1, int(failures[0] + window - time.time()) + 1)
    return 0


def note_failure(ip_key: str) -> None:
    """Record one failed sign-in under both keys, through the limiter that owns the table.

    `check_rate` raises once the limit is reached and does not record that attempt; nothing here cares,
    because `lock_state` is what decides, and the attempt that trips the limit has already been refused."""
    from app.ai.chat_store import RateLimited, check_rate

    settings = get_admin_settings()
    window = settings.login_window_minutes * 60
    for key, limit in ((_PER_NETWORK_KEY % ip_key, settings.login_max_failures),
                       (_GLOBAL_KEY, settings.login_max_failures_all)):
        try:
            check_rate(key, limit, window)
        except RateLimited:
            pass


# ---- the dependency every admin route hangs on -------------------------------------------------------


def _basic_credentials(request: Request) -> tuple[str, str] | None:
    header = request.headers.get("authorization") or ""
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return None
    try:
        user, _, password = b64decode(encoded.strip(), validate=True).decode("utf-8", "replace").partition(":")
    except (ValueError, UnicodeDecodeError):
        return None
    return user, password


def _challenge() -> HTTPException:
    """401 with the basic-auth challenge. `X-Robots-Tag` is on the refusal too: an unauthenticated crawler
    that finds /admin should be told not to index it before it is told anything else."""
    return HTTPException(status_code=401, detail="authentication required",
                         headers={"WWW-Authenticate": f'Basic realm="{REALM}", charset="UTF-8"',
                                  "X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store"})


def require_admin(request: Request) -> str:
    """FastAPI dependency: the authenticated admin user name, or a raised 401 / 429.

    Order matters and is the point: configured? -> locked? -> cookie? -> credentials. The lock is checked
    before anything is compared, and a valid cookie skips the comparison entirely so a page full of
    sub-requests does not spend a hash per asset.
    """
    settings = get_admin_settings()
    if not settings.configured:
        log.warning("/admin was opened but ADMIN_PASSWORD is not set, so it is closed to everyone")
        raise _challenge()

    existing = session_user(request)
    if existing:
        return existing

    ip_key = audit.ip_key_of(request)
    wait = lock_state(ip_key)
    if wait:
        audit.record("?", audit.LOCKED_OUT, detail=f"locked out, {wait}s to wait", request=request)
        raise Locked(wait)

    supplied = _basic_credentials(request)
    if supplied is None:
        raise _challenge()          # no header yet: the browser has not been asked. Not a failed attempt.
    user, password = supplied
    ok = hmac.compare_digest(user, settings.user) and hmac.compare_digest(password, settings.password)
    if not ok:
        note_failure(ip_key)
        audit.record(user[:40] or "?", audit.SIGN_IN_REFUSED, request=request)
        log.warning("/admin sign-in refused for user %r", user[:40])
        raise _challenge()
    audit.record(settings.user, audit.SIGN_IN, request=request)
    request.state.admin_new_session = True   # the route turns this into a Set-Cookie on its response
    return settings.user
