"""Post-deploy smoke check. Run it against the public URL after every deploy (and locally before one).

    .venv/bin/python scripts/smoke_check.py https://rashikundli.com             # full check
    .venv/bin/python scripts/smoke_check.py http://127.0.0.1:8000 --no-https    # local uvicorn: skip redirect / HSTS / Secure checks
        options: --chromium (readiness launches the PDF browser), --no-pdf (skip the local PDF render),
                 --expect-payments (payments off or test keys = FAIL, not warning), --sample N (crawl only every Nth URL)

Read-only and free: it never calls the AI and never creates a Razorpay order. Checks: /health + /health/ready,
robots.txt, every sitemap URL of all three language trees (200, indexable, self-canonical, right <html lang>, hreflang
in the page == hreflang in the sitemap, on BASE_URL), old URLs 301 in one hop, HTTP->HTTPS redirect + HSTS, security
headers + CSP, a real chart from the free API (reference kundali), the FREE chart PDF (ungated, noindex, no-store),
paid report API locked (402), /order/* hidden,
payments switch on the pages + webhook endpoint, static caching + gzip, policy-page placeholders, whether the first
real paid sale has happened (the Swiss Ephemeris licence clock, `scripts/first_sale_status.py`), and - when run
on the server itself - a local render of BOTH PDFs (the paid book and the free chart sheet) with "fallback fonts:
none". Exit 0 = no failures (warnings are listed).
"""

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9", "xhtml": "http://www.w3.org/1999/xhtml"}
failures: list[str] = []
warnings: list[str] = []
# Any birth details will do where the check is about the plumbing rather than the astronomy; a city from the
# lookup keeps it the same shape a visitor sends. Never a real person's data.
SAMPLE_BIRTH = {"date": "1990-01-01", "time": "10:00", "city": "Pune"}


def check(ok: bool, label: str, warn_only: bool = False) -> bool:
    print(("  ok    " if ok else ("  WARN  " if warn_only else "  FAIL  ")) + label)
    if not ok:
        (warnings if warn_only else failures).append(label)
    return ok


def meta(html: str, name: str) -> str:
    match = re.search(rf'<meta (?:name|property)="{re.escape(name)}" content="([^"]*)"', html)
    return match.group(1) if match else ""


