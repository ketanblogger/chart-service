# Payments (Razorpay) - operator's guide

Code: `app/payments/` · API shapes: `docs/API.md` ("Payments") · Razorpay facts below were checked against
Razorpay's docs on 2026-09-21 (URLs given next to each).

## What is sold (prices live only in `app/payments/catalogue.py`)

| Product | id | Price | What the buyer gets |
|---|---|---|---|
| Simple Kundali report | `kundali-report-simple` | ₹49 | a concise Kundali PDF |
| Detailed Kundali report | `kundali-report` | ₹249 | the full 35-45 page print-and-bind book |
| Kundali matching | `matching-report` | ₹99 | matching PDF |
| Mangal dosha guide | `mangal-dosha-remedy` | ₹49 | guide PDF |
| Sade sati guide | `sade-sati-guide` | ₹49 | guide PDF |
| **Consultation Basic** | `consultation-basic` | ₹99 | **10 questions + the simple report** |
| **Consultation Premium** | `consultation-premium` | ₹299 | **10 questions + the detailed book** |

Rashifal is always free, and the first two consultation questions are free.

**The tier is the product id.** A consultation order records which report it includes by *being* that
product: `consultation-basic` bundles the simple report, `consultation-premium` the book, and an id's
bundled report never changes, so an order cannot drift to the other tier. `catalogue.report_product(order)`
is the one place that mapping is read - entitlement, fulfilment and the order page all go through it.

`consultation-pack` is the id sold before the tiers existed (₹99, ten questions and the **detailed** book).
It is still honoured everywhere - entitlement, the order page, re-downloads - but `catalogue.sellable()`
refuses it, so it cannot be bought again and `POST /api/payments/order` rejects it as an unknown product.

Everything else about a consultation purchase is unchanged: ONE order, the questions credited the moment
the payment is verified (idempotent per payment id), the bundled report generated in the background like any
report order, both shown on the same permanent `/order/<token>` page. If that person already owns the report
the tier includes - bought alone, or with an earlier consultation - the new order points at the SAME report:
nothing is generated or charged twice, in either direction.

A product may be priced here before `app/ai/products.py` can generate it. `catalogue.item()` returns None for
it, so it cannot be bought, and `python -m app.hardening` warns until the generator lands.

## How it works

```
buy button -> pay.js -> POST /api/payments/order     server prices the product from app/payments/catalogue.py,
                                                     pins the report (report_id + as_of), creates the Razorpay order
           -> Razorpay Checkout (checkout.js, loaded on click)
           -> POST /api/payments/verify              HMAC_SHA256(our order_id | payment_id, KEY_SECRET) must match
Razorpay   -> POST /api/payments/webhook             HMAC_SHA256(raw body, WEBHOOK_SECRET); payment.captured / order.paid
                                                     (covers a customer who closes the tab after paying)
both       -> mark paid (once) -> fulfil (once):     a consultation tier: +10 messages at once, then the report it bundles
                                                     report: entitled at once; report generated in the background (~9 min)
customer   -> /order/{token}                         permanent page: status + "Download your PDF"; works without cookies
```

- The browser never sends an amount, and nothing is unlocked without one of the two signatures.
- A paid order is never lost. If report generation fails (AI down, safety check rejects the text) the order stays
  `paid` with `fulfilment = failed`; it is retried automatically when the customer's page polls (after 30 s, 2 min,
  10 min, 30 min, 1 h - 6 attempts), and by hand with `scripts/fulfil_order.py`. The log line starts with `PAID order`.
- Refunds are manual for the MVP: Razorpay dashboard > Transactions > Payments > the payment > Issue refund. Nothing
  in the app reacts to a refund; if a refunded customer should lose access, delete that row from `orders` in `var/app.db`.

## The first REAL paid sale (the Swiss Ephemeris licence clock)

