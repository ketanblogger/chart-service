"""What a post must pass before it can be published. The same spirit as the rashifal's checks, on prose
that arrives from outside this codebase instead of from Claude.

The rashifal's rule (app/rashifal/generate.py) is that a page is PUBLISHABLE ONLY WITH AN EMPTY BLOCKING
LIST, and that nothing is quietly tidied into passing: `check_output` returns blocking problems and
warnings per language, and a page with a blocking problem is not published, full stop. A blog post is in
exactly the same position - text we did not write, about to appear on a commercial site under our name -
so it is held to the same bar, with the same three layers:

  1. **structure** - the properties every indexable page on this site is already asserted to have
     (a unique title, a 50-230 character description, enough words to be a page). Getting these wrong
     would turn the lead's suite red days later, so they are refused on the way in.
  2. **safety** - `app.ai.safety.screen_text`, UNCHANGED and not re-tuned for the blog. It is the same
     screen the rashifal, the paid reports and the consultation go through: no death, no illness, no
     catastrophe, no hard sell, no gemstone commerce, no fear as a sales tool. The gemstone ban applies
     here as it does everywhere except the book's own gemstone chapter - a blog post is not that chapter.
  3. **promises and invented predictions** - the checks below, which are the blog's own. A rashifal is
     written against an engine brief and is checked against it (app/ai/validator.py); a blog post has no
     brief, so what has to be checked instead is that it does not pretend to one: a post has not seen
     anybody's chart, cannot date anybody's future, and may not promise a medical, legal or financial
     outcome.

BE HONEST ABOUT WHAT THESE PATTERNS ARE. Every entry in `app/ai/language.py` is there because it was
found in published output, and that file says so. These are not: there is no Blogauto output yet, so
they are written from the rules the rashifal already enforces and from what the fear-selling trade in
this field actually does. The first run of real posts should be read against them, and a rule that
fires on good writing costs a rewrite while a rule that fires on nothing is worse than no rule at all.
What they CANNOT do is catch the next way a sentence promises something; that is what the preview on
/admin/blog is for, and why nothing here publishes itself.
"""

from __future__ import annotations

import re

from app.ai.language import language_problems
from app.ai.safety import screen_text

from . import config, images, markdown, paths

#: A controlled vocabulary, not free text. A category per post is how a blog ends up with ninety
#: categories holding one post each, every one of them a thin indexable page waiting to be built.
CATEGORIES: dict[str, str] = {
    "basics": "Astrology basics",
    "kundli": "Kundli and birth charts",
    "matching": "Matching and marriage",
    "panchang": "Panchang and muhurat",
    "doshas": "Doshas",
    "remedies": "Remedies",
    "transits": "Transits and Sade Sati",
    "nakshatras": "Nakshatras",
    "festivals": "Festivals",
}

# ---- the blog's own checks ---------------------------------------------------------------------------
#
# Each tuple is (pattern, the message the writer gets). The message names the FIX and not just the
# fault, for the reason app/ai/language.py gives about its Marathi table: a correction that names only
# the category gets a rewrite that is wrong in a different way.

#: A GUARANTEE OF ANY KIND. The oldest trick in this trade is certainty, and it is also the one thing
#: astrology cannot sell honestly - the site's own disclaimer says everything here is for guidance and
#: reflection. "100%" is included because an accuracy claim is the same promise wearing a number.
#: How far back a negation can sit and still be negating this word. "No reading can guarantee an
#: outcome" has four words between the two; "no guarantee" has none. Seven words is wide enough for
#: the sentences this site actually writes and narrow enough not to reach the previous clause.
_NEGATORS = re.compile(
    r"\b(?:no|not|never|cannot|can't|cant|don't|dont|doesn't|doesnt|didn't|didnt|won't|wont|"
    r"nothing|nobody|none|without|hardly|rarely|seldom|refuse[sd]?|avoid(?:s|ed)?)\b", re.I)
_NEGATION_WINDOW_WORDS = 7


def _negated_before(text: str, start: int) -> bool:
    """Is the match at `start` negated by something just to its left, within the same sentence?

    A LOOKBEHIND CANNOT DO THIS. It sees a fixed string immediately before the match, so it catches
    "no guarantee" and misses "No reading can guarantee an outcome" - which is the sentence this
    whole rule exists to allow. Eleven drafts were once held back for writing honestly.
    """
    before = text[:start]
    # Stay inside the sentence: a negation in the previous one is about something else.
    for stop in (".", "!", "?", "\n"):
        cut = before.rfind(stop)
        if cut != -1:
            before = before[cut + 1:]
    words = before.split()
    return bool(_NEGATORS.search(" ".join(words[-_NEGATION_WINDOW_WORDS:])))


