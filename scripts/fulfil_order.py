"""Admin: finish (or inspect) paid orders. A paid order is never lost - this is the manual retry path.

    .venv/bin/python scripts/fulfil_order.py --list                 # paid orders that are not delivered yet
    .venv/bin/python scripts/fulfil_order.py ORDER                  # show one order (our id, order_... id, or token)
    .venv/bin/python scripts/fulfil_order.py ORDER --run            # deliver it now, in this process (report: 1-3 min)
    .venv/bin/python scripts/fulfil_order.py ORDER --reconcile      # order still "created"/"failed" here? ask Razorpay
                                                                    # whether a payment was captured; if so mark paid + deliver

`--run` ignores the automatic retry schedule and a stale job lease. `--reconcile` needs the Razorpay keys and
trusts only Razorpay's API answer (captured payment, same amount and currency). Refunds are done by hand in the
Razorpay dashboard; this script never moves money. Exit code: 0 delivered / nothing to do, 1 not delivered, 2 usage.
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai import config as _config  # noqa: E402,F401  (loads .env)
from app.payments import first_sale, razorpay, service, store  # noqa: E402


def _when(ts) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "-"


def _line(order: dict) -> str:
    target = order["report_id"] or order["session_id"] or ""
    return (f"{order['id']}  {order['razorpay_order_id']}  {order['product']:<20} Rs {order['amount_paise'] / 100:g}  "
            f"status={order['status']:<8} fulfilment={order['fulfilment']:<10} attempts={order['attempts']}  "
            f"paid={_when(order['paid_at'])} via={order['paid_via'] or '-'}  {target}" + (f"\n    last error: {order['error']}" if order["error"] else ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finish or inspect paid orders.")
    parser.add_argument("order", nargs="?", help="our order id (ord_...), Razorpay order id (order_...) or access token")
    parser.add_argument("--list", action="store_true", help="list paid orders that are not delivered")
    parser.add_argument("--run", action="store_true", help="deliver now (synchronously)")
    parser.add_argument("--reconcile", action="store_true", help="check Razorpay for a captured payment first")
    args = parser.parse_args(argv)

    if args.list:
        print(first_sale.summary())  # has the real first sale happened? (Swiss Ephemeris licence clock)
        orders = store.unfinished_paid_orders()
        print("\n".join(_line(order) for order in orders) or "no paid order is waiting for delivery")
        return 0
    if not args.order:
        parser.print_usage()
        return 2
    order = store.find(args.order)
    if order is None:
        print(f"no such order: {args.order}")
        return 2

    if args.reconcile and order["status"] != "paid":
        payments = razorpay.order_payments(order["razorpay_order_id"])
        captured = [p for p in payments if p.get("status") == "captured" and p.get("amount") == order["amount_paise"]
                    and p.get("currency") == order["currency"]]
        print(f"Razorpay reports {len(payments)} payment attempt(s), {len(captured)} captured for the right amount")
        if captured:
            store.mark_paid(order["razorpay_order_id"], captured[0]["id"], "reconcile")
            order = store.get_order(order["id"])
            first_sale.note_paid(order)  # a sale found by reconciliation still starts the licence week

    if (args.run or args.reconcile) and order["status"] == "paid":
        service.fulfil(order, sync=True, force=True)
        order = store.get_order(order["id"])
    print(_line(order))
    if order["status"] == "paid":
        print(f"    customer page: /order/{order['token']}")
    if order["status"] != "paid":
        if args.run or args.reconcile:
            print("    NOT PAID - nothing was delivered")
            return 1
        return 0
    return 0 if order["fulfilment"] == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
