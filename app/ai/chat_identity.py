"""Who is chatting, without a login (MVP): a signed cookie plus two anti-abuse keys.

- `uid` cookie: random 128-bit user id + HMAC-SHA256 signature (secret = env SESSION_SECRET). httpOnly,
  SameSite=Lax, Secure on https, 2 years. Free quota and paid balance are stored per user id.
- bucket key: HMAC(birth date + time + rounded place + IP bucket). The free quota is ALSO stored per bucket,
  so clearing cookies and re-entering the same birth details from the same network gives no new free replies.
- IP bucket: IPv4 /24 or IPv6 /48, HMAC'd (raw IPs are never stored). A daily cap of free replies per IP
  bucket bounds what someone gets by varying birth details.

Known limits (accepted for MVP, documented in docs/API.md): a new cookie + different birth details + a new
network gets fresh free messages; people behind one NAT share the per-IP daily cap; a paid balance follows
the cookie (or a live session id), so a customer who clears cookies needs support to restore it.
"""

import hashlib
import hmac
import ipaddress
import logging
import os
import secrets
from pathlib import Path

from fastapi import Request, Response

from .config import ROOT

log = logging.getLogger(__name__)

COOKIE_NAME = "uid"
COOKIE_MAX_AGE = 2 * 365 * 24 * 3600
_generated_secret: bytes | None = None


def _secret() -> bytes:
    """SESSION_SECRET from the environment; otherwise a generated one persisted in var/ (with a warning)."""
    global _generated_secret
    configured = os.getenv("SESSION_SECRET", "").strip()
    if configured:
        return configured.encode()
    if _generated_secret is None:
        path = Path(os.getenv("SESSION_SECRET_FILE", ROOT / "var" / "session_secret"))
        if path.is_file():
            _generated_secret = path.read_bytes().strip()
        else:
            _generated_secret = secrets.token_hex(32).encode()
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(_generated_secret)
                path.chmod(0o600)
            except OSError:
                pass
        log.warning("SESSION_SECRET is not set - using a generated dev secret (%s). Set SESSION_SECRET in production.", path)
    return _generated_secret


def _mac(*parts: str) -> str:
    return hmac.new(_secret(), "\x1f".join(parts).encode(), hashlib.sha256).hexdigest()


def new_user_id() -> str:
    return secrets.token_hex(16)


def sign_user_id(user_id: str) -> str:
    return f"{user_id}.{_mac('uid', user_id)[:32]}"


def verify_cookie(value: str | None) -> str | None:
    """The user id if the cookie is ours and untampered, else None."""
    if not value or "." not in value:
        return None
    user_id, _, signature = value.partition(".")
    if len(user_id) == 32 and hmac.compare_digest(signature, _mac("uid", user_id)[:32]):
        return user_id
    return None


def user_id_from_request(request: Request) -> str | None:
    return verify_cookie(request.cookies.get(COOKIE_NAME))


def set_user_cookie(response: Response, user_id: str) -> None:
    secure = os.getenv("BASE_URL", "").lower().startswith("https://")
    response.set_cookie(COOKIE_NAME, sign_user_id(user_id), max_age=COOKIE_MAX_AGE, httponly=True,
                        samesite="lax", secure=secure, path="/")


def client_ip(request: Request) -> str:
    if os.getenv("TRUST_PROXY", "0").strip() == "1":
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def ip_bucket(ip: str) -> str:
    """HMAC of the /24 (IPv4) or /48 (IPv6) network - coarse on purpose (mobile IPs rotate inside a block)."""
    try:
        address = ipaddress.ip_address(ip)
        prefix = 24 if address.version == 4 else 48
        network = str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False).network_address)
    except ValueError:
        network = ip
    return _mac("ip", network)[:24]


def birth_bucket(birth_date: str, birth_time: str, lat: float, lon: float, ip_key: str) -> str:
    """Same birth details (place rounded to ~10 km) from the same IP bucket -> same free-quota bucket."""
    return _mac("birth", birth_date, birth_time[:5], f"{lat:.1f}", f"{lon:.1f}", ip_key)[:32]
