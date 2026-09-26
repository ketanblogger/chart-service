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
from .chat_safety import LANGUAGES, canned_reply, detect_language, screen_input
from .client import AIBadOutput, AIError, ChatLLMClient, ClaudeClient
from .config import estimate_cost_usd, get_chat_settings
from .report import today_ist
from .safety import screen_text
from .validator import REDACT_KINDS, allow_mentions, check_text, collect_facts, facts_from_json, facts_to_json

log = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 1000
PRODUCT = "consultation-pack"


class SessionNotFound(Exception):
    pass


def get_chat_client() -> ChatLLMClient:
    """The one place the chat gets its AI client. Tests and scripts/browser_check_consultation.py replace it."""
    return ClaudeClient()


def paywall() -> dict:
    settings = get_chat_settings()
    return {"code": "payment_required", "product": PRODUCT, "price_inr": settings.pack_price_inr,
            "messages": settings.pack_messages}


# ---- sessions --------------------------------------------------------------------------------------


def _session_data(birth: dict, as_of: dt.date) -> tuple[dict, dict, dict]:
    data = build_engine_data(birth, as_of)
    return build_context(data, as_of), build_summary(data["chart"], as_of), facts_to_json(collect_facts(data))


def start_session(user_id: str, bucket_key: str, ip_key: str, birth: dict, name: str | None, language: str) -> dict:
    """Builds the chart once (as_of pinned to today, IST) and opens a session."""
    as_of = today_ist()
    context, summary, facts = _session_data(birth, as_of)
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
        "paywall": paywall() if quota["messages_left"] <= 0 else None,
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
    if language.endswith("-Latn") and _DEVANAGARI.search(reply):
        found.append("the person writes in Latin letters, so reply in Latin letters only - remove every Devanagari character")
    return found


def send_message(session_id: str, text: str, *, client: ChatLLMClient | None = None) -> dict:
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

    language = detect_language(text, default=session["language"])
    if language != session["language"]:
        store.set_session_language(session_id, language)

    category = screen_input(text)
    if category:
        # Fixed reply: no AI call, no quota needed (a distressed person at the paywall still gets the helpline).
        reply, kind = canned_reply(category, language), "safe"
        quota = store.record_exchange(session_id, user_id, bucket_key, ip_key, text, reply, kind,
                                      {"language": language, "screen": category})
    else:
        store.reserve_turn(user_id, bucket_key, ip_key)  # QuotaExhausted / Busy: raised before any AI work
        try:
            session = _fresh(session)
            reply, kind, meta = _ask_ai(session, text, language, client or get_chat_client())
            quota = store.record_exchange(session_id, user_id, bucket_key, ip_key, text, reply, kind, meta)
        except BaseException:
            store.release_turn(user_id)  # nothing delivered: nothing spent, slot freed
            raise
    return {
        "reply": {"role": "assistant", "content": reply, "kind": kind},
        "language": language,
        "quota": quota,
        "paywall": paywall() if quota["messages_left"] <= 0 else None,
    }


def _ask_ai(session: dict, text: str, language: str, client: ChatLLMClient) -> tuple[str, str, dict]:
    history = _history(session["session_id"])
    facts = facts_from_json(session["facts"])
    for turn in history:
        if turn["role"] == "user":
            allow_mentions(facts, turn["content"])
    allow_mentions(facts, text)
    system = build_system(session["context"])

    usage_total, calls, note, model = {}, 0, None, None
    for attempt in (1, 2):
        try:
            result = client.generate_chat(system=system, messages=build_messages(history, text, language, note))
        except AIBadOutput as exc:  # refusal / truncation: treat like a failed screen
            log.warning("chat %s attempt %d: %s", session["session_id"][:8], attempt, exc)
            if attempt == 2:
                break
            note = "Your previous reply could not be used. Answer again, briefly and within the rules."
            continue
        calls += 1
        model = result.model
        for key, value in result.usage.items():
            usage_total[key] = usage_total.get(key, 0) + value
        problems = _problems(result.text, facts)
        if not problems and attempt == 1:
            problems = _soft_problems(result.text, language, facts)  # soft: the 2nd draft is delivered either way
        if not problems:
            meta = {"language": language, "model": model, "calls": calls, "usage": usage_total,
                    "cost_usd": estimate_cost_usd(model, usage_total), "request_id": result.request_id}
            return result.text, "ai", meta
        log.warning("chat %s attempt %d rejected: %s", session["session_id"][:8], attempt, problems)
        note = ("Your previous reply was rejected: " + "; ".join(problems[:5]) + ". Write the reply again. Copy facts "
                "from the data or leave them out, and do not use frightening words.")
    meta = {"language": language, "model": model, "calls": calls, "usage": usage_total, "screen": "output"}
    return canned_reply("fallback", language), "fallback", meta


__all__ = ["AIError", "LANGUAGES", "MAX_MESSAGE_CHARS", "SessionNotFound", "get_chat_client", "load_session",
           "paywall", "send_message", "session_view", "start_session"]
