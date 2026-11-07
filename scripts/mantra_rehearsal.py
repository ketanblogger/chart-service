#!/usr/bin/env python3
"""Walk a release morning end to end, with the clock frozen. Reads only; writes nothing.

    .venv/bin/python scripts/mantra_rehearsal.py                 # every morning of the window
    .venv/bin/python scripts/mantra_rehearsal.py --date 2026-11-09

WHY REHEARSE AT ALL. The release gate is a pure function of the date, which is what makes it
trustworthy and also what makes it untested on any ordinary day: every check runs against a
population that is empty until 9 November 2026. That is exactly how `i18n.resolve()` came to return
None for all forty text pages while the pages themselves answered 200 - the reverse index was built
at import from the released set. Nothing was wrong with the pages; nothing was testing them.

So this stands on each morning of the window and walks what a reader and a crawler actually touch:
the page, the PDF, the hub listing, the sitemap entry, the hreflang set, and what IndexNow is owed.
It asserts rather than prints where it can, and exits non-zero on the first thing that is wrong.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
      "xhtml": "http://www.w3.org/1999/xhtml"}


def check(ok: bool, label: str, detail: str = "") -> bool:
    print(f"    {'ok  ' if ok else 'FAIL'} {label}{(' - ' + detail) if detail and not ok else ''}")
    return ok


def rehearse(day: dt.date) -> bool:
    from fastapi.testclient import TestClient
    from pypdf import PdfReader

    from app.main import app
    from app.mantra import submitted, texts as T
    from app.web import i18n

    T.today = lambda: day          # the one seam the gate reads
    client = TestClient(app)
    live = T.live(day)
    due = T.released_on(day)
    print(f"  === {day:%A %d %B %Y}: {len(live)} text(s) live, {len(due)} released this morning")
    good = True

    # What a crawler sees.
    sitemap = ET.fromstring(client.get("/sitemap.xml").text).findall("sm:url", NS)
    sets = {u.find("sm:loc", NS).text:
            {l.get("hreflang"): l.get("href") for l in u.findall("xhtml:link", NS)}
            for u in sitemap}
    mantra_urls = {loc: links for loc, links in sets.items() if "/mantra" in loc}
    good &= check(len(mantra_urls) == 2 + 2 * len(live),
                  f"sitemap lists {len(mantra_urls)} mantra URLs", "expected 2 hubs + 2 per text")

    for loc, links in mantra_urls.items():
        path = urlsplit(loc).path
        resolved = i18n.resolve(path)
        good &= check(resolved is not None, f"the registry resolves {path}")
        if resolved:
            good &= check(set(links) == {*i18n.page_langs(resolved[0]), "x-default"},
                          f"hreflang set for {path}", str(sorted(links)))
        good &= check("mr" not in links, f"no Marathi twin claimed for {path}")

    # What a reader touches, for each text live this morning.
    for text in live:
        for lang in ("hi", "en"):
            path = i18n.url_for("mantra", lang, slug=text.slug)
            page = client.get(path)
            good &= check(page.status_code == 200, f"GET {path}", str(page.status_code))
            if page.status_code != 200:
                continue
            body = page.text
            name = text.names[lang]
            good &= check(name in body, f"{path} names the text")
            verses = T.verses(text.slug)
            import html as H
            unescaped = H.unescape(body)
            missing = [v["n"] for v in verses if v["text"] not in unescaped]
            good &= check(not missing, f"{path} carries all {len(verses)} padas",
                          f"missing {missing[:4]}")
            pdf = client.get(f"{path}.pdf")
            good &= check(pdf.status_code == 200
                          and pdf.headers.get("content-type") == "application/pdf",
                          f"GET {path}.pdf")
            if pdf.status_code == 200:
                good &= check(len(PdfReader(io.BytesIO(pdf.content)).pages) >= 1,
                              f"{path}.pdf has pages")

    # The hub must list exactly what is live, and nothing it links to may 404.
    for lang in ("hi", "en"):
        hub = client.get(i18n.url_for("mantra-hub", lang))
        good &= check(hub.status_code == 200, f"GET the {lang} hub")
        hrefs = re.findall(r'href="(/(?:hi/)?mantra/[a-z-]+)"', hub.text)
        good &= check(len(hrefs) == len(live), f"the {lang} hub lists {len(hrefs)} texts",
                      f"expected {len(live)}")
        dead = [h for h in hrefs if client.get(h).status_code != 200]
        good &= check(not dead, f"every {lang} hub link answers", str(dead[:3]))

    # A text whose date has not arrived must 404, and so must an unverified one.
    not_yet = [t for t in T.PHASE_1 if t.release and t.release > day]
    if not_yet:
        path = i18n.url_for("mantra", "hi", slug=not_yet[0].slug)
        good &= check(client.get(path).status_code == 404,
                      f"{path} still 404s (releases {not_yet[0].release})")
    for slug in ("vishnu-sahasranamam", "lalita-sahasranamam"):
        path = i18n.url_for("mantra", "hi", slug=slug)
        good &= check(client.get(path).status_code == 404, f"{path} 404s (unverified)")

    # What IndexNow is owed. On a normal morning that is this morning's texts.
    owed = submitted.outstanding(day)
    good &= check(len(owed) == 2 * len(live), f"IndexNow is owed {len(owed)} URL(s)",
                  "nothing has been submitted in this rehearsal database")
    return good


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", help="one morning, YYYY-MM-DD; default: every one in the window")
    args = parser.parse_args()

    from app.mantra import texts as T

    if args.date:
        days = [dt.date.fromisoformat(args.date)]
    else:
        dates = sorted({t.release for t in T.PHASE_1 if t.release})
        days = [T.FIRST_RELEASE - dt.timedelta(days=1), *dates,
                dates[-1] + dt.timedelta(days=30)]
    ok = True
    for day in days:
        ok &= rehearse(day)
    print(f"\n  {'ALL CLEAR' if ok else 'SOMETHING IS WRONG'} over {len(days)} morning(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
