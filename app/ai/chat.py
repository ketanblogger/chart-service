"""Consultation chat service (Phase 5). Routes are in chat_routes.py; storage in chat_store.py.

One turn:  rate limit -> session -> input safety screen (fixed reply, free) -> quota + slot (402 BEFORE
           any AI work) -> AI (system + chart JSON + full history, cached prefix) -> output screen (safety + facts)
           -> regenerate once with a checker note -> else fixed fallback -> record, spend one message.

A message is spent only when an AI reply is delivered. Fixed replies (input screen, fallback) and errors
cost the user nothing.
"""

import datetime as dt
import logging
import re

from . import chat_store as store
from .chat_prompts import build_context, build_engine_data, build_messages, build_summary, build_system
from . import chat_style
from .chat_safety import LANGUAGES, canned_reply, detect_language, screen_input, topic_for_refusal
from .client import AIBadOutput, AIError, ChatLLMClient, ClaudeClient
from .config import estimate_cost_usd, get_chat_settings
from .language import normalise_digits
from .report import today_ist
from .safety import screen_text
from .validator import REDACT_KINDS, allow_mentions, check_text, collect_facts, facts_from_json, facts_to_json

log = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 1000
PRODUCT = "consultation-pack"     # the retired id; still honoured for anyone holding one
# What the paywall OFFERS today. Kept apart from PRODUCT on purpose: PRODUCT is history (orders that exist),
# this is the thing for sale, and conflating them is how the 402 came to quote an unsellable product.
OFFER_PRODUCT = "consultation-basic"


class SessionNotFound(Exception):
    pass


def get_chat_client() -> ChatLLMClient:
    """The one place the chat gets its AI client. Tests and scripts/browser_check_consultation.py replace it."""
    return ClaudeClient()


def paywall() -> dict:
    """The 402 payload: what the chat offers to sell when the free messages run out.

    THE PRICE AND THE PRODUCT COME FROM THE CATALOGUE, not from `CHAT_PACK_PRICE_INR`. They used to come from
    the chat settings, and that was a SECOND SOURCE OF TRUTH for a price - it agreed with the catalogue only
    because both happened to say 99. The moment the catalogue moved to 119 on 2026-09-28 the paywall would
    have ADVERTISED ₹99 and checkout would have CHARGED ₹119, which is the failure the catalogue's own
    docstring exists to forbid: "the only place an amount to charge ever comes from".

    It also named `consultation-pack`, the RETIRED id, which cannot be bought at all - so the payload
    described an unsellable product at a price nothing charged. It now names the entry tier, the same entry
    `pages.chat_offer()` reads, so the card and this payload cannot drift apart again.
    """
    settings = get_chat_settings()
    from app.payments import catalogue           # local: app.payments imports app.ai.products at module level
    from app.web import pages

    # EVERY TIER THAT IS ACTUALLY ON SALE, cheapest first, from the same list the card on the page is
    # built from - so the payload and the buttons cannot describe different things. The card has always
    # rendered all of them; this payload named one, and if the smallest tier is live that one was not it.
    offers = [{"product": option["product"], "price_inr": option["price_inr"],
               "messages": getattr(catalogue.item(option["product"]), "messages", 0)}
              for option in pages.purchase_options("consultation")]

    # The HEADLINE stays the single product the 402 has always named, because a client reading
    # `product` and `price_inr` is entitled to the thing somebody is most likely to buy - but it is now
    # the CHEAPEST tier on sale rather than a constant. The jump from two free answers to Rs 119 is the
    # decision this exists to make smaller, and quoting Rs 119 while a Rs 29 pack sits on the same card
    # is the mismatch the docstring above was written about.
    lead = offers[0] if offers else None
    if lead is None:                              # nothing sellable: keep the old shape, not a crash
        pack = catalogue.item(OFFER_PRODUCT)
        return {"code": "payment_required", "product": OFFER_PRODUCT, "price_inr": pack.price_inr,
                "messages": pack.messages or settings.pack_messages}
    return {"code": "payment_required", "product": lead["product"], "price_inr": lead["price_inr"],
            "messages": lead["messages"] or settings.pack_messages, "offers": offers}



