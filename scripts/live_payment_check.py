"""Live check against the real Razorpay API with your TEST keys. Step-by-step guide: docs/PAYMENTS.md.

    .venv/bin/python scripts/live_payment_check.py                       # creates one real test-mode order (Rs 99) and prints it
    .venv/bin/python scripts/live_payment_check.py --product consultation-premium
    .venv/bin/python scripts/live_payment_check.py --payments order_XXXX   # what Razorpay knows about an order's payments
    .venv/bin/python scripts/live_payment_check.py --verify order_XXXX pay_YYYY SIGNATURE   # check a checkout signature

Reads RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET (and reports whether RAZORPAY_WEBHOOK_SECRET is set) from the environment
or .env. Makes real HTTPS calls; nothing is simulated and nothing is charged (an order is only an intent to pay).
Refuses live keys unless --allow-live is given. Never prints a secret. Exit: 0 ok, 1 Razorpay refused, 2 keys missing.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai import config as _config  # noqa: E402,F401  (loads .env)
from app.payments import catalogue, razorpay  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a real Razorpay test-mode order with the configured keys.")
    parser.add_argument("--product", default="kundali-report", choices=[entry.product for entry in catalogue.all_items()])
    parser.add_argument("--payments", metavar="ORDER_ID", help="list the payment attempts Razorpay has for this order")
    parser.add_argument("--verify", nargs=3, metavar=("ORDER_ID", "PAYMENT_ID", "SIGNATURE"), help="check a checkout signature")
    parser.add_argument("--allow-live", action="store_true", help="run even with rzp_live_ keys")
    args = parser.parse_args(argv)

    if not razorpay.configured():
        print("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set.\n"
              "Put your TEST keys (Razorpay dashboard > Test mode > Account & Settings > API keys) into .env - see docs/PAYMENTS.md.")
        return 2
    key = razorpay.key_id()
    print(f"key id: {key[:12]}...  mode: {'TEST' if razorpay.is_test_mode() else 'LIVE'}  "
          f"webhook secret: {'set' if razorpay.webhook_configured() else 'NOT set (webhooks will answer 503)'}")
    if not razorpay.is_test_mode() and not args.allow_live:
        print("These are not test keys (rzp_test_...). Refusing; pass --allow-live if you really mean it.")
        return 2

    try:
        if args.verify:
            ok = razorpay.verify_payment_signature(*args.verify)
            print("signature VALID - this payment would be accepted" if ok else "signature INVALID - this payment would be rejected")
            return 0 if ok else 1
        if args.payments:
            payments = razorpay.order_payments(args.payments)
            print(f"{len(payments)} payment attempt(s) for {args.payments}")
            for payment in payments:
                print(f"  {payment.get('id')}  status={payment.get('status')}  captured={payment.get('captured')}  "
                      f"amount={payment.get('amount')} {payment.get('currency')}  method={payment.get('method')}")
            return 0
        item = catalogue.item(args.product)
        from app.payments.store import new_order_id

        order = razorpay.create_order(item.amount_paise, receipt="live_" + new_order_id(), notes={"product": item.product, "source": "live_payment_check"})
    except razorpay.RazorpayError as exc:
        print(f"Razorpay refused or could not be reached: {exc}")
        return 1
    print(f"created order {order['id']}: {order['amount']} paise {order['currency']}, status={order['status']}, receipt={order.get('receipt')}")
    print("It is visible in the dashboard (Test mode > Transactions > Orders). Order creation, auth and the amount path work.\n"
          "Next: make a test payment through the site - docs/PAYMENTS.md, 'One test payment end to end'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