_PROMISES = (
    # A POSITIVE GUARANTEE ONLY. This fired on "there is no guarantee of any outcome" and on "a high
    # score does not guarantee a happy marriage" - which are the site being HONEST, the exact
    # sentences we want writers to write, and eleven drafts were held back for writing them.
    # The lookbehind refuses the word only when nothing negates it within a few words to its left.
    # THE NEGATION IS CHECKED BY LOOKING BACK, NOT BY A LOOKBEHIND. The first version stacked
    # lookbehinds for "no ", "not ", "doesn't " and so on, which only ever see the word IMMEDIATELY
    # before - so "no guarantee" passed and "No reading can guarantee an outcome" was still blocked.
    # That second sentence is the honest one this site wants written, and it is the example the
    # proprietor gave. `_negated_before` scans the words to the left of the match instead.
    #
    # "100%" IS NOT HERE, ON PURPOSE. It never matched at all until this batch (the alternation ended
    # in `\b` and `%` is not a word character), and switching it on blocked drafts for a qualifier
    # rather than for a promise - "100% accurate" is a boast to delete, and "100% free" about our own
    # free tools is simply true. So app/blog/autofix.py drops the qualifier deterministically and
    # whatever is left is judged on its own: "100% guaranteed results" still blocks, on `guaranteed`.
    (re.compile(r"\b(?:guarantee[sd]?|guaranteeing|assured|assurance|without fail|"
                r"fool\s?proof|never fails?)\b", re.I),
     "a guarantee: nothing on this site promises an outcome. Say what the tradition holds and what the "
     "chart shows, and let the reader decide"),
    (re.compile(r"\b(?:will (?:definitely|certainly|surely|absolutely)|(?:definitely|certainly|surely) "
                r"will|(?:is|are) (?:destined|bound|certain) to|there is no doubt)\b", re.I),
     "certainty about the future: write \"tradition reads this as\" or \"this period tends to\", never "
     "\"will definitely\""),
)

#: A PREDICTION ABOUT THE READER'S OWN LIFE. A blog post is read by everybody and is written about
#: nobody, so the second person plus a life outcome is a reading the post never performed.
_PERSONAL_PREDICTION = re.compile(
    r"\byou\s+(?:will|shall|are going to)\s+(?:soon\s+)?"
    r"(?:get married|marry|conceive|have a (?:child|son|daughter|baby)|win|become (?:rich|wealthy)|"
    r"get (?:a |the )?(?:job|promotion|visa|loan)|be promoted|be cured|recover|inherit|"
    r"buy (?:a |the )?(?:house|flat|car))\b", re.I)

#: A DATED PROMISE. Checked per sentence - a "will" about the reader in the same sentence as a date or a
#: window. The rashifal is allowed dated statements because every date in it comes from the ephemeris and
#: is checked against the brief (app/ai/validator.py); a blog post has no brief to be checked against, so
#: a date attached to the reader's future is invented by construction.
_READER_FUTURE = re.compile(r"\byou(?:r\s+\w+)?\s+(?:will|shall|are going to)\b", re.I)
_WHEN = re.compile(r"\b(?:20\d\d|within\s+\w+\s+(?:days?|weeks?|months?|years?)|"
                   r"in\s+(?:the\s+)?(?:next|coming)\s+\w+\s*(?:days?|weeks?|months?|years?)?|"
                   r"by\s+(?:january|february|march|april|may|june|july|august|september|october|"
                   r"november|december)|next\s+(?:week|month|year))\b", re.I)

#: A CHART THE POST HAS NOT SEEN. "Your chart shows Saturn in the seventh" on a page read by thousands
#: of people is false for almost all of them, and it is the sentence that makes a general article feel
#: like a personal reading - which is precisely what the free calculators are for.
_CHART_IT_HAS_NOT_SEEN = re.compile(
    r"\byour\s+(?:chart|kundli|kundali|horoscope|birth chart)\s+"
    r"(?:shows?|says?|tells?|reveals?|indicates?|confirms?|proves?)\b", re.I)

#: MEDICAL. `screen_text` already blocks the diseases themselves as topics; what is missing from it is
#: the PROMISE, and the one word that turns a traditional remedy into a medical claim is "cure". It is
#: blocked bare rather than in context: there is no sentence on an astrology blog that needs it, and the
#: contextual version ("cure ... illness") is the one a writer slips past by moving two words apart.
_MEDICAL = (
    (re.compile(r"\bcure[sd]?\b|\bcuring\b", re.I),
     "\"cure\" is a medical claim. A remedy is a practice the tradition prescribes, not a treatment: "
     "write what it is and what it is for, and keep health out of it"),
    (re.compile(r"\b(?:heal|fix|reverse|treat)\b[^.;!?\n]{0,30}\b(?:disease|illness|cancer|depression|"
                r"anxiety|infertility|condition|symptoms?|patients?)\b", re.I),
     "a promise to heal or treat a condition. Nothing here is a substitute for medical care - that is "
     "what the site's disclaimer says on every page, and a post may not contradict it"),
    (re.compile(r"\b(?:instead of|rather than|without)\s+(?:a\s+|your\s+|seeing\s+a\s+)?"
                r"(?:doctor|physician|medicine|medication|treatment)\b|"
                r"\b(?:stop|skip|avoid)\s+(?:taking\s+)?(?:your\s+)?(?:medicine|medication|treatment)\b|"
                r"\bno need (?:to see|for) a doctor\b", re.I),
     "telling a reader to go without medical care. This is the one thing on this site that could hurt "
     "somebody; it is refused outright"),
)