# ---- sessions --------------------------------------------------------------------------------------


def _session_data(birth: dict, as_of: dt.date, *, numerology_for: str | None = None) -> tuple[dict, dict, dict]:
    data = build_engine_data(birth, as_of)
    context = build_context(data, as_of)
    if numerology_for is not None:
        # RECOMPUTED FROM THE SAME BIRTH DATE THE CHART USES, rather than carried here from the
        # numerology page through sign-in. One implementation means the chat's numbers cannot drift
        # from the calculator's, and nothing about a reader travels that was not already travelling.
        #
        # `numerology_for` is the NAME, and it does not leave this call: app/numerology/core.py
        # returns the number a name adds up to and not the name, which keeps the chat's standing rule
        # that a reader's name is display-only and is never sent to the model.
        from app.numerology import core as numerology

        context["numerology"] = numerology.for_chat(
            dt.date.fromisoformat(birth["date"]), numerology_for)
    return context, build_summary(data["chart"], as_of), facts_to_json(collect_facts(data))


def start_session(user_id: str, bucket_key: str, ip_key: str, birth: dict, name: str | None, language: str,
                  *, numerology: bool = False) -> dict:
    """Builds the chart once (as_of pinned to today, IST) and opens a session.

    `numerology=True` adds a numbers block to the context and the numerology rules to the system
    prompt. A chat without it is unchanged in every byte, which matters: the chart chat is a live
    paid feature and its system prompt is the cached prefix of every conversation on this site.
    """
    as_of = today_ist()
    context, summary, facts = _session_data(birth, as_of,
                                            numerology_for=(name or "") if numerology else None)
    store.ensure_user(user_id)
    store.sync_free_usage(user_id, bucket_key)
    session_id = store.create_session(user_id, bucket_key, ip_key, name, language, birth, as_of.isoformat(),
                                      context, summary, facts)
    return session_view(store.get_session(session_id))


def _fresh(session: dict) -> dict:
    """Transits and the 'current' dasha go stale overnight: rebuild the context when the IST date changes."""
    today = today_ist()
    if session["as_of"] != today.isoformat():
        context, summary, facts = _session_data(session["birth"], today)
        store.update_session_data(session["session_id"], today.isoformat(), context, summary, facts)
        session.update(as_of=today.isoformat(), context=context, summary=summary, facts=facts)
    return session


def load_session(session_id: str) -> dict:
    session = store.get_session(session_id or "")
    if session is None:
        raise SessionNotFound(session_id)
    return _complete(session)


def _complete(session: dict) -> dict:
    """Top up a summary saved before the page needed everything in it.

    A session stored before the chart panel drew the kundali has no `houses`, so reopening it would show
    a panel with the figures and no diamond - for every conversation that already exists. The chart is
    rebuilt from the birth details the session already holds and written back, once, the first time such
    a session is opened. `_fresh` is deliberately not used here: that one also re-dates the transits, and
    a view should not quietly move the ground under a conversation that is only being read.
    """
    if (session.get("summary") or {}).get("houses"):
        return session
    try:
        as_of = dt.date.fromisoformat(session["as_of"])
        context, summary, facts = _session_data(session["birth"], as_of)
    except Exception:                      # noqa: BLE001 - a missing ornament must never cost a reader
        log.warning("could not top up the summary for a session; the panel will show no chart")
        return session
    store.update_session_data(session["session_id"], session["as_of"], context, summary, facts)
    session.update(context=context, summary=summary, facts=facts)
    return session


def session_view(session: dict) -> dict:
    """What the browser gets: never the model context, never ids other than the session's own."""
    quota = store.quota(session["user_id"], session["bucket_key"], session["ip_key"])
    return {
        "session_id": session["session_id"],
        "name": session["name"],
        "language": session["language"],
        "summary": session["summary"],
        "messages": [{"role": m["role"], "content": m["content"], "kind": m["kind"]}
                     for m in store.get_messages(session["session_id"])],
        "quota": quota,
        "paywall": _paywall_for(quota, session["user_id"], session["language"], False),
    }


