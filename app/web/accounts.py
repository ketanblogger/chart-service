"""E-mail accounts: one verified address, a six-digit code, no password.

WHY THIS EXISTS. The AI astrologer gives two free answers. Until now those were counted against a cookie, so
two answers were available again in every incognito window - the trial was free in a way it was never meant
to be. Counting them against a VERIFIED ADDRESS is the only version of this that holds, because an address
costs something to make and a cookie costs nothing.

WHAT IT DELIBERATELY IS NOT. There is no password, no profile, no password reset and no account deletion
flow in code: the whole account is a name and an address, and the only thing a session can do is read what
that address already bought and spend credits it already has. A stolen session cookie can therefore do
nothing a forwarded order e-mail could not already do.

THE IDENTITY IS THE NORMALISED ADDRESS, and `account_id()` turns it into the same shape `chat_users.user_id`
already uses. That is the whole trick that makes the free allowance follow the account: every quota rule in
app/ai/chat_store.py is keyed by `user_id`, so handing it an account-derived id makes free_used, paid_balance
and the busy lock account-scoped without one line of the quota logic changing.

NORMALISATION IS A SECURITY CONTROL HERE, not a convenience. `a.b+anything@gmail.com` is the same inbox as
`ab@gmail.com`, so without folding it a single Gmail account yields unlimited free trials - the exact hole
this is closing. Folding is applied ONLY to the domains where it is a documented property of the provider;
doing it everywhere would merge addresses that are genuinely different people.
"""

import hashlib
import hmac
import time
import logging
import re
import secrets
import time

from fastapi import Request, Response

from app import db
from app.ai import chat_identity as identity

log = logging.getLogger("app.accounts")

COOKIE_NAME = "sid"
SESSION_MAX_AGE = 30 * 24 * 3600          # 30 days
ADMIN_SESSION_MAX_AGE = 7 * 24 * 3600     # 7 days: an administrator's cookie is worth more, so it lives less
CODE_TTL_SECONDS = 10 * 60                # the code is dead ten minutes after it is made
MAX_ATTEMPTS = 5                          # wrong guesses against ONE code before it is dead
RESEND_COOLDOWN_SECONDS = 60              # between two codes for one address
CODES_PER_ADDRESS_PER_HOUR = 3            # stops the form being used to mail-bomb somebody
CODES_PER_IP_PER_HOUR = 20                # stops an attacker walking a list of addresses
NEW_ACCOUNTS_PER_IP_PER_DAY = 5           # soft cap: a new account is a new pair of free answers
HOUR = 3600
DAY = 24 * 3600

db.register_schema("accounts", """
CREATE TABLE IF NOT EXISTS accounts (
    email       TEXT PRIMARY KEY,          -- NORMALISED; the identity
    email_given TEXT NOT NULL,             -- as the person typed it, for addressing mail
    name        TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    last_seen   REAL NOT NULL
);
-- `rate_events` is also declared by the consultation schema. Repeated here because the login limits must
-- not depend on the chat package having been imported first: CREATE TABLE IF NOT EXISTS is idempotent, and
-- a rate limit that silently does not exist is worse than one that is declared twice.
CREATE TABLE IF NOT EXISTS rate_events (
    key TEXT NOT NULL,
    ts  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS rate_events_key_ts ON rate_events (key, ts);
CREATE TABLE IF NOT EXISTS login_codes (
    email      TEXT PRIMARY KEY,           -- one live code per address; a new one replaces the old
    code_hash  TEXT NOT NULL,              -- never the code itself: this file sits beside the orders
    name       TEXT NOT NULL DEFAULT '',
    expires_at REAL NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
""")


class RateLimited(Exception):
    """Too many codes for this address or this network. Carries the wait in seconds."""

    def __init__(self, retry_after: int):
        super().__init__("rate limited")
        self.retry_after = retry_after


