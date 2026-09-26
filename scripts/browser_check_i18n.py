"""Real-browser check of the three language trees (phone + desktop) with the production CSP enforced.

    LD_LIBRARY_PATH=~/.local/share/astro-chromium/root/usr/lib/x86_64-linux-gnu \
    XDG_DATA_HOME=~/.local/share/astro-chromium/root/usr/share \
    .venv/bin/python scripts/browser_check_i18n.py [OUT_DIR]

(XDG_DATA_HOME only matters on a box without system Devanagari fonts, so the SCREENSHOTS show real glyphs; visitors
use their own device fonts.) Starts the real app in this process on a free port with a temporary database and checks:

  * one tool page per language, submitted for real: /birth-chart (en), /hi/kundali-matching (hi), /mr/kundali (mr) -
    labels, validation messages and the rendered result are in the page language (HI मंगल / शनि, MR मंगळ / शनी);
  * matching BY NAME on the Hindi page: mode toggle, ?mode=name deep link, result from two names, the
    ambiguous-syllable picker and its resubmit, no paid CTA in name mode, back to birth mode;
  * the language switcher: one tap from a page to the same page in the other languages, on a tool page and a reading;
  * a Hindi and a Marathi rashifal reading page, the Hindi daily hub and the Marathi weekly hub;
  * the consultation page in Hindi (form + chat UI strings; no AI call is made);
  * legacy URLs redirect; no horizontal overflow; no console error / CSP violation anywhere.

Exit code 0 = all checks passed. Screenshots land in OUT_DIR (default var/browser_check_i18n) - LOOK at them for
Devanagari shaping and layout.
"""

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "var" / "browser_check_i18n"

_tmp = tempfile.mkdtemp(prefix="i18n-check-")
os.environ.update(APP_DB=f"{_tmp}/app.db", SESSION_SECRET="browser-check", CSP_MODE="enforce")
for _name in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "REPORTS_UNLOCKED"):
    os.environ.pop(_name, None)

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402
from app.pdf.browser import launch_options  # noqa: E402
from app.web import i18n, pages  # noqa: E402

VIEWPORTS = [("mobile", {"width": 390, "height": 844}), ("desktop", {"width": 1280, "height": 900})]

# The form is filled from the city combobox, which only accepts one of the ~124 public cities in
# app/engine/cities.py - so the published reference charts (tests/reference_charts.py), which are given as
# coordinates, cannot be typed into it. These details are ARBITRARY: this script checks the plumbing and
# the language of the page, and every chart-dependent expectation below is read back from the API rather
# than written here. February is kept only so the month name can be checked in Hindi and Marathi.
BIRTH = ("1984-02-19", "09:05", "Pune")
PARTNER = ("1986-11-03", "21:40", "Nagpur")
# A birth the engine flags on both accuracy counts, for the caveats under the chart. Nehru's, which is public and
# already the suite's reference chart (tests/reference_charts.py), entered here as a city like a visitor would.
FLAGGED_BIRTH = ("1889-11-14", "23:30", "Allahabad")


