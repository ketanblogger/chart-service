"""Masking an e-mail address, in one place, for anything that writes one somewhere it will be read later.

It lived in `app/admin/metrics.py`, whose docstring already claimed it was used "in every log line" - and the
mailer was logging the raw address, because importing the admin package from the mailer would have pulled the
dashboard's routers into a module that only sends e-mail. Re-homed here so the low-level modules can reach it
without that, and re-exported from `metrics` so the dashboard's spelling (`metrics.mask_email`) still works.
"""


def mask_email(address: str | None) -> str:
    """`k***@gmail.com`. Used on every admin list and in every log line; the full address appears on the order
    detail page ONLY, and that view is written to admin_audit.

    The first character is kept because it is what lets an operator match a customer who has written in,
    which is the entire reason a masked address beats no address. The local part's length is NOT preserved
    (always three stars): with a fixed domain, its length is a real narrowing of who this is."""
    address = (address or "").strip()
    if not address or "@" not in address:
        return "-" if not address else "***"
    local, _, domain = address.partition("@")
    return f"{local[:1]}***@{domain}" if local else f"***@{domain}"
