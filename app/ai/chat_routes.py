"""Consultation chat API (Phase 5). Shapes are documented in docs/API.md -> "AI consultation chat"."""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api import BirthDetails

from . import chat, chat_identity as identity, chat_store as store
from .client import AIBadOutput, AIError, AINotConfigured

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/consultation")

STARTS_PER_HOUR = 12  # per IP bucket; a start costs engine CPU only, but it should not be a free DoS either


class StartRequest(BirthDetails):
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
    """User id from the signed cookie; else (cookies blocked/cleared) the owner of a valid session id, which is
    an unguessable bearer token; else a new user. Always (re)sets the cookie."""
    user_id = identity.user_id_from_request(request)
    if session is not None and user_id != session["user_id"]:
        user_id = session["user_id"]
    user_id = user_id or identity.new_user_id()
    identity.set_user_cookie(response, user_id)
    return user_id


@router.post("/start")
def start(body: StartRequest, request: Request, response: Response) -> dict:
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
        return chat.start_session(user_id, bucket_key, ip_key, birth, name, body.language)
    except ValueError as exc:  # bad timezone string etc. from the engine
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
    try:
        session = chat.load_session(body.session_id)
    except chat.SessionNotFound:
        raise HTTPException(status_code=404, detail={"code": "session_not_found", "message": "This consultation has expired. Please start again."})
    _identify(request, response, session)
    try:
        return chat.send_message(body.session_id, body.message)
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
