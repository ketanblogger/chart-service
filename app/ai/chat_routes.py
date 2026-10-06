"""Consultation chat API (Phase 5). Shapes are documented in docs/API.md -> "AI consultation chat"."""

import json
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api import BirthDetails

from app.ai import chat_style
from app.web import accounts, site

from . import chat, chat_identity as identity, chat_store as store
from .client import AIBadOutput, AIError, AINotConfigured

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/consultation")

STARTS_PER_HOUR = 12  # per IP bucket; a start costs engine CPU only, but it should not be a free DoS either


class StartRequest(BirthDetails):
    # WHO THIS CHAT IS ABOUT. "me", or a free-text label the reader chose - wife, friend, Aai. It is a
    # label on a conversation, never anything the astrologer is told about a relationship.
    subject: str | None = Field(default=None, max_length=40)
    """Birth details exactly as POST /api/chart, plus optional display name and preferred language."""

    name: str | None = Field(default=None, max_length=60)
    language: Literal["en", "hi", "mr"] = "en"


class MessageRequest(BaseModel):
    session_id: str = Field(min_length=10, max_length=80)
    message: str = Field(min_length=1, max_length=4000)  # the real limit (1000) gives a friendlier error below


def _rate_limited(exc: store.RateLimited) -> HTTPException:
    return HTTPException(status_code=429, headers={"Retry-After": str(exc.retry_after)},
                         detail={"code": "rate_limited", "retry_after": exc.retry_after,
                                 "message": "You are sending messages very quickly. Please wait a moment and try again."})


def _identify(request: Request, response: Response, session: dict | None = None) -> str:
    """Who this request is, for the quota tables.

    SIGNED IN: the ACCOUNT, derived from the verified address. This one line is what makes the free allowance
    follow the person rather than the browser - `chat_users.user_id` is already the single key for
    `free_used`, `paid_balance` and the busy lock, so handing it an account id makes all three account-scoped
    without a word of the quota logic changing, and a second incognito window is the same two answers.

    NOT SIGNED IN: the previous behaviour exactly, which is what `CHAT_LOGIN=off` rolls back to.
    """
    email = accounts.session_email(request) if site.CHAT_LOGIN else None
    if email:
        identity.set_user_cookie(response, identity.user_id_from_request(request) or identity.new_user_id())
        return accounts.account_id(email)
    user_id = identity.user_id_from_request(request)
    if session is not None and user_id != session["user_id"]:
        user_id = session["user_id"]
    user_id = user_id or identity.new_user_id()
    identity.set_user_cookie(response, user_id)
    return user_id


def _require_login(request: Request) -> None:
    """401 unless this request carries a verified address. Only the AI astrologer asks for this.

    The body carries `login_required` so the chat page can show its sign-in form in place of the composer
    rather than guessing what a 401 meant."""
    if site.CHAT_LOGIN and not accounts.session_email(request):
        raise HTTPException(status_code=401, detail={"login_required": True, "login_path": "/login"})


@router.post("/start")
def start(body: StartRequest, request: Request, response: Response) -> dict:
    _require_login(request)
    ip_key = identity.ip_bucket(identity.client_ip(request))
    try:
        store.check_rate(f"start:ip:{ip_key}", STARTS_PER_HOUR, 3600)
    except store.RateLimited as exc:
        raise _rate_limited(exc) from exc
    user_id = _identify(request, response)
    birth = {"date": body.date.isoformat(), "time": body.time.isoformat(timespec="seconds"), "lat": body.lat,
             "lon": body.lon, "timezone": body.timezone, "city": body.city}
    bucket_key = identity.birth_bucket(birth["date"], birth["time"], body.lat, body.lon, ip_key)
    name = " ".join((body.name or "").split())[:60] or None  # display only - never sent to the model
    try:
        # THE CAP, checked before anything is built. Fifty conversations is past the point where a list
        # is usable, and an account that has hit it has almost certainly stopped meaning to open new ones.
        if store.count_chats(user_id, include_archived=True) >= store.MAX_CHATS_PER_ACCOUNT:
            raise HTTPException(status_code=409, detail={
                "code": "too_many_chats",
                "message": f"You have {store.MAX_CHATS_PER_ACCOUNT} conversations. Delete or archive one "
                           f"to start another - nothing is lost by archiving."})
        started = chat.start_session(user_id, bucket_key, ip_key, birth, name, body.language)
        if body.subject:
            store.set_subject(started["session_id"], user_id, body.subject)
            started["subject"] = body.subject
        return started
    except ValueError as exc:  # bad timezone string etc. from the engine
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _page_language(request: Request) -> str:
    """Which of the three trees this request came from, for labelling only."""
    path = request.url.path or ""
    if path.startswith("/hi/") or path.startswith("/hi"):
        return "hi"
    if path.startswith("/mr/") or path.startswith("/mr"):
        return "mr"
    referer = request.headers.get("referer") or ""
    for code in ("hi", "mr"):
        if f"/{code}/" in referer:
            return code
    return "en"