# ---- one turn --------------------------------------------------------------------------------------


def _history(session_id: str) -> list[dict]:
    """Delivered AI exchanges only (fixed replies and the questions that triggered them are left out)."""
    history = []
    for message in store.get_messages(session_id):
        if message["kind"] == "ai":
            history.append({"role": message["role"], "content": message["content"],
                            "language": (message.get("meta") or {}).get("language", "en")})
    return history


_DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def _problems(reply: str, facts) -> list[str]:
    """Blocking problems: a reply that still has one after the regeneration is replaced by the fallback."""
    found = [f"forbidden topic ({hit.category}): '{hit.term}'" for hit in screen_text(reply)]
    found += [issue.message for issue in check_text(reply, facts) if issue.kind in REDACT_KINDS]
    return found


def _soft_problems(reply: str, language: str, facts) -> list[str]:
    """Worth one regeneration, never worth withholding the answer: heuristic "own sign" findings, and a
    Devanagari slip in a romanised reply (seen live: "usके baad")."""
    found = [issue.message for issue in check_text(reply, facts) if issue.kind in ("dignity", "wording")]
    # The script half of this moved to chat_style.script_problems, where it is a HARD check.
    return found


def _paywall_for(quota: dict, account_id: str, language: str, is_admin: bool) -> dict | None:
    """The paywall payload when the allowance is gone, and the event that records that it was shown.

    Two steps of the funnel meet here and neither was counted: the moment somebody runs out of free
    answers, and the moment they are shown what it costs. Everything between a sign-up and a sale was
    invisible, so there was no way to tell a pricing problem from a plumbing one.
    """
    if quota.get("messages_left", 0) > 0:
        return None
    try:
        from app import analytics

        analytics.record_event("chat", "paywall", account_id=account_id, is_admin=is_admin,
                               lang=language, cost_inr=0.0)
    except Exception:  # noqa: BLE001 - counting never blocks the paywall
        log.exception("paywall not counted")
    return paywall()


def _count_question(meta: dict, language: str, account_id: str, is_admin: bool, kind: str = "ai") -> None:
    """One AI answer, with what it cost us and whether the reader actually got an answer.

    A FALLBACK IS A FAILURE. It was recorded as a success, so the Usage page said "Nothing failed" in a
    week when about twelve people asked a question and received "I couldn't put together a reliable
    answer" instead. The thing that went wrong is recorded here with its reason, so it shows up under
    what failed and in the per-day counts. The reason is structural - the checker's own category, never
    the question and never the answer.
    """
    try:
        from app import analytics

        meta = meta or {}
        ok = kind != "fallback"
        detail = "" if ok else _failure_reason(meta)
        analytics.record_event("chat", "question", account_id=account_id, is_admin=is_admin,
                               ok=ok, lang=language, cost_inr=_cost_inr(meta), detail=detail)
    except Exception:  # noqa: BLE001 - counting never breaks a consultation
        log.exception("chat question not counted")


#: The checker's categories, from the wording it rejects with. Structural labels, so they can be counted
#: and compared across a week - never the sentence the model wrote.
_FAILURE_LABELS = (
    ("mixed-script", ("mixes Latin and Devanagari", "another script entirely")),
    ("wrong-script", ("written in Latin letters", "written in Devanagari")),
    ("invented-fact", ("not in the data", "does not appear", "copy facts")),
    ("model-refused", ("declined", "refusal", "could not be used")),
)


def _cost_inr(meta: dict) -> float | None:
    """What this answer cost us, in rupees, from the tokens it actually used.

    IT WAS READING A KEY NOBODY WRITES. `_ask_ai` records `cost_usd`; this read `cost_estimate_inr`, which
    is the REPORT pipeline's name for its own field - so every chat question went into the usage table at
    0.00 and the Usage page showed Margin = Revenue while the Generation page showed real rupees for the
    same calls. The dollars are converted at the same `USD_INR` the ledger uses, so the two agree.

    Every attempt is counted, rejected drafts included: a regeneration is money spent whether or not the
    reader ever saw its output. A call whose model has no price in the table returns 0.0 and is reported
    as not recorded rather than as free.
    """
    usd = meta.get("cost_usd")
    if usd is None:
        # An unpriced model. NOT zero: a column of zeroes is what hid this for months, and "we do not
        # know what this cost" is a different thing to report than "this was free".
        log.warning("chat answer has no priced cost (model %r) - recorded as not known", meta.get("model"))
        return None
    from app.admin.ledger import usd_inr

    return round(float(usd) * usd_inr(), 4)


