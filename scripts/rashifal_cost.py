#!/usr/bin/env python
"""What the rashifal pages cost per month, and what cutting refusals would save. Read-only, no AI calls.

THE SHAPE OF THE SPEND. Every page-language costs one AI call. A draft the checker refuses is rewritten,
and the refused one is paid for and thrown away, so the monthly bill is

    (page-languages per month) x (1 + refusal rate) x (cost per call)

The first factor is fixed by the publishing cadence and cannot be reduced without publishing less. The
third is the model's price. THE REFUSAL RATE IS THE ONLY TERM WE CONTROL, which is why the Marathi prompt
work and this cost item are the same lever.

WHAT IS ALREADY DONE, and was verified rather than rebuilt: a window that has not moved is not
regenerated. `generate.plan` skips a page whose stored `period_start` is the current window and which has
every language, before it even builds the brief, and a page whose brief hash is unchanged has only its
missing languages filled. In the stored runs one refresh skipped 58 pages and generated 6. There is no
saving left in re-running unchanged windows, because it does not happen.

Also already done: languages are generated one per call (RASHIFAL_SPLIT_LANGUAGES defaults on), so a
Marathi refusal rewrites Marathi alone and not the English and Hindi beside it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: How often each period's window moves, from app/rashifal/periods.py. Per month, averaged.
#: today: every day. weekly: every Monday. monthly and 6-months: the 1st. yearly: once, on 20 November.
REFRESHES_PER_MONTH = {"today": 30.44, "weekly": 4.35, "monthly": 1.0, "6-months": 1.0, "yearly": 1 / 12}
RASHIS = 12


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", type=int, default=3, help="languages published (default 3)")
    parser.add_argument("--target-refusal", type=float, default=0.05, metavar="RATE",
                        help="the refusal rate to price the 'after' column at (default 0.05)")
    args = parser.parse_args()

    from app.admin import rashifal_ops
    from app.rashifal import config as rconfig

    runs = rashifal_ops.rashifal_runs()
    produced = sum((r.get("generated") or 0) + (r.get("failed") or 0) for r in runs)
    calls = sum(r.get("calls") or 0 for r in runs)
    cost = sum(float(r["cost_inr"]) for r in runs if r.get("cost_inr") is not None)

    if not runs or not calls or not produced:
        print("no stored runs with costs - run this where the generator has run")
        return 0

    per_call = cost / calls
    refusal_rate = max(0.0, (calls - produced) / calls)

    # WHOSE COST IS THIS? Every figure below is derived from what the stored runs actually paid, and a
    # model switch makes those runs history: after moving rashifal to Haiku 5.5 the table would go on
    # quoting Haiku 4.5 and Sonnet 5 prices with nothing to say so. The models that wrote those runs are
    # compared against the configured one, and the mismatch is printed rather than left to be noticed.
    ran_with = {r.get("model") for r in runs if r.get("model")}
    configured = rconfig.get_rashifal_settings().model
    print(f"From {len(runs)} stored runs: {produced} page-languages, {calls} calls, Rs {cost:.2f}")
    if ran_with and configured not in ran_with:
        print(f"  NOTE: those runs were written by {', '.join(sorted(ran_with))}, and the configured "
              f"model is now {configured}.")
        print("        Every rupee figure below is therefore the OLD model's cost. Re-run this after the "
              "first\n        refresh on the new model for figures that describe what you are now paying.")
    print(f"  cost per call      Rs {per_call:.3f}")
    print(f"  refusal rate       {refusal_rate:.1%}  ({calls - produced} rewrites)\n")

    monthly_jobs = sum(RASHIS * args.languages * n for n in REFRESHES_PER_MONTH.values())
    print("Page-languages per month, from the publishing cadence:")
    for period, n in REFRESHES_PER_MONTH.items():
        print(f"  {period:9} {RASHIS * args.languages * n:8.0f}   ({n:g} refreshes x {RASHIS} rashis x {args.languages} languages)")
    print(f"  {'total':9} {monthly_jobs:8.0f}\n")

    before = monthly_jobs * (1 + refusal_rate) * per_call
    after = monthly_jobs * (1 + args.target_refusal) * per_call
    floor = monthly_jobs * per_call
    print(f"Expected monthly cost at the measured {refusal_rate:.1%} refusal rate:  Rs {before:,.0f}")
    print(f"                       at a {args.target_refusal:.0%} refusal rate:            Rs {after:,.0f}")
    print(f"                       with no refusals at all (the floor):  Rs {floor:,.0f}")
    print(f"\nSaving from getting refusals to {args.target_refusal:.0%}:  Rs {before - after:,.0f} a month.")
    print("The floor is what publishing this many pages costs. Everything above it is rewrites.\n")

    # THE BIGGER LEVER, and it is not the refusals. Marathi is written by a stronger model on purpose,
    # and that model is priced at exactly twice the other one per token - so Marathi is about half the
    # bill while being a third of the calls. Printed rather than acted on: Marathi is on the stronger
    # model because its quality on the weaker one was not good enough, and that is a product decision.
    from app.ai.config import PRICES_PER_MTOK

    defaults = dict(getattr(rconfig, "LANGUAGE_MODEL_DEFAULTS", ()) or ())
    # The base model comes from the settings, not from a literal that goes stale the next time it
    # changes - this said claude-haiku-4-5 and would have mispriced every projection after the switch.
    base = rconfig.get_rashifal_settings().model
    per_language = monthly_jobs / args.languages
    weights = {}
    for code in ("en", "hi", "mr")[: args.languages]:
        model = defaults.get(code, base)
        price = PRICES_PER_MTOK.get(model)
        weights[code] = (model, (price[1] if price else 0.0))
    total_weight = sum(w for _model, w in weights.values()) or 1.0
    print("Where the money goes by language, at the per-token prices of the models actually used:")
    for code, (model, weight) in weights.items():
        share = weight / total_weight
        print(f"  {code}  {model:18} {share:5.0%} of the bill   "
              f"(Rs {before * share:,.0f} a month for {per_language:.0f} calls)")
    cheap = min(w for _m, w in weights.values()) or 1.0
    dear = [code for code, (_m, w) in weights.items() if w > cheap]
    if dear:
        saving = sum((weights[code][1] - cheap) / total_weight for code in dear) * before
        print(f"\nMoving {', '.join(dear)} to the same model as the rest would save about "
              f"Rs {saving:,.0f} a month -\nmore than fixing every refusal. It is NOT done here: that "
              f"model was chosen for quality,\nand the order to try it in is prompt fix first, then "
              f"measure the refusal rate on the cheaper\nmodel, then decide.")
    print("\nCost per call is whatever the stored runs paid, so a model change moves every figure here;\n"
          "the cadence is from periods.py and the refusal rate from the runs. Nothing is typed in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