def _clock12(clock: str) -> str:
    """"09:05" -> "9:05 AM" - what an English page prints for that birth time."""
    hour, minute = (int(part) for part in clock.split(":"))
    return f"{hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'}"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    from playwright.sync_api import sync_playwright

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    def check(condition, label):
        print(("  ok   " if condition else "  FAIL ") + label)
        if not condition:
            failures.append(label)

    def fill_person(page, prefix, date, clock, city):
        """The birth form is staged (date, then time, then place), so each field is filled on its own step.
        A second fill starts wherever the last one left off - usually the final step, where Next is hidden -
        so rewind to the first step before walking forward. Both are best-effort: the step nav is absent in
        by-name mode and without JavaScript, and then every field is visible anyway."""
        def rewind():
            back = page.locator("[data-step-back]")
            for _ in range(6):
                if not back.count() or not back.is_visible():
                    return
                back.click()

        def step_to(selector):
            for _ in range(4):
                if page.locator(selector).is_visible():
                    return
                nxt = page.locator("[data-step-next]")
                if not nxt.count() or not nxt.is_visible():
                    return
                nxt.click()

        rewind()
        step_to(f"#{prefix}-date")
        page.fill(f"#{prefix}-date", date)
        step_to(f"#{prefix}-time")
        page.fill(f"#{prefix}-time", clock)
        step_to(f"#{prefix}-city")
        page.fill(f"#{prefix}-city", city[:3].lower())
        page.locator(f"#{prefix}-city-list [role=option]", has_text=city).first.click()

    def no_overflow(page, label):
        wide = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        check(not wide, f"{label}: no horizontal overflow")

    with sync_playwright() as p:
        browser = p.chromium.launch(**{k: v for k, v in launch_options().items() if k != "headless"})
        for name, viewport in VIEWPORTS:
            print(f"[{name}]")
            context = browser.new_context(viewport=viewport, has_touch=(name == "mobile"))
            page = context.new_page()
            logs: list[str] = []
            page.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
            page.on("pageerror", lambda e: logs.append(f"PAGEERROR: {e}"))

            # ---- English tool page ------------------------------------------------------------------------
            response = page.goto(base + i18n.url_for("kundali", "en"))
            check(response.status == 200 and "script-src 'self'" in response.headers.get("content-security-policy", ""),
                  "/birth-chart served with the enforced CSP")
            check(page.evaluate("document.documentElement.lang") == "en" and "Birth Chart" in page.inner_text("h1"), "en: lang + H1")
            fill_person(page, "self", *BIRTH)
            page.click("#submit-btn")
            page.wait_for_selector("#result:not([hidden])")
            result = page.inner_text("#result-body").replace(" ", " ")
            # what the page must show is whatever the API computed for that birth, not a remembered chart
            chart = page.request.post(base + "/api/chart",
                                      data={"date": BIRTH[0], "time": BIRTH[1], "city": BIRTH[2]}).json()
            lagna = chart["lagna"]["sign"]["name"]
            check(lagna in result and "Graha positions" in result and _clock12(BIRTH[1]) in result,
                  f"en: English result ({lagna}, {_clock12(BIRTH[1])})")
            check(f"₹{pages.product_price('kundali')}" in page.inner_text("#cta"), "en: CTA shows the catalogue price")
            no_overflow(page, "en kundali")
            page.screenshot(path=str(OUT / f"en-birth-chart-{name}.png"), full_page=True)

            # ---- accuracy caveats: shown only when the engine flags the chart (~6% of births) ----------------
            check(page.locator(".accuracy").count() == 0, "en: an ordinary chart carries no accuracy caveat")
            fill_person(page, "self", *FLAGGED_BIRTH)  # 1889 Allahabad: 25 km from a sign change, on Madras time
            page.click("#submit-btn")
            page.wait_for_selector(".accuracy")
            flagged = page.inner_text(".accuracy").replace("\u00a0", " ")
            expected = page.request.post(base + "/api/chart",
                                         data={"date": FLAGGED_BIRTH[0], "time": FLAGGED_BIRTH[1],
                                               "city": FLAGGED_BIRTH[2]}).json()["accuracy"]
            km = str(round(expected["lagna_boundary"]["km_to_change_sign"]))
            adjacent = expected["lagna_boundary"]["adjacent_sign"]["name"]
            check(f"{km} km" in flagged and adjacent in flagged,
                  f"en: the place caveat names the distance and the sign it would become ({km} km, {adjacent})")
            check("Madras time" in flagged and "minutes behind" in flagged,
                  "en: the clock caveat names the era and how far it ran from IST")
            check(page.locator(".accuracy p").count() == 2, "en: both caveats shown, and only those two")
            no_overflow(page, "en accuracy caveats")
            page.locator(".accuracy").screenshot(path=str(OUT / f"en-accuracy-caveats-{name}.png"))

            # ---- language switcher: same page, one tap ------------------------------------------------------
            page.click('.lang-switch a[data-lang="mr"]')
            page.wait_for_url("**" + i18n.url_for("kundali", "mr"))
            check(page.evaluate("document.documentElement.lang") == "mr", "switcher: /birth-chart -> /mr/kundali")
            check(page.get_attribute('.lang-switch a[aria-current="true"]', "data-lang") == "mr", "switcher marks मराठी as current")

            # ---- Marathi tool page --------------------------------------------------------------------------
            page.evaluate("sessionStorage.clear()")
            page.reload()
            # The form is staged now, so an empty field is caught by Next on its own step rather than by one
            # submit of the whole form. Same three fields and the same language check; the path to them moved.
            messages = []
            page.click("[data-step-next]")                                    # step 1, no date
            messages += page.locator(".field-error:visible").all_inner_texts()
            page.fill("#self-date", BIRTH[0])
            page.click("[data-step-next]")
            page.click("[data-step-next]")                                    # step 2, no time
            messages += page.locator(".field-error:visible").all_inner_texts()
            page.fill("#self-time", BIRTH[1])
            page.click("[data-step-next]")
            page.click("#submit-btn")                                         # step 3, no city
            messages += page.locator(".field-error:visible").all_inner_texts()
            check(len(messages) == 3 and all("कृपया" in m for m in messages),
                  f"mr: Marathi validation message on each step {messages}")
            page.reload()
            fill_person(page, "self", *BIRTH)
            page.click("#submit-btn")
            page.wait_for_selector("#result:not([hidden])")
            result = page.inner_text("#result-body").replace(" ", " ")
            # the birth month in Marathi, the Marathi labels, and the Marathi spelling of the graha names
            # (तूळ vs तुला is covered properly by tests/test_render_i18n.py, which pins a Tula Moon)
            for expected in ("फेब्रुवारी", "ग्रहस्थिती", "मंगळ", "शनी", "सध्याची महादशा"):
                check(expected in result, f"mr: result shows {expected}")
            check("मंगल " not in result and "शनि " not in result and "Graha positions" not in result, "mr: no Hindi / English forms")
            labels = page.locator("svg.kundali text.kundali__graha").all_text_contents()
            check("चं" in labels and "Mo" not in labels, "mr: Devanagari chart by default")
            no_overflow(page, "mr kundali")
            page.locator("#result").screenshot(path=str(OUT / f"mr-kundali-result-{name}.png"))
            page.screenshot(path=str(OUT / f"mr-kundali-{name}.png"), full_page=True)

            # ---- Hindi matching page: birth details ---------------------------------------------------------
            page.goto(base + i18n.url_for("matching", "hi"))
            check(page.evaluate("document.documentElement.lang") == "hi" and "कुंडली मिलान" in page.inner_text("h1"), "hi: lang + H1")
            fill_person(page, "boy", *BIRTH)
            fill_person(page, "girl", *PARTNER)
            page.click("#submit-btn")
            page.wait_for_selector("#result:not([hidden])")
            result = page.inner_text("#result-body").replace(" ", " ")
            for expected in ("गुण", "नाड़ी", "भकूट", "मंगल दोष", "फ़रवरी" if "फ़रवरी" in result else "फरवरी"):
                check(expected in result, f"hi: matching result shows {expected}")
            check("मंगळ" not in result and "Points" not in result and "Boy" not in result, "hi: no Marathi / English forms")
            check(page.locator("#cta").is_visible() and f"₹{pages.product_price('matching')}" in page.inner_text("#cta"),
                  "hi: report CTA with the catalogue price")
            page.locator("#result").screenshot(path=str(OUT / f"hi-matching-birth-result-{name}.png"))

            # ---- BY NAME ------------------------------------------------------------------------------------
            page.click('.mode-toggle [data-mode="name"]')
            check(page.url.endswith("?mode=name"), "by-name: toggle sets ?mode=name (deep-linkable)")
            check(not page.locator("#boy-date").is_visible() and page.locator("#boy-name").is_visible(),
                  "by-name: only the two name fields are shown")
            check(page.get_attribute("link[rel=canonical]", "href").endswith(i18n.url_for("matching", "hi")), "by-name: canonical unchanged")
            page.click("#submit-btn")
            errors = page.locator(".field-error:visible").all_inner_texts()
            check(len(errors) == 2 and all("नाम" in e for e in errors), f"by-name: Hindi 'enter the name' errors {errors}")
            page.screenshot(path=str(OUT / f"hi-matching-by-name-form-{name}.png"))
            page.fill("#boy-name", "Keshav")
            page.fill("#girl-name", "Tina")
            page.click("#submit-btn")
            page.wait_for_selector("#result:not([hidden])")
            result = page.inner_text("#result-body")
            check("/ 36" in result.replace(" ", " ") and "Keshav" in result and "Tina" in result, "by-name: score UI for the two names")
            check("अधिक सटीक" in result, "by-name: note that birth-details matching is more accurate")
            check(not page.locator("#cta").is_visible(), "by-name: no paid-report CTA (it needs birth charts)")
            chips = page.locator("[data-name-candidate]")
            check(chips.count() >= 2 and chips.first.get_attribute("aria-pressed") == "true", "by-name: ambiguous-syllable picker shown for Tina")
            page.locator("#result").screenshot(path=str(OUT / f"hi-matching-by-name-result-{name}.png"))
            second = chips.nth(1)
            syllable = second.get_attribute("data-syllable")
            with page.expect_response("**/api/matching") as posted:
                second.click()
            check(posted.value.request.post_data_json["girl"].get("syllable") == syllable, f"by-name: picking {syllable} resubmits with that syllable")
            page.wait_for_function("s => { const b = document.querySelector('[data-name-candidate][aria-pressed=true]'); return b && b.dataset.syllable === s; }", arg=syllable)
            check(True, "by-name: the result is redrawn for the chosen syllable")
            page.goto(base + i18n.url_for("matching", "hi") + "#by-name")
            check(page.get_attribute("#tool-form", "data-mode") == "name", "by-name: #by-name deep link opens name mode")
            page.click('.mode-toggle [data-mode="birth"]')
            check(page.locator("#boy-date").is_visible() and not page.url.endswith("mode=name"), "by-name: back to birth details")
            no_overflow(page, "hi matching")

            # ---- rashifal: Hindi reading, switcher to the Marathi reading, hubs -------------------------------
            hindi_reading = i18n.url_for("rashifal-reading", "hi", rashi="tula", period="today")
            page.goto(base + hindi_reading)
            check("Tula Rashi Today" in page.inner_text("h1") and "तुला राशिफल आज" in page.inner_text("h1"), "hi reading: top-query H1")
            body = page.inner_text("main")
            check("2026" in body or "2027" in body, "hi reading: date visible")
            check("शनि" in body and "मंगल" in body and "Graha" not in body, "hi reading: Hindi facts")
            check(page.locator(f'main a[href="{i18n.url_for("kundali", "hi")}"]').count() >= 1
                  and page.locator(f'main a[href="{i18n.url_for("consultation", "hi")}"]').count() >= 1, "hi reading: kundali + consultation links in Hindi")
            no_overflow(page, "hi reading")
            page.screenshot(path=str(OUT / f"hi-rashifal-tula-aaj-{name}.png"), full_page=True)
            page.click('.lang-switch a[data-lang="mr"]')
            page.wait_for_url("**" + i18n.url_for("rashifal-reading", "mr", rashi="tula", period="today"))
            check("तूळ राशिभविष्य" in page.inner_text("h1"), "switcher: Hindi reading -> the same Marathi reading")
            body = page.inner_text("main")
            check("शनी" in body and "मंगळ" in body and "राशिफल" not in body, "mr reading: Marathi facts, says राशिभविष्य")
            pill = page.evaluate("""() => { const ul = document.querySelector('.site-nav ul'), a = ul.querySelector('[aria-current=page]');
                const u = ul.getBoundingClientRect(), r = a.getBoundingClientRect();
                return r.left >= u.left - 1 && r.right <= u.right + 1 && window.scrollY === 0; }""")
            check(pill, "nav: the active item (राशिभविष्य) is scrolled into view, the page itself is not scrolled")
            no_overflow(page, "mr reading")
            page.screenshot(path=str(OUT / f"mr-rashi-bhavishya-tula-aaj-{name}.png"), full_page=True)

            page.goto(base + i18n.url_for("rashifal-hub", "hi"))
            check(page.locator("#hub-cards > li").count() == 12 and "आज का राशिफल" in page.inner_text("h1"), "hi daily hub: 12 rashis")
            first = page.locator("#hub-cards > li h2 a").first.get_attribute("href")
            check(first == i18n.url_for("rashifal-reading", "hi", rashi="tula", period="today"), "hi daily hub: highest-demand rashi (tula) first")
            no_overflow(page, "hi hub")
            page.screenshot(path=str(OUT / f"hi-rashifal-hub-{name}.png"), full_page=True)
            page.goto(base + i18n.url_for("rashifal-weekly", "mr"))
            check(page.locator("#hub-cards > li").count() == 12 and "साप्ताहिक राशिभविष्य" in page.inner_text("h1"), "mr weekly hub: 12 rashis")
            page.screenshot(path=str(OUT / f"mr-rashi-bhavishya-saptahik-{name}.png"), full_page=True)

            # ---- consultation in Hindi + home pages ----------------------------------------------------------
            page.goto(base + i18n.url_for("consultation", "hi"))
            check(page.get_attribute("#tool-form", "data-lang") == "hi" and "AI" in page.inner_text("h1"), "hi consultation: form starts the chat in Hindi")
            no_overflow(page, "hi consultation")
            page.screenshot(path=str(OUT / f"hi-ai-jyotish-{name}.png"), full_page=True)
            for lang in i18n.LANGS:
                page.goto(base + i18n.url_for("home", lang))
                no_overflow(page, f"{lang} home")
                page.screenshot(path=str(OUT / f"{lang}-home-{name}.png"), full_page=True)

            # ---- legacy URLs ------------------------------------------------------------------------------------
            page.goto(base + "/rashifal/tula/3-months?lang=mr")
            check(page.url == base + i18n.url_for("rashifal-reading", "mr", rashi="tula", period="monthly"), "legacy rashifal URL lands on the Marathi monthly page")
            page.goto(base + "/marathi-kundali")
            check(page.url == base + i18n.url_for("kundali", "mr"), "legacy /marathi-kundali lands on /mr/kundali")

            check(not logs, f"no console errors / CSP violations {logs or ''}")
            context.close()
        print("[breakpoints]")  # the header (brand + nav + switcher) must never widen the page, in any language
        for width in (320, 360, 600, 760, 1024, 1080, 1150, 1239, 1240, 1600):
            context = browser.new_context(viewport={"width": width, "height": 800})
            page = context.new_page()
            wide = []
            for lang in i18n.LANGS:
                for key in ("home", "matching", "rashifal-hub"):
                    page.goto(base + i18n.url_for(key, lang))
                    if page.evaluate("document.documentElement.scrollWidth") > width:
                        wide.append(f"{lang}:{key}")
            check(not wide, f"{width}px: no horizontal overflow {wide or ''}")
            context.close()
        browser.close()

    server.should_exit = True
    print(f"\n{'FAILED: ' + str(len(failures)) if failures else 'ALL CHECKS PASSED'} - screenshots in {OUT}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
