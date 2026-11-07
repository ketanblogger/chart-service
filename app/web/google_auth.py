"""Continue with Google: deciding whether a token is a sign-in.

WHAT THIS MODULE IS FOR. Everything here is about REFUSING. A browser hands us a Google ID token and says
"this is me"; the token is a signed statement by Google about somebody, and the only question that matters
is whether it is a statement about this person, to this application, made recently, with an address Google
has actually checked. Get any of those wrong and the answer is an account takeover, so each is a separate
refusal below rather than one combined condition.

The signature is verified by Google's own tokeninfo endpoint, which also rejects a token whose signature
does not match a current Google key. That is a network call on the sign-in path, which is a real cost; it
is accepted because the alternative - carrying a JWKS cache and a JWT verifier of our own - is more code
in exactly the place where a mistake is worst.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

#: Google issues with either spelling, and refusing one would lock out a share of real people.
ISSUERS = ("accounts.google.com", "https://accounts.google.com")

TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
TIMEOUT_SECONDS = 6


def email_from_claims(claims: dict, client_id: str) -> str | None:
    """The verified address this token is about, or None - and None is the answer to every doubt.

    Each check is its own line because each is a different way of being wrong:

    * AUDIENCE. A perfectly valid Google token issued to somebody else's application is not a sign-in
      here. Matched exactly - not "starts with", not "contains" - or a client id of ours with anything
      appended would pass.
    * ISSUER. Somebody else's signing key is somebody else's opinion.
    * VERIFIED. An address Google has not checked is a claim, not an identity; accepting one would let
      anybody sign in as anybody by putting their address in a Google profile.
    * EXPIRY. An old token is a token somebody else may now have.
    """
    if not isinstance(claims, dict) or not client_id:
        return None

    audience = claims.get("aud") or ""
    if audience != client_id:
        log.warning("google sign-in refused: token is for another application")
        return None

    if (claims.get("iss") or "") not in ISSUERS:
        log.warning("google sign-in refused: issuer is not Google")
        return None

    verified = claims.get("email_verified")
    if verified not in (True, "true", "True"):
        log.warning("google sign-in refused: Google has not verified that address")
        return None

    try:
        expires = int(claims.get("exp") or 0)
    except (TypeError, ValueError):
        return None
    if expires <= time.time():
        log.warning("google sign-in refused: the token has expired")
        return None

    email = (claims.get("email") or "").strip()
    return email or None


def verify_id_token(credential: str, client_id: str) -> str | None:
    """Ask Google what this token says, then decide. None for anything that is not a clean yes."""
    if not credential or not client_id:
        return None
    try:
        import httpx

        response = httpx.get(TOKENINFO, params={"id_token": credential}, timeout=TIMEOUT_SECONDS)
        if response.status_code != 200:
            log.warning("google sign-in refused: tokeninfo answered %s", response.status_code)
            return None
        return email_from_claims(response.json(), client_id)
    except Exception:  # noqa: BLE001 - a failure to verify is a refusal, never an acceptance
        log.exception("google sign-in could not be verified")
        return None


__all__ = ["ISSUERS", "email_from_claims", "verify_id_token"]
