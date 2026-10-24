"""Repairing a post on the way in, and recording every repair.

TWO LAYERS, AND THE ORDER MATTERS. Deterministic rules run first and fix everything that has one
right answer: a known phrase, an image reference, a link that should have been a registry path, a
sentence claiming to have seen the reader's chart. Only what is left goes to the model, once, with the
smallest instruction that can work.

WHY RULES FIRST rather than "ask the model to fix the post". A model asked to repair prose rewrites
prose - it improves sentences nobody complained about, and the diff stops being reviewable. Every rule
here is a find and a replace with a reason attached, so the admin page can show exactly what changed
and somebody can disagree with one line without re-reading the post.

EVERY FIX IS STORED WITH ITS BEFORE AND AFTER. A post that arrives wrong and goes live right, with no
record of the difference, is a post nobody can audit - and these are published under our name.

WHAT THIS WILL NOT DO. It does not fix a factual claim, it does not soften a promise into a hedge, and
it does not touch anything the checks call blocking for a reason of substance. A post that still has a
blocking problem after this stays a draft; auto-fix exists to stop a human re-typing "/kundali" as
"/birth-chart" fifty times, not to argue a post past its own checks.
"""

from __future__ import annotations

import logging
import re

from . import config, images, paths

log = logging.getLogger(__name__)

#: The most it will ask the model, ever. Two rounds, because the first one sometimes fixes three of
#: four problems and the second finishes; a third has never been the difference between a draft and a
#: publish in anything we have seen, and an unbounded loop on somebody else's text is not a thing to
#: ship.
MAX_AI_ROUNDS = 2


def _cta(key: str, label: str) -> str:
    """One of our own calls to action, as Markdown."""
    link = paths.tool_link(key, paths.LANG)
    return f"[{label}]({link['path']})" if link else label


#: SENDING A READER TO SOMEBODY ELSE'S ASTROLOGER. This is the one phrase the old `hard_sell` rule
#: existed to catch that is still worth catching - not because selling is wrong, but because this
#: sells for a competitor from a page we are paying to host. It is rewritten rather than refused: the
#: writer meant "get this looked at properly", and we have the thing that does that.
_OUTSIDE_ASTROLOGER = re.compile(
    r"\bconsult\s+(?:a|an|your|another|a\s+qualified|an\s+experienced)\s+"
    r"(?:astrologer|pandit|priest|jyotish\w*)\b", re.I)

#: A POST HAS NOT SEEN ANYBODY'S CHART. The check refuses these; the fix turns the claim into the
#: general statement the writer almost always meant.
_YOUR_CHART = re.compile(
    r"\byour\s+(?:kundli|kundali|chart|horoscope|birth\s+chart)\s+(?:shows|says|tells|indicates|reveals)\b",
    re.I)


def _capitalise(text: str) -> str:
    """Upper-case the first LETTER, looking past any Markdown that opens the string.

    "[ask our AI astrologer](/x)" has to become "[Ask ...", not "[ask ..." with a capital bracket -
    so this finds the first character that is actually a letter rather than assuming position zero.
    """
    for position, char in enumerate(text):
        if char.isalpha():
            return text[:position] + char.upper() + text[position + 1:]
    return text


#: THE "100%" QUALIFIER, DELETED RATHER THAN REFUSED. On its own it is a boast, not a promise:
#: "100% accurate predictions" is one word of puffery in front of a claim that stands or falls by
#: itself, and blocking a whole draft for it costs a post to save a word. So the qualifier goes and
#: what remains is judged on its own - "100% guaranteed results" becomes "guaranteed results" and is
#: still blocked, by the guarantee rule, which is the rule that should have been blocking it.
#:
#: "100% FREE" IS LEFT ALONE, because it is true. Every tool this site puts behind that phrase costs
#: nothing, and deleting the qualifier there would remove a fact rather than a boast.
#:
#: THE `free` LOOKAHEAD GOES BEFORE THE WHITESPACE, NOT AFTER IT. `\s*` can backtrack to nothing, so
#: a lookahead placed after it was tested against " free" rather than "free", passed, and deleted the
#: qualifier out of "our tools are 100% free" anyway - leaving a double space where a fact had been.
#:
#: THE ARTICLE IS PART OF THE MATCH. "a hundred per cent accurate reading" with the qualifier cut out
#: is "a accurate reading"; the article is re-emitted as a or an according to the word that ends up
#: after it. Without that, this rule fixed a boast and introduced a grammatical error.
_HUNDRED_PER_CENT = re.compile(
    r"(?P<art>\b[Aa]n?\s+)?"
    r"\b(?:100\s*%|100\s*per\s?cent|hundred\s+per\s?cent)"
    r"(?!\s*free\b)"
    r"\s*(?=(?P<next>\w))", re.I)

