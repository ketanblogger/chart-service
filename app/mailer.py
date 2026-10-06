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

from app.masking import mask_email

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
    if os.getenv("MAIL_TEST_MODE", "").strip() == "1":
        return ["MAIL_TEST_MODE=1: sign-in codes are written to the journal instead of being sent - "
                "anyone who can read the log can sign in as anyone"]
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
        log.info("e-mail NOT sent (mailer not configured): to=%s subject=%r", mask_email(address), subject)
        return False
    payload = {"from": sender(), "to": [address], "subject": subject, "text": text}
    reply_to = os.getenv("EMAIL_REPLY_TO", "").strip()
    if reply_to:
        payload["reply_to"] = reply_to
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            response = client.post(API_URL, json=payload, headers={"Authorization": f"Bearer {_key()}"})
    except httpx.HTTPError as exc:                      # DNS, TLS, timeout - the provider is not our problem
        log.warning("e-mail to %s failed: %s: %s", mask_email(address), type(exc).__name__, exc)
        return False
    if response.status_code >= 400:
        # The body can name the address, never the key - the key is only ever in the header above.
        log.warning("e-mail to %s refused: HTTP %s %s", mask_email(address), response.status_code, response.text[:200])
        return False
    log.info("e-mail sent to %s: %r", mask_email(address), subject)
    return True


# ---- the login code ----------------------------------------------------------------------------------

LOGIN_SUBJECT = {
    "en": "{code} is your RashiKundli sign-in code",
    "hi": "{code} - आपका RashiKundli साइन-इन कोड",
    "mr": "{code} - तुमचा RashiKundli साइन-इन कोड",
}
LOGIN_BODY = {
    "en": ("{greeting}\n\n"
           "Your sign-in code for RashiKundli is:\n\n    {code}\n\n"
           "It works once and expires in {minutes} minutes.\n\n"
           "If you did not ask to sign in, nobody can use this code without your inbox - you can ignore "
           "this message.\n\n"
           "We never ask for this code. Nobody from RashiKundli will ever phone or message you about it.\n\n"
           "-- RashiKundli\n{base_url}\n"),
    "hi": ("{greeting}\n\n"
           "RashiKundli के लिए आपका साइन-इन कोड:\n\n    {code}\n\n"
           "यह एक बार चलता है और {minutes} मिनट में ख़त्म हो जाता है।\n\n"
           "अगर आपने साइन-इन नहीं माँगा था, तो आपके इनबॉक्स के बिना इस कोड का कोई उपयोग नहीं - इस संदेश को "
           "अनदेखा कर दीजिए।\n\n"
           "हम यह कोड कभी नहीं माँगते। RashiKundli से कोई भी इसके बारे में आपको फ़ोन या संदेश नहीं करेगा।\n\n"
           "-- RashiKundli\n{base_url}\n"),
    "mr": ("{greeting}\n\n"
           "RashiKundli साठी तुमचा साइन-इन कोड:\n\n    {code}\n\n"
           "तो एकदाच चालतो आणि {minutes} मिनिटांत संपतो.\n\n"
           "तुम्ही साइन-इन मागितले नसेल, तर तुमच्या इनबॉक्सशिवाय या कोडचा काही उपयोग नाही - हा संदेश "
           "दुर्लक्षित करा.\n\n"
           "आम्ही हा कोड कधीही विचारत नाही. RashiKundli कडून कोणीही याबद्दल तुम्हाला फोन किंवा संदेश करणार "
           "नाही.\n\n"
           "-- RashiKundli\n{base_url}\n"),
}
GREETING = {"en": "Hello{name},", "hi": "नमस्ते{name},", "mr": "नमस्कार{name},"}


def send_login_code(to: str, code: str, language: str = "en", name: str = "", minutes: int = 10) -> bool:
    """One sign-in code, in the reader's language.

    TEST MODE. `MAIL_TEST_MODE=1`, or a mailer that is not configured at all, writes the code to the journal
    instead of sending it and reports success. That is what lets this whole flow be driven on a machine whose
    sending domain is not verified yet - without it, every login here would fail for a reason that has
    nothing to do with the code under test. It is gated on an explicit setting and the production self-check
    lists it, because a server that quietly prints sign-in codes into its log instead of mailing them is a
    server handing out accounts to anyone who can read the log.
    """
    language = language if language in LOGIN_SUBJECT else "en"
    greeting = GREETING[language].format(name=f" {name.strip()}" if name and name.strip() else "")
    subject = LOGIN_SUBJECT[language].format(code=code)
    body = LOGIN_BODY[language].format(greeting=greeting, code=code, minutes=minutes,
                                       base_url=os.getenv("BASE_URL", "https://rashikundli.com"))
    if os.getenv("MAIL_TEST_MODE", "").strip() == "1" or not configured():
        log.warning("MAIL TEST MODE: sign-in code for %s is %s (not sent)", mask_email(to), code)
        return True
    return send(to, subject, body)
