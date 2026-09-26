"""Has the first REAL paid sale happened yet? (The Swiss Ephemeris licence clock.)

    .venv/bin/python scripts/first_sale_status.py           # one line, exit 0 = it has happened
    .venv/bin/python scripts/first_sale_status.py --json     # the recorded milestone as JSON

The Astrodienst Swiss Ephemeris professional licence is bought within ONE WEEK of the first order paid with
LIVE Razorpay keys (`LICENSE` explains why). `app/payments/first_sale.py` records that moment in
the database and in `var/first_live_sale.json` and logs it at CRITICAL; this script reads it back.

Razorpay's own payment e-mail is the primary signal - this is the backstop that we control. Nothing here
sends anything anywhere. Exit code: 0 = the first live sale is recorded, 1 = not yet, 2 = cannot tell.
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai import config as _config  # noqa: E402,F401  (loads .env)
from app.payments import first_sale  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print the recorded milestone as JSON")
    args = parser.parse_args(argv)

    try:
        record = first_sale.status()
    except Exception as exc:  # noqa: BLE001 - an operator script must say why, not traceback
        print(f"cannot read the first-sale record: {type(exc).__name__}: {exc}")
        return 2

    if args.json:
        payload = dict(record) if record else {}
        if record:
            payload["deadline"] = first_sale.deadline(record)
            payload["licence_url"] = first_sale.LICENCE_URL
        print(json.dumps(payload, indent=1))
        return 0 if record else 1

    print(first_sale.summary())
    if record:
        print(f"    marker file: {first_sale.marker_path()}")
        print(f"    licence:     {first_sale.LICENCE_URL}")
        print(f"    buy it by:   {time.strftime('%Y-%m-%d', time.localtime(first_sale.deadline(record)))}")
        return 0
    print(f"    when it happens: logged at CRITICAL, written to {first_sale.marker_path()}, and shown by")
    print("                     scripts/fulfil_order.py --list and scripts/smoke_check.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
