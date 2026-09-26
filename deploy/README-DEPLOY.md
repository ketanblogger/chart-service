# Deploy runbook - fresh Ubuntu 22.04 / 24.04 VPS

Everything that needs the server or the domain is here, in order. Nothing in this file has been run against a real
VPS yet (there was no VPS or domain while it was written); the units were linted with `systemd-analyze verify`, the
smoke script was run against a local uvicorn, nginx could not be tested locally - run `sudo nginx -t` before reload.
Domain: **rashikundli.com** (English at `/`, Hindi under `/hi/`, Marathi under `/mr/` - one app, one certificate). **Minimum 2 GB RAM** / 1 vCPU. Printing the 30-60 page Kundali book is the heaviest thing the server does: about **400 MB and 2-3 s** of Chromium per report (measured; proportional set size, two render passes in one browser). **That 2-3 s is PRINT time, not the time to produce a report** - generating one is minutes of AI (see docs/API.md "How it is generated"), and the render slot is held only for the printing. Conflating the two is how you end up sizing this box for a problem it does not have.

Two measurements worth having before you tune anything here (both `taskset -c 0,1` on a dev box, pinned to two cores to model this VPS):

- **The render is not CPU-bound, so cores buy very little.** The 64-page book is 2.35-2.52 s on two pinned cores against 2.28-2.93 s on twelve - six times the cores for under 20%. The free chart sheet is 0.71 s against 0.62-0.65 s. Two *concurrent* book renders on two pinned cores cost about 28% each, not 2x, so raising `PDF_MAX_CONCURRENT` does not trade wall time away.
- **RSS is the binding constraint, at roughly 450-500 MB per additional concurrent render.** One book peaks at ~620 MB and two at once at ~1240 MB (summed VmRSS across the whole Chromium process tree, which double-counts shared pages - the 400 MB above is the same render as proportional set size). So the `600 MB + 450 MB x PDF_MAX_CONCURRENT` budget below is the number to size against, not the core count.

`PDF_MAX_CONCURRENT` (default 1) is enforced **machine-wide** by a file lock in `var/`, so more uvicorn workers do NOT mean more simultaneous renders - one book at a time whatever `--workers` says. Budget roughly `600 MB + 450 MB x PDF_MAX_CONCURRENT`; `python -m app.hardening` warns when this box cannot cover that, and fails production start if you also raised the limit above 1. A paid book waits its turn for that slot; the free chart PDF waits only `PDF_FREE_WAIT_SECONDS` (2) and then returns a 503, because it is the ungated route and a queued request holds a FastAPI threadpool thread. **On a 2 GB box add swap before anything else** - the first book render is where you would otherwise
meet the OOM killer:

```sh
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab      # survives a reboot
free -h                                                          # confirm it is there
```

Before you start, have the accounts and decisions in place: the Anthropic API key, the Razorpay keys (test
first), the AI model choice, the brand
and domain, legal entity details, and the **Swiss Ephemeris licence decision**.

## 0. NEVER `git push` FROM THIS REPOSITORY

**This working repository has no upstream by design, and it must never gain one.** `git remote -v` shows
an `origin` and the public repository at that URL is live - but it was not produced by pushing this tree.
It was built through a separate publication procedure, so the two histories are unrelated. Confirm it in
two commands: `git ls-remote origin` returns a HEAD that `git cat-file -e <that sha>` cannot find here.

A push from here is therefore rejected as unrelated histories. **The danger is not that command - it is
what a person does next when a push "won't go through", which is `--force`.** Forcing would replace the
public repository with this one's entire history, which is not what the public repository is supposed to
contain, and it cannot be undone by deleting anything afterwards.

**Publishing new work is a re-clone through that procedure, never a push.** The procedure, and the list
of what it holds back and why, are in the launch checklist in the private working copy - deliberately not
in this tree, so whoever publishes needs the private repository to do it.

If you are reading this because a push was rejected: that rejection is the guard working. Stop.

## 1. DNS

| Record | Name | Value |
|---|---|---|
| A | `rashikundli.com` | VPS IPv4 |
| AAAA | `rashikundli.com` | VPS IPv6 (only if the VPS has one) |
| CNAME (or A) | `www` | `rashikundli.com` (nginx redirects www to the apex; `BASE_URL` is the apex) |