#: LEGAL AND FINANCIAL. The promise forms only. A sentence that says this is NOT legal advice is exactly
#: what we want a post to be free to say, so the topic words are deliberately absent and only the
#: outcome claims are matched.
_LEGAL_FINANCIAL = (
    (re.compile(r"\b(?:win (?:your|the|this) (?:case|lawsuit|litigation|appeal)|legal victory|"
                r"(?:case|verdict|judgment) will be (?:in your favour|in your favor|won|decided)|"
                r"(?:visa|bail|appeal) will be (?:approved|granted|cleared))\b", re.I),
     "a legal outcome. A chart does not decide a case; please consult a qualified professional is what "
     "this site says, and a post may not say otherwise"),
    (re.compile(r"\b(?:guaranteed|assured|sure|certain)\s+(?:returns?|profits?|gains?|income)\b|"
                r"\b(?:double|triple)\s+your\s+money\b|"
                r"\b(?:buy|sell|invest in)\s+(?:these|this|the following)\s+(?:stocks?|shares?|funds?)\b", re.I),
     "a financial promise or a specific investment. Money questions are exactly where the disclaimer "
     "asks the reader to see a professional"),
)

#: WHICH OF THE SHARED SCREEN'S CATEGORIES STOP A POST. Death and illness: a sentence telling a
#: frightened reader that a transit brings one is the worst thing this site could publish, and no
#: amount of publishing speed is worth it. `gem_fear` is here because it IS threat selling - "wear it
#: or else" - which is the line the proprietor drew. Catastrophe and gemstone talk are recorded and
#: published: an astrology blog that cannot use the word divorce is not an astrology blog.
#: `gem_fear` is threat selling and stops a post on sight. Death and illness are NO LONGER blocked
#: as topics: the screen matches the WORDS, so "the eighth house rules longevity and death in
#: classical texts" and "a muhurat for surgery is chosen away from the dagdha yogas" were refused -
#: information, in an astrology blog, about the things astrology has always discussed. Eleven drafts
#: were held back on sentences like those.
#:
#: What blocks instead is `_READER_HARM`, below: the same subjects aimed AT the reader as a
#: prediction. The topic is recorded as a warning either way, so nothing stops being visible.
_BLOCKING_TOPICS = frozenset({"gem_fear"})

#: The harms themselves, shared by the two rules below.
_HARM = (r"(?:die|died|dying|death|pass away|untimely end|illness|ill\b|disease|cancer|stroke|"
         r"heart attack|paralysis|accident|injur\w+|surgery|operation|hospital\w*|suffer\w*|"
         r"fatal\w*|terminal|miscarriage|widow\w*)")

#: HARM PREDICTED WITHOUT NAMING THE READER. "This period can bring a serious illness to the family"
#: has no second person, so `_READER_HARM` below does not see it - and it is the same claim, landing
#: on a reader who is reading about themselves. So is "people with this placement often face a
#: serious illness".
#:
#: WHAT IT MUST NOT CATCH is the thing an astrology blog is for: what a house SIGNIFIES. "The eighth
#: house rules longevity and death in classical texts" states what a house means; it predicts nothing
#: about anybody. The difference is the verb - a house RULES or SIGNIFIES or GOVERNS, while a transit
#: BRINGS or CAUSES something to someone - so these patterns are built on the verbs of happening and
#: never on the vocabulary of meaning.
_IMPERSONAL_HARM = (
    # a transit / period / placement doing something to someone
    re.compile(r"\b(?:this|the|that)\s+(?:transit|period|phase|dasha|antardasha|placement|yoga|"
               r"combination|conjunction|aspect|position)\b[^.?!\n]{0,60}?"
               r"\b(?:brings?|bring|cause[sd]?|causing|lead[s]? to|leads to|result[s]? in|"
               r"is linked to|has been linked to|is associated with)\b[^.?!\n]{0,40}?" + _HARM, re.I),
    # people / natives / those with X, and what happens to them
    re.compile(r"\b(?:people|natives?|those|anyone|individuals?)\b[^.?!\n]{0,50}?"
               r"\b(?:with|born under|having|in whose)\b[^.?!\n]{0,50}?"
               r"\b(?:face[sd]?|suffer\w*|experience[sd]?|get|develop|are prone to|may|often|"
               r"usually|tend to)\b[^.?!\n]{0,30}?" + _HARM, re.I),
    # harm attributed to a placement with no subject at all: "Saturn here has been linked to an
    # untimely end", "Mars in the 8th causes accidents"
    re.compile(r"\b(?:is|has been|are)\s+(?:linked to|associated with|known to cause)\b"
               r"[^.?!\n]{0,40}?" + _HARM, re.I),
)

#: A PREDICTION OF HARM TO THE READER. Second person, and a future or a likelihood, and one of the
#: harms. All three parts are required: "the eighth house rules death" has the harm and nothing
#: else; "you will be busy in March" has the person and the future and no harm. Only the three
#: together are the sentence this site must never publish.
_READER_HARM = re.compile(
    r"\byou(?:r\s+\w+)?\s+(?:will|shall|are going to|may|might|could|can expect|are likely to|"
    r"are at risk of|risk)\s+(?:\w+\s+){0,3}"
    r"(?:die|death|dying|pass away|illness|ill\b|disease|cancer|stroke|heart attack|paralysis|"
    r"accident|injury|injured|surgery|operation|hospital\w*|suffer\w*|fatal\w*|terminal)",
    re.I)


