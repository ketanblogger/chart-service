#!/usr/bin/env python3
"""Rebuild every mantra text: extract from the cached source, then apply the reviewer's corrections.

    .venv/bin/python scripts/build_mantra_texts.py

THE PIPELINE IS source -> extract -> correct -> text, and every step is repeatable. Nothing is
hand-edited into app/mantra/texts/: a better extractor or a re-fetched source can be run again
without losing a single correction, because the corrections are data in app/mantra/corrections.py.

A correction that does not apply RAISES. A reviewer's note that silently matched nothing would be
the worst outcome here - the text would look corrected and not be.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.mantra import corrections as C
from app.mantra import review

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "var/mantra-sources"
OUT = ROOT / "app/mantra/texts"

#: slug -> (source A, source B or None). A container is named for an HTML source.
SOURCES = {
    "hanuman-chalisa": (("bhaktibharat/hanuman-chalisa.html", "cbody"),
                        ("stotranidhi/hanuman-chalisa.html", "entry-content")),
    # A AND B ARE IN THE ORDER THE REVIEW SHEET USED, which is the order the reviewer's pada
    # numbers refer to. They were reversed here first and the build raised on the second
    # correction; had the numbers happened to be in range it would have applied every Durga
    # correction to the wrong line, and the text would have looked fine.
    "durga-chalisa": (("bhaktibharat/durga-chalisa.html", "cbody"),
                      ("wikisource/durga-chalisa.wikitext", None)),
    "rudrashtakam": (("wikisource/rudrashtakam.wikitext", None),
                     ("second/rudrashtakam.txt", None)),
    "shiv-tandav-stotram": (("wikisource/shiv-tandav-stotram.wikitext", None),
                            ("second/shiv-tandav-stotram.txt", None)),
    "ram-raksha-stotra": (("wikisource/ram-raksha-stotra.wikitext", None),
                          ("second/ram-raksha-stotra.txt", None)),
    "shiv-chalisa": (("bhaktibharat/shiv-chalisa.html", "cbody"), None),
    "om-jai-jagdish-hare": (("bhaktibharat/om-jai-jagdish-hare.html", "cbody"), None),
    "ganesh-aarti-jai-ganesh-deva": (("bhaktibharat/ganesh-aarti-jai-ganesh-deva.html", "cbody"), None),
    "jai-ambe-gauri": (("bhaktibharat/jai-ambe-gauri.html", "cbody"), None),
    "hanuman-aarti": (("bhaktibharat/hanuman-aarti.html", "cbody"), None),
    "aarti-kunj-bihari-ki": (("bhaktibharat/aarti-kunj-bihari-ki.html", "cbody"), None),
    "mahamrityunjaya-mantra": (("bhaktibharat/mahamrityunjaya-mantra.html", "cbody"), None),
    "ganesh-chalisa": (("bhaktibharat/ganesh-chalisa.html", "cbody"), None),
    "shani-chalisa": (("bhaktibharat/shani-chalisa.html", "cbody"), None),
    "hanuman-ashtak": (("bhaktibharat/hanuman-ashtak.html", "cbody"), None),
    "bajrang-baan": (("stotranidhi/bajrang-baan.html", "entry-content"), None),
    "lingashtakam": (("wikisource/lingashtakam.wikitext", None), None),
    "kanakadhara-stotram": (("wikisource/kanakadhara-stotram.wikitext", None), None),
    "ganesh-atharvashirsha": (("wikisource/ganesh-atharvashirsha.wikitext", None), None),
    "gayatri-mantra": (("wikisource/gayatri-mantra.wikitext", None), None),
}

#: THE TWO SAHASRANAMAMS COME IN PARTS. The reviewer rejected both because the page that carried
#: their name held only the पूर्वपीठिका - the preface - and not the thousand names. The stotram is
#: published in three pieces, and the whole text is the three in order.
MULTIPART = {
    "vishnu-sahasranamam": [
        # This part already opens with the purvapeetika, so it is not fetched twice.
        ("stotranidhi/vishnu-sahasranamam-main.html", "entry-content"),
        # NEW PADAS ONLY. The uttarapeetika page reprints 72 padas that the main page already has
        # and adds 8 closing verses of its own; concatenating the two put those 72 lines in the
        # text twice. It is not a suffix/prefix overlap that could be joined cleanly - the repeated
        # lines are interleaved - so this part contributes only what is not already present, and
        # the build prints how many it skipped.
        ("stotranidhi/vishnu-sahasranamam-uttara.html", "entry-content", "new_only"),
    ],
    "lalita-sahasranamam": [
        ("stotranidhi/lalita-sahasranamam.html", "entry-content"),          # purvapeetika
        ("stotranidhi/lalita-sahasranamam-main.html", "entry-content"),     # the thousand names
        ("stotranidhi/lalita-sahasranamam-uttara.html", "entry-content"),
    ],
}


def lines_of(rel: str, container: str | None) -> list[str]:
    raw = (SRC / rel).read_bytes().decode("utf-8", "replace")
    if container:
        return review.container_lines(raw, "div", container)
    raw = re.sub(r"</?br\s*/?>", "\n", raw)
    raw = re.sub(r"\[\[([^\]|]*\|)?|\]\]|'''|\{\{[^}]*\}\}", "", raw)
    raw = re.sub(r"^\s*(वर्गः|श्रेणी|Category)\s*:.*$", "", raw, flags=re.M)
    raw = re.split(r"==\s*(?:संबंधित|सम्बंधित|बाहरी|इन्हें भी|सन्दर्भ|टिप्पणी)", raw)[0]
    raw = re.sub(r"^=+.*?=+\s*$", "", raw, flags=re.M)
    raw = re.sub(r"^\s*#.*$", "", raw, flags=re.M)
    return [" ".join(l.split()) for l in raw.splitlines()]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    problems = []
    for slug, parts in MULTIPART.items():
        padas: list[str] = []
        for part in parts:
            rel, container = part[0], part[1]
            got = review.padas(lines_of(rel, container))
            if len(part) > 2 and part[2] == "new_only":
                fresh = [pada for pada in got if pada not in padas]
                print(f"    {rel}: {len(got) - len(fresh)} pada(s) already present, "
                      f"{len(fresh)} added")
                got = fresh
            padas += got
        final = C.apply(padas, C.BY_SLUG.get(slug, ([], "single"))[0])
        (OUT / f"{slug}.json").write_text(
            json.dumps({"slug": slug,
                        "verses": [{"n": str(i), "text": t} for i, t in enumerate(final, 1)]},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {slug:30} {len(parts)} parts -> {len(final):4} padas")

    for slug, (a_spec, b_spec) in SOURCES.items():
        a = review.padas(lines_of(*a_spec))
        diff_index = b_readings = None
        ops, kind = C.BY_SLUG.get(slug, ([], "single"))
        if kind == "comparison":
            if b_spec is None:
                problems.append(f"{slug}: numbered as a comparison but has no source B")
                continue
            b = review.padas(lines_of(*b_spec))
            rows = review.compare(a, b)
            # Row N of the differences table -> position of that pada in source A.
            diff_index = [i for i, r in enumerate(rows) if r["state"] == "differ"]
            b_readings = {n: rows[i]["b"] for n, i in enumerate(diff_index, start=1)}
        try:
            final = C.apply(a, ops, b_readings=b_readings, diff_index=diff_index)
        except ValueError as exc:
            problems.append(f"{slug}: {exc}")
            continue
        (OUT / f"{slug}.json").write_text(
            json.dumps({"slug": slug,
                        "verses": [{"n": str(i), "text": t} for i, t in enumerate(final, 1)]},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {slug:30} {len(a):4} extracted -> {len(final):4} after corrections")
    for problem in problems:
        print(f"  FAILED {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