Wait until `dig +short rashikundli.com` shows the VPS address before step 7 - certbot fails without it, and
a failed certificate is what strands a first deploy. Check `www` too if you added it to the certificate.

## 2. System packages, user, firewall

```sh
sudo apt update && sudo apt -y upgrade
sudo apt -y install nginx certbot python3-certbot-nginx sqlite3 git curl ufw
sudo adduser --system --group --home /home/astro --shell /bin/bash astro
sudo mkdir -p /srv/astrology && sudo chown astro:astro /srv/astrology
sudo ufw allow OpenSSH && sudo ufw allow "Nginx Full" && sudo ufw --force enable     # 22, 80, 443 only
sudo timedatectl set-timezone Asia/Kolkata                                           # log times; the app itself is timezone-safe
```

## 3. Code, Python 3.11, dependencies

Python 3.11 because `pyswisseph` ships prebuilt wheels for it (no compiler needed). `uv` downloads its own 3.11.

```sh
sudo -iu astro
curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.local/bin/env
git clone https://github.com/ketanblogger/chart-service /srv/astrology && cd /srv/astrology
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
mkdir -p var && chmod 750 var
exit
```

## 4. Headless Chromium for the PDFs

The browser goes inside the project (`PLAYWRIGHT_BROWSERS_PATH`, same value as in `.env`); its system libraries need root.

```sh
sudo PLAYWRIGHT_BROWSERS_PATH=/srv/astrology/.playwright /srv/astrology/.venv/bin/playwright install --with-deps chromium-headless-shell
sudo chown -R astro:astro /srv/astrology/.playwright
```

No system fonts are needed: Noto Sans + Noto Sans Devanagari are bundled in `app/pdf/fonts`.

## 5. Configuration

```sh
sudo -u astro cp /srv/astrology/deploy/env.production.example /srv/astrology/.env
sudo -u astro chmod 600 /srv/astrology/.env
sudo -u astro nano /srv/astrology/.env
```

`BASE_URL=https://rashikundli.com`, `SITE_NAME=RashiKundli` and the models are pre-filled. Fill in: `SESSION_SECRET`, the
`LEGAL_*` / `SUPPORT_*` lines, `ANTHROPIC_API_KEY`, the three `RAZORPAY_*` values (`TRUST_PROXY=1` is already set). Leave
`PDF_CHROMIUM_LD_LIBRARY_PATH=` empty. Never add `REPORTS_UNLOCKED`. Then:

```sh
cd /srv/astrology && sudo -u astro .venv/bin/python -m app.hardening      # must print no FATAL line
sudo -u astro .venv/bin/python -m pytest -q -m "not browser"              # optional: the suite on the server
sudo -u astro .venv/bin/python scripts/pdf_sample.py                      # must end with "fallback fonts: none"
```

## 6. Services

```sh
sudo cp /srv/astrology/deploy/systemd/astrology.service /srv/astrology/deploy/systemd/rashifal-refresh.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now astrology
sudo systemctl enable --now rashifal-refresh.timer
systemctl status astrology --no-pager ; curl -s localhost:8000/health/ready
```

If `astrology` fails at once, `journalctl -u astrology -n 30` shows the config check's reason (that is the intended
behaviour with `APP_ENV=production`). Logs go to journald: `journalctl -u astrology -f`; cap them with
`SystemMaxUse=500M` in `/etc/systemd/journald.conf` (`sudo systemctl restart systemd-journald`). nginx logs are
rotated by the distro's logrotate.

First rashifal content (60 billed AI calls - see the cost estimate first):

```sh
sudo -u astro .venv/bin/python scripts/rashifal_refresh.py --estimate
sudo -u astro .venv/bin/python scripts/rashifal_refresh.py --period all --force && sudo -u astro .venv/bin/python scripts/rashifal_check.py
```

Until then the 60 pages are live with the engine's transit facts (never empty), so deploy order does not matter.

## 7. HTTPS first, then nginx

