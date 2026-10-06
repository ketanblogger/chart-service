"""Phase 7 "done when" check. Run after a real refresh:

    .venv/bin/python scripts/rashifal_refresh.py --period all --force
    .venv/bin/python scripts/rashifal_check.py                 # exit 0 only if everything below holds

Asserts from the store (no server, no AI):
- all 60 (rashi, period) pages are populated in EVERY configured language: 60 x 3 = 180 readings (= 180 URLs);
- each reading is fresh: written for the CURRENT window of its period;
- per language and period the 12 rashis are pairwise distinct (no copy-paste between rashis), and within a page
  the languages are not the same text;
- every reading has its hub summary; the 3 daily + 3 weekly hubs have 12 current summaries each;
- each language's title / H1 (made by code, app/rashifal/i18n.py) is unique across the 180 and uses that
  language's query word (horoscope / राशिफल / राशिभविष्य).
Prints a rashi x period table: generated_at (IST), words per language. `--pages` also fetches the 180 URLs + 6 hubs
in-process through the web layer (app.web owns those routes; off by default while it is being rebuilt).

    .venv/bin/python scripts/rashifal_check.py --snapshot var/rashifal_before.json   # save generated_at + text hashes
    .venv/bin/python scripts/rashifal_check.py --compare  var/rashifal_before.json   # after a 2nd forced run: same 60
                                                                # URLs, content + generated_at changed everywhere
"""

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.rashifal import config, i18n, store  # noqa: E402
from app.rashifal.periods import IST, PERIOD_SLUGS, RASHI_SLUGS, now_ist, url_path, window_for  # noqa: E402
from app.rashifal.prompts import SECTION_IDS  # noqa: E402

MAX_SIMILARITY = 0.5  # share of 4-word sequences two rashis' readings have in common (Jaccard); copy-paste is ~1.0


def body_text(page: dict) -> str:
    return "\n".join([page["headline"], page["overview"], *[p for s in SECTION_IDS for p in page["sections"][s]], page["tip"]])


def shingles(text: str, size: int = 4) -> set:
    words = text.split()
    return {" ".join(words[i:i + size]) for i in range(max(1, len(words) - size + 1))}