def canonical(html: str) -> str:
    match = re.search(r'<link rel="canonical" href="([^"]*)"', html)
    return match.group(1) if match else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-deploy smoke check (read-only).")
    parser.add_argument("base_url")
    parser.add_argument("--no-https", action="store_true", help="skip HTTPS redirect / HSTS checks (local runs)")
    parser.add_argument("--alternates", action="store_true", help=argparse.SUPPRESS)  # no-op: every language version is a sitemap entry now
    parser.add_argument("--sample", type=int, default=1, metavar="N", help="crawl every Nth sitemap URL only (default: all 246)")
    parser.add_argument("--chromium", action="store_true", help="ask /health/ready to launch the PDF browser too")
    parser.add_argument("--no-pdf", action="store_true", help="skip the local PDF render")
    parser.add_argument("--expect-payments", action="store_true", help="fail (not warn) when payments are off or on test keys")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    client = httpx.Client(base_url=base, timeout=60, follow_redirects=False, headers={"User-Agent": "astrology-smoke-check"})

    print("[health]")
    health = client.get("/health")
    check(health.status_code == 200 and health.json() == {"status": "ok"}, "/health")
    ready = client.get("/health/ready", params={"chromium": "1"} if args.chromium else None)
    body = ready.json() if ready.headers.get("content-type", "").startswith("application/json") else {}
    for name, item in (body.get("checks") or {}).items():
        check(item["ok"], f"/health/ready {name}: {item['detail']}")
    check(ready.status_code == 200 and bool(body.get("checks")), f"/health/ready -> {ready.status_code}")

    print("[robots.txt + sitemap.xml]")
    robots = client.get("/robots.txt").text
    check(f"Sitemap: {base}/sitemap.xml" in robots, f"robots.txt points to {base}/sitemap.xml (BASE_URL matches the public URL)")
    check("Disallow: /order/" in robots and "Disallow: /api/" in robots, "robots.txt hides /order/ and /api/")
    sitemap = client.get("/sitemap.xml")
    urls = ET.fromstring(sitemap.content).findall("sm:url", NS) if sitemap.status_code == 200 else []
    hreflang = {url.find("sm:loc", NS).text: {link.get("hreflang"): link.get("href") for link in url.findall("xhtml:link", NS)} for url in urls}
    targets = list(hreflang)
    check(len(targets) >= 246 and len(set(targets)) == len(targets), f"sitemap lists {len(targets)} unique URLs (expected 246)")
    trees = {"hi": sum(1 for t in targets if t.startswith(base + "/hi/")), "mr": sum(1 for t in targets if t.startswith(base + "/mr/"))}
    check(trees["hi"] >= 80 and trees["mr"] >= 80, f"all three language trees are listed (hi {trees['hi']}, mr {trees['mr']}, en {len(targets) - trees['hi'] - trees['mr']})")
    readings = [t for t in targets if re.search(r"/(horoscope|hi/rashifal|mr/rashi-bhavishya)/[a-z]+/[a-z0-9-]+$", t)]
    check(len(readings) == 180, f"all 180 rashifal reading URLs are in the sitemap ({len(readings)})")
    multi = {loc: links for loc, links in hreflang.items() if links}
    broken_sets = [loc for loc, links in multi.items() if set(links) != {"en", "hi", "mr", "x-default"} or loc not in links.values()
                   or links["x-default"] != links["en"] or any(hreflang.get(href) != links for href in links.values())]
    check(not broken_sets, f"{len(multi)} URLs carry a complete, reciprocal hreflang set (en / hi / mr / x-default)" + (f" - PROBLEMS: {broken_sets[:3]}" if broken_sets else ""))
    expected_lang = lambda loc: "hi" if loc.startswith(base + "/hi/") else "mr" if loc.startswith(base + "/mr/") else "en"  # noqa: E731
    bad = []
    crawl = targets[::max(1, args.sample)]
    for target in crawl:
        if not target.startswith(base):
            bad.append(f"{target}: not on {base}")
            continue
        response = client.get(target[len(base):] or "/")
        problem = None
        page_links = dict(re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)"', response.text)) if response.status_code == 200 else {}
        if response.status_code != 200:
            problem = f"HTTP {response.status_code}"
        elif "noindex" in response.headers.get("x-robots-tag", "").lower() or "noindex" in meta(response.text, "robots").lower():
            problem = "noindex"
        elif canonical(response.text) != target:
            problem = f"canonical is {canonical(response.text)!r}"
        elif f'<html lang="{expected_lang(target)}"' not in response.text:
            problem = f"<html lang> is not {expected_lang(target)}"
        elif page_links != hreflang[target]:
            problem = "hreflang in the page differs from the sitemap"
        elif not meta(response.text, "description") or "<h1" not in response.text:
            problem = "missing description or h1"
        if problem:
            bad.append(f"{target}: {problem}")
    check(not bad, f"{len(crawl)} sitemap URLs are 200, indexable, self-canonical, in the right language, hreflang consistent" + (f" - PROBLEMS: {bad[:5]}" if bad else ""))
    for old, new in (("/janam-kundali", "/birth-chart"), ("/consultation", "/ai-astrologer"), ("/marathi-kundali", "/mr/kundali"),
                     ("/rashifal/dhanu/today?lang=hi", "/hi/rashifal/dhanu/aaj")):
        moved = client.get(old)
        location = moved.headers.get("location", "")
        check(moved.status_code == 301 and (location == new or location == base + new), f"old URL {old} -> 301 {new}" + ("" if moved.status_code == 301 else f" (got {moved.status_code} {location})"))

    print("[https + security headers]")
    home = client.get("/")
    if not args.no_https:
        check(base.startswith("https://"), "base URL is https")
        host = urlsplit(base).netloc
        try:
            plain = httpx.get(f"http://{host}/", follow_redirects=False, timeout=30)
            check(plain.status_code in (301, 308) and plain.headers.get("location", "").startswith("https://"), f"http://{host}/ redirects to https ({plain.status_code})")
        except httpx.HTTPError as exc:
            check(False, f"http://{host}/ is reachable for the redirect check ({type(exc).__name__})")
        check("max-age=" in home.headers.get("strict-transport-security", ""), "HSTS header present")
        cookie = client.post("/api/consultation/start", json=SAMPLE_BIRTH).headers.get("set-cookie", "")
        check("secure" in cookie.lower() and "httponly" in cookie.lower() and "samesite=lax" in cookie.lower(), "uid cookie is Secure + HttpOnly + SameSite=Lax")
    csp = home.headers.get("content-security-policy", "")
    check("script-src 'self' https://checkout.razorpay.com" in csp and "frame-ancestors 'none'" in csp, "Content-Security-Policy enforced" if csp else "Content-Security-Policy header missing (CSP_MODE?)")
    check(home.headers.get("x-content-type-options") == "nosniff" and home.headers.get("x-frame-options") == "DENY"
          and bool(home.headers.get("referrer-policy")), "nosniff / frame / referrer headers")
    check("server" not in home.headers or "uvicorn" not in home.headers["server"].lower(), "no uvicorn Server header", warn_only=True)
    check(client.get("/docs").status_code == 404, "/docs is hidden (APP_ENV=production)", warn_only=args.no_https)

    print("[free tools]")
    # The published reference chart and what it must produce both come from app/engine/reference.py, so this
    # check and /health/ready cannot drift apart. The LAGNA is deliberately not asserted: that chart's
    # ascendant is disputed between sources by a few minutes of birth time.
    sys.path.insert(0, str(ROOT))
    from app.engine.reference import SELF_CHECK

    reference = SELF_CHECK
    want = reference["expect"]
    chart = client.post("/api/chart", json={"date": reference["date"].isoformat(),
                                            "time": reference["time"].strftime("%H:%M"),
                                            "lat": reference["lat"], "lon": reference["lon"],
                                            "timezone": reference["tz"]})
    data = chart.json() if chart.status_code == 200 else {}
    got = {"sun_sign": (data.get("grahas", {}).get("Sun", {}).get("sign") or {}).get("name"),
           "moon_sign": (data.get("moon_rashi") or {}).get("name"),
           "nakshatra": (data.get("janma_nakshatra") or {}).get("name"),
           "ephemeris": (data.get("meta") or {}).get("ephemeris")}
    check(chart.status_code == 200 and got == want,
          f"POST /api/chart: {reference['name']}'s published chart = {want['sun_sign']} Surya, {want['moon_sign']} "
          f"rashi, {want['nakshatra']} (Swiss Ephemeris files in use)" + ("" if got == want else f" - GOT {got}"))
    for lang, path in (("hi", "/hi/kundli"), ("mr", "/mr/kundali")):
        localized = client.get(path)
        check(localized.status_code == 200 and f'<html lang="{lang}"' in localized.text, f"{path} is served with html lang={lang}")
    static = re.search(r'href="(/static/css/site\.css\?v=\w+)"', home.text)
    asset = client.get(static.group(1)) if static else None
    check(bool(asset) and asset.status_code == 200 and "immutable" in asset.headers.get("cache-control", ""), "versioned static files are cached for a year")
    gz = client.get("/birth-chart", headers={"Accept-Encoding": "gzip"})
    check(gz.headers.get("content-encoding") == "gzip", "HTML is gzipped")
    missing = client.get("/this-page-does-not-exist")
    check(missing.status_code == 404 and "noindex" in missing.headers.get("x-robots-tag", ""), "custom 404 page, noindex")

    print("[paid products stay locked]")
    locked = client.post("/api/report", json={"product": "kundali-report", "language": "en", "birth": SAMPLE_BIRTH})
    check(locked.status_code == 402, f"POST /api/report without payment -> {locked.status_code} (must be 402; anything else: is REPORTS_UNLOCKED set?)")
    order = client.get("/order/" + "A" * 32)
    check(order.status_code == 404, "/order/<unknown token> -> 404")
    check(client.get("/api/payments/order/order_DoesNotExist01").status_code == 404, "order status is not public")

    print("[payments]")
    config = client.get("/api/payments/config").json()
    page = client.get("/birth-chart").text
    on = config.get("enabled") and 'data-pay data-enabled="1"' in page
    check(bool(on), "payments are configured and pay.js is switched on" if on else "payments are OFF: buy buttons show 'launching soon'", warn_only=not args.expect_payments)
    if on:
        check(not config.get("test_mode"), "Razorpay LIVE keys" if not config.get("test_mode") else "Razorpay TEST keys: real customers cannot pay", warn_only=not args.expect_payments)
        hook = client.post("/api/payments/webhook", content=b"{}", headers={"X-Razorpay-Signature": "0" * 64})
        check(hook.status_code == 400, "webhook endpoint rejects a bad signature (secret is set)" if hook.status_code == 400
              else f"webhook endpoint -> {hook.status_code}: RAZORPAY_WEBHOOK_SECRET is not set", warn_only=hook.status_code == 503 and not args.expect_payments)
    check("rzp_" not in page.replace(str(config.get("key_id")), "") and "KEY_SECRET" not in page, "no key material in the page")

    print("[first real sale / Swiss Ephemeris licence]")
    try:  # local state, so this says something only when the check runs on the server itself
        sys.path.insert(0, str(ROOT))
        from app.payments import first_sale

        line = first_sale.summary()
        check(True, line, warn_only=True) if first_sale.status() is None else check(True, line)
    except Exception as exc:  # noqa: BLE001 - never fail a deploy check over a bookkeeping line
        check(True, f"first-sale record not readable from here ({type(exc).__name__})", warn_only=True)

    print("[business details]")
    # Every policy page, not just /contact: the AGPL source offer lives on /about, and a source offer
    # pointing at a placeholder is not an offer (see LICENSE and the launch checklist).
    left = set()
    for page in ("/contact", "/about", "/terms", "/privacy", "/refund-policy", "/disclaimer"):
        left |= set(re.findall(r"\[[A-Z][A-Z ,'/_-]+\]", client.get(page).text))
    left = sorted(left)
    check(not left, "policy pages carry real business details" if not left else f"placeholders still on the policy pages: {left}", warn_only=True)

    # the free chart PDF is ungated, so it is checked over HTTP like any other free page (the render
    # itself is exercised below, without paying for a second browser launch here)
    free_pdf = client.post("/api/chart/pdf", json={"date": "1931-10-15", "time": "06:30", "city": "Miraj",
                                                   "language": "mr"})
    check(free_pdf.status_code in (200, 503) and (free_pdf.status_code == 503
                                                  or free_pdf.content.startswith(b"%PDF-")),
          f"POST /api/chart/pdf (free, no entitlement) -> {free_pdf.status_code}")
    if free_pdf.status_code == 200:
        check(free_pdf.headers.get("x-robots-tag") == "noindex"
              and free_pdf.headers.get("cache-control") == "private, no-store",
              "the free chart PDF is not cached or indexed")

    if not args.no_pdf:
        print("[local PDF render]")
        try:
            sys.path.insert(0, str(ROOT))
            import json

            import pypdf

            from app.pdf import fallback_fonts, html_to_pdf, render_basic_html, render_book, render_report_html

            report = json.loads((ROOT / "tests/fixtures/kundali_book_mr.json").read_text(encoding="utf-8"))
            pdf = render_book(lambda toc_pages: render_report_html(report, names={"self": "केशव"}, toc_pages=toc_pages))
            pages = len(pypdf.PdfReader(__import__("io").BytesIO(pdf)).pages)
            check(pdf.startswith(b"%PDF-") and not fallback_fonts(pdf),
                  f"Marathi sample BOOK rendered on this machine ({pages} pages, {len(pdf) // 1024} KB), fallback fonts: none")

            # the free chart sheet goes through the same browser but a different template, so a deploy that
            # can print the book can still be missing this one
            free = html_to_pdf(render_basic_html(data, language="mr", name="केशव"))
            free_pages = len(pypdf.PdfReader(__import__("io").BytesIO(free)).pages)
            check(free.startswith(b"%PDF-") and not fallback_fonts(free),
                  f"Marathi FREE chart sheet rendered ({free_pages} pages, {len(free) // 1024} KB), fallback fonts: none")
        except Exception as exc:  # noqa: BLE001
            check(False, f"local PDF render failed: {type(exc).__name__}: {str(exc)[:200]}")

    print(f"\n{len(failures)} failure(s), {len(warnings)} warning(s)")
    for line in failures:
        print("  FAIL:", line)
    for line in warnings:
        print("  warn:", line)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
