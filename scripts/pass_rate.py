"""First-attempt pass rate per book call per language, N repetitions, every rejection reason kept.

    PYTHONPATH=. uv run python scripts/pass_rate.py baseline --reps 3
    PYTHONPATH=. uv run python scripts/pass_rate.py baseline --report-only   # no calls, re-read the cells
    PYTHONPATH=. uv run python scripts/pass_rate.py wiring --dry-run         # no calls, prove the wiring

ONE attempt per cell - no retries, no repair - so what it measures is exactly "would this draft have
been accepted as written". That is the number the retry spend is a function of.

IT MUST RUN THE PIPELINE PRODUCTION RUNS, and on 2026-09-30 it briefly did not. `judge_draft` takes a
`strip` callable, and this script passed the bare `strip_markup`, whose `language` then defaults to None -
so `language.fix_language` never ran, while production passes `Tidy(language)` and it does. The arm measured
that day counted fifteen `wording` findings of which TEN were spellings and Latin glosses production
corrects before any check sees them. The number was not wrong about the drafts; it was measuring a pipeline
nobody ships. Arms measured before this line changed are not comparable with arms measured after it on
`wording` - every other kind is unaffected, because the fixer only ever touches those.

WHY THIS FILE IS TRACKED, AND WHY IT APPENDS. Its first version lived in /tmp, buffered every cell and
wrote one JSON file at the end. A killed run destroyed 45 paid calls (Rs 260), and a power cut later
took the script itself. So: it lives in `scripts/`, it writes under `var/pass_rate/`, and each cell is
appended to a .jsonl THE MOMENT IT LANDS. Re-running the same label skips the cells already there, so
an interrupted run resumes instead of being paid for twice.

Every row carries the git sha it was measured on. Arms are only comparable within one sha: pooling
drafts written across a code change once inflated a category and produced a ranking that was wrong.

The five calls are the ones the Rs 3,000 investigation measured - the long, fact-dense ones, plus E1
as a known-easy control (it passed 9/9). Keep them fixed, or the 47% / 58% arms stop being comparable.
"""

import argparse
import collections
import datetime as dt
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.book import plan  # noqa: E402
from app.ai.book_report import (all_windows, build_book_data, call_message,  # noqa: E402
                                judge_draft, system_blocks, _public)
from app.ai.config import estimate_cost_usd, get_settings  # noqa: E402
from app.ai.products import PRODUCTS  # noqa: E402
from app.ai.report import Tidy, book_facts, build_data  # noqa: E402
from app.ai.schema import CALL_SCHEMA  # noqa: E402
from tests import reference_charts  # noqa: E402
from tests.test_pdf import AS_OF, _birth  # noqa: E402

CALLS = ("D-now", "BC", "D-far2", "E1", "F")
LANGUAGES = ("en", "hi", "mr")
OUT = ROOT / "var/pass_rate"


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def load_cells(path: pathlib.Path) -> list[dict]:
    """Every row written so far. A half-written last line (killed mid-write) is dropped, not fatal."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"  (dropping a truncated final row in {path.name})")
    return rows


def append_cell(path: pathlib.Path, row: dict) -> None:
    """One row, flushed and fsynced before the next call is made. This is the whole resume story."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        import os
        os.fsync(handle.fileno())