#: SOMEBODY ELSE'S TILL. The `hard_sell` category is skipped on the blog so that a post may recommend
#: OUR paid products - and that removed the guard against third-party commerce along with it, because
#: the one category covered both. This is the narrower rule the proprietor asked for in its place.
#:
#: WHAT IT REFUSES: a paid ritual booked through somebody else, a paid reading from another astrologer,
#: an object bought from an outside seller. A blog post we host and pay for is not a shopfront for a
#: trade we have no sight of, and "book a puja with a priest" is the single most common way money
#: leaves a reader's hands in this field.
#:
#: WHAT IT MUST NOT TOUCH, and what every pattern here is shaped around:
#:   - our own products, named and priced honestly: they have none of these words in them
#:   - FREE traditional practice - a temple visit, charity, fasting, a mantra, lighting a lamp. The
#:     tradition is full of remedies that cost nothing, and refusing to mention them would be the
#:     site pretending the only answer is a purchase, which is the opposite of the point.
#: So every pattern below needs a word of COMMERCE in it - book, hire, order, buy, paid, fee - and
#: never fires on the practice alone.
_THIRD_PARTY_PAID = (
    (re.compile(r"\b(?:book|booking|arrange|order|hire|pay\s+for|sponsor)\s+(?:a|an|the|any)?\s*"
                r"(?:paid\s+)?(?:puja|pooja|homa|havan|havana|yagna|yagya|yajna|abhishek\w*|"
                r"ritual|ceremony|parihara?m?)\b", re.I),
     "a paid ritual booked through somebody else. Our own products may be recommended and priced; "
     "a third party's cannot. A free traditional practice - a temple visit, charity, a mantra - is "
     "always fine to mention"),
    (re.compile(r"\b(?:paid|sponsored|professional)\s+(?:puja|pooja|homa|havan|yagna|yagya|"
                r"consultation|reading|horoscope\s+reading)\b(?!\s+(?:from|on)\s+(?:us|this\s+site))",
                re.I),
     "a paid service somebody else provides. Name ours instead, with its real price"),
    (re.compile(r"\b(?:buy|purchase|order|get\s+it\s+from)\s+(?:a|an|the|your)?\s*"
                r"(?:yantra|rudraksha\w*|kavach|locket|talisman|amulet|idol|murti)\b", re.I),
     "an object sold by somebody we have no sight of. The tradition's free remedies are not"),
    (re.compile(r"\b(?:hire|engage|pay)\s+(?:a|an|the)?\s*(?:pandit|priest|astrologer|jyotish\w*)\b",
                re.I),
     "paying another astrologer, from a page we host. The AI astrologer on this site is ours"),
)

#: FEAR, SOLD. `hard_sell` is skipped on the blog now (see the note in `content_problems`), so this is
#: no longer the companion to it - it is the whole of that defence here. Selling is allowed; telling
#: somebody they MUST buy a ritual is not, and that distinction is this pattern's job alone.
_COMPULSION = re.compile(
    r"\byou\s+(?:must|have to|need to|should immediately)\s+(?:do|perform|book|arrange|get)\s+"
    r"(?:a|an|this|the)?\s*(?:puja|pooja|homa|havan|havana|yagna|yagya|ritual|remedy|abhishek)\b", re.I)

#: Anything tag-shaped. See the note at the top of app/blog/markdown.py: HTML is refused rather than
#: escaped, so a writer who pastes markup is told, instead of discovering their tags as visible text on
#: the live page.
_TAG_SHAPED = re.compile(r"<\s*/?\s*[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?\s*>|<!--")

#: An UNFILLED COPY PLACEHOLDER. The site's own copy system fills `{price_kundali}`-shaped tokens, and
#: tests/test_pages_i18n.py asserts that no such token survives into the <main> of any page - so a
#: template variable the writer's own generator failed to substitute would be a brace on a live page and
#: a failing assertion in somebody else's test file. Refused here, where the writer can still see it.
_PLACEHOLDER = re.compile(r"\{[a-z][a-z0-9_]{1,30}\}")

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
#: From app/rashifal/generate.py's `style_problems`, for the same reason: a year repeated after every
#: date reads as filler. A warning here rather than blocking - a post may legitimately be about a year.
_MAX_SAME_YEAR = 6


def reader_text(post: dict) -> str:
    """Everything a reader sees, with the markup taken off: title, summary and body."""
    return "\n".join([(post.get("title") or "").strip(), (post.get("summary") or "").strip(),
                      markdown.plain_text(post.get("body_md") or "")])


def _slots(post: dict) -> tuple[tuple[str, str], ...]:
    """(where, text) per slot, so a problem names which part of the post it is in - the shape
    `content_problems` in app/rashifal/generate.py reports in."""
    return (("title", (post.get("title") or "").strip()),
            ("summary", (post.get("summary") or "").strip()),
            ("body", markdown.plain_text(post.get("body_md") or "")))


# ---- structure ---------------------------------------------------------------------------------------


