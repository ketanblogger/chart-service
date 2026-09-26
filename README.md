# AI Astrology Platform

Swiss Ephemeris calculates, Claude interprets: the engine computes every position, date and degree, and
the AI only puts those facts into words. `docs/API.md` is the reference for both halves.

## Setup

Uses Python 3.11 in a [uv](https://docs.astral.sh/uv/)-managed venv. 3.11 because
`pyswisseph` publishes prebuilt wheels for it — the dev machine has no C compiler,
so everything must install from wheels.

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env   # then fill in keys
.venv/bin/playwright install chromium-headless-shell   # headless Chromium for report PDFs (docs/API.md, "Report PDFs")
.venv/bin/python scripts/pdf_sample.py                 # smoke test: Marathi sample PDF -> var/samples/
```

## Run

```sh
.venv/bin/uvicorn app.main:app --reload --port 8000
curl localhost:8000/health         # {"status":"ok"}
curl localhost:8000/health/ready   # database, Swiss Ephemeris files, fonts, var/ (add ?chromium=1 for the PDF browser)
.venv/bin/python -m app.hardening  # what would block / worry a production start
```

Works without any key: the free tools, rashifal pages (engine facts until the first refresh), SEO pages. Buy buttons
show "launching soon" until Razorpay keys are set; paid report APIs answer 402.

## What is built (spec phases)

| Phase | What | Where | Status |
|---|---|---|---|
| 0-1 | FastAPI + Swiss Ephemeris engine (chart, dasha, doshas, matching, transits) | `app/engine`, `app/api.py` | done |
| 2 | Tool landing pages (one template) | `app/web`, `app/static` | done |
| 3 | AI detailed reports (interpret-only, fact + safety checked) | `app/ai` | code done; live check needs the Anthropic key |
| 4 | Report PDFs (Chromium, bundled Devanagari fonts) | `app/pdf` | done |
| 5 | AI consultation chat (2 free, paywall, memory, safety) | `app/ai/chat*`, `/consultation` | code done; live check needs the key |
| 6 | Razorpay payments (orders, signature verify, webhook, order page) | `app/payments`, `docs/PAYMENTS.md` | code done; test payment needs Razorpay test keys |
| 7 | Rashifal automation: 60 permanent URLs, scheduled refresh | `app/rashifal`, `deploy/systemd/rashifal-refresh.*` | code done; first refresh needs the key |
| 8 | SEO (sitemap, robots, JSON-LD, Marathi flagship page, policy pages), hardening, deploy kit | `app/web/seo.py`, `app/web/marathi.py`, `app/web/policies.py`, `app/hardening.py`, `deploy/` | built; the deploy itself is an operator step |

Deploy runbook: `deploy/README-DEPLOY.md`. API reference: `docs/API.md`. Payments operator guide:
`docs/PAYMENTS.md`. Licence and the source offer: `LICENSE`.

## Live checks (real, billed calls - run once the keys exist, then READ the output)

```sh
.venv/bin/python scripts/live_report_check.py                 # Phase 3: en + mr kundali report -> var/live_check/*.md, prints cost
.venv/bin/python scripts/live_chat_check.py                   # Phase 5: scripted consultation incl. safety probes
.venv/bin/python scripts/live_payment_check.py                # Phase 6: one real Razorpay test-mode order (needs test keys)
.venv/bin/python scripts/rashifal_refresh.py --estimate       # Phase 7: cost table, no AI call
.venv/bin/python scripts/rashifal_refresh.py --period all --force && .venv/bin/python scripts/rashifal_check.py
```

Offline checks that need no key: `scripts/pdf_sample.py` (Marathi sample PDF), `scripts/smoke_check.py
http://127.0.0.1:8000 --no-https` (against a running server), and the real-browser checks
`scripts/browser_check_payments.py`, `browser_check_i18n.py`, `browser_check_consultation.py`,
`browser_check_rashifal.py`, `browser_check.py` (Playwright; on the dev box without system libraries see each
script's docstring for `LD_LIBRARY_PATH` / `XDG_DATA_HOME`).

## Test

```sh
.venv/bin/python -m pytest          # no network, no keys; browser-marked tests skip if Chromium cannot launch
```

## Layout

- `app/main.py` — FastAPI app; `app/api.py` — JSON API over the engine, documented in `docs/API.md`
- `app/engine/` — calculation engine (pyswisseph, Lahiri). Math only, no AI.
  `app/engine/ephe/*.se1` are the official Swiss Ephemeris data files (1800–2399 CE);
  without them swisseph silently falls back to the less precise built-in Moshier ephemeris.
- `app/ai/` — Claude interpretation layer. Interprets engine output, never calculates.
- `app/payments/` — Razorpay: price catalogue, orders (SQLite), signature-verified payment, idempotent fulfilment,
  webhook, `/order/{token}` purchase page. Operator's guide: `docs/PAYMENTS.md`.
- `app/hardening.py` — production config check (`APP_ENV=production`), security headers + CSP, gzip, static caching,
  `/health/ready`, 404/500 pages.
- `app/pdf/` — report JSON → print HTML (Jinja2) → PDF via headless Chromium. Bundles Noto Sans + Noto Sans
  Devanagari (`fonts/`, OFL) so Marathi/Hindi never depend on system fonts; `chart_svg.py` mirrors `render.js`.
- `app/rashifal/` — rashifal automation (180 permanent URLs = 12 rashis × 5 periods × en/hi/mr): engine transit brief → Claude → checked, stored readings;
  `scripts/rashifal_refresh.py` is the scheduler entry point (`deploy/systemd/`), `scripts/rashifal_check.py` the
  "done when" check. Pages: `app/web/rashifal.py` — they read the store and the engine, never the AI. See `docs/API.md`, "Rashifal".
- `app/web/` — server-rendered public pages (Jinja2). Every tool page is `templates/tool.html` + one entry in
  `app/web/pages.py` (copy, FAQs, form type, API endpoint, paid product); brand name lives in `app/web/site.py`.
- `app/static/` — `css/site.css`, `js/render.js` (pure JSON → HTML renderers, also run by the tests in an
  embedded V8) and `js/app.js` (form, city combobox, fetch). No build step, no CDN, no AI calls.
- `deploy/` — runbook, production `.env` template, systemd units, nginx site, backup script.
- `tests/`
- `var/` — runtime data, git-ignored: `app.db` (orders, balances, chats, rashifal), `reports/`, `pdfs/` (cache)
