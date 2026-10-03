"""Phase 3 live check: generate the kundali-report for the test chart with the real Claude API.

    .venv/bin/python scripts/live_report_check.py                 # English + Marathi
    .venv/bin/python scripts/live_report_check.py --languages hi  # one language
    .venv/bin/python scripts/live_report_check.py --model claude-sonnet-5 --product sade-sati-guide

Needs ANTHROPIC_API_KEY in the project's .env (or the environment). Writes
var/live_check/<product>.<lang>.json and a readable .md, and prints token usage and cost.
Each run is a real, billed API call (it bypasses the report cache on purpose).
"""

import argparse
import datetime as dt
import json
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Public, independently published charts - see tests/reference_charts.py for why. `AS_OF` is pinned
# there so a generated fixture does not change meaning as real time passes.
sys.path.insert(0, str(ROOT / "tests"))
from reference_charts import AS_OF as REFERENCE_AS_OF  # noqa: E402
from reference_charts import NEHRU, PRIMARY  # noqa: E402

def _birth(reference) -> dict:
    """A reference chart as the `Birth` kwargs this script builds its request from."""
    request = reference.request()
    return dict(date=dt.date.fromisoformat(request["date"]),
                time=dt.time.fromisoformat(request["time"]),
                lat=request["lat"], lon=request["lon"],
                timezone=request["timezone"], city=reference.place)


TEST_BIRTH = _birth(PRIMARY)      # Kalam: 9 yogas, mangal dosha high, a debilitated Chandra
PARTNER_BIRTH = _birth(NEHRU)     # a second-cycle Vimshottari chart, for matching-report runs


def book_to_markdown(report: dict) -> str:
    """The flagship Kundali book (Parts A-H). Every dated heading is an engine range, not AI text."""
    meta = report["meta"]
    lines = [f"# {report['title']}", "",
             f"_{report['product_name']} · {report['language']} · as of {meta['as_of']} · {meta['model']} · "
             f"{len(meta['calls'])} calls · Rs {meta['cost_estimate_inr']}_", "", report["summary"], ""]
    if report.get("highlights"):
        h = report["highlights"]
        lines += ["---", "", "# Highlights (top-level object)", ""]
        for key in ("mangal", "sade_sati", "dasha"):
            for field, text in (h.get(key) or {}).items():
                lines += [f"**{key}.{field}** {text}", ""]
        for key in ("strengths", "cautions"):
            lines += [f"**{key}**", ""] + [f"- {line}" for line in h.get(key) or []] + [""]
        lines += [f"- **{y['name']}** {y['text']}" for y in h.get("yogas") or []] + [""]
    if report.get("gemstone"):
        lines += ["**gemstone** " + json.dumps(report["gemstone"], ensure_ascii=False), ""]
    for part in report["parts"]:
        lines += ["---", "", f"# PART {part['label']} — {part['heading']}", ""]
        if part.get("intro"):
            lines += [part["intro"], ""]
        for chapter in part["chapters"]:
            lines += [f"## {chapter['heading']}", ""]
            lines += [p for paragraph in chapter["paragraphs"] for p in (paragraph, "")]
            for sub in chapter.get("subsections") or []:
                lines += [f"### {sub['heading']}", ""]
                lines += [p for paragraph in sub["paragraphs"] for p in (paragraph, "")]
            for window in chapter["windows"]:
                dasha = " / ".join(lord["name"] for lord in window["dasha"].values() if lord)
                lines += [f"### {window['label']} — {window['headline']}", "", f"_{dasha}_", ""]
                lines += [p for paragraph in window["paragraphs"] for p in (paragraph, "")]
                lines += [f"- **{a['area']}** {a['text']}" for a in window.get("areas") or []]
                lines += [""] if window.get("areas") else []
            lines += [f"- {bullet}" for bullet in chapter["bullets"]] + ([""] if chapter["bullets"] else [])
            if chapter["table"]:
                columns = chapter["table"]["columns"]
                lines += ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
                lines += ["| " + " | ".join(row) + " |" for row in chapter["table"]["rows"]] + [""]
    lines += ["---", "", "# Remedies", ""]
    for remedy in report["remedies"]:
        lines += [f"**{remedy['title']}** ({remedy['type']}, {remedy['frequency']})", "",
                  remedy["description"], "", remedy["how_to"], ""]
    words = book_words(report)
    lines += ["---", "", report["disclaimer"], "", "## Checks", "",
              f"~{words} words ≈ {words // 350} printed pages", "",
              f"```\n{json.dumps(meta['calls'], indent=1)}\n```", "",
              f"```\n{json.dumps(meta['checks'], ensure_ascii=False, indent=1)[:6000]}\n```", ""]
    return "\n".join(lines)


