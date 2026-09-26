"""Rashifal refresh - the single entry point for cron / systemd timers, and the Phase 7 "run the scheduler
once manually" command.

    .venv/bin/python scripts/rashifal_refresh.py --period all --force     # regenerate all 60 pages now
    .venv/bin/python scripts/rashifal_refresh.py                          # what the timer runs: only pages whose
                                                                          # stored reading is not for the current window
    .venv/bin/python scripts/rashifal_refresh.py --period today --rashi dhanu --force --verbose   # one page, called
                                                                          # directly (runs under 4 pages never batch)
    .venv/bin/python scripts/rashifal_refresh.py --period today --force --sync   # 12 pages without the Batches API
    .venv/bin/python scripts/rashifal_refresh.py --estimate               # no AI call: prompt sizes, calls/day, cost table
    .venv/bin/python scripts/rashifal_refresh.py --rollback --rashi dhanu --period today   # put the previous reading back

Needs ANTHROPIC_API_KEY in .env (or the environment) for anything but --estimate / --rollback. Settings:
RASHIFAL_MODEL, RASHIFAL_EFFORT, RASHIFAL_LANGUAGES, RASHIFAL_BATCH ... (app/rashifal/config.py).
Every generated page is a real, billed API call; skipped pages cost nothing. Runs of 4+ pages go through the
Message Batches API (RASHIFAL_BATCH=1, the default): half price, but the command then waits for the batch
(usually minutes, at worst RASHIFAL_BATCH_TIMEOUT_MINUTES). Each run writes var/rashifal/runs/<run id>.json
(token usage, cost, per-language rejections, wall-clock) - nothing secret is ever written or printed.

Exit codes: 0 = every requested page is up to date; 1 = at least one page failed (its old content was kept);
2 = the AI is not configured, nothing was generated; 3 = another refresh holds the lease.
"""

import argparse
import dataclasses
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.client import AIError, AINotConfigured  # noqa: E402
from app.ai.config import PRICES_PER_MTOK, get_settings  # noqa: E402
from app.rashifal import store  # noqa: E402
from app.rashifal.brief import build_brief  # noqa: E402
from app.rashifal.config import get_rashifal_settings  # noqa: E402
from app.rashifal.generate import RefreshBusy, refresh  # noqa: E402
from app.rashifal.periods import PERIOD_SLUGS, RASHI_SLUGS, now_ist  # noqa: E402
from app.rashifal.prompts import SYSTEM_PROMPT, build_user_prompt  # noqa: E402

CALLS_PER_DAY = {"today": 12.0, "weekly": 12 / 7, "monthly": 12 / 30.44, "6-months": 12 / 30.44, "yearly": 12 / 30.44}
_TARGET_WORDS = {"today": 210, "weekly": 320, "monthly": 400, "6-months": 490, "yearly": 560}  # incl. the hub summary
_TOKENS_PER_WORD = {"en": 1.4, "mr": 3.5, "hi": 3.5}  # rough; Devanagari is token-hungry
_THINKING_TOKENS = 400  # effort=low; Haiku 4.5 does not think
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _estimate_tokens(text: str) -> int:
    devanagari = len(_DEVANAGARI.findall(text))
    return round(devanagari / 1.5 + (len(text) - devanagari) / 3.3)  # compact JSON is denser than prose


