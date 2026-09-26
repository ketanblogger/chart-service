"""Production hardening (Phase 8): security headers + CSP, gzip, static caching, config check, readiness, error pages.

`install(app)` is called once from app/main.py. Everything is env-driven:

| Env var | Default | Meaning |
|---|---|---|
| `APP_ENV` | `development` | `production` turns the config check from warnings into a refusal to start, and hides /docs |
| `CSP_MODE` | `enforce` | `enforce` / `report-only` / `off`. If the real Razorpay popup is ever blocked, switch to `report-only`, read the browser console, extend `_CSP`, switch back |
| `TRUST_PROXY` | `0` | `1` behind your own reverse proxy: client IP for rate limits comes from X-Forwarded-For (app/ai/chat_identity.py) |

The site has no inline scripts and loads exactly one third-party script (Razorpay's checkout.js, on the Pay click),
so the policy can be strict: scripts only from self + checkout.razorpay.com. Razorpay's popup is an iframe served
from api.razorpay.com / checkout.razorpay.com that talks to *.razorpay.com; `style-src 'unsafe-inline'` is needed for
the width of the guna-milan meter (a style attribute written by render.js) and for checkout.js's injected styles.
scripts/browser_check_payments.py runs the whole purchase flow with this CSP enforced and fails on any violation.
"""

import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]

# Third parties, and only these: Razorpay for checkout, Google Analytics for measurement. GA sends its hits
# with fetch/beacon to *.google-analytics.com (region1.* included) and falls back to an image, so it needs
# connect-src and img-src as well as the script host - a script-src line alone silently drops every pageview.
_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://checkout.razorpay.com https://www.googletagmanager.com",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https://*.razorpay.com https://*.google-analytics.com https://*.googletagmanager.com",
    "font-src 'self' data:",
    "connect-src 'self' https://api.razorpay.com https://lumberjack.razorpay.com https://*.razorpay.com"
    " https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com",
    "frame-src https://api.razorpay.com https://checkout.razorpay.com https://*.razorpay.com",
    "form-action 'self' https://api.razorpay.com",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
])
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")  # Swagger UI loads from a CDN; development only
STATIC_IMMUTABLE = "public, max-age=31536000, immutable"  # URLs carry ?v=<hash of all static files>
STATIC_SHORT = "public, max-age=3600"


def is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() == "production"


def _is_https() -> bool:
    return os.getenv("BASE_URL", "").strip().lower().startswith("https://")


def security_headers(path: str, has_version: bool) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-Frame-Options": "DENY",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(self \"https://api.razorpay.com\" \"https://checkout.razorpay.com\")",
        "Cross-Origin-Opener-Policy": "same-origin-allow-popups",  # Razorpay may open a bank / UPI window
    }
    mode = os.getenv("CSP_MODE", "enforce").strip().lower()
    if mode != "off" and not path.startswith(_DOCS_PATHS):
        headers["Content-Security-Policy-Report-Only" if mode == "report-only" else "Content-Security-Policy"] = _CSP
    if _is_https():
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if path.startswith("/static/"):
        headers["Cache-Control"] = STATIC_IMMUTABLE if has_version else STATIC_SHORT
    return headers


# ---- configuration check ---------------------------------------------------------------------------