**Order matters here and it is the one place a first deploy can strand you.** The shipped config has a 443
block naming `/etc/letsencrypt/live/rashikundli.com/...`, so `nginx -t` **fails until those files exist** - and
the webroot flow needs nginx already serving port 80, which it cannot do while `nginx -t` fails. On a fresh box
that is a circle. Break it with `--standalone`, which runs certbot's own listener for a few seconds:

```sh
sudo systemctl stop nginx                                     # certbot needs port 80 to itself
sudo certbot certonly --standalone -d rashikundli.com -d www.rashikundli.com \
    --agree-tos -m YOUR-EMAIL --no-eff-email
sudo ls /etc/letsencrypt/live/rashikundli.com/fullchain.pem   # must exist before you go on
```

DNS must already resolve to this box (step 1) or certbot fails - that is the check at the end of step 1.

Now install the site config, which can be tested because the certificates exist:

```sh
sudo cp /srv/astrology/deploy/nginx/astrology.conf /etc/nginx/sites-available/astrology      # already written for rashikundli.com
sudo ln -sf /etc/nginx/sites-available/astrology /etc/nginx/sites-enabled/astrology && sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl start nginx
```

## 8. Certificate renewal

Renewal is automatic and uses **webroot**, which works from now on because nginx serves
`/.well-known/acme-challenge/` on port 80 (it is in the shipped config). Give it a reload hook so a renewed
certificate is actually picked up:

```sh
sudo mkdir -p /var/www/html
echo 'renew_hook = systemctl reload nginx' | sudo tee -a /etc/letsencrypt/cli.ini
sudo systemctl list-timers | grep certbot        # the timer certbot installed
sudo certbot renew --dry-run                     # proves the renewal path before it matters in 60 days
```

Do the dry run. A renewal that fails silently takes the site down 90 days from now, and that is a worse night
than this one.

## 9. Smoke check

```sh
cd /srv/astrology && sudo -u astro .venv/bin/python scripts/smoke_check.py https://rashikundli.com --chromium --expect-payments
```

Must end with `0 failure(s)`. It checks readiness, robots + all 246 sitemap URLs of the three language trees (200,
indexable, self-canonical, right `<html lang>`, hreflang in the page == sitemap), the 180 rashifal URLs, that old URLs
(`/janam-kundali`, `/rashifal/...?lang=`) 301 in one hop, the HTTP->HTTPS redirect, HSTS, the Secure cookie, CSP and other headers, the reference kundali from the
free API, that the paid report API answers 402, that `/order/*` is hidden, the payments switch and webhook secret,
static caching, gzip, placeholders left on the policy pages, and a local Marathi PDF ("fallback fonts: none").

## 10. Razorpay webhook + the end-to-end purchase ("done when")

1. Razorpay dashboard > Account & Settings > Webhooks > Add: `https://rashikundli.com/api/payments/webhook`, secret =
   `RAZORPAY_WEBHOOK_SECRET`, events `payment.captured`, `order.paid`, `payment.failed` (details: `docs/PAYMENTS.md`).