def snapshot() -> dict:
    result = {}
    for rashi in RASHI_SLUGS:
        for period in PERIOD_SLUGS:
            page = store.get_page(rashi, period)
            if page:
                text = json.dumps(page["content"], ensure_ascii=False, sort_keys=True)
                result[f"/rashifal/{rashi}/{period}"] = {"generated_at": page["generated_at"],
                                                         "sha": hashlib.sha256(text.encode()).hexdigest()[:16]}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--snapshot", help="write {url: generated_at, content hash} to this file and exit")
    parser.add_argument("--compare", help="compare with a snapshot taken before a second forced run")
    parser.add_argument("--export", help="write every stored reading as readable text files into this directory and exit")
    parser.add_argument("--pages", action="store_true", help="also fetch the 180 page URLs and 6 hubs through the web layer")
    args = parser.parse_args()
    if args.snapshot:
        Path(args.snapshot).write_text(json.dumps(snapshot(), indent=1), encoding="utf-8")
        print(f"snapshot of {len(snapshot())} pages written to {args.snapshot}")
        return 0

    if args.export:
        out = Path(args.export)
        out.mkdir(parents=True, exist_ok=True)
        count = 0
        for rashi in RASHI_SLUGS:
            for period in PERIOD_SLUGS:
                page = store.get_page(rashi, period)
                if not page:
                    continue
                lines = [f"{rashi} / {period} / {page['period_start']} .. {page['period_end']} / generated {page['generated_at']} / {page['model']}", ""]
                for code, content in page["content"].items():
                    lines += [f"===== {code} =====", "HEADLINE: " + content["headline"], "SUMMARY: " + content["summary"],
                              "OVERVIEW: " + content["overview"]]
                    for section in SECTION_IDS:
                        lines += [f"[{section}]"] + content["sections"][section]
                    lines += ["KEY DATES: " + json.dumps(content["key_dates"], ensure_ascii=False), "TIP: " + content["tip"], ""]
                (out / f"{rashi}_{period}.txt").write_text("\n".join(lines), encoding="utf-8")
                count += 1
        print(f"{count} pages exported to {out}/")
        return 0

    now, languages, problems = now_ist(), config.languages(), []
    pages = {(r, p): store.get_page(r, p) for r in RASHI_SLUGS for p in PERIOD_SLUGS}

    print(f"Languages expected: {','.join(languages)}   now: {now:%Y-%m-%d %H:%M} IST\n")
    print(f"{'rashi':11s}" + "".join(f"{period:>30s}" for period in PERIOD_SLUGS))
    for rashi in RASHI_SLUGS:
        cells = []
        for period in PERIOD_SLUGS:
            page = pages[(rashi, period)]
            if not page:
                cells.append("MISSING")
                problems.append(f"{rashi}/{period}: no stored reading")
                continue
            generated = dt.datetime.fromisoformat(page["generated_at"]).astimezone(IST)
            words = "/".join(str(len(body_text(page["content"][code]).split())) if code in page["content"] else "-" for code in languages)
            cells.append(f"{generated:%d-%b %H:%M} {words}w")
            window = window_for(period, now)
            if page["period_start"] != window.key:
                problems.append(f"{rashi}/{period}: stale - written for {page['period_start']}, current window starts {window.key}")
            missing = [code for code in languages if code not in page["languages"]]
            if missing:
                problems.append(f"{rashi}/{period}: missing languages {missing}")
        print(f"{rashi:11s}" + "".join(f"{cell:>30s}" for cell in cells))

    worst: dict = {}
    for period in PERIOD_SLUGS:
        for code in languages:
            texts = {r: shingles(body_text(pages[(r, period)]["content"][code])) for r in RASHI_SLUGS
                     if pages[(r, period)] and code in pages[(r, period)]["content"]}
            names = list(texts)
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    ratio = len(texts[a] & texts[b]) / max(1, len(texts[a] | texts[b]))
                    worst[code] = max(worst.get(code, 0), ratio)
                    if ratio > MAX_SIMILARITY:
                        problems.append(f"{period} [{code}]: {a} and {b} are {ratio:.0%} identical - not rashi-specific")

    print("\nHighest similarity between two rashis' readings (same period), per language: "
          + ", ".join(f"{code} {value:.0%}" for code, value in worst.items()) + f"  (limit {MAX_SIMILARITY:.0%})")

    # within a page the language versions must be different texts, and every reading needs its hub summary
    readings = 0
    for (rashi, period), page in pages.items():
        if not page:
            continue
        texts = [body_text(page["content"][code]) for code in page["content"]]
        if len(set(texts)) != len(texts):
            problems.append(f"{rashi}/{period}: two language versions are the same text")
        for code, content in page["content"].items():
            readings += 1
            if not content.get("summary", "").strip():
                problems.append(f"{rashi}/{period} [{code}]: no hub summary")
    for period in ("today", "weekly"):
        rows, window = store.hub_rows(period), window_for(period, now)
        for code in languages:
            current = [r for r in RASHI_SLUGS if r in rows and rows[r]["period_start"] == window.key and rows[r]["summaries"].get(code)]
            if len(current) != 12:
                problems.append(f"hub {url_path(code, period=period)}: {len(current)}/12 current summaries")
            elif len({rows[r]["summaries"][code] for r in current}) != 12:
                problems.append(f"hub {url_path(code, period=period)}: summaries are not distinct across rashis")

    # titles / H1s are code, not AI: unique across the 180 and in each language's own vocabulary
    titles = {(code, r, p): i18n.page_title(r, p, code) for code in languages for r in RASHI_SLUGS for p in PERIOD_SLUGS}
    h1s = {key: i18n.page_h1(key[1], key[2], key[0]) for key in titles}
    urls = {key: url_path(key[0], key[1], key[2]) for key in titles}
    for name, values in (("title", titles), ("H1", h1s), ("URL", urls)):
        if len(set(values.values())) != len(values):
            problems.append(f"{name}s are not unique across the {len(values)} pages")
    words = {"en": "horoscope", "hi": "राशिफल", "mr": "राशिभविष्य"}
    for (code, r, p), title in titles.items():
        if code in words and (words[code] not in title.lower() or words[code] not in h1s[(code, r, p)].lower()):
            problems.append(f"{urls[(code, r, p)]}: title / H1 lacks '{words[code]}'")
    print(f"\n{readings} readings stored for {len(pages)} pages x {len(languages)} languages = {len(urls)} permanent URLs "
          f"(e.g. {urls[(languages[-1], 'tula', 'today')]}).")

    if args.pages:
        from fastapi.testclient import TestClient  # the real pages, in-process

        from app.main import app

        client, fetched = TestClient(app), 0
        hubs = [url_path(code, period=period) for code in languages for period in ("today", "weekly")]
        for url in list(urls.values()) + hubs:
            response = client.get(url)
            fetched += 1
            if response.status_code != 200:
                problems.append(f"{url}: HTTP {response.status_code}")
        print(f"{fetched} URLs fetched in-process through the web layer.")

    if args.compare:
        before, after = json.loads(Path(args.compare).read_text(encoding="utf-8")), snapshot()
        if set(before) != set(after):
            problems.append(f"URL set changed between runs: {sorted(set(before) ^ set(after))}")
        same_text = [url for url in before if url in after and before[url]["sha"] == after[url]["sha"]]
        same_time = [url for url in before if url in after and before[url]["generated_at"] == after[url]["generated_at"]]
        if same_text:
            problems.append(f"{len(same_text)} pages have identical content after the re-run, e.g. {same_text[:3]}")
        if same_time:
            problems.append(f"{len(same_time)} pages kept their generated_at after the re-run, e.g. {same_time[:3]}")
        print(f"Compared with {args.compare}: {len(after)} URLs, {len(after) - len(same_text)} changed content.")

    if problems:
        print(f"\nFAILED - {len(problems)} problem(s):")
        for problem in problems[:40]:
            print("  -", problem)
        return 1
    print("\nOK - all 60 pages are populated, current, rashi-specific and served at their permanent URLs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
