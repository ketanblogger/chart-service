# Blog publishing API

The interface an external writer ("Blogauto") uses to put posts on the RashiKundli blog. This file is
the whole specification: the Blogauto side can be built against it without reading our source.

**The one rule that governs everything below: a post arrives as a DRAFT.** `publish: true` in a request
body is a *request*, never an instruction. On a normal install the answer is always a draft, and a
human puts it live from `/admin/blog`. Nothing in this API can publish a post that fails a check, and
with the default configuration nothing in this API can publish a post at all.

| Route | Purpose | Success |
|---|---|---|
| `GET /api/blog/options` | the tool keys, category keys and limits this install accepts | 200 |
| `POST /api/blog/posts` | create a post | **201** |
| `PUT /api/blog/posts/{slug}` | replace a post's editable fields | 200 |
| `GET /api/blog/posts/{slug}` | read one back, with its state and why it is a draft | 200 |
| `POST /api/blog/images` | upload one image (the raw request body **is** the file) | **201** |

Everything is `application/json` except the image upload, whose request body is the image's bytes. Every
response carries `Cache-Control: no-store` and `X-Robots-Tag: noindex, nofollow`.

The blog is **English only**. There is no language field, and a body written in Devanagari is refused -
not because the writing is bad, but because there is no Hindi or Marathi blog tree for it to live in and
publishing it would put Devanagari under an English canonical with no `hreflang` to anywhere.

---

## 1. Authentication

A bearer token on every request:

```
Authorization: Bearer <token>
```

There is no other scheme, no API-key query parameter and no cookie. The token is a shared secret between
the operator and the writer; it is not per-user and it carries no identity.

### How the token is configured on the server

Either of these, in `/srv/astrology/.env`. **The file is preferred** - an environment variable is
readable from `/proc/<pid>/environ` by anything running as that user.

```bash
# preferred: the token lives in a file, and only its PATH is in the environment
BLOG_API_TOKEN_FILE=/home/<user>/.blog_api_token

# the fallback
BLOG_API_TOKEN=<token>
```

Create one with:

```bash
printf '%s' "$(python -c 'import secrets;print(secrets.token_urlsafe(32))')" > ~/.blog_api_token
chmod 600 ~/.blog_api_token
```

Rules the server applies:

* the token file **must be mode 600 or 400**. A looser mode is refused and logged (the mode is logged;
  the contents never are), and the API then behaves as if no token were configured;
* the file is read on every request, so **rotating the token is "write the file"** - no restart, and no
  window in which the old one still works;
* comparison is constant-time;
* **the token is never logged, echoed in a response, or returned by any endpoint.** A refusal says
  nothing about it - not its length, not whether the scheme was right, not how close a guess was.

### With no token configured, this API does not exist