def estimate() -> None:
    now = now_ist()
    system = _estimate_tokens(SYSTEM_PROMPT)
    print(f"ESTIMATE ONLY (no API call; token counts are heuristics - the live run prints real usage).\n"
          f"System prompt ~{system} tokens (cached after the first call of a run).\n")
    inputs = {}
    for period in PERIOD_SLUGS:
        sizes = [_estimate_tokens(build_user_prompt(build_brief(rashi, period, now), ("en", "hi", "mr"))) for rashi in RASHI_SLUGS]
        inputs[period] = sum(sizes) / len(sizes)
        print(f"  {period:9s} user prompt ~{inputs[period]:6.0f} tokens   {CALLS_PER_DAY[period]:5.2f} calls/day")
    calls = sum(CALLS_PER_DAY.values())
    print(f"\nAverage AI calls per day: {calls:.1f}  (12/day + 12/week + 36/month; the budget allows 12-20)\n")
    usd_inr = get_settings().usd_inr
    print(f"{'model':18s} {'languages':10s} {'USD/day':>8s} {'INR/day':>8s} {'INR/month':>10s} {'batch INR/month':>16s}")
    for model in ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"):
        price_in, price_out = PRICES_PER_MTOK[model]
        for languages in (("en",), ("en", "hi", "mr")):
            day = 0.0
            for period in PERIOD_SLUGS:
                out = (0 if model.startswith("claude-haiku") else _THINKING_TOKENS) + 150 + sum(_TARGET_WORDS[period] * _TOKENS_PER_WORD[code] for code in languages)
                per_call = (inputs[period] * price_in + system * price_in * 0.1 + out * price_out) / 1_000_000
                day += per_call * CALLS_PER_DAY[period]
            print(f"{model:18s} {','.join(languages):10s} {day:8.2f} {day * usd_inr:8.0f} {day * usd_inr * 30.44:10.0f} "
                  f"{day * usd_inr * 30.44 / 2:16.0f}")
    print("\nA regeneration (checker rejected the first draft) doubles that page's cost; the live run reports attempts.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--period", default="all", choices=PERIOD_SLUGS + ["all"])
    parser.add_argument("--rashi", action="append", choices=RASHI_SLUGS, help="repeatable; default: all 12")
    parser.add_argument("--languages", help="only write these languages, e.g. mr (default: all configured). "
                                           "The versions not named are left untouched, not blanked.")
    parser.add_argument("--force", action="store_true", help="regenerate even if the stored reading covers the current window")
    parser.add_argument("--batch", action="store_true", help="force the Message Batches API on (default: RASHIFAL_BATCH, on)")
    parser.add_argument("--sync", action="store_true", help="never batch: direct API calls, full price, immediate")
    parser.add_argument("--workers", type=int, default=3, help="parallel API calls when not batching (default 3)")
    parser.add_argument("--estimate", action="store_true", help="print prompt sizes, calls/day and a cost table; no AI call")
    parser.add_argument("--rollback", action="store_true", help="restore the previous reading (needs --rashi and --period)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.estimate:
        estimate()
        return 0
    periods = PERIOD_SLUGS if args.period == "all" else [args.period]
    if args.rollback:
        if not args.rashi or args.period == "all":
            parser.error("--rollback needs --rashi and one --period")
        for rashi in args.rashi:
            done = store.rollback(rashi, args.period)
            print(f"{rashi}/{args.period}: {'previous reading restored' if done else 'no previous version stored'}")
        return 0

    settings = get_rashifal_settings()
    if args.batch or args.sync:
        settings = dataclasses.replace(settings, batch=not args.sync)
    rashis = args.rashi or RASHI_SLUGS
    print(f"Rashifal refresh: periods={','.join(periods)} rashis={len(rashis)} force={args.force} model={settings.model} "
          f"effort={settings.effort} languages={','.join(settings.languages)} batch={settings.batch}")
    started = time.time()
    try:
        only = tuple(code.strip().lower() for code in args.languages.split(",")) if args.languages else None
        if only:
            unknown = [code for code in only if code not in settings.languages]
            if unknown:
                parser.error(f"--languages: {unknown} not in the configured languages {list(settings.languages)}")
        summary = refresh(periods, rashis, force=args.force, settings=settings, workers=args.workers,
                          only_languages=only)
    except AINotConfigured as exc:
        print(f"\nNOTHING WAS GENERATED: the AI is not configured.\n  {exc}\n"
              "  Stored readings were left untouched; pages without a reading keep serving the engine's transit facts.")
        return 2
    except RefreshBusy as exc:
        print(f"\nNothing done: {exc}")
        return 3
    except AIError as exc:
        print(f"\nRefresh stopped: {exc}\n  Stored readings were left untouched.")
        return 1

    for outcome in summary.outcomes:
        if outcome.status != "skipped" or args.verbose:
            cost = "" if outcome.cost_usd is None else f"  ${outcome.cost_usd:.4f}"
            print(f"  {outcome.status:9s} {outcome.rashi:10s} {outcome.period:9s} attempts={outcome.attempts} "
                  f"langs={','.join(outcome.languages) or '-'}{cost}  {outcome.detail}")
    inr = summary.cost_usd * get_settings().usd_inr
    by_language: dict = {}
    for rejection in summary.rejections:
        by_language[rejection["language"]] = by_language.get(rejection["language"], 0) + 1
    report = {
        "run_id": summary.run_id, "periods": periods, "rashis": list(rashis), "force": args.force, "model": settings.model,
        "languages": list(settings.languages), "batch": settings.batch, "batches": summary.batches,
        "split_languages": settings.split_languages, "wall_clock_seconds": round(time.time() - started, 1),
        "calls": summary.calls, "usage": summary.usage, "cost_estimate_usd": summary.cost_usd, "cost_estimate_inr": round(inr, 2),
        "counts": {status: summary.count(status) for status in ("generated", "partial", "skipped", "failed")},
        "failed_checks_by_language": by_language, "rejections": summary.rejections,
        "outcomes": [dataclasses.asdict(outcome) for outcome in summary.outcomes if outcome.status != "skipped"],
    }
    if summary.calls:
        runs = Path(os.getenv("RASHIFAL_RUNS_DIR", ROOT / "var" / "rashifal" / "runs"))  # tests point this at a temp dir
        runs.mkdir(parents=True, exist_ok=True)
        (runs / f"{summary.run_id}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nAI calls: {summary.calls} ({summary.batches} batch(es)); tokens in/out: "
              f"{summary.usage['input_tokens'] + summary.usage['cache_read_input_tokens'] + summary.usage['cache_creation_input_tokens']}"
              f"/{summary.usage['output_tokens']}; failed checks by language: {by_language or 'none'}; "
              f"run report: {runs}/{summary.run_id}.json")
    print(f"\nDone in {time.time() - started:.0f}s: {summary.count('generated')} generated, {summary.count('partial')} partial, "
          f"{summary.count('skipped')} skipped (already current), {summary.count('failed')} FAILED. "
          f"Estimated cost ${summary.cost_usd:.2f} (Rs {inr:.0f}).")
    if summary.count("partial"):
        print("Partial = at least one language failed its checks and was not published; the next scheduled run retries it.")
    if not summary.ok:
        print("Failed pages kept their previous content (or the transit-facts view). Re-run the same command to retry them.")
    return 0 if summary.ok else 1


if __name__ == "__main__":
    sys.exit(main())