def structure_problems(post: dict) -> list[str]:
    """What the request schema cannot enforce: lengths, the tool, the categories, the slug."""
    problems: list[str] = []
    slug = (post.get("slug") or "").strip()
    if not paths.is_slug(slug):
        problems.append(
            f"{slug!r} is not a usable slug. Lowercase letters, digits and single hyphens, at most "
            f"{paths.MAX_SLUG_CHARS} characters, and not one of {sorted(paths.RESERVED_SLUGS)} - those "
            "are reserved under /blog")
    title = (post.get("title") or "").strip()
    if not config.MIN_TITLE_CHARS <= len(title) <= config.MAX_TITLE_CHARS:
        problems.append(f"the title is {len(title)} characters; it must be "
                        f"{config.MIN_TITLE_CHARS}-{config.MAX_TITLE_CHARS} (a longer one is truncated "
                        "in a search result anyway)")
    summary = (post.get("summary") or "").strip()
    if not config.MIN_SUMMARY_CHARS <= len(summary) <= config.MAX_SUMMARY_CHARS:
        problems.append(f"the summary is {len(summary)} characters; it must be "
                        f"{config.MIN_SUMMARY_CHARS}-{config.MAX_SUMMARY_CHARS}. It is the page's meta "
                        "description, and every page on this site is asserted to be inside that range")
    body = post.get("body_md") or ""
    if len(body) > config.MAX_BODY_CHARS:
        problems.append(f"the body is {len(body)} characters; the limit is {config.MAX_BODY_CHARS}")
    words = markdown.word_count(body)
    if words < config.MIN_BODY_WORDS:
        problems.append(f"the body is {words} words; a post needs at least {config.MIN_BODY_WORDS}. "
                        "This site has enough thin pages")
    tool = (post.get("tool") or "").strip()
    if tool not in paths.tool_keys():
        problems.append(f"`tool` is {tool!r}; it must be one of {sorted(paths.tool_keys())}. Every post "
                        "links to the tool it is about, by registry key rather than by URL, so the link "
                        "follows the tool if its slug ever moves")
    categories = post.get("categories") or ()
    if len(categories) > config.MAX_CATEGORIES:
        problems.append(f"{len(categories)} categories; at most {config.MAX_CATEGORIES}")
    unknown = [name for name in categories if name not in CATEGORIES]
    if unknown:
        problems.append(f"unknown categor{'y' if len(unknown) == 1 else 'ies'} {unknown}; the vocabulary "
                        f"is fixed: {sorted(CATEGORIES)}")
    return problems


# ---- what a writer is told, before they write ---------------------------------------------------------

#: WHAT THE CHECKER BLOCKS, IN WORDS A WRITER CAN USE. Served by GET /api/blog/options so a generating
#: client can put these in its own prompt and check its own text before posting, instead of discovering
#: them from a 422 after the fact.
#:
#: THE LIST IS CURATED, NOT GENERATED. Turning these regexes into readable phrases automatically
#: produces either noise ("(?:guarantee[sd]?|guaranteeing)") or a lie, and a writer cannot act on
#: either. So it is written by hand - and tests/test_blog_options.py asserts that every phrase here is
#: genuinely blocked by the checker and that every blocking rule has an entry, which is what stops the
#: two drifting apart. A list that quietly stops matching the rules is worse than no list, because a
#: client trusts it.
FORBIDDEN: tuple[dict, ...] = (
    {
        "category": "guarantee",
        "blocks": True,
        "phrases": ["guaranteed", "guarantees", "assured", "assurance", "without fail",
                    "foolproof", "never fails"],
        "instead": ("Say what the tradition holds and what the chart shows, and let the reader decide. "
                    "A NEGATED guarantee is welcome and will not be blocked - \"no reading can "
                    "guarantee an outcome\" and \"a high score does not guarantee a happy marriage\" "
                    "both pass. \"100%\" does not block on its own either: the qualifier is simply "
                    "deleted before the check (\"100% accurate\" becomes \"accurate\"), so what is "
                    "judged is the claim underneath it. \"100% free\" is left alone."),
    },
    {
        "category": "certainty",
        "blocks": True,
        "phrases": ["will definitely", "will certainly", "will surely", "definitely will",
                    "is destined to", "are bound to", "is certain to", "there is no doubt"],
        "instead": "Write \"tradition reads this as\" or \"this period tends to\".",
    },
    {
        "category": "reader_harm",
        "blocks": True,
        "phrases": ["you will suffer", "you may suffer", "you will fall ill", "you could die",
                    "you will face an accident", "you may develop a disease",
                    "you will have a stroke", "you might need surgery"],
        "instead": ("Do not predict death, illness, accident or surgery for the reader - second "
                    "person plus a harm, in any tense of likelihood. Naming what a house or a graha "
                    "SIGNIFIES is information and passes: \"the 8th house signifies longevity\" is "
                    "fine, and so is \"a muhurta for surgery\"."),
    },
    {
        "category": "impersonal_harm",
        "blocks": True,
        "phrases": ["this transit brings illness", "this placement causes accidents",
                    "this transit leads to disease", "this yoga brings death in the family",
                    "this placement causes cancer"],
        "instead": ("The same rule with nobody named: a placement or transit that BRINGS, CAUSES or "
                    "LEADS TO harm, to a family or to \"people with this placement\". What a "
                    "configuration signifies is fine; what it will do to somebody is not."),
    },
    {
        "category": "gem_fear",
        "blocks": True,
        "phrases": ["without this gemstone you will suffer", "not wearing this stone brings misfortune"],
        "instead": ("Selling is allowed; frightening somebody into buying is not. Describe a stone's "
                    "traditional association without a consequence for not wearing it."),
    },
    {
        "category": "compulsion",
        "blocks": True,
        "phrases": ["you must do a puja", "you have to perform a havan", "you need to book a ritual"],
        "instead": ("A remedy is offered, never required. Write \"the tradition suggests\", and "
                    "prefer a free practice: a temple visit, charity, or chanting the mantra oneself."),
    },
    {
        "category": "html",
        "blocks": True,
        "phrases": ["<p>", "<div>", "<br>", "<!--"],
        "instead": "The body is Markdown and the tags are built here. Send Markdown, not HTML.",
    },
    {
        "category": "placeholder",
        "blocks": True,
        "phrases": ["{price_kundali}"],
        "instead": ("Any brace-shaped token your generator failed to substitute. Fill it before "
                    "posting - it would otherwise appear as a brace on a live page."),
    },
    {
        "category": "personal_prediction",
        "blocks": False,
        "phrases": ["you will get married", "you will have a child", "you will get a job",
                    "you will be promoted", "you will become rich", "you will win"],
        "instead": ("Recorded as a warning, not blocked. A post is read by everybody and written "
                    "about nobody, so a second-person life outcome is a reading it never performed."),
    },
    {
        "category": "third_party_paid",
        "blocks": False,
        "phrases": ["book a puja with a priest", "order a yantra from", "hire an astrologer",
                    "pay a pandit to perform"],
        "instead": ("Recorded as a warning. Some phrasings - \"consult an astrologer\" among them - "
                    "are rewritten automatically toward this site's own tool or a free traditional "
                    "practice before the check runs, so they never reach you as a problem. Our own "
                    "paid products may be recommended honestly, with a real price."),
    },
)


