#!/usr/bin/env python3
"""How often a report phrases a TRANSIT with the date the data gave it, per language.

    uv run python scripts/measure_transit_dates.py --read var/transit-measure/before.json
    uv run python scripts/measure_transit_dates.py --generate --label before --charts 2
    uv run python scripts/measure_transit_dates.py --compare before after

WHAT IT MEASURES AND WHY. A transit sentence that names only सध्या / अभी / गोचरात tells a reader
nothing they can check or act on, and goes stale the day the graha moves - while the date is sitting
right there in the data the model was handed. The prompt now requires the date. This counts whether
the drafts obey, per language, so "we tightened the prompt" is a measurement rather than a hope.

THREE NUMBERS PER LANGUAGE:
  dated      transit sentences that carry a date from the data   <- the one to move
  undated    transit sentences with only a sadhya/gochar marker  <- the one to drive to zero
  rejected   claims the checker refused                          <- must not get worse

GENERATING COSTS MONEY: one paid report per chart per language. --charts 2 in three languages is
six reports. The invented charts are the repository's own fixtures; no real birth data is used.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

OUT = ROOT / "var" / "transit-measure"

#: A month name in any of the three languages, or a four-digit year - the same shapes the checker
#: accepts as "when". Imported rather than retyped so this cannot drift from what is enforced.
from app.ai.validator import _MONTHS_DEVANAGARI, _MONTHS_LATIN  # noqa: E402

_DATE = re.compile(rf"(?<!\d)(?:1[89]|2[01])\d\d(?!\d)|{_MONTHS_DEVANAGARI}|\b(?:{_MONTHS_LATIN})\b",
                   re.IGNORECASE)
#: A sentence is ABOUT a transit when it carries one of these markers.
_TRANSIT = re.compile(r"गोचर|प्रवेश|भ्रमण|संक्रमण|सध्या|आत्ता|आता|अभी|इस समय|फिलहाल|वर्तमान|"
                      r"\b(?:transit\w*|ingress\w*|enters?|moves?|currently|at present)\b", re.IGNORECASE)
_SENTENCE = re.compile(r"[^.।!?\n]+[.।!?\n]?")


def prose(report: dict) -> str:
    """Every word of a report a reader actually reads.

    SECTIONS DO NOT HAVE A `body`. They carry heading / paragraphs / bullets / subsections / table,
    and the first version of this read section["body"] - which is absent - so it scored three real
    reports as having ZERO transit sentences and would have reported that as a result. Walk the
    whole structure and take every string.
    """
    out: list[str] = []

    def walk(node):
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)

    for key in ("summary", "sections", "remedies"):
        walk(report.get(key))
    return "\n".join(out)


def count(text: str) -> dict:
    """{dated, undated, sentences} for one report's prose."""
    dated = undated = 0
    for sentence in _SENTENCE.findall(text or ""):
        if not _TRANSIT.search(sentence):
            continue
        if _DATE.search(sentence):
            dated += 1
        else:
            undated += 1
    return {"dated": dated, "undated": undated}


def summarise(rows: list[dict]) -> dict:
    """Per language: the counts, and the share of transit sentences that carry a date."""
    out: dict = {}
    for row in rows:
        bucket = out.setdefault(row["language"], {"dated": 0, "undated": 0, "rejected": 0, "reports": 0})
        bucket["dated"] += row["dated"]
        bucket["undated"] += row["undated"]
        bucket["rejected"] += row.get("rejected", 0)
        bucket["reports"] += 1
    for bucket in out.values():
        total = bucket["dated"] + bucket["undated"]
        bucket["with_a_date_percent"] = round(100 * bucket["dated"] / total, 1) if total else None
    return out


def _print(label: str, summary: dict) -> None:
    print(f"[{label}]")
    print(f"  {'lang':5} {'reports':>7} {'dated':>6} {'undated':>8} {'with a date':>12} {'rejected':>9}")
    for lang in ("en", "hi", "mr"):
        b = summary.get(lang)
        if not b:
            continue
        share = "-" if b["with_a_date_percent"] is None else f"{b['with_a_date_percent']}%"
        print(f"  {lang:5} {b['reports']:>7} {b['dated']:>6} {b['undated']:>8} {share:>12} {b['rejected']:>9}")


