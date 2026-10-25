#!/usr/bin/env python3
"""Builds the sample page images for /kundli-pdf, from an INVENTED birth.

    uv run python scripts/sample_preview.py            # all three languages
    uv run python scripts/sample_preview.py --lang hi  # one

WHY THIS EXISTS. The sample page says in three languages what the free PDF contains and what the paid
report adds, and the comment in the URL registry has promised "with a sample of each" since the page was
written. There was no sample on it - two bullet lists and a price. The one thing somebody deciding
whether to pay Rs 299 for a document wants is to SEE A PAGE OF IT.

THE BIRTH IS INVENTED and says so on every image: 14 May 1990, 07:30, Pune, for a person called Asha
Kulkarni, who does not exist. No real birth detail and no real person's name appears in this repository,
which is a standing rule and not a preference - these images are published, cached and indexed.

WHAT IT PRODUCES: app/static/img/sample/{lang}-{free,paid}-{n}.webp, one per previewed page, plus the
two sample PDFs themselves under the same directory so the page can offer the whole thing. Checked in,
because regenerating them needs Chromium and a page render must never depend on that.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
OUT = Path("app/static/img/sample")

#: The invented person. Real-looking and entirely made up - the name is as common as a name gets in
#: Maharashtra, which is the point: nobody's chart, and nothing to trace.
SAMPLE = {"date": "1990-05-14", "time": "07:30", "city": "Pune", "name": "Asha Kulkarni"}

#: WHICH PAGES. The cover and the first reading page of each document - enough to show the typesetting
#: and the depth, and not enough to be the product. The paid report is 35-45 pages; three of them is a
#: preview, and a reader who wants the rest buys it.
FREE_PAGES = (1, 2)
PAID_PAGES = (1, 3, 5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", action="append", choices=["en", "hi", "mr"])
    parser.add_argument("--numerology", action="store_true",
                        help="also build the paid numerology sample (ONE BILLED AI CALL per language)")
    args = parser.parse_args()
    langs = args.lang or ["en", "hi", "mr"]

    OUT.mkdir(parents=True, exist_ok=True)
    for lang in langs:
        print(f"[{lang}] rendering the free Basic Chart PDF through the site's own code path")
        pdf = build_free(lang)
        made = rasterise(pdf, f"{lang}-free", FREE_PAGES)
        print(f"[{lang}] {pdf.name} + {', '.join(path.name for path in made)}")
        if args.numerology:
            print(f"[{lang}] writing the paid numerology report - ONE BILLED AI CALL")
            npdf = build_numerology(lang)
            nmade = rasterise(npdf, f"{lang}-numerology", (NUMEROLOGY_PAGE,))
            print(f"[{lang}] {npdf.name} + {', '.join(path.name for path in nmade)}")
    return 0


#: The invented person for the NUMEROLOGY sample. A numerology report needs a name and a date and
#: nothing else - no time, no city - so this is deliberately a shorter record than SAMPLE above.
#: Same rule: real-looking, entirely made up, and nobody's.
NUMEROLOGY_SAMPLE = {"name": "Asha Kulkarni", "born": "1990-05-14"}

#: Which page of the numerology report to show. Page 2 is the first page of actual reading - page 1
#: is the cover, which shows typesetting and says nothing about the contents.
NUMEROLOGY_PAGE = 5


def build_numerology(lang: str) -> Path:
    """The paid numerology report for the invented person, through the site's own generator.

    THIS SPENDS MONEY: one AI call per language, because the report is written rather than
    assembled. That is the point of the picture - a reader deciding whether to pay for a document
    should see a page of the real thing, not a mock-up of it. The output is checked in so the call
    happens once and never on a page render.
    """
    import datetime as dt

    from app.ai.report import generate_report
    from app.numerology import core
    from app.pdf.service import ensure_pdf

    born = dt.date.fromisoformat(NUMEROLOGY_SAMPLE["born"])
    facts = core.for_chat(born, NUMEROLOGY_SAMPLE["name"])
    report = generate_report("numerology-report", lang, [], as_of=dt.date.today(),
                             numerology_facts=facts)
    built = ensure_pdf(report, {"self": NUMEROLOGY_SAMPLE["name"]})
    # NOT UNDER app/static, AND NOT CHECKED IN. The free chart PDF is published whole because it is
    # free and the page offers it; this one is the Rs 199 product. A complete nine-page report in a
    # public repository is the paid deliverable given away - for an invented person, yes, but it is
    # every section in full, which is the thing people pay for. Only the single preview page is
    # published. var/ is git-ignored scratch.
    scratch = ROOT / "var" / "numerology-samples"
    scratch.mkdir(parents=True, exist_ok=True)
    target = scratch / f"{lang}-numerology-sample.pdf"
    target.write_bytes(built.read_bytes())
    return target


def build_free(lang: str) -> Path:
    """The free PDF, through THE ROUTE THE SITE SERVES - not a lookalike assembled for the picture.

    The city becomes a latitude and longitude inside the request model, so going through the endpoint is
    both less code here and the only way the sample is guaranteed to be the document a reader downloads.
    If this ever stops matching, the picture is wrong and that is worth finding out here.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.post("/api/chart/pdf", json={**SAMPLE, "language": lang})
    if response.status_code != 200:
        raise SystemExit(f"the site refused to render the sample: {response.status_code} {response.text[:200]}")
    target = OUT / f"{lang}-free-sample.pdf"
    target.write_bytes(response.content)
    return target


def rasterise(pdf: Path, stem: str, pages: tuple[int, ...]) -> list[Path]:
    """PDF page -> webp, in process.

    pypdfium2 and Pillow are already dependencies; poppler's pdftoppm and cwebp are not installed and
    adding two system packages to produce three checked-in pictures is not a trade worth making.
    """
    import pypdfium2

    made: list[Path] = []
    document = pypdfium2.PdfDocument(str(pdf))
    try:
        for number in pages:
            if number > len(document):
                print(f"  ! {pdf.name} has {len(document)} pages; skipping page {number}")
                continue
            # 110 dpi against a 72-dpi point grid: sharp on a 2x phone screen at the width the page
            # shows these (about 320 CSS px), without carrying a print-resolution bitmap to every reader.
            image = document[number - 1].render(scale=110 / 72).to_pil()
            target = OUT / f"{stem}-{number}.webp"
            image.save(target, "WEBP", quality=82, method=6)
            made.append(target)
    finally:
        document.close()
    return made


if __name__ == "__main__":
    raise SystemExit(main())
