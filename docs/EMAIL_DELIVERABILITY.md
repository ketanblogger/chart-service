# Sign-in e-mail: the DNS records Resend needs

Every sign-in now depends on one e-mail arriving. If these records are not right, the code lands in spam and
**the login looks broken to the customer** - the feature fails in a way that looks like our bug and is not.

This is the one part of the feature that is not code and cannot be tested from here: DNS is the operator's to set,
and whether a record is live can only be read from the public DNS, not asserted in pytest.

## What to do, in order

1. In the Resend dashboard, open **Domains → Add Domain** and enter `rashikundli.com`.
2. Resend shows **three records**. Add them at the DNS host for the domain, exactly as shown there.
3. Press **Verify** in Resend. It usually goes green in minutes; DNS can take up to an hour.
4. Then, on the VPS, set `MAIL_TEST_MODE` to nothing (or remove the line) and restart. **Until the domain is
   verified, leave `MAIL_TEST_MODE=1`** - see the warning below.

## The three records, and what each is for

Resend generates the exact values; these are the names and shapes so you can tell at a glance that the right
thing has been pasted into the right box.

| Type | Name (host) | Value | What it does |
|---|---|---|---|
| `TXT` | `send.rashikundli.com` | `v=spf1 include:amazonses.com ~all` | **SPF.** Says Amazon SES (which Resend sends through) is allowed to send as this domain. Without it the mail is "unauthenticated" and Gmail puts it in spam |
| `TXT` | `resend._domainkey.rashikundli.com` | `p=MIGfMA0GCSq...` (a long public key, from Resend) | **DKIM.** Signs every message so the receiver can prove it was not altered and did come from us. This is the one that matters most |
| `MX` | `send.rashikundli.com` | `feedback-smtp.<region>.amazonses.com` priority `10` | Bounce and complaint handling, so a dead address stops being retried |

**Do not put SPF on the root domain** if you already have an SPF record there for another sender - a domain
may have only ONE SPF record, and a second one makes both invalid. Resend's subdomain (`send.`) exists
precisely so this does not collide with anything already on `rashikundli.com`.

## Afterwards, worth adding (not required by Resend)

| Type | Name | Value | Why |
|---|---|---|---|
| `TXT` | `_dmarc.rashikundli.com` | `v=DMARC1; p=none; rua=mailto:<your address>` | **DMARC** on `p=none` changes nothing about delivery but makes Gmail and Outlook send you a weekly report of who is sending as your domain. Start at `p=none`; only tighten to `quarantine` after the reports are clean for a few weeks |

## How to check it is actually working

```sh
dig +short TXT send.rashikundli.com
dig +short TXT resend._domainkey.rashikundli.com
dig +short MX  send.rashikundli.com
```

Then send yourself a sign-in code and, in Gmail, open the message → **⋮ → Show original**. The header block at
the top must read:

```
SPF:   PASS
DKIM:  PASS
DMARC: PASS
```

Three PASSes is the whole test. One FAIL and the record for it has not propagated or was pasted wrong.

## MAIL_TEST_MODE: what it is for, and why it must not stay on

`MAIL_TEST_MODE=1` writes the sign-in code **to the journal** instead of sending it, and reports success. It
exists so the sign-in flow can be built and driven on a machine whose sending domain is not verified - without
it every login here would fail for a reason that has nothing to do with the code under test.

**On the live server it is the opposite of a convenience: it hands an account to anyone who can read the
log.** `python -m app.hardening` lists it as a problem for exactly that reason, and the smoke check will
show it. Turn it off the moment Resend goes green.