def book_words(report: dict) -> int:
    def texts():
        yield report["summary"]
        for part in report["parts"]:
            for chapter in part["chapters"]:
                yield from chapter["paragraphs"]
                yield from chapter["bullets"]
                for sub in chapter.get("subsections") or []:
                    yield from sub["paragraphs"]
                for window in chapter["windows"]:
                    yield from window["paragraphs"]
                    yield from (a["text"] for a in window.get("areas") or [])
        for key in ("strengths", "cautions"):
            yield from (report.get("highlights") or {}).get(key) or []
        for remedy in report["remedies"]:
            yield remedy["description"] + " " + remedy["how_to"]

    return sum(len(text.split()) for text in texts())


def to_markdown(report: dict) -> str:
    if report.get("parts"):
        return book_to_markdown(report)
    lines = [f"# {report['title']}", "", f"_{report['product_name']} · {report['language']} · "
             f"as of {report['meta']['as_of']} · {report['meta']['model']}_", "", report["summary"], ""]
    for section in report["sections"]:
        lines += [f"## {section['heading']}", ""]
        for paragraph in section["paragraphs"]:
            lines += [paragraph, ""]
        for sub in section["subsections"]:
            lines += [f"### {sub['heading']}", ""]
            for paragraph in sub["paragraphs"]:
                lines += [paragraph, ""]
        lines += [f"- {bullet}" for bullet in section["bullets"]] + ([""] if section["bullets"] else [])
        if section["table"]:
            columns = section["table"]["columns"]
            lines += ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
            lines += ["| " + " | ".join(row) + " |" for row in section["table"]["rows"]] + [""]
    lines += ["## Remedies", ""]
    for remedy in report["remedies"]:
        lines += [f"**{remedy['title']}** ({remedy['type']}, {remedy['frequency']})", "",
                  remedy["description"], "", remedy["how_to"], ""]
    lines += ["---", "", report["disclaimer"], "", "## Checks", "", f"```\n{report['meta']['checks']}\n```", ""]
    return "\n".join(lines)


SPENT: list = []   # every LLMResult this process saw, so a failure can still be costed


def _report_partial_spend(language: str, settings) -> None:
    """What the run had already spent when it died. A run that can consume real money and leave no
    record of it is a measurement problem in its own right - it happened twice before this existed."""
    from app.ai.config import estimate_cost_usd

    if not SPENT:
        print(f"      [{language}] no completed API calls recorded - spend likely zero", file=sys.stderr)
        return
    usage = {key: sum(r.usage.get(key, 0) for r in SPENT)
             for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                         "cache_read_input_tokens")}
    usd = estimate_cost_usd(SPENT[-1].model, usage) or 0.0
    print(f"      [{language}] SPENT BEFORE FAILING: {len(SPENT)} call(s), {usage}, "
          f"${usd:.4f} = Rs {usd * settings.usd_inr:.2f}", file=sys.stderr)