def forbidden_phrases() -> list[str]:
    """Every blocked or warned phrase, flat, lowercase - the shape a prompt wants."""
    seen: list[str] = []
    for rule in FORBIDDEN:
        for phrase in rule["phrases"]:
            if phrase not in seen:
                seen.append(phrase)
    return seen


def forbidden_rules() -> list[dict]:
    """The same thing grouped, with what to write instead and whether it blocks or only warns."""
    return [dict(rule) for rule in FORBIDDEN]


# ---- safety and promises -----------------------------------------------------------------------------


def blocking_terms(text: str, *, lang: str = "en") -> list[str]:
    """The exact substrings in `text` that would BLOCK a post, or [] - no slug, length or HTML rules.

    This exists so app/blog/autofix.py can find the offending SENTENCE without parsing the English
    out of a check message. Reading "body: 'guaranteeing' - a guarantee: ..." back apart to learn
    which words to delete would make the wording of every message load-bearing, and somebody would
    reword one.

    Only the content rules, and only the blocking ones: the structural checks (a duplicate slug, a
    body under the word floor, a tag in the prose) are about the post as a whole and deleting a
    sentence cannot answer any of them.
    """
    found: list[str] = []
    if not text:
        return found
    for hit in screen_text(text):
        if hit.category in _BLOCKING_TOPICS:
            found.append(hit.term)
    for pattern, _ in (*_PROMISES, *_MEDICAL):
        for match in pattern.finditer(text):
            if not _negated_before(text, match.start()):
                found.append(match.group(0).strip())
                break
    for pattern in _IMPERSONAL_HARM:
        if (match := pattern.search(text)):
            found.append(match.group(0).strip())
            break
    for pattern in (_READER_HARM, _COMPULSION):
        if (match := pattern.search(text)):
            found.append(match.group(0).strip())
    for problem in language_problems(text, lang):
        found.append(problem)
    return found