The site ships under the AGPL while it links pyswisseph, and the plan is to buy the Astrodienst **Swiss Ephemeris
Professional License** within **one week of the first real paid order** (`LICENSE` states the position).
That week starts exactly once, so `app/payments/first_sale.py` records it the moment an order reaches `paid`
while **live** keys (`rzp_live_...`) are in use:

- a **CRITICAL** log line containing `*** FIRST LIVE SALE ***`, the order, the amount and the licence URL
  (what `journalctl -p crit -u rashikundli` and any log alert will show);
- a durable marker file, `var/first_live_sale.json` (`FIRST_SALE_MARKER`), readable with `cat`;
- a row in the `milestones` table, whose primary key makes a second fire impossible across restarts, workers and
  Razorpay's webhook retries. If the database is ever restored from an older backup, the marker file is read back
  and the row restored, so the week is never restarted.

Test-mode payments never count. **Razorpay's own payment e-mail is the primary signal**; this is the backstop we
control. **This app sent no e-mail and called no third party until 2026-09-26**, and that invariant was
retired deliberately, not eroded: a buyer who closed the tab during the five to ten minutes a report takes
had no way back to it, and the order page link is only a recovery route if it reaches them. So there is now
exactly ONE outbound message, at payment, carrying that link - `app/mailer.py` (Resend) and
`app/payments/order_email.py`. It is off unless `REPORT_EMAIL_ENABLED` is set, it never raises into the
payment path, and everything it offers stays reachable without it.

    .venv/bin/python scripts/first_sale_status.py        # has it happened? when? which order? by when to buy?
    .venv/bin/python scripts/fulfil_order.py --list      # prints the same line above the pending orders
    .venv/bin/python scripts/smoke_check.py <url>        # prints it in the "[first real sale]" section

## Environment

| Env var | Meaning |
|---|---|
| `RAZORPAY_KEY_ID` | Public key id (`rzp_test_...` / `rzp_live_...`). The only Razorpay value a browser ever sees |
| `RAZORPAY_KEY_SECRET` | API secret: creates orders and verifies checkout signatures. Server only |
| `RAZORPAY_WEBHOOK_SECRET` | The secret you type when creating the webhook (any long random string). Without it `/api/payments/webhook` answers 503 |
| `SESSION_SECRET` | Already required by the chat: signs the `uid` cookie that also identifies a buyer |
| `BASE_URL` | Public origin. With `REPORTS_UNLOCKED=1` and a non-localhost `BASE_URL` the app logs a CRITICAL warning |
| `TRUST_PROXY=1` | Behind your own nginx/caddy only: rate limits then use `X-Forwarded-For` |

Without the two keys the site behaves as before: buy buttons show "launching soon", `POST /api/payments/*` answer 503.
Generate the webhook secret with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Once you have TEST keys

1. Razorpay dashboard, switch to **Test mode** > Account & Settings > API keys > Generate test key. Put both values in `.env`:
   ```
   RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxxx
   RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
   RAZORPAY_WEBHOOK_SECRET=<a long random string you invent>
   ```
2. `.venv/bin/python scripts/live_payment_check.py` - makes one real test-mode order and prints its id. If this
   works, authentication, the API client and the amount path are proven. Exit code 2 = keys missing, 1 = Razorpay refused.
   **Done on 2026-09-21 with the real test keys:** Razorpay returned `order_TehSm5IZvO7xE1` (4900 paise INR, status
   `created`) and, with `--product consultation-pack` (the id sold before the tiers existed - use
   `consultation-basic` now), `order_TehSx6sOMWZL5o` (9900 paise INR, `created`); `--payments`
   on the first order answered "0 payment attempt(s)"; a made-up signature was reported INVALID. Both orders are
   visible in the dashboard under Test mode > Transactions > Orders (unpaid orders cost nothing).