class Rejected(Exception):
    """The address cannot hold an account - malformed, or a disposable domain."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# ---- the address ------------------------------------------------------------------------------------

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s.]+(\.[^@\s.]+)+$")

# Providers that DOCUMENT dots-and-plus as the same inbox. Folding anywhere else would merge two different
# people: at most providers `a.b@` and `ab@` are separate mailboxes.
_DOT_AND_PLUS = {"gmail.com", "googlemail.com"}
_PLUS_ONLY = {"outlook.com", "hotmail.com", "live.com", "yahoo.com", "proton.me", "protonmail.com", "icloud.com"}
_ALIASES = {"googlemail.com": "gmail.com"}

# Throwaway-inbox providers. A short, high-traffic list rather than a pretence at completeness: a blocklist of
# disposable domains is never finished, and the free allowance is two answers, so the cost of a miss is two
# answers and not a breach. tests/test_accounts.py asserts the shape, not the length.
_DISPOSABLE = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "sharklasers.com", "grr.la",
    "10minutemail.com", "10minutemail.net", "tempmail.com", "temp-mail.org", "tempmailo.com",
    "yopmail.com", "yopmail.fr", "trashmail.com", "trashmail.de", "getnada.com", "nada.email",
    "dispostable.com", "maildrop.cc", "mailnesia.com", "throwawaymail.com", "fakeinbox.com",
    "mohmal.com", "emailondeck.com", "spamgourmet.com", "mytemp.email", "tempr.email",
    "burnermail.io", "mailsac.com", "inboxkitten.com", "harakirimail.com", "moakt.com",
}


def split(email: str) -> tuple[str, str]:
    local, _, domain = email.strip().lower().rpartition("@")
    return local, _ALIASES.get(domain, domain)


def normalise(email: str) -> str:
    """The identity of an address: one string per INBOX, not per spelling.

    `Asha.Vernekar+chat@GoogleMail.com` and `ashavernekar@gmail.com` are one inbox and therefore one account.
    Without this a single Gmail account is an unlimited supply of free trials, which is the hole this whole
    feature closes - so the folding is part of the control, not a nicety."""
    local, domain = split(email)
    if domain in _DOT_AND_PLUS:
        local = local.split("+", 1)[0].replace(".", "")
    elif domain in _PLUS_ONLY:
        local = local.split("+", 1)[0]
    return f"{local}@{domain}"


def valid(email: str) -> bool:
    return bool(_EMAIL.match(email.strip())) and len(email.strip()) <= 254


def is_disposable(email: str) -> bool:
    return split(email)[1] in _DISPOSABLE


def check(email: str) -> str:
    """The normalised address, or `Rejected` with a reason the page can translate."""
    if not valid(email):
        raise Rejected("invalid")
    if is_disposable(email):
        raise Rejected("disposable")
    return normalise(email)


def account_id(email: str) -> str:
    """The chat identity for an account, in the shape `chat_users.user_id` already uses.

    32 hex characters, like `chat_identity.new_user_id()`, so every quota rule keyed by `user_id` applies to
    the account with no change - and an HMAC rather than the address itself, so the consultation tables never
    hold an e-mail address."""
    return identity._mac("acct", normalise(email))[:32]


# ---- the code ---------------------------------------------------------------------------------------


def _hash(email: str, code: str) -> str:
    """Salted by the address, so one stolen table row cannot be matched against a rainbow table of 10^6."""
    return hashlib.sha256(f"{email}\x1f{code}".encode()).hexdigest()


def _rate(conn, key: str, limit: int, window: int) -> None:
    cutoff = time.time() - window
    conn.execute("DELETE FROM rate_events WHERE ts <= ?", (cutoff,))
    rows = conn.execute("SELECT ts FROM rate_events WHERE key = ? AND ts > ? ORDER BY ts", (key, cutoff)).fetchall()
    if len(rows) >= limit:
        raise RateLimited(int(rows[0]["ts"] + window - time.time()) + 1)


def request_code(email: str, name: str, ip_key: str) -> str:
    """Make and store a code for this address, and return it to the caller to send.

    Returned rather than mailed here so the sending stays in one place (app/mailer.py) and so a test can
    assert on the code without reading mail. The code is stored HASHED; this return value is the only time
    it exists in the clear."""
    normalised = check(email)
    now = time.time()
    with db.transaction() as conn:
        existing = conn.execute("SELECT created_at FROM login_codes WHERE email = ?", (normalised,)).fetchone()
        if existing and now - existing["created_at"] < RESEND_COOLDOWN_SECONDS:
            raise RateLimited(int(RESEND_COOLDOWN_SECONDS - (now - existing["created_at"])) + 1)
        _rate(conn, f"otp:{normalised}", CODES_PER_ADDRESS_PER_HOUR, HOUR)
        _rate(conn, f"otpip:{ip_key}", CODES_PER_IP_PER_HOUR, HOUR)

        code = f"{secrets.randbelow(1_000_000):06d}"
        conn.execute("INSERT INTO login_codes (email, code_hash, name, expires_at, attempts, created_at) "
                     "VALUES (?, ?, ?, ?, 0, ?) ON CONFLICT(email) DO UPDATE SET "
                     "code_hash = excluded.code_hash, name = excluded.name, expires_at = excluded.expires_at, "
                     "attempts = 0, created_at = excluded.created_at",
                     (normalised, _hash(normalised, code), (name or "").strip()[:60], now + CODE_TTL_SECONDS, now))
        conn.execute("INSERT INTO rate_events (key, ts) VALUES (?, ?)", (f"otp:{normalised}", now))
        conn.execute("INSERT INTO rate_events (key, ts) VALUES (?, ?)", (f"otpip:{ip_key}", now))
    return code


def verify_code(email: str, code: str, ip_key: str = "") -> str | None:
    """The normalised address on success, None on any failure. Single use; five attempts; ten minutes.

    Every failure answers the same None - a caller that distinguished "no such code" from "wrong code" would
    tell an attacker which addresses have asked to log in."""
    normalised = normalise(email.strip()) if valid(email) else ""
    if not normalised or not re.fullmatch(r"\d{6}", (code or "").strip()):
        return None
    now = time.time()
    with db.transaction() as conn:
        row = conn.execute("SELECT code_hash, name, expires_at, attempts FROM login_codes WHERE email = ?",
                           (normalised,)).fetchone()
        if not row or row["expires_at"] < now or row["attempts"] >= MAX_ATTEMPTS:
            return None
        if not hmac.compare_digest(row["code_hash"], _hash(normalised, code.strip())):
            conn.execute("UPDATE login_codes SET attempts = attempts + 1 WHERE email = ?", (normalised,))
            return None
        conn.execute("DELETE FROM login_codes WHERE email = ?", (normalised,))   # single use

        # THE THIRD LAYER. Alias folding and the disposable list stop one person reusing one inbox; neither
        # stops them opening real inboxes, and every new account is a fresh pair of free answers. So a
        # network may only CREATE so many accounts a day. Deliberately soft and generous: a shared office,
        # a college or a CGNAT mobile block are all one bucket here, and the cost of being wrong is turning
        # away a real customer, so the cap sits far above any household and the code is still accepted for
        # an account that already exists.
        known = conn.execute("SELECT 1 FROM accounts WHERE email = ?", (normalised,)).fetchone()
        if not known and ip_key:
            cutoff = now - DAY
            made = conn.execute("SELECT COUNT(*) AS n FROM rate_events WHERE key = ? AND ts > ?",
                                (f"newacct:{ip_key}", cutoff)).fetchone()["n"]
            if made >= NEW_ACCOUNTS_PER_IP_PER_DAY:
                log.warning("new-account cap reached for one network bucket")
                raise RateLimited(int(DAY))
            conn.execute("INSERT INTO rate_events (key, ts) VALUES (?, ?)", (f"newacct:{ip_key}", now))

        conn.execute("INSERT INTO accounts (email, email_given, name, created_at, last_seen) "
                     "VALUES (?, ?, ?, ?, ?) ON CONFLICT(email) DO UPDATE SET "
                     "last_seen = excluded.last_seen, "
                     "name = CASE WHEN accounts.name = '' THEN excluded.name ELSE accounts.name END",
                     (normalised, email.strip()[:254], row["name"], now, now))
    return normalised


def account(email: str) -> dict | None:
    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT * FROM accounts WHERE email = ?", (normalise(email),)).fetchone()
    return dict(row) if row else None


# ---- the session ------------------------------------------------------------------------------------


def is_admin(email: str | None) -> bool:
    """True only for an EXACT address on the allowlist.

    NO ALIAS FOLDING HERE, deliberately, and it is the one place on the site where that is true. Everywhere
    else `normalise` folds Gmail dots and +tags so that one person has one account - which is right for a
    customer and wrong for this: with folding, anybody who can add a dot or a +tag to a listed address
    would hold the dashboard. The address that signed in is the address that is checked.
    """
    if not email:
        return False
    from app.web import site

    return email.strip().lower() in site.ADMIN_EMAILS


def session_max_age(email: str | None) -> int:
    return ADMIN_SESSION_MAX_AGE if is_admin(email) else SESSION_MAX_AGE


def sign(email: str, issued_at: float | None = None) -> str:
    """`email.issued_at.mac`. The timestamp is INSIDE the signature, so the lifetime is ours to enforce.

    It used to be `email.mac` with nothing to date it, which meant a session lasted exactly as long as the
    browser chose to keep the cookie - `max_age` is a request, not a rule, and a copied cookie had no
    expiry at all. The old shape is still ACCEPTED below so that nobody is signed out by this change; it is
    no longer issued, and an administrator never has one because the allowlist is new.
    """
    stamp = str(int(issued_at if issued_at is not None else time.time()))
    return f"{email}.{stamp}.{identity._mac('sid2', email, stamp)[:32]}"


def verify_session(value: str | None, now: float | None = None) -> str | None:
    if not value or "." not in value:
        return None
    head, _, signature = value.rpartition(".")
    email, _, stamp = head.rpartition(".")
    if email and stamp.isdigit() and hmac.compare_digest(signature, identity._mac("sid2", email, stamp)[:32]):
        age = (now if now is not None else time.time()) - int(stamp)
        # A clock that has gone backwards is not a reason to refuse a session; one that has run out is.
        return email if age <= session_max_age(email) else None
    # The old timestampless shape, still honoured so that this change signs nobody out. An administrator
    # cannot have one: the allowlist did not exist when these were issued.
    legacy, _, legacy_signature = value.rpartition(".")
    if legacy and hmac.compare_digest(legacy_signature, identity._mac("sid", legacy)[:32]):
        return None if is_admin(legacy) else legacy
    return None


def session_email(request: Request) -> str | None:
    return verify_session(request.cookies.get(COOKIE_NAME))


def _secure_cookies() -> bool:
    """`Secure` only when the site is actually served over https, or a local http dev server could never
    set the cookie at all. In production BASE_URL is https, so this is True there."""
    import os

    return os.getenv("BASE_URL", "").lower().startswith("https://")


def set_session(response: Response, email: str) -> None:
    response.set_cookie(COOKIE_NAME, sign(email), max_age=session_max_age(email), httponly=True,
                        samesite="lax", secure=_secure_cookies(), path="/")


def clear_session(response: Response) -> None:
    """THE DELETION CARRIES THE SAME ATTRIBUTES AS THE COOKIE IT DELETES, which is not a detail.

    A browser matches a Set-Cookie for removal on name, domain and path - and a deletion sent without
    `Secure` on an https site is itself an insecure cookie, which some browsers will refuse outright. Sent
    with only `Path` and `SameSite`, as this was, signing out could leave the session cookie in place.

    It is also the one response that shows the session cookie's attributes WITHOUT signing anyone in, which
    is what lets scripts/smoke_check.py check them on the live site with no side effect at all.
    """
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=_secure_cookies())