_RASHI_SLUG = {
    "Aries": "mesha", "Taurus": "vrishabha", "Gemini": "mithuna", "Cancer": "karka", "Leo": "simha",
    "Virgo": "kanya", "Libra": "tula", "Scorpio": "vrishchika", "Sagittarius": "dhanu",
    "Capricorn": "makara", "Aquarius": "kumbha", "Pisces": "meena",
}


def _rashi_of(summary_json: str | None) -> dict:
    """The rashi for one sidebar row, or empty when the chart cannot be read.

    A chat with no readable rashi simply shows its title: a missing glyph is nothing, and a WRONG one
    beside somebody's name would be worse than none.
    """
    try:
        sign = ((json.loads(summary_json or "{}") or {}).get("moon_rashi")) or {}
        key = sign.get("key")
        if not key:
            return {}
        if key not in _RASHI_SLUG:
            return {}
        # BOTH SPELLINGS. The sidebar is drawn in the browser, which knows which page it is on, so the
        # English page can read "Kanya" where the Hindi and Marathi ones read "कन्या" - rather than
        # Devanagari on every page because this function happened to prefer it.
        return {"rashi": sign.get("name") or key,
                "rashi_deva": sign.get("devanagari") or sign.get("name") or key,
                "rashi_glyph": "r-" + _RASHI_SLUG[key]}
    except Exception:  # noqa: BLE001 - a sidebar must not fail over an ornament
        return {}


@router.get("/mine")
def my_consultations(request: Request, response: Response) -> dict:
    """The signed-in reader's own consultations, newest first.

    THIS IS WHAT MAKES THE CHAT FOLLOW THE ACCOUNT. The browser keeps its session id in sessionStorage,
    which is per-tab and empty in a new window - so signing in somewhere else, or opening a second tab,
    showed an empty astrologer and offered a fresh start. The sessions were keyed to the account all along;
    there was simply nothing that asked for them.

    Only ever the caller's own: the user id is derived from the request here, exactly as everywhere else,
    and never read from the query.
    """
    _require_login(request)
    user_id = _identify(request, response)
    include_archived = request.query_params.get("archived") == "1"
    return {"sessions": [
        {"session_id": row["session_id"], "name": row["name"], "language": row["language"],
         "created_at": row["created_at"], "messages": row["messages"],
         # What the sidebar shows: a title taken from the first question, and WHO the chat is about -
         # every person has a different chart, so a chat is about one of them and says which.
         "title": row["title"] or row["name"] or "",
         "subject": row["subject"] or "",
         # The style this chat is written in, and the words for it: the person can see what the answers
         # will be in, and click to change it, instead of discovering it from a reply.
         "style": row["style"] or "",
         "style_label": chat_style.label(row["style"] or row["language"], _page_language(request)),
         # The person's own rashi, so the sidebar can show "Samprita - Dhanu" with its glyph. Read from
         # the stored summary rather than recomputed: it is the same chart the conversation was built on.
         **_rashi_of(row.get("summary_json")),
         "archived": bool(row["archived"]),
         "last_at": row["last_at"] or row["created_at"]}
        for row in store.chats_for_user(user_id, include_archived=include_archived)],
        "limit": store.MAX_CHATS_PER_ACCOUNT}