_VOWEL = re.compile(r"[aeiouAEIOU]")


def _repair_hundred_per_cent(body: str) -> tuple[str, list[dict]]:
    """Drop the qualifier wherever it is not "100% free". Returns (body, fixes)."""
    fixes: list[dict] = []

    def swap(match: "re.Match[str]") -> str:
        article = match.group("art") or ""
        after = ""
        if article:
            # a / an, decided by the word the deletion leaves behind it.
            word = "an" if _VOWEL.match(match.group("next") or "") else "a"
            after = (word.capitalize() if article.strip()[:1].isupper() else word) + " "
        fixes.append({"what": 'a "100%" qualifier was dropped',
                      "before": match.group(0).strip(), "after": after.strip(), "by": "rules"})
        return after

    out = _HUNDRED_PER_CENT.sub(swap, body)
    if fixes:
        # A deletion that opened a sentence leaves the next word carrying the capital.
        out = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)
    return out, fixes


def deterministic(body: str, *, lang: str = "en") -> tuple[str, list[dict]]:
    """Every repair with exactly one right answer. Returns (body, fixes)."""
    fixes: list[dict] = []

    def record(what: str, before: str, after: str) -> None:
        fixes.append({"what": what, "before": before, "after": after, "by": "rules"})

    def sub(pattern: re.Pattern, replacement, what: str, text: str) -> str:
        def swap(match: "re.Match[str]") -> str:
            after = replacement(match) if callable(replacement) else replacement
            # KEEP THE CAPITAL. "Consult an astrologer for a reading" became "[ask our AI
            # astrologer](...) for a reading" - a lower-case letter opening a sentence, in a repair
            # meant to be invisible. If the writer's phrase started a sentence, so does ours.
            if match.group(0)[:1].isupper():
                after = _capitalise(after)
            record(what, match.group(0), after)
            return after
        return pattern.sub(swap, text)

    # Somebody else's astrologer becomes ours. The sentence keeps its shape.
    body = sub(_OUTSIDE_ASTROLOGER,
               lambda m: _cta("consultation", "ask our AI astrologer"),
               "an outside astrologer became our own", body)

    # "your kundli shows" -> "a chart with ...": the general claim the writer meant.
    body = sub(_YOUR_CHART, "a chart like this shows",
               "a claim about the reader's own chart became a general one", body)

    body, hundred_fixes = _repair_hundred_per_cent(body)
    fixes += hundred_fixes
    body, paid_fixes = _repair_third_party(body)
    fixes += paid_fixes
    body, link_fixes = _repair_links(body)
    fixes += link_fixes
    body, image_fixes = _repair_images(body)
    fixes += image_fixes
    body, dead_fixes = _drop_what_does_not_resolve(body)
    fixes += dead_fixes
    return body, fixes


#: SOMEBODY ELSE'S TILL, REWRITTEN RATHER THAN REFUSED. The check blocks a paid ritual booked through
#: a third party; most of the time the writer meant "do something about this", and the tradition has
#: answers that cost nothing. So a paid booking becomes the free practice, and a paid READING becomes
#: ours - the reader wanted a chart looked at, and we have the thing that looks at charts.
#:
#: The whole phrase is matched, including its "with a priest" tail, because replacing only the verb
#: leaves "visit a temple with any temple priest" on the page.
_FREE_PRACTICE = "visit a temple, give to charity, or chant the mantra yourself"