> **Read this before the live-key run.** The first order paid with LIVE Razorpay keys starts the **Swiss
> Ephemeris licence clock**: `app/payments/first_sale.py` logs `*** FIRST LIVE SALE ***` at CRITICAL, writes
> `var/first_live_sale.json` and records it in the database, and the professional licence must be bought
> **within 7 days** of that moment (https://www.astro.com/swisseph/swephprice_e.htm). It fires once and cannot
> be reset, and **your own test purchase counts** - it is a real payment with real keys. Do the test-key pass
> first, and only switch to live keys when you are ready for that week to start.
> Check it any time with `sudo -u astro .venv/bin/python scripts/first_sale_status.py`.

2. On a phone, open `https://rashikundli.com/mr/` > the kundali page (English: `/birth-chart`), create a kundali, buy the
   **₹49 simple report** - the cheapest real charge, and the kundali page now offers ₹49 and ₹249 side by side, so
   press the right one. Do the whole sequence with **test** keys and the test card / `success@razorpay` first; then
   swap `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` (and the webhook secret, if the Live webhook has its own) in
   `/srv/astrology/.env`, `sudo systemctl restart astrology`, and repeat once with a real ₹49.
   Keep the browser console open on a
   desktop run: **no Content-Security-Policy errors may appear while Razorpay's window is open**. If one does, set
   `CSP_MODE=report-only`, restart, note the blocked host, add it to `_CSP` in `app/hardening.py`, switch back.
3. Expect: "preparing your report" -> Download PDF -> the PDF opens with correct Marathi -> the `/order/...` link works
   in a private window.
4. Pay again and close the tab right after paying: within a minute `scripts/fulfil_order.py --list` is empty and the
   journal shows `PAID via webhook`.
5. On `/ai-astrologer`, after the 2 free questions, buy the ₹99 consultation: "10 questions left" at once, and within
   3-5 minutes the included Kundali PDF appears above the chat and on the same `/order/...` page (the ₹99 pack
   bundles the simple report, so it is promised the shorter wait; the ₹299 tier promises 5-10).
6. Refund the live test payments in the Razorpay dashboard.

## 11. Google Search Console

1. https://search.google.com/search-console > Add property > **Domain** property for `rashikundli.com` > add the TXT
   record it shows to DNS > Verify.
2. Sitemaps > submit `https://rashikundli.com/sitemap.xml` (one sitemap for all three language trees, hreflang en / hi / mr + x-default).
3. URL inspection > Request indexing for `/`, `/hi/`, `/mr/`, `/birth-chart`, `/horoscope`, `/hi/rashifal`,
   `/mr/rashi-bhavishya` and two or three daily rashifal pages per language. After a week check Pages > "Why pages aren't indexed" and International targeting / hreflang errors.
4. Optional: Bing Webmaster Tools can import the property from Search Console.

## 12. Backups

```sh
sudo -u astro crontab -e      # add:
17 2 * * * /srv/astrology/deploy/backup.sh >> /srv/astrology/var/backup.log 2>&1
```

`deploy/backup.sh` snapshots `var/app.db` with `sqlite3 .backup` (safe while the app writes) and tars `var/reports`,
keeping 14 days in `var/backups`. **Copy them off the server** (rclone / rsync line at the end of the script).
Restore: stop the service, `gunzip -c app-....db.gz > var/app.db`, untar reports into `var/`, start the service.
Also keep a copy of `.env` somewhere safe - losing `SESSION_SECRET` logs every customer out of their paid balance
(purchased reports stay reachable through their `/order/<token>` links).

## 13. Updates and rollback

```sh
cd /srv/astrology
sudo -u astro git fetch --tags && sudo -u astro git status                   # must be clean
sudo -u astro git pull --ff-only
sudo -u astro ~astro/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt
sudo -u astro .venv/bin/python -m app.hardening && sudo systemctl restart astrology
sudo -u astro .venv/bin/python scripts/smoke_check.py https://rashikundli.com --expect-payments
```

A restart never loses a paid order: report jobs interrupted by it are resumed at startup. Static files get a new
`?v=` hash automatically. If Playwright was upgraded in `requirements.txt`, repeat step 4.

Rollback = check out the previous good commit (tag each release: `git tag release-YYYYMMDD && git push --tags`):

```sh
sudo -u astro git checkout release-YYYYMMDD      # or the commit of the last completed phase
sudo -u astro ~astro/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt
sudo systemctl restart astrology && sudo -u astro .venv/bin/python scripts/smoke_check.py https://rashikundli.com
```

The database only ever gains tables / columns through `CREATE TABLE IF NOT EXISTS`, so older code runs on a newer
`var/app.db`. Take a backup (`deploy/backup.sh`) before any update anyway.

## 14. Operations cheat sheet

```sh
journalctl -u astrology -f                                   # app log ("PAID order" = a paid order needing attention)
journalctl -u rashifal-refresh -n 100 ; systemctl list-timers rashifal-refresh.timer
sudo -u astro .venv/bin/python scripts/fulfil_order.py --list   # paid but not delivered
sudo -u astro .venv/bin/python -m app.hardening              # configuration problems
curl -s https://rashikundli.com/health/ready?chromium=1          # deep health (monitor /health every minute, this hourly)
```

Privacy note: `/order/<token>` and `?token=` URLs are credentials. The nginx log format in
`deploy/nginx/astrology.conf` strips tokens and query strings, and the systemd unit starts uvicorn with
`--no-access-log`, so tokens are not written to any log. Keep both settings.