def content_problems(post: dict) -> tuple[list[str], list[str]]:
    """(blocking, warnings): the shared safety screen, the language check, and the blog's own rules."""
    blocking: list[str] = []
    warnings: list[str] = []
    # THE POST'S OWN TREE, not "en". This was hardcoded to English with a comment saying the blog was
    # English only, which was true when it was written and stopped being true the day the Hindi and
    # Marathi trees shipped - so every Hindi and Marathi post was blocked with "the English version
    # is not in English", and no post could ever go live in either tree.
    #
    # The tests did not catch it because test_blog_languages.py publishes with a precomputed report
    # and store.publish(), so the one path that would have run this check on a Devanagari post was
    # the one path those tests skipped. A green suite about a population that never included the
    # case.
    lang = (post.get("language") or "en").strip() or "en"

    for where, text in _slots(post):
        if not text:
            continue
        # THE SHARED SCREEN, MINUS ONE CATEGORY. Nothing here passes `allow_gemstone`: that exists for
        # one chapter of the paid book, where the engine computed the recommendation, and a blog post
        # is not it.
        #
        # `hard_sell` IS SKIPPED ON THE BLOG, and only on the blog - the proprietor's decision, made
        # once the blog existed to sell anything from. A post may recommend our own paid products with
        # an honest call to action and a real price. The screen itself is NOT changed: the rashifal,
        # the paid reports and the consultation all run through the same function and still refuse it,
        # because none of them is a place to sell from.
        #
        # What is NOT relaxed, and is the reason this is a skip of one category rather than of the
        # screen: `gem_fear` still fires, `_COMPULSION` below still fires on "you must do a puja", and
        # the promise rules still refuse a guaranteed outcome. Selling is allowed; frightening somebody
        # into buying is not, and neither is promising what the thing will do for them.
        # DEATH AND ILLNESS STOP A POST; the rest of the screen is recorded and published.
        # Telling somebody a transit brings a serious illness is the one thing on this site that
        # could reach a person who is already frightened, and "divorce is common under this transit"
        # - catastrophe - is the kind of sentence an astrology blog is for.
        for hit in screen_text(text):
            if hit.category == "hard_sell":
                continue
            line = f"{where}: forbidden topic ({hit.category}): {hit.term!r}"
            (blocking if hit.category in _BLOCKING_TOPICS else warnings).append(line)
        # A post is checked against the tree it says it is in. A Devanagari body in the English tree
        # is still blocked - that would put Hindi under an /en canonical - but a Devanagari body in
        # the Hindi tree is simply a Hindi post.
        for problem in language_problems(text, lang):
            blocking.append(f"{where}: {problem}")
        if (tag := _TAG_SHAPED.search(text)):
            blocking.append(
                f"{where}: {tag.group(0)[:40]!r} is HTML, and HTML is not accepted - the body is "
                "Markdown and we build the tags ourselves (docs/BLOG_API.md, \"The body is Markdown\")")
        # THE LAW AND THE FRIGHTENED READER stop a post: a guaranteed outcome, a medical claim.
        # Third-party selling has a repair rule, so anything left of it here is a phrasing the rule
        # did not match - written down, and published.
        for pattern, message in (*_PROMISES, *_MEDICAL):
            for found in pattern.finditer(text):
                # A NEGATED PROMISE IS NOT A PROMISE. Every match is tested, not just the first:
                # a post that says "no guarantee" early and "guaranteed results" later must still be
                # caught by the second one.
                if _negated_before(text, found.start()):
                    continue
                blocking.append(f"{where}: {found.group(0).strip()!r} - {message}")
                break
        for pattern in _IMPERSONAL_HARM:
            if (found := pattern.search(text)):
                blocking.append(
                    f"{where}: {found.group(0).strip()[:90]!r} - a prediction that this placement "
                    "brings harm to people. What a house SIGNIFIES is fine to write; what a transit "
                    "will DO to somebody is not, named reader or not")
                break
        if (found := _READER_HARM.search(text)):
            blocking.append(
                f"{where}: {found.group(0).strip()!r} - a prediction that the reader will come to "
                "harm. The subject is fine to write about; aiming it at the person reading, as "
                "something that will or may happen to them, is the one thing this site will not do")
        for pattern, message in (*_LEGAL_FINANCIAL, *_THIRD_PARTY_PAID):
            if (found := pattern.search(text)):
                warnings.append(f"{where}: {found.group(0).strip()!r} - {message}")
        if (found := _PERSONAL_PREDICTION.search(text)):
            warnings.append(f"{where}: {found.group(0).strip()!r} - a post is read by everybody and "
                            "written about nobody, so it cannot predict one reader's life. The free "
                            "calculators are where somebody's own chart gets looked at")
        # THERE IS A REPAIR RULE FOR THIS, so what reaches here is a phrasing it did not match.
        if (found := _CHART_IT_HAS_NOT_SEEN.search(text)):
            warnings.append(f"{where}: {found.group(0).strip()!r} - this post has not seen anybody's "
                            "chart. Write \"a chart with Saturn in the seventh\", not \"your chart shows\"")
        if (found := _COMPULSION.search(text)):
            blocking.append(f"{where}: {found.group(0).strip()!r} - a remedy is offered, never required. "
                            "This is the pattern the dosha guides were written against")
        if (found := _PLACEHOLDER.search(text)):
            blocking.append(f"{where}: {found.group(0)!r} looks like an unfilled template placeholder. "
                            "Braces on a live page are a visible defect, and this site asserts that none "
                            "survive onto one")

    body = markdown.plain_text(post.get("body_md") or "")
    for sentence in _SENTENCE.split(body):
        if _READER_FUTURE.search(sentence) and _WHEN.search(sentence):
            blocking.append(
                f"body: {sentence.strip()[:120]!r} dates the reader's future. Every date in the rashifal "
                "comes from the ephemeris and is checked against the brief; a post has no brief, so a "
                "date attached to \"you will\" is invented")
            break

    years = re.findall(r"(?<!\d)(20\d\d)(?!\d)", body)
    for year in set(years):
        if years.count(year) > _MAX_SAME_YEAR:
            warnings.append(f"the year {year} appears {years.count(year)} times; give it where it is "
                            "needed rather than after every date")
            break
    if not (post.get("categories") or ()):
        warnings.append("no categories: the post will not appear under any heading on /blog")
    return blocking, warnings


# ---- links -------------------------------------------------------------------------------------------


def _media_id(href: str) -> str | None:
    """The image id in a /blog/media/<id> path, or None if this is not one."""
    prefix = paths.media_path("")
    return href[len(prefix):] or None if href.startswith(prefix) and len(href) > len(prefix) else None


