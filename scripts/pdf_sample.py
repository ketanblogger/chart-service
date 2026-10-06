"""Render a report JSON to PDF with the real (two-pass) pipeline - the smoke test for Chromium + fonts,
and the way to LOOK at the book after changing anything in app/pdf.

    .venv/bin/python scripts/pdf_sample.py [REPORT_JSON] [OUT_DIR] [--name NAME] [--page-size a5|a4]
                                           [--pages 1,2,5-8] [--scale 2]
    .venv/bin/python scripts/pdf_sample.py --basic [--language en|hi|mr] [--date YYYY-MM-DD]
                                           [--time HH:MM] [--city NAME] ...

`--basic` renders the FREE Basic Chart PDF instead of a report: it computes a chart with the engine and
prints app/pdf/basic.py's document (one pass, no contents page, and no AI call anywhere on the path).

Defaults: the long Marathi book fixture, var/samples/, A5. Prints the render time, page count, embedded
fonts and any fallback font (there must be none), and checks that every page number printed on the
contents page is the page that heading actually landed on.

With `pypdfium2` and `pillow` installed it also writes a PNG per selected page, so the Devanagari shaping
and the page layout can be checked by eye:
    ~/.local/bin/uv pip install --python .venv/bin/python pypdfium2 pillow
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.pdf import (embedded_fonts, fallback_fonts, heading_ids, html_to_pdf,  # noqa: E402
                     outline_pages, render_basic_html, render_book, render_report_html)

DEFAULT_REPORT = ROOT / "tests/fixtures/kundali_book_mr.json"


def page_numbers(text: str, total: int) -> list[int]:
    """"1,2,5-8" -> [1, 2, 5, 6, 7, 8]. "all" / "" -> every page."""
    if not text or text == "all":
        return list(range(1, total + 1))
    out: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        first, _, last = part.partition("-")
        out += list(range(int(first), int(last or first) + 1))
    return [number for number in out if 1 <= number <= total]


def basic(args) -> None:
    """The free chart sheet: compute a chart, render it once, rasterise it. No report, no AI."""
    import datetime as dt

    from app import engine

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    city = engine.find_city(args.city)
    chart = engine.compute_chart(dt.date.fromisoformat(args.date), dt.time.fromisoformat(args.time),
                                 city["lat"], city["lon"], city["tz"], detail="basic")
    chart["input"]["city"] = city["name"]

    started = time.time()
    html = render_basic_html(chart, language=args.language, name=args.name or None,
                             page_size=args.page_size)
    pdf = html_to_pdf(html)
    seconds = time.time() - started

    stem = f"basic-chart-{args.language}"
    (out_dir / f"{stem}.html").write_text(html, encoding="utf-8")
    pdf_path = out_dir / f"{stem}.pdf"
    pdf_path.write_bytes(pdf)

    import pypdf

    pages = len(pypdf.PdfReader(str(pdf_path)).pages)
    print(f"{pdf_path}  {len(pdf) // 1024} KB  {pages} pages  {seconds:.2f} s  1 render pass")
    print("embedded fonts:", sorted(embedded_fonts(pdf)))
    print("fallback fonts:", sorted(fallback_fonts(pdf)) or "none (good)")
    print("headings:", heading_ids(html))
    rasterise(pdf_path, stem, out_dir, args)


def rasterise(pdf_path: Path, stem: str, out_dir: Path, args) -> None:
    try:
        import pypdfium2
    except ImportError:
        print("pypdfium2 not installed - skipping PNG pages")
        return
    document = pypdfium2.PdfDocument(str(pdf_path))
    wanted = page_numbers(args.pages, len(document))
    for number in wanted:
        document[number - 1].render(scale=args.scale).to_pil().save(out_dir / f"{stem}-p{number}.png")
    print(f"{len(wanted)} page PNG(s) -> {out_dir}/{stem}-p{wanted[0] if wanted else 1}.png ...")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", nargs="?", default=str(DEFAULT_REPORT))
    parser.add_argument("out_dir", nargs="?", default=str(ROOT / "var/samples"))
    parser.add_argument("--name", default="")
    parser.add_argument("--page-size", default=None, choices=["a5", "a4"])
    parser.add_argument("--pages", default="1-4", help='pages to rasterise, e.g. "1,2,5-8" or "all" (default: 1-4)')
    parser.add_argument("--scale", type=float, default=2.0, help="PNG scale (default 2 = 144 dpi)")
    parser.add_argument("--basic", action="store_true", help="render the FREE Basic Chart PDF instead")
    parser.add_argument("--language", default="mr", choices=["en", "hi", "mr"], help="--basic only")
    parser.add_argument("--date", default="1931-10-15", help="--basic only")
    parser.add_argument("--time", default="06:30", help="--basic only")
    parser.add_argument("--city", default="Miraj", help="--basic only")
    args = parser.parse_args()

    if args.basic:
        return basic(args)

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{report.get('product', 'report')}-{report.get('language', 'en')}"
    names = {"self": args.name, "boy": args.name} if args.name else None

    passes = []

    def build(toc_pages):
        html = render_report_html(report, names=names, page_size=args.page_size, toc_pages=toc_pages)
        passes.append((toc_pages, html))
        return html

    started = time.time()
    pdf = render_book(build)
    seconds = time.time() - started
    (out_dir / f"{stem}.html").write_text(passes[-1][1], encoding="utf-8")
    pdf_path = out_dir / f"{stem}.pdf"
    pdf_path.write_bytes(pdf)

    import pypdf

    pages = len(pypdf.PdfReader(str(pdf_path)).pages)
    print(f"{pdf_path}  {len(pdf) // 1024} KB  {pages} pages  {seconds:.2f} s  {len(passes)} render pass(es)")
    print("embedded fonts:", sorted(embedded_fonts(pdf)))
    print("fallback fonts:", sorted(fallback_fonts(pdf)) or "none (good)")

    printed = passes[-1][0] or {}
    landed = dict(zip(heading_ids(passes[-1][1]), outline_pages(pdf)))
    wrong = {anchor: (number, landed.get(anchor)) for anchor, number in printed.items() if landed.get(anchor) != number}
    print(f"contents page: {len(printed)} entries numbered, wrong: {wrong or 'none (good)'}")

    rasterise(pdf_path, stem, out_dir, args)


if __name__ == "__main__":
    main()
