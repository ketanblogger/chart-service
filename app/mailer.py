"""Outbound e-mail: one provider, one entry point, and a mode that sends nothing.

| variable                | default | meaning                                                              |
|-------------------------|---------|----------------------------------------------------------------------|
| `REPORT_EMAIL_ENABLED`  | off     | master switch. Off = nothing is ever sent, whatever else is set.      |
| `RESEND_API_KEY`        | -       | a SENDING-ONLY Resend key                                             |
| `EMAIL_FROM`            | -       | `orders@rashikundli.com` or `RashiKundli <orders@rashikundli.com>`.   |
|                         |         | The domain must be the one verified in Resend, or every send 403s.    |
| `EMAIL_REPLY_TO`        | -       | optional; omit and replies go to `EMAIL_FROM`                         |

THIS MODULE NEVER RAISES INTO ITS CALLER. It is called from the payment path, and an e-mail that fails
to send is an inconvenience while an order that fails to complete is lost money - so `send` returns
True or False and logs, and the caller does not branch on it for anything the customer depends on.
Everything a customer needs is reachable without e-mail: the order page link is permanent and works on
any device, which is the fallback for a message that lands in spam or is never sent at all.

With no key, or with the switch off, `send` logs what it WOULD have sent and returns False. That is the
development mode, and it is deliberately indistinguishable to the caller from a provider outage.
"""

import logging
import os

import httpx

log = logging.getLogger(__name__)

API_URL = "https://api.resend.com/emails"
TIMEOUT_SECONDS = 10.0


def enabled() -> bool:
    """The master switch. Off by default so a key alone can never start sending."""
    return os.getenv("REPORT_EMAIL_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _key() -> str:
    return os.getenv("RESEND_API_KEY", "").strip()


def sender() -> str:
    return os.getenv("EMAIL_FROM", "").strip()


def configured() -> bool:
    """True when a real send could actually happen."""
    return bool(enabled() and _key() and sender())


def problems() -> list[str]:
    """Why sending is off, for the production self-check. Empty when it would work."""
    if not enabled():
        return ["REPORT_EMAIL_ENABLED is not set: no e-mail will be sent"]
    missing = [name for name, value in (("RESEND_API_KEY", _key()), ("EMAIL_FROM", sender())) if not value]
    return [f"REPORT_EMAIL_ENABLED is on but {name} is empty: no e-mail will be sent" for name in missing]


def send(to: str, subject: str, text: str) -> bool:
    """Send one plain-text message. True if the provider accepted it. Never raises.

    Plain text on purpose: an HTML mail for a two-line message buys nothing and costs deliverability,
    and these go to people who have just paid, where the spam folder is the expensive outcome.
    """
    address = (to or "").strip()
    if not address:
        return False
    if not configured():
        log.info("e-mail NOT sent (mailer not configured): to=%s subject=%r", address, subject)
        return False
    payload = {"from": sender(), "to": [address], "subject": subject, "text": text}
    reply_to = os.getenv("EMAIL_REPLY_TO", "").strip()
    if reply_to:
        payload["reply_to"] = reply_to
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            response = client.post(API_URL, json=payload, headers={"Authorization": f"Bearer {_key()}"})
    except httpx.HTTPError as exc:                      # DNS, TLS, timeout - the provider is not our problem
        log.warning("e-mail to %s failed: %s: %s", address, type(exc).__name__, exc)
        return False
    if response.status_code >= 400:
        # The body can name the address, never the key - the key is only ever in the header above.
        log.warning("e-mail to %s refused: HTTP %s %s", address, response.status_code, response.text[:200])
        return False
    log.info("e-mail sent to %s: %r", address, subject)
    return True
