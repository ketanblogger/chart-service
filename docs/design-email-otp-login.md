# Design: e-mail OTP login and a "My orders" page

**Status: design only. No code exists for any of this, and none should be written from this document until
the open questions at the end are answered.** Written 30 September 2026. Several decisions that constrain it
were taken at launch and are stated here where this design depends on them - each one is marked as a decision
already taken, rather than argued again.

## What problem this solves, and what it does not

A customer buys a report and gets a permanent link, `/order/{token}`, by e-mail. That link is the whole
account system today. It works, it survives a lost cookie, it works on any device, and it needs nothing from
the customer — which is why **it is not being replaced**.

What it does not do is answer "what have I bought from you?". A customer who bought three reports has three
links in three e-mails, and if one of those e-mails went to spam that purchase is, from their side, gone. They
write to support, support asks for the order reference they do not have, and the exchange costs more than the
report did. That is the problem: **recovery and a list**, not authentication for its own sake.

Two things follow from that framing and they are the load-bearing decisions in this design:

- **Login is an ALTERNATIVE route to things the customer can already reach, never the only route.**
  `/order/{token}` keeps working, without login, permanently. It is the fallback when an OTP lands in spam,
  which would otherwise turn "I cannot log in" into "I cannot get the thing I paid for". This is not a
  transitional arrangement to be tidied away later.
- **Nothing is gated BEHIND login that is not gated today.** The download, the invoice, the credit note and
  the consultation all stay reachable by token. Adding a login that takes something away from a customer who
  had it yesterday is the one outcome that makes this a net loss.

## The shape of it

Three endpoints and one page. Nothing else.

| Route | Method | What it does |
|---|---|---|
| `/login` | GET | The form: one e-mail field, in the page's language |
| `/api/auth/request-code` | POST | Accepts an address, always answers the same, sends a code if there is anything to log in to |
| `/api/auth/verify-code` | POST | Accepts address + code, sets the session cookie on success |
| `/orders` | GET | The list, for a signed-in reader. Redirects to `/login` when there is no session |

### The code

Six digits, cryptographically random (`secrets.randbelow(1_000_000)`, zero-padded — **not** `random`).
Ten-minute expiry, **single use**, at most five verification attempts against one code, after which it is
dead and a new one must be requested. Stored as a hash, not in the clear: this table will sit in the same
SQLite file as the orders, and a code in the clear is a password in the clear for the ten minutes it lives.

Rate limits, all three of which are needed and none of which is the same limit:

- per address: 3 codes per hour — stops an attacker using the site to mail-bomb somebody,
- per IP bucket: 20 codes per hour — stops an attacker walking a list of addresses,
- per code: 5 verification attempts — stops guessing six digits.

The IP bucket is `chat_identity.ip_bucket`, which is already an HMAC of the /24 or /48 and never a raw IP.

### The session

A signed cookie, ~30 days, `httpOnly`, `Secure`, `SameSite=Lax`, **reusing `app/ai/chat_identity`'s HMAC** so
there is no new crypto and no second secret to rotate. It carries the verified e-mail address, not a user id,
because the address IS the identity here — there is no user row to point at, and inventing one would mean
deciding what happens when the same person buys under two addresses, which nothing in this design needs to
answer.

The `uid` cookie stays exactly as it is and keeps doing its job. The two are independent: a signed-in reader
still has their `uid`, and losing one does not affect the other.

### The list

`/orders` shows, for the verified address, every paid order with that address in `orders.email`: what it was,
when, how much, its state, and the same links the order page offers — download, invoice, credit note. It shows
**no birth data**: the list is a list of purchases, and a page that prints a date of birth is a page that
leaks one if the session is ever wrong. The order page already shows what the customer entered; this does not
repeat it.

## What makes this harder than it looks: the credits

This is the part to write tests for FIRST, before any of the above.

Consultation credits today live on `chat_users.paid_balance`, keyed by `user_id` — the cookie. A purchase
adds to the balance of whichever cookie was in the browser at checkout. That is fine while the cookie is the
only identity. It stops being fine the moment a second identity exists, because then "does this person have
credits?" has two possible answers and the wrong one either **loses a customer's credits** or **lets them
spend the same credit twice**.