_THIRD_PARTY_REWRITES = (
    (re.compile(r"\b(?:you\s+(?:can|could|should|may)\s+)?(?:book|booking|arrange|order|sponsor)\s+"
                r"(?:a|an|the|any)?\s*(?:paid\s+)?"
                r"(?:puja|pooja|homa|havan|havana|yagna|yagya|yajna|abhishek\w*|ritual|ceremony)"
                r"(?:\s+(?:with|from|through|at|by)\s+(?:a|an|the|any|your)?\s*"
                r"(?:[a-z]+\s+){0,2}(?:priest|pandit|temple|astrologer|centre|center|office|service|shop))?",
                re.I),
     lambda m: _FREE_PRACTICE,
     "a paid ritual became a free traditional practice"),
    (re.compile(r"\b(?:buy|purchase|order|get)\s+(?:a|an|the|your)?\s*"
                r"(?:yantra|rudraksha\w*|kavach|locket|talisman|amulet)"
                r"(?:\s+(?:from|at|online|through)\s+(?:a|an|the)?\s*(?:[a-z]+\s+){0,2}"
                r"(?:seller|shop|store|site|jeweller|jeweler|dealer))?", re.I),
     lambda m: _FREE_PRACTICE,
     "an object bought from an outside seller became a free traditional practice"),
    (re.compile(r"\b(?:hire|engage|pay\s+for)\s+(?:a|an|the)?\s*"
                r"(?:pandit|priest|astrologer|jyotish\w*)\b", re.I),
     lambda m: _cta("consultation", "ask our AI astrologer"),
     "paying another astrologer became our own"),
    (re.compile(r"\b(?:a|an)\s+paid\s+(?:consultation|reading|horoscope\s+reading)\b", re.I),
     lambda m: _cta("consultation", "a question to our AI astrologer"),
     "a paid reading elsewhere became our own"),
)


def _repair_third_party(body: str) -> tuple[str, list[dict]]:
    """Third-party commerce, rewritten toward our own call to action or a free practice."""
    fixes: list[dict] = []
    for pattern, replacement, what in _THIRD_PARTY_REWRITES:
        def swap(match: "re.Match[str]", replacement=replacement, what=what) -> str:
            after = replacement(match)
            if match.group(0)[:1].isupper():
                after = _capitalise(after)
            fixes.append({"what": what, "before": match.group(0), "after": after, "by": "rules"})
            return after
        body = pattern.sub(swap, body)
    return body, fixes


#: Paths writers reach for that are not the registry's. The right-hand side is a registry KEY, so the
#: replacement is whatever that page's path is in this tree - never a path typed twice.
_PATH_ALIASES = {
    "/kundali": "kundali", "/kundli-chart": "kundali", "/birth-chart/": "kundali",
    "/matching": "matching", "/kundli-matching": "matching", "/guna-milan": "matching",
    "/mangal": "mangal-dosha", "/manglik": "mangal-dosha",
    "/sadesati": "sade-sati", "/shani": "sade-sati",
    "/panchangam": "panchang", "/ai": "consultation", "/chat": "consultation",
    "/horoscope/today": "rashifal-hub", "/rashifal": "rashifal-hub",
}

_LINK = re.compile(r"(?<!!)\[(?P<text>[^\]]*)\]\((?P<href>[^)\s]+)\)")
_IMAGE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<href>[^)\s]+)\)")


def _repair_links(body: str) -> tuple[str, list[dict]]:
    """Known wrong paths, mapped through the URL registry.

    THE REGISTRY IS ASKED, not a second table of paths. A hard-coded right-hand side would be a path
    written twice, and the one in here would be the one nobody updated.
    """
    fixes: list[dict] = []

    def swap(match: "re.Match[str]") -> str:
        href = match.group("href")
        bare = href.split("#", 1)[0].split("?", 1)[0].rstrip("/") or "/"
        key = _PATH_ALIASES.get(bare) or _PATH_ALIASES.get(bare + "/")
        if not key:
            return match.group(0)
        link = paths.tool_link(key, paths.LANG)
        if not link or link["path"] == href:
            return match.group(0)
        after = f"[{match.group('text')}]({link['path']})"
        fixes.append({"what": "a link was pointed at the page that exists",
                      "before": match.group(0), "after": after, "by": "rules"})
        return after

    return _LINK.sub(swap, body), fixes