def _failure_reason(meta: dict) -> str:
    text = " ".join(str(p) for p in (meta.get("problems") or []))
    for label, needles in _FAILURE_LABELS:
        if any(needle in text for needle in needles):
            return label
    return "other"


def _muhurta_reply(session: dict, text: str, language: str) -> str | None:
    """The engine's answer to a date question, or None when this is not one.

    Off entirely unless `site.MUHURTA` is on, and silent unless the message asks for a date FOR a purpose
    the finder knows - see app/ai/muhurta_intent.py for why that bar is set where it is. Anything that
    raises here is swallowed: a muhurta question that cannot be computed must become an ordinary question
    for the astrologer, never an error in the middle of somebody's consultation.
    """
    from app.web import site

    if not site.MUHURTA:
        return None
    from app.ai import muhurta_intent

    try:
        refusal = muhurta_intent.refusal_for(text, language)
        if refusal:
            return refusal
        purpose = muhurta_intent.detect(text)
        if purpose is None:
            return None
        birth = session.get("birth") or {}
        if birth.get("lat") is None or birth.get("lon") is None:
            return None
        place = {"name": birth.get("city"), "lat": birth["lat"], "lon": birth["lon"],
                 "tz": birth.get("timezone") or "Asia/Kolkata"}
        return muhurta_intent.answer(purpose, language, place)
    except Exception:  # noqa: BLE001 - see the docstring: never break a consultation over this
        log.exception("muhurta intent failed; falling back to the astrologer")
        return None