A decision already taken: **paid credits are keyed by the CHECKOUT E-MAIL from the start, not re-keyed
later.** Free credits stay on `chat_users.user_id`. That means:

- every "has credits?" read consults both identities and spends from the paid one first,
- a purchase adopts the checkout e-mail as the session's identity at payment time, so a buyer keeps chatting
  immediately without logging in at all,
- there is no merge step, and therefore no merge bug, when the same person buys on a phone and logs in on a
  laptop.

**Write the double-spend test and the lost-credit test before the feature.** Concretely: buy 10 questions as
a cookie with no login; spend 4; log in on a different "device" (a second client with no cookie); spend 6;
assert the balance is 0 and not 6, and that no seventh question is answered. Then the reverse: buy, clear the
cookie, log in, assert the 10 are still there. Both of these are cheap to write now and impossible to
retrofit confidently once the feature is live and money has moved.

## Failure modes, and what each one must do

| What goes wrong | What must happen |
|---|---|
| The OTP e-mail does not arrive | `/order/{token}` still works. The `/login` page says so, with the words "check the link in your purchase e-mail" — the fallback has to be **on the page**, not in support's head |
| Resend is down | Requesting a code answers the same as always, and the journal carries the failure. The customer is not told the mail system is broken; they are told to use their purchase link |
| An address with no orders asks for a code | The same answer as an address with orders, and no e-mail. Anything else turns this form into an oracle for "is this person a customer" |
| Somebody guesses a code | Five attempts, then the code is dead. The rate limit is per code, not per session, or a new session resets the counter |
| A session cookie is stolen | It expires in 30 days and carries no ability to change anything — there is nothing to change. It can read the list and download what was already bought |
| Two people share an address | They see each other's orders, which is the same thing that happens with a shared inbox today |

## The dependency that is not code

**Deliverability.** Resend with SPF and DKIM verified on the sending domain, before any of this ships. An OTP
that lands in spam is worse than no login: the customer tried, it failed, and now they think the site is
broken. This is a prerequisite, not a nice-to-have, and it is the reason this design keeps the token link as
a first-class route rather than a legacy one.

There is also a cost that is not technical: **e-mail becomes required at checkout**, and it is labelled
optional in three languages today. Requiring it will cost some conversions. Watch the order rate for a week
after that change specifically, separately from this feature — if the two ship together, a fall in orders
cannot be attributed to either.

And one invariant is retired deliberately: `docs/PAYMENTS.md` says "nothing in this app sends e-mail or calls
a third party". That sentence has already stopped being true (the order-link e-mail), and the correction
belongs in the same commit as the change that breaks it, so that no later reader treats it as an accident.

## What this design deliberately does not include

- **Passwords.** Nothing here is worth a password, and a password is a support burden and a breach surface.
- **A profile, a name, or preferences.** There is nothing to store that is not already on the order.
- **Deleting an order from the list.** The list is a record of purchases; a customer who wants data removed
  is a privacy request, which `/privacy` already describes and which is handled by a person.
- **Social login.** A third party between a customer and their purchase, for no gain.
- **Merging two addresses.** See the credits section: the design avoids needing it.

## Open questions, which are why this is a design and not a plan

1. **Does the order e-mail become required before or with this?** They are separable and the answer changes
   the rollout. Requiring it first makes this feature useful on day one; doing both at once makes a fall in
   conversion impossible to attribute.
2. **What happens to orders placed before e-mail was required?** They have no address, so they can never
   appear in a list. The token link still works — but a customer who logs in and sees two of their three
   purchases will write to support about the third, which is a worse experience than not offering the list.
   Possibly the list should say how many older purchases are not shown.
3. **Is `/orders` indexable, and what does a logged-out visitor see?** It must be `noindex` either way; the
   question is whether it redirects to `/login` or renders an explanation.
4. **Which languages?** The rest of the site is three; the policy pages are English only. A login form is
   product, not legal, so it should be three — which means three OTP e-mail templates as well.
