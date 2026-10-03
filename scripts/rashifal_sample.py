"""Write ONE rashifal page with a chosen model / language set and save it as readable text - without touching
the store. For judging a model's Hindi and Marathi before trusting it with the 180 pages.

    .venv/bin/python scripts/rashifal_sample.py --rashi dhanu --period today --model claude-haiku-4-5 --languages mr
    .venv/bin/python scripts/rashifal_sample.py --rashi dhanu --period today --model claude-sonnet-5 --languages hi,mr

One direct (non-batch) billed call per invocation. Output: var/rashifal/samples/<rashi>_<period>_<model>_<langs>.txt
with the text, the automatic checker's verdict per language, token usage and cost.
"""

import argparse
import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.client import ClaudeClient  # noqa: E402
from app.ai.config import estimate_cost_usd  # noqa: E402
from app.ai.validator import collect_facts  # noqa: E402
from app.rashifal.brief import build_brief  # noqa: E402
from app.rashifal.config import client_settings, get_rashifal_settings  # noqa: E402
from app.rashifal.generate import check_output  # noqa: E402
from app.rashifal.periods import PERIOD_SLUGS, RASHI_SLUGS  # noqa: E402
from app.rashifal.prompts import SECTION_IDS, SYSTEM_PROMPT, build_user_prompt, rashifal_schema  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--rashi", default="dhanu", choices=RASHI_SLUGS)
    parser.add_argument("--period", default="today", choices=PERIOD_SLUGS)
    parser.add_argument("--model", default=None)
    parser.add_argument("--languages", default="en,hi,mr")
    parser.add_argument("--tag", default="", help="suffix for the output file name")
    args = parser.parse_args()

    settings = get_rashifal_settings()
    if args.model:
        settings = dataclasses.replace(settings, model=args.model)
    languages = tuple(code for code in ("en", "hi", "mr") if code in args.languages.split(","))
    brief = build_brief(args.rashi, args.period)
    result = ClaudeClient(client_settings(settings)).generate_json(
        system=SYSTEM_PROMPT, user=build_user_prompt(brief, languages), schema=rashifal_schema(languages))
    report = check_output(result.data, languages, brief, collect_facts(brief))

    lines = [f"{args.rashi} / {args.period} / {result.model} / languages in this call: {','.join(languages)}",
             f"usage: {json.dumps(result.usage)}  cost: ${estimate_cost_usd(result.model, result.usage) or estimate_cost_usd(settings.model, result.usage)}", ""]
    for code in languages:
        page = result.data[code]
        lines += [f"===== {code} =====  checker: {report[code]['blocking'] or 'clean'}  warnings: {report[code]['warnings'] or '-'}",
                  "HEADLINE: " + page["headline"], "SUMMARY: " + page["summary"], "OVERVIEW: " + page["overview"]]
        for section in SECTION_IDS:
            lines += [f"[{section}]"] + page["sections"][section]
        lines += ["KEY DATES: " + json.dumps(page["key_dates"], ensure_ascii=False), "TIP: " + page["tip"], ""]
    out = ROOT / "var" / "rashifal" / "samples"
    out.mkdir(parents=True, exist_ok=True)
    name = f"{args.rashi}_{args.period}_{settings.model}_{'-'.join(languages)}{('_' + args.tag) if args.tag else ''}.txt"
    (out / name).write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"saved: var/rashifal/samples/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