def link_problems(post: dict, *, known_slugs: dict[str, str] | None = None) -> tuple[list[str], list[str]]:
    """(blocking, warnings) for the internal links in a body.

    A BROKEN INTERNAL LINK IS BLOCKING, and not out of neatness: tests/test_seo.py crawls every indexed
    page and asserts that every internal href it finds answers 200 directly - not a 301, not a 404. A
    post with a typo in a path would therefore turn the whole suite red after a merge, long after the
    writer had gone. Refusing it here is the only place the writer can still be told.
    """
    from app.web import i18n

    blocking: list[str] = []
    warnings: list[str] = []
    known = known_slugs or {}
    blog_root = paths.list_path().rstrip("/")
    for match in markdown._LINK.finditer(post.get("body_md") or ""):
        href = match.group("href").split("#", 1)[0].split("?", 1)[0]
        if not href.startswith("/") or href.startswith("/static/"):
            continue
        if href.startswith("//"):
            continue    # not a path at all; `markdown.render` reports it and drops the link
        if href in (blog_root, blog_root + "/") or i18n.resolve(href) is not None:
            continue
        # AN IMAGE WE ARE HOSTING. /blog/media/<id> is served by the blog's own route and is not in the
        # URL registry, so the registry check above cannot know about it and every post carrying a
        # picture was refused for linking to one. The id is checked against the store rather than
        # waved through on shape: a reference to an image nobody uploaded is a broken picture on a
        # live page, which is the thing this function exists to prevent.
        if (media_id := _media_id(href)) is not None:
            if images.file_for(media_id) is None:
                blocking.append(
                    f"the image {href!r} is not in the media store. Upload it to "
                    f"POST {paths.media_path('<id>').rsplit('/', 1)[0]} first and use the id it "
                    "returns, or drop the reference")
            continue
        slug = href[len(blog_root) + 1:] if href.startswith(blog_root + "/") else ""
        if slug and slug in known:
            if known[slug] != "published":
                warnings.append(f"the link to {href} points at a post that is still a draft, so it will "
                                "404 until that one is published too")
            continue
        blocking.append(
            f"the link {href!r} is not a page on this site. Internal links must answer 200 directly - "
            "tests/test_seo.py crawls them - so check the path against the URL registry, or link the "
            "tool by its registry key instead")
    return blocking, warnings


# ---- the whole check ---------------------------------------------------------------------------------


def check(post: dict, *, known_slugs: dict[str, str] | None = None,
          taken_titles: dict[str, str] | None = None) -> dict:
    """{"blocking": [...], "warnings": [...]}. An empty blocking list is the only thing that may be
    published - the rule `check_output` applies to a rashifal page, applied to a post.

    `known_slugs` is {slug: status} of the other posts, for the link check. `taken_titles` is
    {normalised title: slug} and {normalised summary: slug}; a duplicate of either is BLOCKING, because
    tests/test_pages_i18n.py asserts that no two pages on this site share a title or a description.
    """
    rendered, render_problems = markdown.render(post.get("body_md") or "")
    structure = structure_problems(post)
    content_blocking, content_warnings = content_problems(post)
    _link_blocking, link_warnings = link_problems(post, known_slugs=known_slugs)

    # ONLY WHAT BREAKS THE SITE OR THE LAW STOPS A POST. Everything else is written down and
    # published - the proprietor's decision, and the reasoning is cost: a post held back for a
    # phrasing nobody would notice costs a person's evening, and the posts this blog exists to
    # publish are worth more than the phrasings are worth avoiding.
    #
    # A BROKEN LINK IS NO LONGER BLOCKING. It is repaired instead: the link is dropped and its words
    # are kept, a missing image is dropped. See app/blog/autofix.py. `link_problems` still runs,
    # because what it finds after the repair is worth recording, but it cannot refuse a post.
    blocking = [problem for problem in structure if _breaks_the_site(problem)]
    warnings = [problem for problem in structure if not _breaks_the_site(problem)]
    blocking += [f"body: {problem}" for problem in render_problems]
    blocking += content_blocking
    warnings += content_warnings + link_warnings + _link_blocking

    for field in ("title", "summary"):
        value = _normalise((post.get(field) or ""))
        other = (taken_titles or {}).get(value)
        if value and other and other != post.get("slug"):
            # BLOCKING, and this is a judgement beyond the list given: two pages sharing a title or a
            # description is a duplicate in a search result AND a failing assertion in
            # tests/test_pages_i18n.py, so it is "breaks the site" rather than a matter of taste.
            blocking.append(f"the {field} is already used by the post {other!r}. Every page on this site "
                            "has its own title and its own description; two the same is a duplicate in "
                            "a search result and a failing assertion in tests/test_pages_i18n.py")
    return {"blocking": blocking, "warnings": warnings, "html": rendered}


#: Which STRUCTURAL problems stop a post. A slug that is not a slug has nowhere to live and an empty
#: body is not a page; a title eight characters too long is a worse page, not a broken one.
#:
#: THE SUMMARY'S LENGTH IS IN HERE and the title's is not, which looks arbitrary until you look at
#: what each one feeds. The summary is the page's meta description, and tests/test_pages_i18n.py
#: asserts that EVERY page on this site has one between 50 and 230 characters - so a short summary
#: is not a worse page, it is a red suite and a published page that violates a site-wide invariant.
#: Nothing asserts a title length; a long one is truncated in a search result and that is all.
_SITE_BREAKING = ("is not a usable slug", "the body is", "is HTML", "placeholder", "the summary is")


def _breaks_the_site(problem: str) -> bool:
    return any(marker in problem for marker in _SITE_BREAKING)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())