class ChatEdit(BaseModel):
    # The id travels in the BODY rather than as a path suffix. A suffix means the browser has to build
    # `.../{id}/edit`, and a bare "/edit" in a script is a page path as far as the check that forbids them
    # is concerned - a rule worth keeping, so the endpoint moved rather than the rule.
    session_id: str = Field(min_length=10, max_length=80)
    title: str | None = Field(default=None, max_length=80)
    archived: bool | None = None
    style: str | None = Field(default=None, max_length=10)


@router.post("/edit")
def edit_chat(body: ChatEdit, request: Request, response: Response) -> dict:
    """Rename a chat, or put it away. Scoped to the owner: an id alone edits nobody else's."""
    _require_login(request)
    user_id = _identify(request, response)
    done = False
    if body.title is not None:
        done = store.set_title(body.session_id, user_id, body.title) or done
    if body.archived is not None:
        done = store.set_archived(body.session_id, user_id, body.archived) or done
    if body.style is not None:
        # Changing the style from the page is the same act as asking for it in the conversation, so it
        # goes through the same door: one of the five, on a chat that belongs to this person.
        if body.style not in chat_style.LANGUAGES:
            raise HTTPException(status_code=400, detail={"code": "bad_style",
                                                         "message": "That is not a language we write in."})
        done = store.set_style_for_owner(body.session_id, user_id, body.style) or done
    if not done:
        raise HTTPException(status_code=404, detail={"code": "not_found",
                                                     "message": "That conversation is not yours."})
    return {"ok": True}


@router.delete("/session/{session_id}")
def delete_chat(session_id: str, request: Request, response: Response) -> dict:
    """Delete a conversation AND its messages. Not a flag - gone means gone."""
    _require_login(request)
    user_id = _identify(request, response)
    if not store.delete_chat(session_id, user_id):
        raise HTTPException(status_code=404, detail={"code": "not_found",
                                                     "message": "That conversation is not yours."})
    return {"ok": True, "deleted": session_id}


@router.get("/session/{session_id}")
def get_session(session_id: str, request: Request, response: Response) -> dict:
    try:
        session = chat.load_session(session_id)
    except chat.SessionNotFound:
        raise HTTPException(status_code=404, detail={"code": "session_not_found", "message": "This consultation has expired. Please start again."})
    _identify(request, response, session)
    return chat.session_view(session)


@router.post("/message")
def message(body: MessageRequest, request: Request, response: Response) -> dict:
    _require_login(request)
    try:
        session = chat.load_session(body.session_id)
    except chat.SessionNotFound:
        raise HTTPException(status_code=404, detail={"code": "session_not_found", "message": "This consultation has expired. Please start again."})
    _identify(request, response, session)
    try:
        email = accounts.session_email(request) if site.CHAT_LOGIN else None
        return chat.send_message(body.session_id, body.message,
                                 unlimited=accounts.is_admin(email),
                                 account_id=accounts.account_id(email) if email else "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "bad_message", "message": str(exc)}) from exc
    except store.RateLimited as exc:
        raise _rate_limited(exc) from exc
    except store.QuotaExhausted:
        # The paywall. Raised before any AI work. Phase 6 credits a pack with chat_store.credit_session().
        raise HTTPException(status_code=402, detail={**chat.paywall(), "session_id": body.session_id,
                                                     "message": "Your free messages are used. Get 10 more messages to continue."})
    except store.Busy:
        raise HTTPException(status_code=409, detail={"code": "busy", "message": "Your previous question is still being answered."})
    except AIError as exc:
        log.error("consultation reply failed: %s", exc)
        code = "ai_not_configured" if isinstance(exc, AINotConfigured) else "ai_unavailable"
        raise HTTPException(status_code=502 if isinstance(exc, AIBadOutput) else 503,
                            detail={"code": code, "message": "The astrologer is unavailable right now. Please try again in a "
                                                             "few minutes - this message was not counted."}) from exc