def report(label: str, rows: list[dict]) -> None:
    """Pass rate, PROBLEMS PER FAILING DRAFT and the kind counts - per language and overall.

    Problems per failing draft is the metric that decides what a failure costs: a draft with one or two
    problems is a paragraph repair, one with four or more is a regeneration. A pass rate alone hides that.
    """
    if not rows:
        print("no cells yet")
        return
    shas = sorted({row.get("sha", "unknown") for row in rows})
    print(f"\n=== {label}: first-attempt pass rate ===")
    if len(shas) > 1:
        print(f"  !! MIXED SHAS {shas} - these rows are NOT comparable; measure one arm per sha")
    else:
        print(f"  sha {shas[0]}")

    def block(name: str, mine: list[dict]) -> None:
        if not mine:
            return
        passed = sum(1 for row in mine if row["passed"])
        failing = [row for row in mine if not row["passed"]]
        problems = sum(len(row["problems"]) for row in failing)
        density = f"{problems / len(failing):.1f}" if failing else "-"
        print(f"  {name:6} {passed:3}/{len(mine):<3} = {passed / len(mine) * 100:3.0f}%"
              f"   problems per failing draft {density}")

    for language in LANGUAGES:
        block(language, [row for row in rows if row["lang"] == language])
    block("ALL", rows)

    print("\n  per call:")
    for key in CALLS:
        mine = [row for row in rows if row["call"] == key]
        if mine:
            passed = sum(1 for row in mine if row["passed"])
            print(f"    {key:8} {passed}/{len(mine)}")

    kinds = collections.Counter(problem["kind"] for row in rows for problem in row["problems"])
    print("\n  failure kinds:", dict(kinds.most_common()))
    for language in LANGUAGES:
        mine = collections.Counter(problem["kind"] for row in rows if row["lang"] == language
                                   for problem in row["problems"])
        if mine:
            print(f"    {language}: {dict(mine.most_common())}")

    spend = collections.Counter()
    for row in rows:
        for key, value in (row.get("usage") or {}).items():
            spend[key] += value
    settings = get_settings()
    usd = estimate_cost_usd(settings.model, dict(spend))
    inr = None if usd is None else round(usd * settings.usd_inr, 2)
    print(f"\n  SPEND so far: Rs {inr}   (usage {dict(spend)})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("label", help="arm name, e.g. baseline / style-sheet. Its cells are var/pass_rate/<label>.jsonl")
    parser.add_argument("--reps", type=int, default=3, help="repetitions per (call, language) cell")
    parser.add_argument("--calls", default=",".join(CALLS), help="comma-separated call keys")
    parser.add_argument("--languages", default=",".join(LANGUAGES), help="comma-separated language codes")
    parser.add_argument("--report-only", action="store_true", help="re-read the cells and print the table; no calls")
    parser.add_argument("--dry-run", action="store_true",
                        help="build every prompt and skip the model; proves the wiring for free")
    args = parser.parse_args()

    calls_wanted = tuple(key.strip() for key in args.calls.split(",") if key.strip())
    languages = tuple(code.strip() for code in args.languages.split(",") if code.strip())
    path = OUT / f"{args.label}.jsonl"
    done = load_cells(path)

    if args.report_only:
        report(args.label, done)
        return 0

    sha = git_sha()
    seen = {(row["lang"], row["call"], row["rep"]) for row in done}
    if seen:
        print(f"resuming {path.name}: {len(seen)} cell(s) already measured")

    settings = get_settings()
    client = None if args.dry_run else __import__("app.ai.client", fromlist=["ClaudeClient"]).ClaudeClient(settings)
    chart = build_data(PRODUCTS["kundali-report"], [_birth(reference_charts.PRIMARY)], AS_OF)[0]["chart"]

    for language in languages:
        full, prefix, book = build_book_data(chart, language, AS_OF, "detailed")
        system = system_blocks(prefix)
        windows = all_windows(full["timeline"])
        facts = book_facts(full)
        planned = {call.key: call for call in plan(book, "detailed")}
        for key in calls_wanted:
            call = planned.get(key)
            if call is None:
                print(f"  {language} {key}: not in the plan for this chart, skipped")
                continue
            for rep in range(1, args.reps + 1):
                if (language, key, rep) in seen:
                    continue
                user = call_message(call, language, AS_OF.isoformat(), full, None)
                if args.dry_run:
                    print(f"  {language} {key:8} rep{rep} DRY-RUN  prompt {len(user):,} chars, "
                          f"system {sum(len(b.get('text', '')) for b in system):,} chars")
                    continue
                started = time.time()
                result = client.generate_json(system=system, user=user, schema=CALL_SCHEMA)
                _content, structure, repairable, problems, feedback = judge_draft(
                    call, result, facts=facts, gemstone_allowed=True, windows=windows,
                    language=language, timeline=full["timeline"], strip=Tidy(language))
                row = {
                    "sha": sha, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                    "lang": language, "call": key, "rep": rep, "passed": not feedback,
                    "seconds": round(time.time() - started, 1),
                    "model": getattr(result, "model", None), "usage": dict(result.usage or {}),
                    "structure": [str(item)[:160] for item in structure],
                    "repairable": [str(item)[:160] for item in repairable],
                    # `sentence` is what the Marathi style sheet is sourced from: the rule pairs come from
                    # our own rejected drafts, so the offending sentence has to survive the run.
                    "problems": [_public(problem) for problem in problems],
                }
                append_cell(path, row)
                print(f"  {language} {key:8} rep{rep} {'PASS ' if not feedback else 'RETRY'} "
                      f"{[problem['kind'] for problem in problems] or ''}", flush=True)

    if not args.dry_run:
        report(args.label, load_cells(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