def _repair_images(body: str) -> tuple[str, list[dict]]:
    """Image references, against the media store.

    A BARE ID OR A FILENAME becomes the path it should have been, WHEN that id is really in the store.
    An id nobody uploaded is left exactly as it is: the check then refuses the post and says so, which
    is the honest outcome - inventing a path to a picture that does not exist would turn a clear
    refusal into a broken image on a live page.
    """
    fixes: list[dict] = []
    prefix = paths.media_path("")

    def swap(match: "re.Match[str]") -> str:
        href = match.group("href")
        if href.startswith(prefix) or href.startswith(("http://", "https://", "/static/")):
            return match.group(0)
        candidate = href.strip("/").split("/")[-1].split(".")[0]
        if not candidate or images.file_for(candidate) is None:
            return match.group(0)
        after = f"![{match.group('alt')}]({paths.media_path(candidate)})"
        fixes.append({"what": "an image reference was pointed at the media store",
                      "before": match.group(0), "after": after, "by": "rules"})
        return after

    return _IMAGE.sub(swap, body), fixes


# ---- the model, once, with the smallest instruction that can work --------------------------------

#: What the model may return: literal find/replace pairs and a reason for each. NOT a rewritten post.
#: A model handed a post and asked to fix it returns a better post, and nobody can review that against
#: the one that arrived; handed a list of problems and asked for replacements, it returns something a
#: person can read line by line and disagree with one of.
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["replacements"],
    "properties": {
        "replacements": {
            "type": "array", "maxItems": 12,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["find", "replace", "why"],
                "properties": {
                    "find": {"type": "string", "minLength": 3, "maxLength": 300},
                    "replace": {"type": "string", "maxLength": 300},
                    "why": {"type": "string", "maxLength": 200},
                },
            },
        }
    },
}

_SYSTEM = """You repair blog posts for an Indian Vedic astrology site so they pass its publishing checks.

Return ONLY find/replace pairs. Never rewrite a sentence that is not named in the problems you are
given. `find` must appear in the body EXACTLY ONCE, character for character.

The rules you are repairing against:
- A post has not seen any reader's chart. It may describe what a chart with a placement shows; it may
  not say what the reader's own chart shows.
- No promise of an outcome: no guaranteed result, no dated prediction about a reader's life, no
  medical, legal or financial advice.
- No fear used to sell: nothing a reader MUST do or buy to avoid a bad outcome.
- Recommending this site's own paid products is ALLOWED and welcome, with an honest description and a
  real price. Do not remove those.
- Keep the writer's voice, the facts and the structure. Change as little as possible.

If a problem cannot be fixed by replacing a phrase - it needs a fact checked, or a whole paragraph
rethought - leave it out. A post that stays a draft is a fine outcome; a post edited into something
its writer did not say is not."""


def ai_pass(body: str, problems: list[str], *, client=None) -> tuple[str, list[dict]]:
    """One model round. Returns (body, fixes) and NEVER raises.

    Haiku, because this is find-and-replace against a list that has already been narrowed by the
    rules above - not a writing task. If the model is not configured, or errors, or returns something
    that does not apply cleanly, the body comes back exactly as it went in and the post stays a draft.
    That is the failure this is designed for: auto-fix is a convenience, and a convenience that breaks
    a post is worse than no convenience.
    """
    if not problems:
        return body, []
    try:
        client = client or _haiku()
    except Exception as exc:  # noqa: BLE001 - not configured is an ordinary state, not an error
        log.info("blog auto-fix: no model available (%s)", type(exc).__name__)
        return body, []

    listed = "\n".join(f"- {problem}" for problem in problems[:12])
    user = f"PROBLEMS TO FIX:\n{listed}\n\nTHE BODY:\n{body}"
    try:
        result = client.generate_json(system=_SYSTEM, user=user, schema=_SCHEMA)
        pairs = (result.data or {}).get("replacements") or []
    except Exception as exc:  # noqa: BLE001 - see the docstring
        log.warning("blog auto-fix: the model call failed (%s)", type(exc).__name__)
        return body, []

    fixes = []
    for pair in pairs:
        find, replace = str(pair.get("find", "")), str(pair.get("replace", ""))
        # EXACTLY ONCE, or not at all. A `find` that appears twice would change a sentence nobody
        # looked at, and one that appears zero times means the model invented the text it was
        # quoting - which is the failure mode worth refusing rather than guessing around.
        if not find or body.count(find) != 1:
            log.info("blog auto-fix: skipped a replacement that matched %d times", body.count(find))
            continue
        body = body.replace(find, replace, 1)
        fixes.append({"what": str(pair.get("why", ""))[:200] or "the model repaired a phrase",
                      "before": find, "after": replace, "by": "haiku"})
    return body, fixes


