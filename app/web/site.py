"""Site-wide constants for the public pages.

Brand: RashiKundli, domain rashikundli.com (English at /, Hindi under /hi/, Marathi under /mr/). Everything that names
the business is still read from the environment here, so brand / domain / legal entity stay a configuration change
(deploy/env.production.example), never a code change. The development BASE_URL default stays http://localhost:8000.
Values in [SQUARE BRACKETS] are placeholders that must be replaced before launch; `placeholders_left()` lists the
ones still unset, and the production config check refuses to start while one of them is undecided.
ISOLATION: this is a standalone venture - only this venture's own entity and contact details go here.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")  # idempotent; this module may be imported before app.ai.config


def _env(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


# THE ONE SWITCH FOR THE FULL-WIDTH DESIGN. "on" (the default from 3 October) makes it the design every
# visitor gets on every page that has one; `DESIGN_V2=off` in /srv/astrology/.env and a restart puts the
# previous design back everywhere, with no deploy and nothing to revert. The old templates are all still
# here, and `?design=v1` renders them whatever this is set to - so the rollback can be checked on the live
# site BEFORE it is taken, and a single page can be compared at any time.
DESIGN_V2 = _env("DESIGN_V2", "on").lower() in ("1", "on", "true", "yes")

# COMPULSORY SIGN-IN FOR THE AI ASTROLOGER, and nothing else. The two free answers were counted against a
# cookie, so they were available again in every incognito window; counted against a verified address they are
# two answers per person. `CHAT_LOGIN=off` in /srv/astrology/.env and a restart goes back to the cookie, with
# no deploy - the free tools never ask for a sign-in either way, because they are what brings people here.
CHAT_LOGIN = _env("CHAT_LOGIN", "on").lower() in ("1", "on", "true", "yes")

# The muhurta finder: the engine module, the chat intent, the /muhurta page and the paid PDF, all behind
# one switch. DEFAULT OFF - it ships dark and is turned on deliberately, which is the opposite of the two
# flags above and is why the default is written here rather than inherited. `MUHURTA=on` in
# /srv/astrology/.env and a restart turns it on; removing that line and restarting is the whole rollback.
MUHURTA = _env("MUHURTA", "off").lower() in ("1", "on", "true", "yes")

# "Continue with Google" beside the e-mail code. DEFAULT OFF, like the muhurta finder: it needs a client
# id created in the Google Cloud Console first, and a half-configured sign-in button is worse than none.
# The address is still the identity, so an account made with a code and the same address through Google
# are one account. `GOOGLE_SIGNIN=on` plus `GOOGLE_CLIENT_ID=...` in /srv/astrology/.env and a restart.
GOOGLE_SIGNIN = _env("GOOGLE_SIGNIN", "off").lower() in ("1", "on", "true", "yes")
GOOGLE_CLIENT_ID = _env("GOOGLE_CLIENT_ID", "").strip()

# A SMALL PACK AT THE PAYWALL. The jump from two free answers to Rs 119 is the decision somebody makes
# after asking two questions and liking the answers, and it is a large one; a Rs 49 pack of three is a
# different sort of decision. It carries no report - the two tiers are questions PLUS a Kundali PDF or the
# book, and that is what their price is for - so this does not undercut them.
#
# PRICED AT Rs 29 AND STILL DEFAULT OFF, which is two separate decisions.
#
# Rs 29 was chosen because it splits as cleanly as the rest under the inclusive rate: 24.58 + 4.42 =
# 29.00, the same shape as Rs 59 (50.00 + 9.00) and Rs 299 (253.39 + 45.61), so the total a customer
# reads stays a round number.
#
# The FLAG stays off in code. Turning a paid product on for every visitor is a release, not a default,
# and this file has always said so; making it live is one line in /srv/astrology/.env (`MINI_PACK=on`)
# and a restart, which is also the rollback in reverse. Nothing about the price needs a deploy either:
# `MINI_PACK_PRICE_INR=<n>`, same restart.
MINI_PACK = _env("MINI_PACK", "off").lower() in ("1", "on", "true", "yes")
MINI_PACK_PRICE_INR = max(1, int(_env("MINI_PACK_PRICE_INR", "29") or 29))
MINI_PACK_MESSAGES = max(1, int(_env("MINI_PACK_MESSAGES", "3") or 3))

# WHO MAY SEE THE DASHBOARD. An allowlist of EXACT verified addresses, from the environment - never a
# name in the source, so adding or removing an administrator is a line in .env and a restart rather than a
# deploy. Comma-separated; blank means nobody, which is the safe default for a box that forgot to set it.
ADMIN_EMAILS = tuple(
    part.strip().lower() for part in _env("ADMIN_EMAILS", "").split(",") if part.strip()
)

SITE_NAME = _env("SITE_NAME", "RashiKundli")
SITE_TAGLINE = _env("SITE_TAGLINE", "Accurate Vedic astrology, calculated with Swiss Ephemeris")
PRODUCTION_DOMAIN = "rashikundli.com"  # documentation / deploy templates only - the app always uses BASE_URL

# Who runs the site - printed on /about, /contact, /privacy, /terms, /refund-policy (Razorpay needs these for
# activation, and the E-Commerce Rules expect a seller to be identifiable). Every one of them is an env
# override, so the operator can change any of it without a code edit - and so there is one place to look
# when checking the isolation rule: nothing here may name any other business the proprietor runs.
LEGAL_ENTITY = _env("LEGAL_ENTITY", "Ketan Pujari, sole proprietor, trading as RashiKundli AI")
LEGAL_ADDRESS = _env("LEGAL_ADDRESS", "E504, Greenlands Society, Pimple Saudagar, Pune, Maharashtra - 411027, India")
SUPPORT_EMAIL = _env("SUPPORT_EMAIL", "support@rashikundli.com")
# Support is e-mail only. "" means deliberately none and is a complete answer; "[SUPPORT PHONE]" means nobody
# has decided yet. `placeholders_left()` tells the two apart, so the launch check stops asking about a phone
# we have chosen not to have.
SUPPORT_PHONE = _env("SUPPORT_PHONE", "")
GSTIN = _env("GSTIN", "27CPNPP5754C2ZI")  # printed wherever an Indian GST-registered seller names itself
JURISDICTION = _env("LEGAL_JURISDICTION", "Pune, India")
POLICIES_UPDATED = _env("POLICIES_UPDATED", "21 September 2026")  # shown as "Last updated" on the policy pages

# AGPL source offer. While the deployed site links pyswisseph (GNU AGPL v3 unless the Astrodienst professional
# licence is bought - see LICENSE), section 13 of the AGPL asks that users interacting with
# the site over a network are offered its source. SOURCE_URL is where that source is published.
SOURCE_URL = _env("SOURCE_URL", "https://github.com/ketanblogger/chart-service")

DISCLAIMER = (
    "Astrology is a traditional faith-based practice. Everything on this site is offered for "
    "guidance and reflection only and is not a substitute for professional advice - please consult "
    "qualified professionals for health, legal or financial decisions."
)


def base_url() -> str:
    """Public origin used for canonical and Open Graph URLs (env BASE_URL, no trailing slash)."""
    return os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")


def placeholders_left() -> list[str]:
    """Names of the business details that still hold a [PLACEHOLDER].

    An empty value is NOT a placeholder: `SUPPORT_PHONE = ""` is the decision "e-mail support only", and the
    pages say so in words. Only a literal `[...]` counts as undecided."""
    values = {"LEGAL_ENTITY": LEGAL_ENTITY, "LEGAL_ADDRESS": LEGAL_ADDRESS, "SUPPORT_EMAIL": SUPPORT_EMAIL,
              "SUPPORT_PHONE": SUPPORT_PHONE, "GSTIN": GSTIN, "LEGAL_JURISDICTION": JURISDICTION,
              "SOURCE_URL": SOURCE_URL}
    return [name for name, value in values.items() if "[" in value]


def has_support_phone() -> bool:
    """True only for a real, decided phone number."""
    return bool(SUPPORT_PHONE.strip()) and "[" not in SUPPORT_PHONE


def has_gstin() -> bool:
    return bool(GSTIN.strip()) and "[" not in GSTIN


def support_phone_line() -> str:
    """The contact bullet about the phone - or, when there is no phone, the sentence that says so. Never an
    empty bullet and never a dangling label."""
    if has_support_phone():
        return f"Phone: {SUPPORT_PHONE} (Monday to Friday, 10:00 to 18:00 IST)"
    if "[" in SUPPORT_PHONE:
        return f"Phone: {SUPPORT_PHONE}"
    return "We answer by e-mail only - there is no support phone line."


def gstin_line() -> str:
    return f"GSTIN: {GSTIN}" if GSTIN.strip() else ""


def contact_details() -> str:
    """E-mail, phone (only if there is one) and address as one comma-separated clause, for running text -
    so a missing phone never leaves ", ," in a sentence."""
    parts = [SUPPORT_EMAIL, SUPPORT_PHONE if has_support_phone() else "", LEGAL_ADDRESS]
    return ", ".join(part for part in parts if part.strip())


def has_support_email() -> bool:
    return "[" not in SUPPORT_EMAIL and "@" in SUPPORT_EMAIL