def _record_spend(client):
    """Wrap the client so every result is counted even if the run dies before it reports."""
    for name in ("generate_json", "generate_json_batch"):
        original = getattr(client, name, None)
        if original is None:
            continue

        def wrapped(*args, _original=original, _batch=name.endswith("batch"), **kwargs):
            out = _original(*args, **kwargs)
            SPENT.extend(v for v in (out.values() if _batch else [out]) if hasattr(v, "usage"))
            return out

        setattr(client, name, wrapped)
    return client


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--languages", nargs="+", default=["en", "mr"], choices=["en", "hi", "mr"])
    parser.add_argument("--product", default="kundali-report")
    parser.add_argument("--model", help="override REPORT_MODEL for this run")
    parser.add_argument("--effort", help="override REPORT_EFFORT for this run")
    args = parser.parse_args()
    if args.model:
        os.environ["REPORT_MODEL"] = args.model
    if args.effort:
        os.environ["REPORT_EFFORT"] = args.effort

    from app.ai import AIError, Birth, generate_report
    from app.ai.config import get_settings, has_credentials
    from app.ai.products import PRODUCTS

    if not has_credentials():
        print("ANTHROPIC_API_KEY is not set.\n"
              f"Add it to {ROOT / '.env'} as  ANTHROPIC_API_KEY=sk-ant-...  and run this again.\n"
              "Nothing was generated.", file=sys.stderr)
        return 2
    if args.product not in PRODUCTS:
        print(f"unknown product; choose from {sorted(PRODUCTS)}", file=sys.stderr)
        return 2

    # The book makes ten calls over several minutes; without this the terminal looks hung.
    logging.basicConfig(level=logging.INFO, format="      %(message)s", stream=sys.stderr)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)

    settings = get_settings()
    births = [Birth(**TEST_BIRTH)] + ([Birth(**PARTNER_BIRTH)] if PRODUCTS[args.product].kind == "pair" else [])
    out_dir = ROOT / "var" / "live_check"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"model={settings.model} effort={settings.effort} product={args.product}")

    total_usd = 0.0
    for language in args.languages:
        started = time.monotonic()
        try:
            from app.ai.client import ClaudeClient
            report = generate_report(args.product, language, births, use_cache=False,
                                     as_of=REFERENCE_AS_OF.date(),
                                     client=_record_spend(ClaudeClient(settings)))
        except AIError as exc:
            # A failed run has usually already spent real money - a batch round, or several part
            # calls before one of them failed. Printing nothing leaves that spend unaccounted, which
            # has now happened twice. Report whatever the client managed to record.
            print(f"[{language}] FAILED after {time.monotonic() - started:.0f}s: {exc}", file=sys.stderr)
            _report_partial_spend(language, settings)
            return 1
        except Exception as exc:  # a bug in our own code, after the API was already billed
            print(f"[{language}] CRASHED after {time.monotonic() - started:.0f}s: {exc!r}", file=sys.stderr)
            _report_partial_spend(language, settings)
            raise
        seconds = time.monotonic() - started
        stem = out_dir / f"{args.product}.{language}"
        stem.with_suffix(f".{language}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        stem.with_suffix(f".{language}.md").write_text(to_markdown(report), encoding="utf-8")
        meta, usage = report["meta"], report["meta"]["usage"]
        words = book_words(report) if report.get("parts") else sum(
            len(p.split()) for s in report["sections"] for p in
            s["paragraphs"] + [q for sub in s["subsections"] for q in sub["paragraphs"]])
        total_usd += meta["cost_estimate_usd"] or 0
        calls = meta.get("calls")
        print(f"[{language}] {seconds:.0f}s  attempts={meta['attempts']}  served_by={meta['model']}  ~{words} words"
              + (f"  ~{words // 350} pages  {len(calls)} part calls" if calls else "") + "\n"
              f"      tokens: in={usage['input_tokens']} cache_write={usage['cache_creation_input_tokens']} "
              f"cache_read={usage['cache_read_input_tokens']} out={usage['output_tokens']}\n"
              f"      cost: ${meta['cost_estimate_usd']} = Rs {meta['cost_estimate_inr']}  "
              f"checks_clean={meta['checks']['clean']} redactions={len(meta['checks']['redactions'])} "
              f"warnings={len(meta['checks']['warnings'])}\n"
              f"      wrote {stem}.json and .md")
    print(f"total: ${total_usd:.4f} = Rs {total_usd * settings.usd_inr:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
