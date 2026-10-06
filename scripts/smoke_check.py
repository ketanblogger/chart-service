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
real paid sale has happened (a milestone, not a licence countdown - `scripts/first_sale_status.py`), and - when run
on the server itself - a local render of BOTH PDFs (the paid book and the free chart sheet) with "fallback fonts:
none". Exit 0 = no failures (warnings are listed).
"""

import argparse
import re
import sys
from pathlib import Path as _Path

# THE REPO ROOT, ON sys.path, BEFORE ANY `app.*` IMPORT.
#
# The deploy runbook says to run this as `.venv/bin/python scripts/smoke_check.py ...`, and Python then puts
# `scripts/` on the path rather than the directory above it - so `import app.pdf.browser` fails with
# ModuleNotFoundError and the browser check skipped itself with a message about "browser settings". The
# script is the thing that knows where it lives, so it is the thing that should say so; requiring a
# PYTHONPATH in front of a documented command is a trap for whoever runs it next.
_ROOT = _Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9", "xhtml": "http://www.w3.org/1999/xhtml"}
failures: list[str] = []
warnings: list[str] = []
skipped: list[str] = []
# Any birth details will do where the check is about the plumbing rather than the astronomy; a city from the
# lookup keeps it the same shape a visitor sends. Never a real person's data.
SAMPLE_BIRTH = {"date": "1990-01-01", "time": "10:00", "city": "Pune"}


def check(ok: bool, label: str, warn_only: bool = False) -> bool:
    print(("  ok    " if ok else ("  WARN  " if warn_only else "  FAIL  ")) + label)
    if not ok:
        (warnings if warn_only else failures).append(label)
    return ok


def skip(label: str) -> None:
    """A check that could NOT be made here, and why. Neither a pass nor a failure.

    It exists because the alternative is worse than either: the cookie-flag check used to probe an endpoint
    that answers 401 once the sign-in is on, and a tick over a response carrying no cookie is a check that
    has stopped checking while still looking green."""
    print("  skip  " + label)
    skipped.append(label)


def meta(html: str, name: str) -> str:
    match = re.search(rf'<meta (?:name|property)="{re.escape(name)}" content="([^"]*)"', html)
    return match.group(1) if match else ""


def canonical(html: str) -> str:
    match = re.search(r'<link rel="canonical" href="([^"]*)"', html)
    return match.group(1) if match else ""


def _attributes(header: str) -> dict:
    found = {}
    for part in [piece.strip() for piece in header.split(";")][1:]:
        key, _, value = part.partition("=")
        found[key.lower()] = value or True
    return found


def _cookie_flags(client, check) -> None:
    """Both cookies this site sets, in whichever state the sign-in flag is in.

    THE OLD CHECK PROBED A GATED ENDPOINT. It posted to /api/consultation/start and read the `uid` cookie
    off the reply - but with CHAT_LOGIN on that endpoint answers 401 before anything sets a cookie, so it
    was inspecting a response that carries none. A check that cannot see its subject must say so; it must
    not pass, and it must not fail as though the flags were wrong.

    `sid` is read from POST /api/auth/sign-out, which carries the session cookie's full attribute set and is
    free of side effects: there is no session to end, nothing is written, and no mail is sent. Its lifetime
    cannot be read that way (a deletion is Max-Age=0) and is covered by tests/test_cookie_flags.py.
    """
    out = client.post("/api/auth/sign-out")
    flags = _attributes(out.headers.get("set-cookie", ""))
    check(out.status_code == 200 and flags.get("httponly") is True
          and str(flags.get("samesite", "")).lower() == "lax" and flags.get("secure") is True
          and flags.get("path") == "/",
          "sign-in cookie is Secure + HttpOnly + SameSite=Lax + Path=/")

    # `uid` is set by the chat, which may be behind the sign-in. Probe it, and SKIP rather than guess when
    # the gate is closed - the alternative is a green tick over a response with no cookie in it.
    started = client.post("/api/consultation/start", json=SAMPLE_BIRTH)
    if started.status_code == 401:
        skip("uid cookie flags: the chat requires a sign-in (CHAT_LOGIN=on) and no unauthenticated "
             "endpoint sets it without a side effect - covered in both flag states by "
             "tests/test_cookie_flags.py")
        return
    header = started.headers.get("set-cookie", "")
    uid = [part for part in header.split(", ") if part.strip().startswith("uid=")]
    flags = _attributes(uid[0]) if uid else {}
    check(bool(uid) and flags.get("httponly") is True
          and str(flags.get("samesite", "")).lower() == "lax" and flags.get("secure") is True,
          "uid cookie is Secure + HttpOnly + SameSite=Lax")


# An environment gap is not a failure of the site. The browser check needs A browser; when there is none
# it must say so and move on, because a smoke check that goes red over a missing development tool trains
# everyone to ignore it. These are the ways "there is no usable browser here" arrives.
_NO_BROWSER_SIGNS = (
    "executable doesn't exist",          # Playwright's own browser was never downloaded
    "executable does not exist",
    "please run the following command to download new browsers",
    "playwright is not installed",
    "no such file or directory",         # PDF_CHROMIUM_EXECUTABLE points at nothing
    "cannot find chromium",
    # NOT a generic "browsertype.launch" catch-all. That was here and it swallowed every launch failure
    # into a skip, including ones that have nothing to do with a missing browser - a check that can excuse
    # itself for reasons nobody enumerated is a check that will excuse a real breakage. Each sign here
    # names a specific way of saying "there is no browser at that path".
)


def _is_missing_browser(message: str) -> bool:
    """True when the browser could not be STARTED, as opposed to started and then misbehaved."""
    lowered = (message or "").lower()
    return any(sign in lowered for sign in _NO_BROWSER_SIGNS)


def _browser_launch_options(root: Path | None = None) -> dict:
    """The SAME options the app's own PDF renderer launches with.

    `app.pdf.browser.launch_options()` reads `PDF_CHROMIUM_EXECUTABLE` and friends from the environment -
    and this script is a separate process that systemd never handed those to: the service has no
    EnvironmentFile on purpose, because the app loads `/srv/astrology/.env` itself. So the file is loaded
    here too, exactly as `app/web/site.py` does, BEFORE the options are read. Without that the smoke check
    went looking for Playwright's own bundled Chromium, which is not installed on the server and never
    was - while the Chromium the site actually prints with sat there working.
    """
    root = root or Path(__file__).resolve().parents[1]
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env")       # does not override anything already in the environment
    except ImportError:
        pass
    from app.pdf.browser import launch_options

    return launch_options()


def _muhurta_button_downloads(base: str, launcher=None) -> tuple[str, str]:
    """Drive the finder in a real browser and CLICK the download. -> (verdict, detail).

    verdict is "ok", "fail", or "skip". SKIP is only ever for a browser that could not be started; once one
    is running, anything that goes wrong is a FAIL, because then it is the page under test and not the box.

    A cold context: no cookies, no cache, nobody signed in - the state a first-time reader is in, and the
    one in which this is supposed to work.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "skip", "playwright is not installed on this machine"
    try:
        options = _browser_launch_options()
    except Exception as exc:  # noqa: BLE001 - cannot even ask what to launch
        return "skip", f"could not read the browser settings: {type(exc).__name__}: {exc}"[:160]

    with sync_playwright() as play:
        try:
            browser = (launcher or play.chromium.launch)(**options)
        except Exception as exc:  # noqa: BLE001
            message = f"{type(exc).__name__}: {exc}".split(chr(10))[0]
            where = options.get("executable_path") or "playwright's own chromium"
            if _is_missing_browser(message):
                return "skip", f"no usable browser here ({where}): {message}"[:300]
            return "fail", f"the browser would not start ({where}): {message}"[:300]
        # From here on the browser IS running, so nothing below may skip.
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 860}, accept_downloads=True)
            page = context.new_page()
            page.goto(f"{base}/muhurta", wait_until="networkidle")
            page.fill("#m-city", "Pune")
            page.wait_for_timeout(1200)
            if not page.locator("#m-city-list li").count():
                return "fail", "the city list returned nothing"
            page.locator("#m-city-list li").first.click()
            page.click("#m-submit")
            page.wait_for_timeout(3000)
            if not page.locator("#m-table tbody tr").count():
                return "fail", "no dates came back"
            with page.expect_download(timeout=45000) as download:
                page.click("#m-pdf-btn")
            saved = download.value.path()
            head = saved.read_bytes()[:5]
            if head != b"%PDF-":
                return "fail", f"the file did not start with %PDF- ({head!r})"
            return "ok", f"{saved.stat().st_size // 1024} KB"
        except Exception as exc:  # noqa: BLE001 - the browser ran; this is the page's fault
            return "fail", f"{type(exc).__name__}: {exc}".split(chr(10))[0][:200]
        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-deploy smoke check (read-only).")
    parser.add_argument("base_url")
    parser.add_argument("--no-https", action="store_true", help="skip HTTPS redirect / HSTS checks (local runs)")
    parser.add_argument("--alternates", action="store_true", help=argparse.SUPPRESS)  # no-op: every language version is a sitemap entry now
    parser.add_argument("--sample", type=int, default=1, metavar="N", help="crawl every Nth sitemap URL only (default: all 249)")
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
    # 249 since 2026-09-29: /pricing and /delivery-policy, both English-only policy pages, so they add ONE URL
    # each rather than three. It was 247 before that, and 246 before /sidereal-birth-chart (d1d2810). The number
    # is a floor, not an equality, because this runs against a deployed site and a new page is a reason to look,
    # not a reason to fail a post-deploy check - but the printed figure has to be the one this revision expects,
    # or a green line teaches the reader to ignore the count. tests/test_seo.py asserts the exact 249 in-process,
    # which is where an off-by-one belongs, and pins these two literals against the registry.
    check(len(targets) >= 249 and len(set(targets)) == len(targets), f"sitemap lists {len(targets)} unique URLs (expected 249)")
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
        _cookie_flags(client, check)
    csp = home.headers.get("content-security-policy", "")
    check("script-src 'self' https://checkout.razorpay.com" in csp and "frame-ancestors 'none'" in csp, "Content-Security-Policy enforced" if csp else "Content-Security-Policy header missing (CSP_MODE?)")
    check(home.headers.get("x-content-type-options") == "nosniff" and home.headers.get("x-frame-options") == "DENY"
          and bool(home.headers.get("referrer-policy")), "nosniff / frame / referrer headers")
    check("server" not in home.headers or "uvicorn" not in home.headers["server"].lower(), "no uvicorn Server header", warn_only=True)
    check(client.get("/docs").status_code == 404, "/docs is hidden (APP_ENV=production)", warn_only=args.no_https)

    # THE SIGN-IN HAS TO BE FINDABLE. It existed only inside the AI astrologer once, which meant a visitor
    # with an account could not reach it - or their own orders - from anywhere else on the site. Checked on
    # the home page because that is where most visitors arrive, and only when the sign-in is switched on.
    # WHICH STATE THE SIGN-IN IS IN, read off the PAGE rather than inferred from a side effect.
    #
    # This used to be "did POST /start answer 401", and anything that was not a 401 was taken to mean the
    # sign-in was switched off. On the live server that probe came back as something else - a rate limit,
    # most likely, since this script makes a few hundred requests from one address - and the check
    # announced "CHAT_LOGIN=off" on a box where it was plainly on, then skipped the three checks it exists
    # for. A diagnosis drawn from one status code that has several causes is a guess with a confident
    # voice.
    #
    # The home page's own sign-in control is unambiguous: it is rendered when, and only when, the sign-in
    # is on. The chat probe is still made, and now DISAGREEING with the page is itself a failure - that
    # really would mean the two halves of the feature are in different states.
    sign_in_offered = 'class="site-account__in"' in home.text
    probe = client.post("/api/consultation/start", json=SAMPLE_BIRTH)
    if sign_in_offered and probe.status_code not in (401, 429):
        check(False, f"the home page offers a sign-in but the chat let a stranger start one "
                     f"(POST /api/consultation/start -> {probe.status_code})")
    if sign_in_offered:
        check('class="site-account__in"' in home.text and "/login" in home.text,
              "the home page offers a way to sign in")
        orders = client.get("/orders", follow_redirects=False)
        check(orders.status_code == 303 and "next=" in orders.headers.get("location", ""),
              "a signed-out visit to /orders goes to sign-in and comes back")
        # The reader's own consultations. This is the endpoint that makes a chat follow the account into a
        # second window, so the thing to check live is that it is not readable WITHOUT one.
        mine = client.get("/api/consultation/mine")
        check(mine.status_code == 401, "the consultation list needs an account (signed out -> 401)")

    else:
        # Genuinely off: no control on the page. Then the chat must really be open, or the two halves
        # disagree and that is worth a failure rather than a shrug.
        check(probe.status_code != 401,
              f"the sign-in is off (no control on the home page) but the chat still demands one "
              f"(POST /api/consultation/start -> {probe.status_code})")
        skip("sign-in checks: the sign-in is switched off (CHAT_LOGIN=off), so there is deliberately "
             "nothing to offer - covered in both flag states by tests/test_account_header.py")

    # THE DASHBOARD MUST NOT EXIST FOR A STRANGER. 404, not 403: a 403 confirms there is something
    # here worth finding. Checked live because the allowlist is read from the SERVER's environment.
    #
    # THIS LOOP USED TO SIT BETWEEN THE `if` ABOVE AND ITS `else`, which Python accepted without a
    # murmur - `for ... else` is real syntax - so the else stopped belonging to the sign-in check and
    # ran on every deploy. That is why the live smoke check announced the sign-in as switched off on a
    # box where it plainly was not, and skipped the three checks it exists for.
    for admin_path in ("/admin", "/admin/usage"):
        answer = client.get(admin_path)
        check(answer.status_code == 404,
              f"{admin_path} does not exist for a visitor who is not an administrator "
              f"(got {answer.status_code})")

    # THE MUHURTA FINDER, WHEN IT IS ON. The feature ships dark, so the check is the flag's own state read
    # off the server rather than a guess: if the page answers, everything it needs must answer too - and if
    # it does not, the pages and the search endpoint must BOTH be absent, because a page hidden while its
    # endpoint still answers is the feature on, not off.
    finder = client.get("/muhurta")
    search_body = {"purpose": "griha-pravesh", "from_date": "2027-03-01", "to_date": "2027-03-31",
                   "lat": 18.5204, "lon": 73.8567, "city": "Pune"}
    if finder.status_code == 200:
        check('class="site-nav__extra"' in home.text and "/muhurta" in home.text,
              "the muhurta finder can be reached from the home page")
        found = client.post("/api/muhurta/search", json=search_body)
        ok = found.status_code == 200 and isinstance(found.json().get("found"), int)
        check(ok, "the muhurta search answers with a count of the days it found")
        # THE WHOLE POINT OF THE FEATURE: a visitor with no account gets the PDF. This client has never
        # signed in, so if this passes on the live server, nothing in the flow is asking for one.
        token = found.json().get("token") if ok else None
        printed = client.post("/api/muhurta/pdf", json={**search_body, "token": token}) if token else None
        check(bool(printed) and printed.status_code == 200
              and printed.headers.get("content-type") == "application/pdf",
              "the muhurta PDF downloads for a visitor who is not signed in")
        # ...AND THE SAME THING BY CLICKING IT. The fetch above passed on the live server while the BUTTON
        # did nothing, because the page was holding a cached script that wired a button id the HTML no
        # longer had. A request proves the endpoint; only a click proves the page.
        if args.chromium:
            verdict, detail = _muhurta_button_downloads(base)
            if verdict == "skip":
                # An environment gap, never a red: the site is not what is missing.
                skip(f"the muhurta PDF BUTTON could not be clicked - {detail}")
            else:
                check(verdict == "ok",
                      f"the muhurta PDF button really downloads when clicked ({detail})")
        else:
            skip("the muhurta PDF BUTTON: pass --chromium to drive a real browser. The fetch above proves "
                 "the endpoint, which is not the same as proving the button")
        check(all(client.get(path).status_code == 200 for path in ("/hi/muhurta", "/mr/muhurta")),
              "the muhurta finder answers in all three languages")
    else:
        dark = (finder.status_code == 404
                and client.post("/api/muhurta/search", json=search_body).status_code == 404)
        check(dark, "the muhurta finder is off, and its search endpoint is off with it")
        skip("muhurta checks: MUHURTA is off, which is the shipping default - covered in both flag states "
             "by tests/test_muhurta_feature.py")

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

    # INFORMATIONAL. This section used to print a countdown that reached "OVERDUE" and read, on a deploy
    # check, like a licence violation in progress. It never was one: the AGPL is one of the Swiss Ephemeris's
    # two licences, and publishing the source of every deploy complies with it for as long as we keep doing it.
    print("[first real sale / Swiss Ephemeris licence - informational, no deadline]")
    try:  # local state, so this says something only when the check runs on the server itself
        sys.path.insert(0, str(ROOT))
        from app.payments import first_sale

        line = first_sale.summary()
        check(True, line, warn_only=True) if first_sale.status() is None else check(True, line)
    except Exception as exc:  # noqa: BLE001 - never fail a deploy check over a bookkeeping line
        check(True, f"first-sale record not readable from here ({type(exc).__name__})", warn_only=True)

    print("[business details]")
    # Every policy page, not just /contact: the AGPL source offer lives on /about, and a source offer
    # pointing at a placeholder is not an offer (see LICENSE and the launch checklist). The list is spelled
    # out rather than derived because it is also the list a payment gateway's reviewer opens by hand -
    # Razorpay refused international payments on 2026-09-29 for "pages missing or not found" - so a page
    # going quietly absent has to fail here. tests/test_seo.py pins it against app/web/policies.py, so it
    # cannot fall behind the registry either.
    left, missing, unlinked = set(), [], []
    footers = {lang: client.get(path).text.split("<footer", 1)[-1]
               for lang, path in (("en", "/"), ("hi", "/hi/"), ("mr", "/mr/"))}
    policies = ("/about", "/contact", "/pricing", "/delivery-policy", "/privacy", "/terms", "/refund-policy", "/disclaimer")
    for page in policies:
        body = client.get(page)
        # Words inside <main>, not the whole document: the nav and footer are 149 words by themselves, so a
        # whole-page floor would pass a page that had lost every word of its own copy. The smallest real
        # policy page is /contact at 131 words of <main>.
        inner = re.search(r"<main.*?</main>", body.text, re.S)
        words = len(re.sub(r"<[^>]+>", " ", inner.group(0) if inner else "").split())
        if body.status_code != 200 or words < 80:
            missing.append(f"{page} -> {body.status_code}, {words} words")
            continue
        left |= set(re.findall(r"\[[A-Z][A-Z ,'/_-]+\]", body.text))
        unlinked += [f'{lang}{page}' for lang, footer in footers.items() if f'href="{page}"' not in footer]
    left = sorted(left)
    check(not missing, f"all {len(policies)} policy pages answer 200 with real copy" if not missing else f"policy pages a reviewer cannot open: {missing}")
    check(not unlinked, "every policy page is linked in the footer in all three languages" if not unlinked else f"not linked in the footer: {unlinked}")
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

    print(f"\n{len(failures)} failure(s), {len(warnings)} warning(s), {len(skipped)} skipped")
    for line in skipped:
        print("  skip: " + line)
    for line in failures:
        print("  FAIL:", line)
    for line in warnings:
        print("  warn:", line)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