def config_problems() -> tuple[list[str], list[str]]:
    """(fatal, warnings) for running as a public site. Pure: reads the environment and the filesystem only."""
    from app.web import site

    fatal, warnings = [], []
    base = os.getenv("BASE_URL", "").strip()
    host = (urlparse(base).hostname or "").lower()
    if not os.getenv("SESSION_SECRET", "").strip():
        fatal.append("SESSION_SECRET is not set (it signs the uid cookie that carries paid balances and purchases)")
    elif len(os.getenv("SESSION_SECRET", "").strip()) < 32:
        warnings.append("SESSION_SECRET is shorter than 32 characters")
    if not base.lower().startswith("https://") or host in ("localhost", "127.0.0.1", ""):
        fatal.append(f"BASE_URL must be the public https:// origin (it is {base or 'not set'!r}): canonicals, sitemap and Secure cookies depend on it")
    if os.getenv("REPORTS_UNLOCKED", "0").strip() == "1":
        fatal.append("REPORTS_UNLOCKED=1 gives every paid report away and lets any visitor spend AI credits")
    var = ROOT / "var"
    try:
        var.mkdir(exist_ok=True)
        probe = var / f".write-test-{os.getpid()}"
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        fatal.append(f"{var} is not writable ({exc}): orders, reports and PDFs live there")

    key = os.getenv("RAZORPAY_KEY_ID", "").strip()
    if not key or not os.getenv("RAZORPAY_KEY_SECRET", "").strip():
        warnings.append("Razorpay keys are not set: buy buttons show 'launching soon'")
    else:
        if key.startswith("rzp_test_"):
            warnings.append("RAZORPAY_KEY_ID is a TEST key: real customers cannot pay")
        if not os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip():
            warnings.append("RAZORPAY_WEBHOOK_SECRET is not set: a customer who closes the tab after paying is only fulfilled by reconcile")
    if not (os.getenv("ANTHROPIC_API_KEY", "").strip() or os.getenv("ANTHROPIC_AUTH_TOKEN", "").strip()):
        warnings.append("ANTHROPIC_API_KEY is not set: paid reports, the consultation and rashifal refresh cannot run")
    # The order-link e-mail is the customer's only route back to a purchase they closed the tab on, so a
    # production box that cannot send is worth saying out loud rather than discovering from a support mail.
    from app import mailer

    warnings.extend(mailer.problems())
    if os.getenv("TRUST_PROXY", "0").strip() != "1":
        warnings.append("TRUST_PROXY is not 1: behind nginx every visitor shares one rate-limit bucket (127.0.0.1)")
    if os.getenv("CSP_MODE", "enforce").strip().lower() != "enforce":
        warnings.append(f"CSP_MODE={os.getenv('CSP_MODE')}: the Content-Security-Policy is not enforced")
    fatal_ram, warn_ram = _pdf_memory_problem()
    fatal.extend(fatal_ram)
    warnings.extend(warn_ram)
    # AGPL section 13: while the site links pyswisseph under the AGPL it must offer its source to the people
    # using it. A source offer pointing at "[PUBLIC SOURCE REPOSITORY URL]" is not an offer, so this is the one
    # placeholder that stops production rather than warning about it (LICENSE explains the position).
    if "[" in site.SOURCE_URL:
        fatal.append("SOURCE_URL is still a placeholder: while this ships under the AGPL, /about must offer the "
                     "real public repository (see LICENSE). Set SOURCE_URL to that URL")
    elif not site.SOURCE_URL.lower().startswith(("https://", "http://")):
        warnings.append(f"SOURCE_URL is not a URL ({site.SOURCE_URL!r}): /about offers the source at that address")
    remaining = [name for name in site.placeholders_left() if name != "SOURCE_URL"]
    if remaining:
        warnings.append("business details still hold placeholders on the policy pages: " + ", ".join(remaining))
    pending = catalogue_pending()
    if pending:
        warnings.append("priced but not generatable yet, so not for sale: " + ", ".join(pending)
                        + " (app/payments/catalogue.py has a price; app/ai/products.py has no product)")
    return fatal, warnings


def catalogue_pending() -> list[str]:
    """Products the price list names but `app/ai` cannot generate yet (a new report lands price-first)."""
    try:
        from app.payments.catalogue import pending_products

        return pending_products()
    except Exception:  # noqa: BLE001 - a config check must never be the thing that breaks
        return []


PDF_RENDER_MB = 450   # measured peak of one 30-60 page book: ~400 MB, rounded up
APP_BASELINE_MB = 600  # the app itself, SQLite, nginx and room for the OS


def total_ram_mb() -> int | None:
    """Physical RAM of this box, or None where we cannot tell (non-Linux)."""
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _pdf_memory_problem() -> tuple[list[str], list[str]]:
    """Printing the Kundali book is the most memory-hungry thing the server does. The concurrency limit is
    machine-wide (app/pdf/browser.py takes a file lock, so uvicorn workers share it), which is what makes
    this arithmetic true rather than per-process wishful thinking."""
    from app.pdf.browser import max_concurrent

    ram, slots = total_ram_mb(), max_concurrent()
    need = APP_BASELINE_MB + PDF_RENDER_MB * slots
    if ram is None or ram >= need:
        return [], []
    message = (f"this box has {ram} MB RAM; printing {slots} Kundali book(s) at once needs about {need} MB "
               f"(~{PDF_RENDER_MB} MB per render plus the app). Lower PDF_MAX_CONCURRENT, or give it more RAM "
               f"or swap - see deploy/README-DEPLOY.md")
    return ([message], []) if slots > 1 else ([], [message])


def check_config() -> None:
    """Development: log what would be wrong in production, quietly. Production: warnings are logged, anything fatal
    is logged CRITICAL and the process refuses to start (systemd then shows the unit as failed with the reason)."""
    fatal, warnings = config_problems()
    if not is_production():
        if fatal or warnings:
            log.info("APP_ENV is not 'production'; %d setting(s) would need attention before going live "
                     "(python -m app.hardening lists them)", len(fatal) + len(warnings))
        return
    for message in warnings:
        log.warning("config: %s", message)
    for message in fatal:
        log.critical("config: %s", message)
    if fatal:
        raise RuntimeError("refusing to start with APP_ENV=production: " + "; ".join(fatal))


# ---- readiness -------------------------------------------------------------------------------------

_chromium_cache: dict = {"at": 0.0, "result": None}
CHROMIUM_CACHE_SECONDS = 600