3. Check that payments are **auto-captured**: Account & Settings > Payment capture = "Automatic" (Razorpay's default).
   A payment that is only authorised is refunded by Razorpay after a few days; the app delivers on verify / captured.

### The two manual test payments (no webhook needed) - about 10 minutes

Test methods (Razorpay docs: https://razorpay.com/docs/payments/payments/test-card-details/ and
https://razorpay.com/docs/payments/payments/test-upi-details/): card **4100 2800 0000 1007** (Visa) or
**5555 5100 0008 1006** (Mastercard), any future expiry, any CVV, any name; on the OTP page type any 4-10 digits
(fewer than 4 digits = a failed payment). UPI: **success@razorpay** (or **failure@razorpay** to see a failure).
Nothing is charged in test mode.

Start the site: `.venv/bin/uvicorn app.main:app --port 8000` (the Razorpay test keys and `ANTHROPIC_API_KEY` must be
in `.env`; the report step really writes a report - a real, billed AI call whose cost is recorded in the
report's `meta.cost_estimate_inr`).

**There are two tiers of each product, and the pair below is chosen to exercise all four in two payments.**
The kundali page sells a **₹49 simple report** and a **₹249 detailed book**; the consultation sells **₹99 Basic**
(10 questions + the *simple* report) and **₹299 Premium** (10 questions + the *detailed* book). Which report a
consultation includes is recorded in its product id and never changes, so the two tiers cannot drift into each other.

**A. ₹249 detailed Kundali book** - http://localhost:8000/birth-chart
1. Enter name, date, time and city of birth > **generate the kundali**.
2. Under the result there are **two** buttons: **Get the ₹49 report** and **Get the ₹249 book**. Press
   **Get the ₹249 book** > choose the report language > pay.
3. Razorpay window: Card > the test card above > any OTP like `1234` > Success.
4. The page says "Payment received - preparing your report (5-10 minutes)" - the **book**'s wait; the simple
   report promises 3-5 - then shows **Download your PDF** and your
   order page link. Download the PDF and read it - this is the print-and-bind book, so check it is 35-45 pages with a
   cover and a table of contents whose page numbers are right.
5. Copy the `/order/...` link into a private window: it must show the purchase and download the PDF without cookies.
6. Press **Get the ₹249 book** again for the same details and language: no payment window - "already yours".
7. Press **Get the ₹49 report** for those same details: it **must still charge**. It is a different product, not a
   cheaper copy of what you already own.

**B. ₹99 Basic consultation (10 questions + the simple report)** - http://localhost:8000/ai-astrologer
1. Enter birth details > start the consultation > ask 2 questions (free).
2. The paywall appears with **two** buttons: **₹99: 10 questions + your report** and
   **₹299: 10 questions + the detailed book**. Press the **₹99** one > pay with `success@razorpay` (UPI) or the test card.
3. At once: the chat re-opens with **10 questions left** and a box above it says the included Kundali PDF is being
   prepared. Ask a question meanwhile - it works.
4. Within **3-5 minutes** the box turns into **Download your PDF** - the ₹99 pack bundles the *simple* report, so it
   is promised the shorter wait. The same `/order/...` page lists both parts. This PDF is the **simple report**
   (~8-12 pages), not the book - that is what ₹99 includes.
5. **The step that proves the tiers are wired up.** Go to `/birth-chart` with the same birth details and the
   consultation's language:
   - **Get the ₹49 report** must NOT charge again - "already yours", because the ₹99 pack included it;
   - **Get the ₹249 book** must still charge normally.
   If the ₹49 button asks for payment, or the ₹249 one says "already yours", the bundled entitlement is pointing at the
   wrong tier - stop and report it rather than paying again.

If something goes wrong after paying: `.venv/bin/python scripts/fulfil_order.py --list` shows paid orders that are not
delivered (e.g. the AI key was missing); `... ord_XXXX --run` delivers it. A payment is never lost.
Negative check: `.venv/bin/python scripts/live_payment_check.py --verify order_X pay_Y 0000` prints INVALID.

(Until frontend's new URLs are live the same steps work at the old addresses `/janam-kundali` and `/consultation`.
Hindi and Marathi: `/hi/...` and `/mr/...` versions of the same two pages - the purchase panel follows the page language.)

### Setting `RAZORPAY_WEBHOOK_SECRET` later, on the VPS

1. Invent the secret on the server: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. Put it into `/srv/astrology/.env` as `RAZORPAY_WEBHOOK_SECRET=...` and `sudo systemctl restart astrology`.
3. Razorpay dashboard (Test mode now, Live mode again at go-live) > Account & Settings > Webhooks > **+ Add New Webhook**:
   URL `https://rashikundli.com/api/payments/webhook`, **Secret = the same string**, events `payment.captured`,
   `order.paid`, `payment.failed`. Test mode asks for an OTP: `754081`.
4. Check: `scripts/smoke_check.py https://rashikundli.com` must say "webhook endpoint rejects a bad signature (secret is
   set)"; then pay once and close the tab before the success screen - `journalctl -u astrology | grep "PAID"` shows
   `via webhook`. Until the secret is set the endpoint answers 503 and only the browser path (`/verify`) confirms
   payments - fine for local testing, not for production.

### Webhook (needs a public https URL, so usually first on the VPS)

https://razorpay.com/docs/webhooks/setup-edit-payments/ and https://razorpay.com/docs/webhooks/validate-test/

1. Dashboard in Test mode (set it up again in Live mode later - check that the webhook list of each mode shows it) > Account & Settings >
   Webhooks > **+ Add New Webhook**.
2. URL `https://rashikundli.com/api/payments/webhook`, Secret = your `RAZORPAY_WEBHOOK_SECRET`, an alert e-mail, Active
   events: **payment.captured**, **order.paid**, **payment.failed**. In test mode the dashboard asks for an OTP: `754081`.
3. Test it: start a payment on the site, pay, and close the tab before the success screen. Within seconds the order
   is `paid` anyway (`scripts/fulfil_order.py ord_...` prints `via=webhook`; the log says `PAID via webhook`).
   For a local machine Razorpay's docs suggest a tunnel (zrok); localhost URLs are not accepted.
4. Razorpay expects a 2xx within 5 seconds and retries for 24 hours with back-off; the endpoint only records the
   payment and answers, generation runs in the background. Duplicate deliveries are harmless (`x-razorpay-event-id`
   is de-duplicated and fulfilment is idempotent anyway).

If both the browser and the webhook were missed (rare): `scripts/fulfil_order.py order_XXXX --reconcile` asks
Razorpay's API whether the order has a captured payment of the right amount, and delivers if so.

## Going live (Phase 8)

- Live keys + a Live-mode webhook with its own secret; `BASE_URL=https://...` (makes the cookie `Secure`);
  `SESSION_SECRET` set; **no `REPORTS_UNLOCKED`**; `TRUST_PROXY=1` behind the reverse proxy; nginx must pass the
  webhook body through untouched (default) and allow POST without buffering tricks; persistent, backed-up `var/`
  (`app.db` = orders and balances, `reports/` = what customers bought, `pdfs/` = cache, may be deleted).
- Razorpay account activation (KYC, website policy pages: terms, refund policy, contact) is needed before live keys work.
- The order token travels in URLs (`/order/<token>`, `...pdf?token=`): treat web-server access logs as confidential.
- On start the app resumes paid orders whose report job was interrupted by a restart.
- Checks that need no browser: `scripts/live_payment_check.py`, `scripts/fulfil_order.py --list`;
  full offline browser check of the flow: `scripts/browser_check_payments.py`.

## Admin

```
.venv/bin/python scripts/fulfil_order.py --list              # paid but not delivered
.venv/bin/python scripts/fulfil_order.py ord_... --run       # deliver now (also accepts order_... or the page token)
.venv/bin/python scripts/fulfil_order.py order_... --reconcile
sqlite3 var/app.db "select id, product, status, fulfilment, attempts, error from orders order by created_at desc limit 20"
```
