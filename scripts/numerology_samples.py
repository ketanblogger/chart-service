#!/usr/bin/env python3
"""Render numerology reports to compare one batch's output against the last. BILLED: one AI call each.

    render_samples.py invented            # three invented people, en/hi/mr, through fulfilment
    render_samples.py one <lang> <iso-date> <name...>   # one named report, for comparison

THE NAMED FORM TAKES ITS VALUES ON THE COMMAND LINE and writes only to var/, which is git-ignored.
Nothing about that person reaches the repository, a commit, or a test fixture - which is the rule
for real birth data here, and the reason this script holds no name but the invented ones below.

    scripts/numerology_samples.py invented
    scripts/numerology_samples.py one mr 1990-05-14 Some Invented Person
"""
import datetime as dt, os, sys, tempfile
from pathlib import Path

# Derived, never written. A hardcoded path carries the developer's username into published
# source - which is what it did, and what the publication guard caught.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_t = tempfile.mkdtemp()
os.environ.setdefault("APP_DB", f"{_t}/a.db")
os.environ.setdefault("SESSION_SECRET", "render")

from app.numerology import core
from app.ai.report import generate_report
from app.pdf.service import ensure_pdf

OUT = ROOT / "var" / "numerology-samples"
OUT.mkdir(parents=True, exist_ok=True)

INVENTED = [("en", "1990-05-14", "Asha Kulkarni"),
            ("hi", "1983-11-02", "Devdatta Rane"),
            ("mr", "1996-07-21", "Priya Shelar")]


def render(lang: str, born: str, name: str, label: str, as_of: dt.date) -> Path:
    day = dt.date.fromisoformat(born)
    facts = core.for_report(day, name)
    print(f"  {label} ({lang}) - ONE BILLED CALL")
    report = generate_report("numerology-report", lang, [], as_of=as_of,
                             numerology_facts=facts, use_cache=False)
    pdf = ensure_pdf(report, {"self": name})
    target = OUT / f"{label}.pdf"
    target.write_bytes(pdf.read_bytes())
    import pypdfium2
    doc = pypdfium2.PdfDocument(str(target))
    pages = len(doc)
    doc.close()
    print(f"    -> {target}  ({pages} pages, {target.stat().st_size // 1024} kb)")
    return target


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "invented":
        for lang, born, name in INVENTED:
            render(lang, born, name, f"sample-{lang}", dt.date.today())
    else:
        lang, born, name = sys.argv[2], sys.argv[3], " ".join(sys.argv[4:])
        render(lang, born, name, "re-render", dt.date.fromisoformat("2026-11-05"))