Every route answers **404**, not 401. A 401 announces that there is something here worth guessing at,
and a half-finished deploy must not be able to accept a post. If you get a 404 from
`GET /api/blog/options`, the token is not configured on that box (or its file's mode is wrong).

### Rate limiting on failed attempts

Ten failed attempts from one network in fifteen minutes (`BLOG_API_MAX_FAILURES`,
`BLOG_API_FAILURE_WINDOW_MINUTES`) and the API stops comparing anything from that network:

```
429 Retry-After: <seconds>
{"detail": {"error": "locked_out", "message": "too many failed attempts; try again in 847 seconds"}}
```

A locked-out caller gets 429 **even with the correct token** until the window passes. Back off; do not
retry in a loop.

---

## 2. The body is Markdown, in a fixed subset

**HTML is not accepted. It is not sanitised, not stripped, and not escaped into visible text - it is
refused, and the post stays a draft.** Anything tag-shaped anywhere in the title, summary or body is a
blocking problem:

```
body: '<b>' is HTML, and HTML is not accepted - the body is Markdown and we build the tags ourselves
```

The reason is worth stating plainly, because it decides how Blogauto should generate prose: the server
escapes the whole body before it recognises a single construct, and then writes the tags itself from a
fixed list. There is no path by which a character from your text becomes part of a tag name or an
attribute. Sanitising HTML instead would be an allowlist we would have to keep current forever, and
every gap in it would be a cross-site scripting hole on a commercial site.

### What is supported

| Markdown | Becomes |
|---|---|
| `## Heading` | `<h2>` |
| `### Heading` | `<h3>` |
| a blank-line-separated block of text | `<p>` (single newlines inside it become spaces) |
| `- item` or `* item` | `<ul><li>` - consecutive lines make **one** list |
| `1. item` | `<ol><li>` |
| `> quoted` | `<blockquote><p>` |
| `---` or `***` alone on a line | `<hr>` |
| `**bold**` | `<strong>` |
| `*italic*` or `_italic_` | `<em>` |
| `` `code` `` | `<code>` (inline markup inside it is left alone) |
| `[text](target)` | `<a>` - see the link rules below |
| `![alt](url)` | `<img>` - see the image rules below |

### What is NOT supported

`# Heading` (a single hash), tables, fenced code blocks, footnotes, reference-style links, nested lists,
inline HTML, and raw URLs that are not inside `[...](...)`.

**`# Heading` is a blocking problem, not a silently demoted `<h2>`.** The post's one `<h1>` is its
title, rendered by the page; a second one on the page is a real defect. Use `##` for a section.

Anything else unsupported is simply not recognised and stays as literal text - which will look wrong on
the page, so do not rely on it.

### Link rules

A `[text](target)` target may be:

* **a path on this site**, e.g. `/birth-chart`, `/horoscope-matching`, `/blog/another-post`;
* **an `https://` or `http://` URL**. Rendered with `rel="nofollow ugc noopener" target="_blank"`;
* **a `#anchor`** on the same page.

Everything else is refused, the link is dropped, and the link's *text* is kept:

* `javascript:` and `data:` - they execute;
* `mailto:` - a house rule: no real address goes on a public page here;
* anything starting `//` (a protocol-relative URL). It begins with a slash but is **another site**, so
  it gets its own message: `the link target '//x/y' starts with // , which is another site`;
* any other scheme (`vbscript:`, `ftp:`, ...).

**An internal path that is not a real page on this site is BLOCKING.** Our own test suite crawls every
internal link on every indexed page and requires a direct `200` - not a `301`, not a `404` - so a typo
in a path would break our build days later. Check paths against `GET /api/blog/options` (`tools[].path`)
or use the known blog paths. A link to a blog post that exists but is still a draft is allowed and comes
back as a **warning**, because it will 404 until that post is published too.

### Image rules

**An image may only be one you have uploaded to us.** Use the `url` from `POST /api/blog/images`, which
looks like `/blog/media/<32 hex characters>`. A remote image is refused:

```
the image 'https://cdn.example.com/x.png' is not hosted here. Upload it with POST /api/blog/images ...
```

This is not caution for its own sake: the site's `Content-Security-Policy` is `img-src 'self' data:`, so
a remote image in a post would be **blocked by the browser** and render as a broken box. Refusing it
when the post arrives tells you; allowing it shows the reader a hole in the page.

Alt text is expected. An image with empty square brackets is a blocking problem.

---

## 3. Endpoints

### `GET /api/blog/options`

Fetch this once at start-up instead of hardcoding our vocabularies.

```json
{
  "tools": [{"key": "matching", "path": "/horoscope-matching", "label": "Free kundli matching (guna milan)"}],
  "categories": [{"key": "basics", "label": "Astrology basics"}],
  "limits": {
    "title_chars": [10, 70],
    "summary_chars": [50, 230],
    "body_words_min": 300,
    "body_chars_max": 80000,
    "categories_max": 4,
    "image_bytes_max": 2097152,
    "image_types": ["image/png", "image/jpeg", "image/webp"]
  },
  "autopublish": false,
  "language": "en",

  "forbidden_phrases": ["guaranteed", "100%", "will definitely", "you will suffer", "..."],
  "forbidden_rules": [
    {
      "category": "guarantee",
      "blocks": true,
      "phrases": ["guaranteed", "guarantees", "assured", "100%", "..."],
      "instead": "Say what the tradition holds ... A NEGATED guarantee is welcome and will not be blocked."
    }
  ],
  "accepted_fields": {
    "fact_check_warnings": {
      "type": "list[str]", "max_items": 20, "max_chars": 300, "blocks": false,
      "what": "What the writer could not verify. Shown on /admin/blog; never holds a post back."
    },
    "key_points":     {"type": "list[str]", "max_items": 5, "blocks": false, "what": "..."},
    "language":       {"type": "str",       "blocks": false, "what": "en, hi or mr. Defaults to en."},
    "translation_of": {"type": "str|null",  "blocks": false, "what": "..."}
  }
}
```

#### `forbidden_phrases` and `forbidden_rules`

Both describe the same thing and exist for two different jobs.

**`forbidden_phrases`** is a flat list of strings, lowercase, for dropping into a prompt. Every entry
is a phrase the checker reacts to.

**`forbidden_rules`** groups them, and is what to use for a self-check before posting. Each entry has:

| field | meaning |
|---|---|
| `category` | a stable key: `guarantee`, `certainty`, `reader_harm`, `impersonal_harm`, `gem_fear`, `compulsion`, `html`, `placeholder`, `personal_prediction`, `third_party_paid` |
| `blocks` | `true` = the post cannot be published until it is gone. `false` = recorded as a warning and published anyway |
| `phrases` | the phrases in this category |
| `instead` | what to write in its place, in words you can put in a prompt |

**Read `blocks` before you act on an entry.** Six categories block and four do not, and treating a
warning as fatal makes a writer avoid phrasings that would have been published.

**Matching is case-insensitive and these are patterns, not literals.** `"guaranteed"` also catches
*guarantees*, *guaranteeing* and *assured*; `"you will suffer"` also catches *you may suffer*, *you
could die* and *you might need surgery*. Use them to steer the writing, and treat a clean self-check
as a good sign rather than a promise - the server's own checker is the one that decides.

**A negated guarantee is not a guarantee.** "No reading can guarantee an outcome" and "a high score
does not guarantee a happy marriage" both pass. These are the sentences this site wants written; the
rule looks back along the sentence, so a negation a few words to the left is enough.

**"100%" does not block on its own.** The qualifier is deleted before the check runs - "100% accurate
predictions" becomes "Accurate predictions" - and what is judged is the claim underneath it. So "100%
guaranteed results" is still refused, by the guarantee rule rather than by the per cent sign. **"100%
free" is left exactly as written**, because about these tools it is true. The same applies to "100 per
cent" and "hundred per cent". You do not need to avoid the phrase; it will simply not survive into the
published text unless it is about something being free.

**Some third-party phrasings never reach you as a problem.** "Consult an astrologer" and similar are
rewritten automatically toward this site's own tool or a free traditional practice before the check
runs.

This list is checked against the real rules by `tests/test_blog_options.py`, in both directions: every
phrase advertised as blocking is confirmed to block, and every phrase advertised as a warning is
confirmed not to. If the two ever disagree, that test fails rather than this document going stale.

### `POST /api/blog/posts` → 201

```json
{
  "slug": "what-the-ayanamsa-actually-is",
  "title": "What the ayanamsa actually is",
  "summary": "The one number that separates a Vedic chart from a Western one, and why two published charts for the same birth can disagree by a whole sign.",
  "body_markdown": "Two astrologers can work from the same birth ...\n\n## Where the number comes from\n\n...",
  "tool": "sidereal",
  "categories": ["basics", "kundli"],
  "hero_image_id": "9f2c41a0b7d84e6f1c3a5b9d7e0f2a46",
  "author": "RashiKundli",
  "language": "en",
  "translation_of": null,
  "fact_check_warnings": [
    "the 1947 ayanamsa figure is from a secondary source and could not be confirmed"
  ],
  "key_points": [
    "A Vedic chart is the Western one shifted by about 24 degrees.",
    "The shift is the ayanamsa, and it grows by about 50 arcseconds a year.",
    "Lahiri is the Indian standard and what this site uses."
  ],
  "publish": false
}
```

| Field | Required | Notes |
|---|---|---|
| `slug` | no | Lowercase letters, digits and single hyphens, max 80 chars. **Derived from the title if omitted.** Reserved: `media`, `feed`, `rss`, `index`, `page`, `tag`, `category`, `admin` |
| `title` | **yes** | 10-70 characters. Must not repeat another post's title or summary |
| `summary` | **yes** | 50-230 characters. This is the page's `<meta name="description">` and the card text on `/blog`. Must not repeat another post's summary or title |
| `body_markdown` | **yes** | The subset in §2. At least 300 words of visible text, at most 80 000 characters |
| `tool` | **yes** | A key from `options.tools`. Every post links to the tool it is about |
| `categories` | no | Up to 4 keys from `options.categories`. An empty list is allowed and comes back as a warning |
| `hero_image_id` | no | An `id` from `POST /api/blog/images`. An unknown id is a 422 |
| `author` | no | A byline. **It must be the publication's own name - never a private individual's.** Defaults to the site name |
| `key_points` | no | **3 to 5** short takeaways, shown as a "Key points" box above the post. 120 characters each. See §7 |
| `fact_check_warnings` | no | Anything you could not verify. **Information only: it never blocks a post** and never holds one out of the autopublish queue. Recorded against the post and shown on `/admin/blog`. See §8 |
| `language` | no | `en`, `hi` or `mr`. Defaults to `en`. See §6 |
| `translation_of` | no | The slug of the post this one translates. See §6 |
| `publish` | no | A request to go live. See §4 |

**An unknown field is a 422, not an ignored key** - a typo that is quietly dropped is a post that arrives
wrong and looks fine.

Response (201):

```json
{
  "slug": "what-the-ayanamsa-actually-is",
  "status": "draft",
  "url": "/blog/what-the-ayanamsa-actually-is",
  "autopublish": false,
  "published_at": null,
  "updated_at": "2026-10-22T14:03:11+05:30",
  "checks": {"blocking": [], "warnings": []},
  "message": "saved as a draft, and it passes every check. It goes live when somebody publishes it"
}
```

`status` is `"draft"` or `"published"`. `url` is the public path, which answers **404 while the post is
a draft**. `checks.blocking` empty means the post *can* be published; it does not mean it has been.
`message` always says what happened and why, in words - read it, and log it.

### `PUT /api/blog/posts/{slug}` → 200

The same body, the same response. It is a **full replacement** of the editable fields; there is no
`PATCH`, because a partial update of prose that is about to be checked as a whole invites checking half
of it.

* `slug` in the body must match the URL, or be omitted. **A slug cannot be changed** (409
  `slug_immutable`): it is the post's public URL, and moving it would leave the old one answering 404
  with no redirect. To change a URL, create a new post and take the old one down from `/admin/blog`.
* **Updating a post that is already live into a blocking problem does NOT take it down.** It stays
  published, the problem is recorded against it, and `/admin/blog` shows it in red. A live URL vanishing
  is the more damaging of the two failures, so taking it down is left to a human with the reason in
  front of them. Your response will show `"status": "published"` with a non-empty `checks.blocking` -
  that combination means **fix it and resubmit**.

### `GET /api/blog/posts/{slug}` → 200

```json
{
  "slug": "what-the-ayanamsa-actually-is",
  "status": "draft",
  "url": "/blog/what-the-ayanamsa-actually-is",
  "autopublish": false,
  "published_at": null,
  "updated_at": "2026-10-22T14:03:11+05:30",
  "checked_at": "2026-10-22T14:09:52+05:30",
  "title": "What the ayanamsa actually is",
  "summary": "...",
  "tool": "sidereal",
  "categories": ["basics", "kundli"],
  "hero_image_id": null,
  "checks": {"blocking": ["summary: ..."], "warnings": []},
  "message": "saved as a draft: 1 check(s) must be fixed before it can be published. See `checks.blocking`"
}
```

The body is deliberately **not** returned: this endpoint is for checking state, not for round-tripping
prose. `checks` here is the last recorded verdict, which is refreshed whenever the post is submitted or
previewed in `/admin/blog`.

### `POST /api/blog/images` → 201

**The request body IS the file.** This is not a multipart form.

```
POST /api/blog/images
Authorization: Bearer <token>
Content-Type: image/png
X-Blog-Image-Label: hero-chart.png        (optional)

<raw bytes>
```

| Rule | Value |
|---|---|
| Accepted types | `image/png`, `image/jpeg`, `image/webp` - **raster only** |
| Refused | SVG, GIF, PDF, AVIF, TIFF, anything else |
| Maximum size | 2 MiB (2 097 152 bytes), configurable as `BLOG_MAX_IMAGE_KB` |
| Type detection | **from the file's own first bytes.** `Content-Type` is ignored |
| File name | **there is none in the protocol.** `X-Blog-Image-Label` is recorded for the admin page to display and is never used to build a path |
| Dimensions | **not reported.** Nothing on our side decodes the image |
| Duplicates | the same bytes uploaded twice return the same `id` |

```json
{
  "id": "9f2c41a0b7d84e6f1c3a5b9d7e0f2a46",
  "url": "/blog/media/9f2c41a0b7d84e6f1c3a5b9d7e0f2a46",
  "media_type": "image/png",
  "bytes": 2841,
  "note": "nothing here decodes the image, so its dimensions are not reported"
}
```

Reference the image in a body by the `url` **exactly as returned**, or pass the `id` as
`hero_image_id`.

Why SVG is refused: an SVG is a document that can carry `<script>`, and served from our own origin it
would run inside a policy that trusts `'self'`. Why `Content-Type` is ignored: a caller controls it
completely. Why the size is counted while reading rather than taken from `Content-Length`: a client that
lies about its length is cut off at the limit instead of after filling our disk.

---

## 4. The draft / publish lifecycle

```
POST or PUT  ->  checks run  ->  DRAFT (the public URL answers 404)
                                   |
                                   |  a human opens /admin/blog, reads the post and the check report,
                                   |  clicks Publish. The checks run AGAIN and refuse on any blocking
                                   |  problem, so the click is a decision and not a bypass.
                                   v
                                PUBLISHED  ->  the URL answers 200, the post appears on /blog,
                                               and Bing and Yandex are told through IndexNow
```

### `publish: true` and `BLOG_AUTOPUBLISH`

| `BLOG_AUTOPUBLISH` | `publish` | `checks.blocking` | Result |
|---|---|---|---|
| off *(default, and what ships)* | anything | anything | **draft** |
| on | `false` / omitted | anything | draft |
| on | `true` | non-empty | **draft**, with the reasons recorded |
| on | `true` | empty | published, and IndexNow is called |

`options.autopublish` and the `autopublish` field on every post response tell you which install you are
talking to. **Do not build Blogauto on the assumption that it can publish**: write to the draft contract,
read `status` from the response, and treat `"published"` as a bonus.

Taking a post down (from `/admin/blog` only) returns its URL to 404 and keeps its original
`published_at`, so a post put back does not get a new dateline.

---

## 5. The checks

A post with an **empty `checks.blocking` can be published; one with anything in it cannot**, and no
endpoint and no setting changes that. `checks.warnings` are worth reading and do not stop anything.

Every message is a sentence that names the fix, prefixed with the slot it was found in (`title:`,
`summary:`, `body:`). The three groups:

### 5.1 Structure

| Refused | Why |
|---|---|
| title outside 10-70 characters | a longer one is truncated in a search result anyway |
| summary outside 50-230 characters | it is the meta description, and every page here is asserted to be in that range |
| body under 300 words | the site has enough thin pages |
| body over 80 000 characters | |
| a slug that is not `[a-z0-9]+(-[a-z0-9]+)*`, is over 80 characters, or is reserved | it is a URL |
| a `tool` that is not a key from `options.tools` | every post links to the tool it is about |
| a category key not in `options.categories` | a free-text taxonomy is how a blog gets ninety one-post categories |
| more than 4 categories | |
| a title or summary already used by another post | no two pages on this site may share a title or a description - our own suite asserts it site-wide, so a duplicate inside the blog would break it |
| a `{placeholder}`-shaped token anywhere | an unfilled template variable is a brace on a live page |

### 5.2 Safety - the same screen the rest of the site goes through

This is **not** a blog-specific rule set. It is the screen the horoscopes, the paid reports and the AI
consultation all pass through, unchanged. A hit names its category:

```
body: forbidden topic (illness): 'serious illness'
```

| Category | What is refused |
|---|---|
| `death` | death, dying, lifespan, longevity, suicide, widowhood, "untimely end" |
| `illness` | named diseases and conditions, surgery, hospitalisation, infertility, miscarriage |
| `catastrophe` | accidents, disaster, bankruptcy, imprisonment, divorce, litigation, "cursed", "doomed" |
| `hard_sell` | yantras, paid pujas, "consult an astrologer", and any commerce word near the name of a stone |
| `gemstone` | naming gemstones at all |
| `gem_fear` | "without this stone", "you must wear", "if you do not wear" |

Two things about this list that commonly surprise a writer:

* **`death`, `illness` and `catastrophe` are not negated.** "There is no danger of an accident in this
  period" is still a hit, on purpose: these are forbidden as *topics*, not as claims, and a negated
  mention still puts the idea in front of an anxious reader.
* **gemstones are refused outright**, not merely un-priced. Write about remedies the tradition
  prescribes that are free or nearly so.

### 5.3 Promises and invented predictions - the blog's own rules

A horoscope is written against an engine brief and is checked against it. A post has no brief, so what
is checked instead is that it does not pretend to one.

| Refused | Example that is refused | Write instead |
|---|---|---|
| any guarantee | "the result is guaranteed", "100% accurate", "never fails" | "tradition reads this as" |
| certainty about the future | "will definitely improve", "is destined to" | "this period tends to" |
| a prediction about the reader's own life | "you will get married", "you will win", "you will get a job" | describe the configuration, and link the calculator |
| a date attached to the reader's future | "you will see the change by March 2027" | give the transit's own dates, not the reader's |
| a chart the post has not seen | "your chart shows Saturn in the seventh" | "a chart with Saturn in the seventh" |
| "cure" in any form | "this mantra cures it" | say what the practice is and what it is for |
| a promise to heal or treat a condition | "heals a chronic condition" | nothing; keep health out of it |
| going without medical care | "instead of a doctor", "stop taking your medication" | **never**; this is the one thing here that could hurt somebody |
| a legal outcome | "you will win your case", "the visa will be approved" | |
| a financial promise or a specific investment | "guaranteed returns", "buy these shares" | |
| a required remedy | "you must perform a puja before..." | a remedy is offered, never required |

The dated-promise rule is per **sentence**: a "will" about the reader *together with* a date in the same
sentence. Each half alone is ordinary writing - "you will find the dates in the table below" and
"Saturn enters Pisces in 2027" are both fine.

### 5.4 Warnings (not blocking)

* a year repeated more than six times in the body;
* no categories;
* a link to a blog post that is still a draft.

---

## 6. Status codes and errors

| Code | When | Body |
|---|---|---|
| 200 | `GET`, `PUT` succeeded | the post view |
| 201 | `POST /posts`, `POST /images` succeeded | the post view / the image view |
| **401** | missing, malformed or wrong bearer token | `{"detail": {"error": "unauthorised", "message": "..."}}` plus `WWW-Authenticate: Bearer` |
| **404** | **no token configured on this install** (every route), or the slug does not exist | `{"detail": {"error": "no_such_post", ...}}` for a slug |
| **409** | `slug_taken` on create; `slug_immutable` on an update that changes the slug; the image store is full | `{"detail": {"error": "...", "message": "..."}}` |
| **413** | the image is over the size limit | `{"detail": {"error": "image_refused", "message": "..."}}` |
| **413 with an HTML body** | **not us** - the reverse proxy refused the body before the application saw it. See below |
| **415** | the uploaded bytes are not a PNG, JPEG or WebP | `{"detail": {"error": "image_refused", "message": "..."}}` |
| **422** | the request does not match the schema (missing field, wrong type, **unknown field**), or `hero_image_id` names an image that does not exist | FastAPI's `{"detail": [...]}`, or `{"detail": {"error": "unknown_image", ...}}` |
| **429** | too many failed token attempts from this network | `{"detail": {"error": "locked_out", ...}}` plus `Retry-After` |
| 400 | the image upload body was empty | `{"detail": {"error": "image_refused", ...}}` |
| 500 | our fault. Retry once, then stop and tell the operator | |

**A 413 WITH AN HTML BODY IS THE PROXY, NOT THE API.** nginx caps request bodies site-wide at 256k, and
`POST /api/blog/images` sends the file AS the body - so without an exception every real hero image is
refused before the application is reached, and the answer is nginx's own error page rather than JSON.
The deployed config lifts the limit to 3m for that one route (`deploy/nginx/astrology.conf`).

Telling the two apart: ours is JSON with `{"error": "image_refused"}` and respects
`BLOG_MAX_IMAGE_KB`; the proxy's is HTML and arrives whatever the token says - including for a request
with no token at all, which is how `scripts/smoke_check.py` tests for it.


**A 200 or 201 does not mean published.** It means stored. Read `status`.

Retry policy: retry a 429 after `Retry-After` and a 500 once. **Never retry a 4xx that is not 429** -
the request is wrong and retrying it will not fix it.

---

## 7. Worked examples

The token is read from a file and passed through an environment variable that is never printed. Note
`$(cat ...)` rather than the literal: the token must not reach your shell history or a process list.

```bash
BASE=https://rashikundli.com
TOKEN_FILE=~/.blog_api_token          # mode 600
```

### The vocabularies

```bash
curl -sS "$BASE/api/blog/options" \
  -H "Authorization: Bearer $(cat "$TOKEN_FILE")" | jq .
```

### Upload a hero image

```bash
curl -sS -X POST "$BASE/api/blog/images" \
  -H "Authorization: Bearer $(cat "$TOKEN_FILE")" \
  -H "Content-Type: image/png" \
  -H "X-Blog-Image-Label: ayanamsa-diagram.png" \
  --data-binary @ayanamsa-diagram.png | jq .
```

```json
{"id": "9f2c41a0b7d84e6f1c3a5b9d7e0f2a46",
 "url": "/blog/media/9f2c41a0b7d84e6f1c3a5b9d7e0f2a46",
 "media_type": "image/png", "bytes": 48211,
 "note": "nothing here decodes the image, so its dimensions are not reported"}
```

### Create a post

```bash
cat > post.json <<'JSON'
{
  "slug": "what-the-ayanamsa-actually-is",
  "title": "What the ayanamsa actually is",
  "summary": "The one number that separates a Vedic chart from a Western one, where it comes from, and why two published charts for the same birth can disagree by a whole sign.",
  "tool": "sidereal",
  "categories": ["basics", "kundli"],
  "hero_image_id": "9f2c41a0b7d84e6f1c3a5b9d7e0f2a46",
  "author": "RashiKundli",
  "body_markdown": "Two astrologers can work from the same birth and hand back charts that put the Sun in different signs. Neither has made a mistake.\n\n## Where the number comes from\n\nThe sidereal zodiac begins at a fixed point among the stars; the tropical zodiac begins at the equinox, and the equinox moves. The angle between them is the ayanamsa.\n\n![The two zodiacs, 24 degrees apart](/blog/media/9f2c41a0b7d84e6f1c3a5b9d7e0f2a46)\n\n## What it changes\n\nEvery position moves with the starting point, so a Sun near the edge of a sign can land in the one before it. Run your own with the [sidereal birth chart calculator](/sidereal-birth-chart)."
}
JSON

curl -sS -X POST "$BASE/api/blog/posts" \
  -H "Authorization: Bearer $(cat "$TOKEN_FILE")" \
  -H "Content-Type: application/json" \
  --data @post.json | jq .
```

```json
{"slug": "what-the-ayanamsa-actually-is", "status": "draft",
 "url": "/blog/what-the-ayanamsa-actually-is", "autopublish": false,
 "published_at": null, "updated_at": "2026-10-22T14:03:11+05:30",
 "checks": {"blocking": [], "warnings": []},
 "message": "saved as a draft, and it passes every check. It goes live when somebody publishes it"}
```

(That body is well under 300 words, so the real request would be refused with
`body: 142 words; a post needs at least 300. This site has enough thin pages` - the example is cut for
length.)

### A post that is refused

```bash
curl -sS -X POST "$BASE/api/blog/posts" \
  -H "Authorization: Bearer $(cat "$TOKEN_FILE")" \
  -H "Content-Type: application/json" \
  --data '{"slug":"manglik-truth","title":"The truth about manglik dosha","summary":"What manglik dosha is, how it is identified, and where the two main traditions disagree about the second house.","tool":"mangal-dosha","categories":["doshas"],"body_markdown":"...800 words... You must perform a puja before your marriage, and the outcome is guaranteed."}' | jq .checks
```

```json
{
  "blocking": [
    "body: 'guaranteed' - a guarantee: nothing on this site promises an outcome. Say what the tradition holds and what the chart shows, and let the reader decide",
    "body: 'You must perform a puja' - a remedy is offered, never required. This is the pattern the dosha guides were written against"
  ],
  "warnings": []
}
```

Fix both, `PUT` the post again, and `checks.blocking` comes back empty.

### Update a post

```bash
curl -sS -X PUT "$BASE/api/blog/posts/what-the-ayanamsa-actually-is" \
  -H "Authorization: Bearer $(cat "$TOKEN_FILE")" \
  -H "Content-Type: application/json" \
  --data @post.json | jq '.status, .checks'
```

### Check a post's state

```bash
curl -sS "$BASE/api/blog/posts/what-the-ayanamsa-actually-is" \
  -H "Authorization: Bearer $(cat "$TOKEN_FILE")" | jq '.status, .message'
```

---

## 8. What is explicitly NOT allowed

A short list, because each item is a thing somebody will eventually ask for:

1. **Auto-publishing is not the default and cannot be requested into existence.** `publish: true` is a
   request. On an install with `BLOG_AUTOPUBLISH` off - the shipped state - the answer is a draft, every
   time. There is no header, parameter or endpoint that overrides it.
2. **There is no way to publish a post that fails a check.** Not through the API, not through
   `/admin/blog`, not with a flag. The one-click publish re-runs every check and refuses.
3. **HTML in a body is refused, not sanitised.** We do not accept markup we would then have to clean.
4. **A remote image URL will not work**, in a body or as a hero. Upload it and use the URL we return.
5. **`javascript:`, `data:`, `mailto:` and protocol-relative (`//...`) link targets are refused.**
6. **SVG is not an accepted image type**, at any size.
7. **No real person's name, e-mail address or birth data** anywhere in a post, including the `author`
   byline. The byline is the publication's name.
8. **No Hindi or Marathi.** The blog is English only; see the top of this file.
9. **A slug cannot be changed** once created, and a post cannot be deleted through this API. Both are
   decisions about a public URL and both are made from `/admin/blog`.
10. **No endpoint returns the token, any part of it, or its length.** If you lose it, the operator
    writes a new one into the token file; nothing needs a restart.

---

## 9. What a published post looks like on the site

For reference, so Blogauto knows what its fields become:

* `/blog` lists every published post, newest first, with its title, published date, categories and
  summary;
* `/blog/<slug>` renders the post with the title as the page's single `<h1>`, the summary as the lede
  and as the `<meta name="description">`, the published date **visibly** (and an updated date only when
  it differs), the categories, the hero image, the body, and a prominent link to the tool named in
  `tool`;
* the page carries `Article` JSON-LD with `headline`, `description`, `datePublished`, `dateModified`,
  `articleSection` (the category labels), `author` and `publisher` (the organisation, never a person),
  `inLanguage: "en"`, and `image` when there is a hero - plus a `BreadcrumbList`;
* the canonical URL is the post's own path, and there is no `hreflang` set, because the page exists in
  one language;
* **a draft renders nothing at all.** Its URL answers 404 and it does not appear on `/blog`. There is no
  preview URL and no `?draft=1`: a guessable preview link is an unpublished page published to anybody
  who guesses it.

## 6. Languages and translations

**A post lives in ONE tree** - the language it was written in. It is listed on that tree's index and
nowhere else, and its URL carries that tree's prefix:

| `language` | index | post |
|---|---|---|
| `en` | `/blog` | `/blog/{slug}` |
| `hi` | `/hi/blog` | `/hi/blog/{slug}` |
| `mr` | `/mr/blog` | `/mr/blog/{slug}` |

A Hindi post is **not** an English post awaiting translation, so it is never shown on `/blog`, and
asking for it at an English URL is a 404 rather than a redirect. An unknown `language` is a 422 naming
the trees that exist - a post written into a tree nothing serves would be live and invisible, which
looks like a publishing bug rather than a typo.

**A translation keeps its own slug.** A Hindi URL spelled like an English one helps nobody who types
it. The two are linked by `translation_of`, which names the ORIGINAL's slug:

```json
POST /api/blog/posts
{ "slug": "reading-a-kundli", "language": "en", "title": "Reading a kundli", ... }

POST /api/blog/posts
{ "slug": "kundli-kaise-padhein", "language": "hi", "translation_of": "reading-a-kundli", ... }
```

That makes them `hreflang` alternates of each other, in both directions, as soon as both are
published. A group is "this slug plus everything pointing at it", so the link is found from either
end and there is no second table to keep in step.

**Drafts are never alternates.** An `hreflang` pointing at a 404 is worse than no `hreflang`, so only
published translations are linked.

**Omitting both fields behaves exactly as before**: an English post with no alternates.

## 7. Key points

**Optional, and refused rather than trimmed.** Send between **3 and 5**, or none at all:

- fewer than 3 is refused - a box with two lines in it reads as an omission
- more than 5 is refused - a caller that sends eight meant eight, and silently keeping five would
  publish a box that misrepresents what they wrote, with no way for them to know
- each one is at most **120 characters**, because it is a line somebody reads at a glance

**A post without them is not worse off.** It gets a box built from its own `##` headings, labelled
"What this post covers" rather than "Key points" - a heading says what a section is about, a takeaway
says what to conclude from it, and deriving the second from the first would be this site writing
claims nobody wrote.

Both boxes appear above the body, with key points first where both are present.

## 8. Fact-check warnings, and what makes a post publish itself

Send anything you could not verify. Each entry is a sentence; twenty at most.

```json
"fact_check_warnings": ["the 1947 date is from a secondary source"]
```

**This is the one field that stops a post going live on its own, however clean its checks are.** Our
checks can only read the text; they cannot know whether a date is right. A claim nobody has stood
behind is exactly what a person should see before it goes out under our name, so a post carrying any
warning waits on `/admin/blog`. Send an empty list - or leave it out - when there is nothing to say.

### What `publish: true` actually does

With `BLOG_AUTOPUBLISH` off, which is the default, it is a request and the post is a draft.

With it on, a post goes live when **both** of these hold, and the response's `message` names the one
that did not:

1. nothing blocking, **after** the automatic repairs below have run
2. fewer than **2 posts** have gone live automatically today - the rest queue, oldest first

`fact_check_warnings` do **not** hold a post back. They are recorded on it, shown on `/admin/blog`,
and written to the log at the moment it goes public, so an unverified claim stays findable - it is
auditable after publication rather than before.

### What actually blocks a post

Only what breaks the site or the law:

| | |
|---|---|
| an empty or too-short body, an unusable slug, HTML in the body, an unfilled `{placeholder}` | the page would be broken |
| a duplicate title or summary | two pages sharing one is a duplicate in search and a failing site-wide test |
| a **guaranteed outcome** | "this remedy guarantees a marriage within the year" |
| **fear or threat selling** | "wear it or your marriage will fail", "you must do a puja or else" |
| a **death or illness** prediction | the worst thing this site could put in front of a frightened reader |

**Everything else is repaired where a rule exists and published with a warning where one does not** -
catastrophe words, gemstone talk, a phrasing that claims to read the reader's chart, third-party
selling the rewrite rules did not match, financial talk. The warnings come back in `checks.warnings`
and are shown on `/admin/blog`.

A **link that points at nothing is never blocking**: it is dropped and its words are kept, so
"See the [matching tool](/nope)" becomes "See the matching tool". A missing image is dropped.

## 9. What we repair on the way in, and how you see it

A post is repaired before it is checked, so the checks judge the text as it will be published.
Deterministic rules run first; only what they cannot fix goes to a model, at most twice, and only as
literal find-and-replace pairs.

The rules, all of them:

| What | Becomes |
|---|---|
| "consult an astrologer / pandit / jyotishi" | a link to our own AI astrologer |
| "book a puja with a priest", "buy a yantra from a seller" | a free traditional practice |
| "hire an astrologer", "a paid consultation" | a link to our own AI astrologer |
| "your kundli shows ..." | "a chart like this shows ..." |
| a known wrong path (`/kundali`, `/guna-milan`, `/manglik` ...) | the real path from the URL registry |
| `![alt](some-id)` where `some-id` is in the media store | `![alt](/blog/media/some-id)` |

An image id that is **not** in the store is left alone and the post is refused with a message saying
so. Inventing a path to a picture nobody uploaded would turn a clear refusal into a broken image on a
live page.

The model pass is **off by default** (`BLOG_AI_FIX=on` turns it on). The deterministic rules do the
repairs; what they cannot fix is written down and published rather than sent to a model.

**Every repair comes back in the response**, as `fixes`, with `what`, `before`, `after` and `by`
(`rules` or `haiku`), and the same list is shown on `/admin/blog`. Nothing is changed silently.

## 10. Selling: ours yes, somebody else's no

A post may recommend **our own** paid products - the detailed report, the AI astrologer, the matching
report - with an honest description and a real price.

**Third-party paid services and goods are refused**, and auto-fix rewrites them rather than only
refusing: a paid ritual becomes a free traditional practice, a paid reading becomes our AI astrologer.

| | |
|---|---|
| allowed | our products, named and priced honestly |
| allowed | **free** traditional practice - a temple visit, charity, fasting, a mantra, lighting a lamp |
| refused | booking or sponsoring a paid puja, homa, havan or ceremony through anyone |
| refused | buying a yantra, rudraksha, kavach or amulet from an outside seller |
| refused | hiring or paying another astrologer, pandit or priest |
| refused | "a paid consultation" or "a paid reading" that is not ours |

The tradition is full of remedies that cost nothing. Refusing to mention those would be this site
pretending the only answer is a purchase, which is the opposite of the point - so every rule above
needs a word of COMMERCE in it (book, hire, order, buy, paid, sponsor) and never fires on the
practice alone.

Also still refused, and not negotiable:

- **fear as a sales tool**: anything a reader must buy or do to avoid a bad outcome
- **a guaranteed outcome**: a promise about what a product or a remedy will do for someone
- **a claim about the reader's own chart**: a post is read by thousands and written about none of them

## 11. The disclaimer

Every post carries this under its body, in the post's own language, added when the page is rendered:

> This article explains traditional Vedic astrology for general information. It is not a personal
> reading or professional advice.

It is not a field and it is not yours to remove. It says what this section of the site is, and with
autopublish on a post can reach a reader before anybody here has read it.