#: WHICH PRODUCT. The sade-sati guide is entirely about one transit - Saturn's - so nearly every
#: paragraph is the thing being measured. The concise kundali report was the obvious first choice and
#: was the wrong one: a run of it produced ZERO transit sentences, because it reads a birth chart.
#: Measuring that would have produced a confident 0 out of 0 and proved nothing.
DEFAULT_PRODUCT = "sade-sati-guide"


def generate(label: str, charts: int, languages: list[str], product: str = DEFAULT_PRODUCT) -> Path:
    """One paid report per chart per language, through the real generator. BILLED."""
    import datetime as dt

    # The repository's own reference charts: published figures whose birth details are a matter of
    # record, which is why they are the fixtures here and no customer's chart ever is.
    from reference_charts import GANDHI, KALAM

    from app.ai.report import generate_report

    from app.ai.report import Birth

    people = [GANDHI, KALAM][:max(1, charts)]
    rows = []
    for person in people:
        r = person.request()
        # Birth takes real date/time objects, not the strings the fixture's request() hands the API.
        birth = Birth(dt.date.fromisoformat(r["date"]), dt.time.fromisoformat(r["time"]),
                      r["lat"], r["lon"], r["timezone"], person.city)
        for language in languages:
            print(f"  generating {person.name} in {language} - ONE BILLED CALL")
            report = generate_report(product, language, [birth],
                                     as_of=dt.date.today(), use_cache=False)
            written = prose(report)
            counts = count(written)
            # THE PROSE IS KEPT WITH THE ROW. A report id is a function of the chart and
            # the date, not of the prompt, so generating an "after" arm OVERWRITES the
            # "before" report of the same chart in the cache. The first before/after run
            # lost its baseline exactly that way, and re-scoring it under a corrected
            # metric would have meant paying to generate it a second time.
            counts["prose"] = written
            counts.update(language=language, chart=person.name,
                          rejected=int((report.get("meta") or {}).get("rejected", 0)))
            rows.append(counts)
            print(f"    dated={counts['dated']} undated={counts['undated']} rejected={counts['rejected']}")
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{label}.json"
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--generate", action="store_true", help="generate reports (BILLED)")
    parser.add_argument("--label", default="run", help="name this run, e.g. before / after")
    parser.add_argument("--charts", type=int, default=2)
    parser.add_argument("--lang", action="append", choices=["en", "hi", "mr"])
    parser.add_argument("--product", default=DEFAULT_PRODUCT)
    parser.add_argument("--read", help="print a saved run")
    parser.add_argument("--rescore", nargs=2, metavar=("LABEL", "PRODUCT"),
                        help="recount reports already on disk - costs nothing")
    parser.add_argument("--since-minutes", type=float, default=30.0,
                        help="rescore only reports written this recently (default 30). The cache "
                             "keeps every report ever generated, and a 46-day-old one written under "
                             "a different prompt was silently counted as 'before' the first time.")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    args = parser.parse_args(argv)

    if args.read:
        rows = json.loads(Path(args.read).read_text(encoding="utf-8"))
        # RE-APPLY THE CURRENT METRIC to any row that kept its prose, so a corrected definition can
        # be tried against a run that has already been paid for.
        for row in rows:
            if row.get("prose"):
                row.update(count(row["prose"]))
        _print(Path(args.read).stem, summarise(rows))
        return 0
    if args.compare:
        for label in args.compare:
            path = OUT / f"{label}.json"
            if not path.exists():
                print(f"no such run: {path}")
                return 2
            _print(label, summarise(json.loads(path.read_text(encoding="utf-8"))))
        return 0
    if args.rescore:
        label, product = args.rescore
        from app.ai.config import get_settings

        rows = []
        import time

        cutoff = time.time() - args.since_minutes * 60
        for path in sorted(get_settings().reports_dir.glob("*.json"), key=lambda q: q.stat().st_mtime):
            if path.stat().st_mtime < cutoff:
                continue
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get("product") != product:
                continue
            counts = count(prose(report))
            counts.update(language=report.get("language"), chart=path.stem, rejected=0)
            rows.append(counts)
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{label}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        _print(label, summarise(rows))
        return 0
    if args.generate:
        target = generate(args.label, args.charts, args.lang or ["en", "hi", "mr"], args.product)
        print(f"\nsaved {target}")
        _print(args.label, summarise(json.loads(target.read_text(encoding="utf-8"))))
        return 0
    parser.print_usage()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