def _haiku():
    """A client pinned to Haiku, whatever the site's main model is set to."""
    import dataclasses

    from app.ai.client import ClaudeClient
    from app.ai.config import get_settings

    settings = get_settings()
    return ClaudeClient(dataclasses.replace(settings, model="claude-haiku-5-5"))


def repair(post: dict, recheck, *, client=None) -> tuple[dict, list[dict]]:
    """Fix what can be fixed, then hand back the post and everything that was changed.

    `recheck(post) -> {"blocking": [...], ...}` is passed in rather than imported so this module does
    not depend on the one that calls it.

    THE RULES ALWAYS RUN. The model runs only if something is still blocking afterwards, at most
    MAX_AI_ROUNDS times, and stops early the moment a round changes nothing - a model that cannot fix
    a problem on its first look does not fix it on its third, and the rounds exist for the case where
    one fix reveals the next.
    """
    body, fixes = deterministic(post.get("body_md") or "")
    working = {**post, "body_md": body}

    # THE MODEL IS OFF BY DEFAULT. The rules above do the repairs; whatever they cannot fix is
    # recorded as a warning and the post publishes anyway. Turning BLOG_AI_FIX on buys a second
    # attempt at the leftovers, at a cost per post, and nothing about this pipeline needs it.
    if not config.ai_fix():
        return working, fixes

    for _ in range(MAX_AI_ROUNDS):
        blocking = recheck(working).get("blocking") or []
        if not blocking:
            break
        body, round_fixes = ai_pass(working["body_md"], blocking, client=client)
        if not round_fixes:
            break
        fixes += round_fixes
        working = {**working, "body_md": body}

    return working, fixes


def _drop_what_does_not_resolve(body: str) -> tuple[str, list[dict]]:
    """A link to nothing loses its link and keeps its words. An image that is not there is dropped.

    NEITHER IS BLOCKING ANY MORE. A post held back because one path in it is wrong costs a person an
    evening over something nobody reading the post would notice - the sentence reads perfectly well
    without the link, which is why dropping it is a repair rather than a loss.

    THE WORDS SURVIVE, ALWAYS. "See the [matching tool](/nope)" becomes "See the matching tool", not
    "See the". Deleting a writer's sentence to fix their URL would be a worse bargain than the broken
    URL, and it is the mistake this is most likely to make if it is ever rewritten.
    """
    from app.web import i18n

    fixes: list[dict] = []
    blog_root = paths.list_path()
    media_prefix = paths.media_path("")

    def resolves(href: str) -> bool:
        path = href.split("#", 1)[0].split("?", 1)[0]
        if not path.startswith("/") or path.startswith(("/static/", "//")):
            return True                       # not ours to judge
        if path in (blog_root, blog_root + "/") or i18n.resolve(path) is not None:
            return True
        if path.startswith(media_prefix):
            return images.file_for(path[len(media_prefix):]) is not None
        slug = path[len(blog_root) + 1:] if path.startswith(blog_root + "/") else ""
        from . import store

        return bool(slug) and slug in store.slug_status()

    def drop_image(match: "re.Match[str]") -> str:
        if resolves(match.group("href")):
            return match.group(0)
        fixes.append({"what": "an image that is not in the store was dropped",
                      "before": match.group(0), "after": "", "by": "rules"})
        return ""

    def unlink(match: "re.Match[str]") -> str:
        if resolves(match.group("href")):
            return match.group(0)
        after = match.group("text")
        fixes.append({"what": "a link that pointed at nothing was dropped, keeping its words",
                      "before": match.group(0), "after": after, "by": "rules"})
        return after

    body = _IMAGE.sub(drop_image, body)
    body = _LINK.sub(unlink, body)
    return body, fixes