def send_message(session_id: str, text: str, *, client: ChatLLMClient | None = None,
                 unlimited: bool = False, account_id: str = "") -> dict:
    """Returns {reply, quota, paywall}. Raises SessionNotFound, ValueError (bad text), store.RateLimited,
    store.QuotaExhausted (-> 402, no AI call), store.Busy, AIError."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Please type a question.")
    if len(text) > MAX_MESSAGE_CHARS:
        raise ValueError(f"Please keep your question under {MAX_MESSAGE_CHARS} characters.")
    session = load_session(session_id)
    user_id, bucket_key, ip_key = session["user_id"], session["bucket_key"], session["ip_key"]
    settings = get_chat_settings()
    store.check_rate(f"msg:user:{user_id}", settings.rate_per_minute, 60)
    store.check_rate(f"msg:ip:{ip_key}", settings.rate_per_minute * 3, 60)

    # THE STYLE OF THIS CHAT. Settled by the first message and then kept: a follow-up typed in another
    # script is how a phone keyboard behaves, not a request. Only an explicit instruction moves it.
    language, first_reply = _settle_style(session, text)

    # THE TITLE IS THE FIRST QUESTION, taken before the answer is known so that a chat has a name in the
    # sidebar even if the answer fails. Only ever set once, and never over a name the reader chose.
    store.title_if_unset(session_id, text)

    # THE SAFETY REPLIES FOLLOW THE MESSAGE, NOT THE LOCK. The lock exists because the MODEL mixes scripts
    # when it is asked to change mid-conversation; a canned reply is a fixed sentence we wrote, in a known
    # language, so there is nothing to mix. And the person typing "main marna chahta hoon" into a chat that
    # opened in English needs the helpline in the language they just reached for - consistency of style is
    # not worth answering a distressed person in a language they may not read.
    spoken = detect_language(text, default=language)

    category = screen_input(text)
    muhurta_reply = _muhurta_reply(session, text, language) if not category else None
    if category:
        # Fixed reply: no AI call, no quota needed (a distressed person at the paywall still gets the helpline).
        reply, kind = canned_reply(category, spoken), "safe"
        quota = store.record_exchange(session_id, user_id, bucket_key, ip_key, text, reply, kind,
                                      {"language": spoken, "screen": category})
    elif muhurta_reply is not None:
        # A DATE QUESTION, ANSWERED BY THE ENGINE. Same path as a screened reply and for the same reason:
        # no model is called, so no quota is spent. The rate limiter above has already run, which is what
        # keeps this from being an unmetered way to make the server compute sixty sunrises.
        reply, kind = muhurta_reply, "muhurta"
        quota = store.record_exchange(session_id, user_id, bucket_key, ip_key, text, reply, kind,
                                      {"language": language, "muhurta": True})
    else:
        # AN ADMINISTRATOR IS NOT RATIONED - the free allowance exists to meter strangers, and the person
        # who pays for the model is not one. The BUSY lock still applies to them, because that one stops
        # two answers being generated for the same person at once and is not a limit on anybody.
        if unlimited:
            store.take_busy_slot(user_id)
        else:
            store.reserve_turn(user_id, bucket_key, ip_key)  # QuotaExhausted / Busy: before any AI work
        try:
            session = _fresh(session)
            reply, kind, meta = _ask_ai(session, text, language, client or get_chat_client(),
                                        first_reply=first_reply)
            quota = store.record_exchange(session_id, user_id, bucket_key, ip_key, text, reply, kind, meta,
                                          charge=not unlimited)
            _count_question(meta, language, account_id, unlimited, kind)
        except BaseException:
            store.release_turn(user_id)  # nothing delivered: nothing spent, slot freed
            raise
    return {
        "reply": {"role": "assistant", "content": reply, "kind": kind},
        "language": language,
        "quota": quota,
        "paywall": _paywall_for(quota, user_id, language, unlimited),
    }


def _settle_style(session: dict, text: str) -> tuple[str, bool]:
    """(the style to answer in, whether this is the conversation's first reply).

    A chat from before this column has no style; it is settled now, from the message in hand, so an old
    conversation simply locks to whatever it has been speaking rather than starting to drift.
    """
    session_id = session["session_id"]
    already = (session.get("style") or "").strip()

    # WHAT COUNTS AS THE FIRST MESSAGE. Every conversation that existed before this column has no style,
    # and settling it from the message in hand would be exactly wrong for the chat this was built for:
    # Meera's was four Devanagari turns old and her next message was romanised, so "settle from what
    # they just typed" would have locked her Devanagari chat to Latin letters. The style of an existing
    # conversation is the style it has been speaking - its FIRST user message - and the one in hand only
    # decides it when there is no history at all.
    earlier = [m["content"] for m in store.get_messages(session_id) if m["role"] == "user"]
    first_reply = not earlier

    if not already:
        style = chat_style.settle(earlier[0] if earlier else text, default=session["language"])
    else:
        style = already
    if earlier:
        # An explicit request is honoured whether or not a style was stored - including on the very turn
        # an old conversation is being settled, so "reply in English" is never swallowed by the migration.
        asked = chat_style.requested_style(text, current=style)
        if asked and asked != style:
            log.info("chat %s: style changed on request, %s -> %s", session_id[:8], style, asked)
            style = asked

    if style != already:
        store.set_style(session_id, style)
        session["style"] = style
    if style != session["language"]:
        store.set_session_language(session_id, style)
        session["language"] = style
    return style, first_reply


def _ask_ai(session: dict, text: str, language: str, client: ChatLLMClient,
            *, first_reply: bool = False) -> tuple[str, str, dict]:
    history = _history(session["session_id"])
    facts = facts_from_json(session["facts"])
    for turn in history:
        if turn["role"] == "user":
            allow_mentions(facts, turn["content"])
    allow_mentions(facts, text)
    system = build_system(session["context"], language, first_reply=first_reply)

    usage_total, calls, note, model, repairs, refused = {}, 0, None, None, 0, False
    problems: list[str] = []
    for attempt in (1, 2):
        try:
            result = client.generate_chat(system=system, messages=build_messages(history, text, language, note))
        except AIBadOutput as exc:  # refusal / truncation: treat like a failed screen
            refused = True
            log.warning("chat %s attempt %d: %s", session["session_id"][:8], attempt, exc)
            if attempt == 2:
                break
            note = "Your previous reply could not be used. Answer again, briefly and within the rules."
            continue
        calls += 1
        model = result.model
        # B8: before anything reads it, and before it is stored. Unconditional rather than mr/hi only,
        # because ०-९ has no place in a romanised reply either - that is the one the person reads in Latin.
        reply_text = normalise_digits(result.text)
        for key, value in result.usage.items():
            usage_total[key] = usage_total.get(key, 0) + value

        # REPAIR BEFORE REJECTING. A word half in each script - 'chintित', 'dhैर्य', 'rashीत' - is a
        # spelling problem, and spelling is deterministic. Twelve answers in a week were regenerated twice
        # over this and then replaced by the fallback, which is a non-answer somebody paid for. The draft
        # is transliterated into the chat's own script and only then judged; a regeneration is for a draft
        # that is actually wrong, not one that is merely misspelt.
        repaired, was_repaired = chat_style.repair(reply_text, language)
        if was_repaired and not chat_style.script_problems(repaired, language):
            log.info("chat %s attempt %d: script repaired without a regeneration",
                     session["session_id"][:8], attempt)
            reply_text, repairs = repaired, repairs + 1

        problems = _problems(reply_text, facts)
        # SCRIPT IS A HARD CHECK, on both attempts. It used to be soft - "worth one regeneration, never
        # worth withholding the answer" - and that is precisely how "Kundalit sध्या Chandra mahadasha"
        # reached a paying customer: the second draft was delivered whether or not it was clean. A reply
        # in no script at all is not a worse answer, it is an unreadable one, and the fallback sentence is
        # better than unreadable.
        problems = problems or chat_style.script_problems(reply_text, language)
        if not problems and attempt == 1:
            problems = _soft_problems(reply_text, language, facts)  # soft: the 2nd draft is delivered either way
        if not problems:
            meta = {"language": language, "model": model, "calls": calls, "usage": usage_total,
                    "cost_usd": estimate_cost_usd(model, usage_total), "request_id": result.request_id,
                    "repairs": repairs}
            return reply_text, "ai", meta
        log.warning("chat %s attempt %d rejected: %s", session["session_id"][:8], attempt, problems)
        note = ("Your previous reply was rejected: " + "; ".join(problems[:5]) + ". Write the reply again. Copy facts "
                "from the data or leave them out, and do not use frightening words. Write the WHOLE reply in "
                f"{chat_style.name(language)} - every word in one script, and no word mixing two.")
    # WHICH NON-ANSWER TO GIVE. If the model declined because of what was ASKED - how long somebody will
    # live, whether they have cancer - then "I couldn't put together a reliable answer" is the wrong thing
    # to say: it reads as a malfunction when it was a decision, and it tells the reader nothing about what
    # we will help with. The subject gets its own explanation, in the chat's own language.
    topic = topic_for_refusal(text) if refused else None
    if topic:
        log.info("chat %s: refused on topic %s, answering with its explanation",
                 session["session_id"][:8], topic)
        meta = {"language": language, "model": model, "calls": calls, "usage": usage_total,
                "cost_usd": estimate_cost_usd(model, usage_total), "screen": topic, "refused_topic": topic}
        return canned_reply(topic, language), "safe", meta

    # The attempts were paid for whether or not the reader got an answer out of them. A fallback recorded
    # at zero is the same mistake as a question recorded at zero, one branch along.
    meta = {"language": language, "model": model, "calls": calls, "usage": usage_total, "screen": "output",
            "cost_usd": estimate_cost_usd(model, usage_total), "repairs": repairs, "problems": problems[:3]}
    return canned_reply("fallback", language), "fallback", meta


__all__ = ["AIError", "LANGUAGES", "MAX_MESSAGE_CHARS", "SessionNotFound", "get_chat_client", "load_session",
           "paywall", "send_message", "session_view", "start_session"]