def readiness(check_chromium: bool = False) -> dict:
    """Deep health: database, Swiss Ephemeris data files (and a real calculation), bundled fonts, writable var/.
    `check_chromium` also launches headless Chromium (about 1.5 s; the result is cached for 10 minutes)."""
    import datetime as dt

    checks: dict[str, dict] = {}

    def run(name, function):
        try:
            checks[name] = {"ok": True, "detail": function()}
        except Exception as exc:  # noqa: BLE001 - a health check reports, it never raises
            checks[name] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"[:200]}

    def database():
        from app import db

        with db.transaction(write=False) as conn:
            conn.execute("SELECT 1").fetchone()
        return "sqlite ok"

    def ephemeris():
        from app import engine

        files = sorted(path.name for path in (ROOT / "app" / "engine" / "ephe").glob("*.se1"))
        if not files:
            raise RuntimeError("no .se1 files in app/engine/ephe")
        # app/engine/reference.py owns the expectation: a published chart, checked on the Sun's sign, the
        # Moon's sign and the nakshatra. Deliberately NOT the lagna - that chart's ascendant is disputed
        # between sources by a few minutes of birth time, and a probe must not be hostage to that.
        ok, detail = engine.self_check()
        if not ok:
            raise RuntimeError(detail)
        return f"{len(files)} data files, {detail}"

    def fonts():
        from app.pdf.render import FONTS_DIR

        names = sorted(path.name for path in FONTS_DIR.glob("*.ttf"))
        if len(names) < 4:
            raise RuntimeError(f"expected 4 bundled fonts, found {names}")
        return f"{len(names)} bundled fonts"

    def storage():
        probe = ROOT / "var" / f".ready-{os.getpid()}"
        probe.parent.mkdir(exist_ok=True)
        probe.write_text("ok")
        probe.unlink()
        return "var/ writable"

    def chromium():
        from app.pdf.browser import chromium_available

        now = time.time()
        if _chromium_cache["result"] is None or now - _chromium_cache["at"] > CHROMIUM_CACHE_SECONDS:
            _chromium_cache.update(at=now, result=chromium_available())
        ok, reason = _chromium_cache["result"]
        if not ok:
            raise RuntimeError(reason)
        return "headless Chromium renders a PDF"

    for name, function in (("database", database), ("ephemeris", ephemeris), ("fonts", fonts), ("storage", storage)):
        run(name, function)
    if check_chromium:
        run("chromium", chromium)
    return {"status": "ok" if all(item["ok"] for item in checks.values()) else "fail", "checks": checks}


# ---- error pages -----------------------------------------------------------------------------------

_ERROR_TEXT = {
    404: ("Page not found", "The page you are looking for does not exist or has moved. The free tools are all still here."),
    500: ("Something went wrong", "An unexpected error happened on our side. Please try again in a minute."),
}


def _wants_html(request: Request) -> bool:
    path = request.url.path
    return request.method in ("GET", "HEAD") and not path.startswith(("/api/", "/static/", "/health"))


def _error_page(request: Request, status: int):
    from app.web.routes import _context, templates

    heading, text = _ERROR_TEXT[status]
    context = _context(request.url.path)
    context.update(heading=heading, text=text)
    response = templates.TemplateResponse(request, "error.html", context, status_code=status)
    response.headers["X-Robots-Tag"] = "noindex"
    response.headers["Cache-Control"] = "no-store"
    return response


def install(app: FastAPI) -> None:
    check_config()
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def _headers(request: Request, call_next):
        response = await call_next(request)
        for name, value in security_headers(request.url.path, "v" in request.query_params).items():
            if name == "Cache-Control" and response.status_code != 200:
                continue
            if name == "Referrer-Policy" and "referrer-policy" in response.headers:
                continue  # /order/{token} sets the stricter no-referrer itself
            response.headers[name] = value
        return response

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404 and _wants_html(request):
            return _error_page(request, 404)
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def _server_error(request: Request, exc: Exception):
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        if _wants_html(request):
            try:
                return _error_page(request, 500)
            except Exception:  # noqa: BLE001 - the error page itself must never be the problem
                pass
        return JSONResponse(status_code=500, content={"detail": {"error": "server_error", "message": _ERROR_TEXT[500][1]}})

    @app.get("/health/ready", include_in_schema=False)
    def ready(chromium: bool = False):
        """Deep health check for deploys and monitoring (`?chromium=1` also launches the PDF browser)."""
        result = readiness(check_chromium=chromium)
        return JSONResponse(result, status_code=200 if result["status"] == "ok" else 503, headers={"Cache-Control": "no-store"})


if __name__ == "__main__":  # .venv/bin/python -m app.hardening  -> what would block / worry a production start
    from app.ai import config as _config  # noqa: F401  (loads .env)

    fatal_problems, warning_list = config_problems()
    for line in fatal_problems:
        print("FATAL  ", line)
    for line in warning_list:
        print("warning", line)
    print("ok" if not (fatal_problems or warning_list) else f"{len(fatal_problems)} fatal, {len(warning_list)} warning(s)")
    raise SystemExit(1 if fatal_problems else 0)
