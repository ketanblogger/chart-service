"""Thin wrapper over the Anthropic SDK: one call in, schema-valid JSON + token usage out.

The rest of app/ai talks to the `LLMClient` protocol, never to the SDK, so tests inject a fake
and no test touches the network.
"""

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Protocol

from .config import Settings, get_settings, has_credentials

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"  # gates `fallbacks: "default"`
_FALLBACK_MODELS = ("claude-opus-5", "claude-fable-5")


class AIError(Exception):
    """Base class. `public_message` is safe to show to a customer; str(exc) is for logs."""

    public_message = "The report service is temporarily unavailable. Please try again in a few minutes."


class AINotConfigured(AIError):
    public_message = "The report service is not configured yet. Please try again later."


class AIUnavailable(AIError):
    """Network / rate limit / 5xx after the SDK's own retries."""


class AIBadOutput(AIError):
    """Refusal, truncated output, or JSON that does not fit the schema."""

    public_message = "We could not prepare this report right now. Please try again; you will not be charged twice."


@dataclass
class LLMResult:
    data: dict
    model: str
    stop_reason: str | None = None
    usage: dict = field(default_factory=dict)
    request_id: str | None = None


@dataclass
class ChatResult:
    text: str
    model: str
    stop_reason: str | None = None
    usage: dict = field(default_factory=dict)
    request_id: str | None = None


class LLMClient(Protocol):
    def generate_json(self, *, system, user: str, schema: dict) -> LLMResult: ...


class ChatLLMClient(Protocol):
    def generate_chat(self, *, system: list[dict], messages: list[dict]) -> ChatResult: ...


def _usage_dict(usage) -> dict:
    keys = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    return {key: int(getattr(usage, key, 0) or 0) for key in keys}


class ClaudeClient:
    """Real client. Streams (long outputs), uses structured outputs, adaptive thinking and prompt caching."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        if not has_credentials():
            raise AINotConfigured(
                "ANTHROPIC_API_KEY is not set. Put it in the project's .env (see .env.example)."
            )
        import anthropic  # imported here so the app and tests start without touching the SDK

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(
            timeout=self.settings.timeout_seconds, max_retries=self.settings.api_retries
        )

    def _request(self, system, user: str, schema: dict) -> dict:
        s = self.settings
        request = {
            "model": s.model,
            "max_tokens": s.max_tokens,
            # A plain string is the whole cached prefix (one frozen prompt shared by every report).
            # A list is passed through as given: the flagship book sends two blocks - the frozen prompt,
            # which caches across customers, and this chart's data, which caches across its ~10 calls.
            "system": ([{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
                       if isinstance(system, str) else list(system)),
            "messages": [{"role": "user", "content": user}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        if not s.model.startswith("claude-haiku"):  # Haiku 4.5 has neither adaptive thinking nor effort
            request["thinking"] = {"type": "adaptive"}
            request["output_config"]["effort"] = s.effort
        return request

    def _stream(self, request: dict, use_fallbacks: bool):
        if use_fallbacks:
            manager = self._client.beta.messages.stream(**request, betas=[FALLBACK_BETA], fallbacks="default")
        else:
            manager = self._client.messages.stream(**request)
        with manager as stream:
            return stream.get_final_message()

    @contextmanager
    def _api_errors(self, model: str):
        """SDK errors become AIError subclasses (most specific first)."""
        anthropic = self._anthropic
        try:
            yield
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise AINotConfigured(f"Claude API rejected the credentials: {exc}") from exc
        except anthropic.NotFoundError as exc:
            raise AINotConfigured(f"Unknown model {model!r} (check REPORT_MODEL / CHAT_MODEL / RASHIFAL_MODEL): {exc}") from exc
        except anthropic.BadRequestError as exc:
            raise AIBadOutput(f"Claude API rejected the request: {exc}") from exc
        except anthropic.RateLimitError as exc:
            raise AIUnavailable(f"Claude API rate limit: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise AIUnavailable(f"Claude API error {exc.status_code}: {exc}") from exc
        except anthropic.APIConnectionError as exc:  # includes APITimeoutError
            raise AIUnavailable(f"Could not reach the Claude API: {exc}") from exc

    @staticmethod
    def _check_stop(message, max_tokens) -> None:
        request_id = getattr(message, "_request_id", None)
        if message.stop_reason == "refusal":
            raise AIBadOutput(f"model refused (request {request_id})")
        if message.stop_reason == "max_tokens":
            raise AIBadOutput(f"output hit max_tokens={max_tokens} (request {request_id})")

    def _send(self, request: dict):
        """Stream one request and return the final message. SDK errors become AIError subclasses."""
        anthropic = self._anthropic
        model = request["model"]
        use_fallbacks = self.settings.fallbacks == "default" and model.startswith(_FALLBACK_MODELS)
        with self._api_errors(model):
            try:
                message = self._stream(request, use_fallbacks)
            except anthropic.BadRequestError as exc:
                # The fallback parameter is beta; if this account/model rejects it, go without it.
                if not (use_fallbacks and "fallback" in str(exc).lower()):
                    raise
                log.warning("fallbacks rejected (%s); retrying without", exc)
                message = self._stream(request, False)
        self._check_stop(message, request["max_tokens"])
        return message

    @staticmethod
    def _text(message) -> str:
        text = "".join(block.text for block in message.content if block.type == "text").strip()
        if not text:
            raise AIBadOutput(f"no text in response (request {getattr(message, '_request_id', None)})")
        return text

    def _json_result(self, message) -> LLMResult:
        request_id = getattr(message, "_request_id", None)
        text = self._text(message)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIBadOutput(f"response is not valid JSON (request {request_id}): {exc}") from exc
        return LLMResult(
            data=data,
            model=message.model,
            stop_reason=message.stop_reason,
            usage=_usage_dict(message.usage),
            request_id=request_id,
        )

    def generate_json(self, *, system, user: str, schema: dict) -> LLMResult:
        """`system` is either the whole frozen prompt as a string, or a ready list of system blocks
        that already carry their own `cache_control` marks."""
        return self._json_result(self._send(self._request(system, user, schema)))

    def generate_json_batch(self, requests: list[dict], *, poll_seconds: float = 30.0,
                            timeout_seconds: float = 3 * 3600, on_poll=None) -> dict:
        """Many `generate_json` calls through the Message Batches API: asynchronous, 50% of the token price.

        `requests` is [{"custom_id", "system", "user", "schema"}]; returns {custom_id: LLMResult | AIError} -
        one failed item never fails the others. Blocks (polling) until the batch ends; after
        `timeout_seconds` the batch is cancelled and whatever did not finish comes back as AIUnavailable.
        `on_poll()` is called on every poll (the rashifal job renews its lease there). Not streamed, and
        without the server-side `fallbacks` parameter, which the Batches API rejects.
        """
        import time

        from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
        from anthropic.types.messages.batch_create_params import Request

        if not requests:
            return {}
        model, max_tokens = self.settings.model, self.settings.max_tokens
        batches = self._client.messages.batches
        with self._api_errors(model):
            batch = batches.create(requests=[
                Request(custom_id=item["custom_id"],
                        params=MessageCreateParamsNonStreaming(**self._request(item["system"], item["user"], item["schema"])))
                for item in requests
            ])
            log.info("batch %s created with %d requests", batch.id, len(requests))
            deadline, cancelled = time.monotonic() + timeout_seconds, False
            while batch.processing_status != "ended":
                if on_poll:
                    on_poll()
                if not cancelled and time.monotonic() > deadline:
                    log.warning("batch %s not finished after %.0fs; cancelling", batch.id, timeout_seconds)
                    batches.cancel(batch.id)
                    cancelled, deadline = True, time.monotonic() + 600  # cancellation itself takes a moment
                elif cancelled and time.monotonic() > deadline:
                    raise AIUnavailable(f"batch {batch.id} did not end after being cancelled")
                time.sleep(poll_seconds)
                batch = batches.retrieve(batch.id)

            results: dict = {}
            for entry in batches.results(batch.id):  # any order: key by custom_id
                outcome = entry.result
                try:
                    if outcome.type == "succeeded":
                        self._check_stop(outcome.message, max_tokens)
                        results[entry.custom_id] = self._json_result(outcome.message)
                    elif outcome.type == "errored":
                        error = getattr(outcome.error, "error", outcome.error)
                        kind = AIBadOutput if getattr(error, "type", "") == "invalid_request_error" else AIUnavailable
                        results[entry.custom_id] = kind(f"batch item failed: {getattr(error, 'message', error)}")
                    else:  # canceled | expired
                        results[entry.custom_id] = AIUnavailable(f"batch item {outcome.type}")
                except AIError as exc:
                    results[entry.custom_id] = exc
        for item in requests:
            results.setdefault(item["custom_id"], AIUnavailable("batch returned no result for this item"))
        return results

    def generate_chat(self, *, system: list[dict], messages: list[dict]) -> ChatResult:
        """One consultation-chat turn. `system` and `messages` arrive with their cache_control marks
        (see app/ai/chat_prompts.py); plain-text reply, no structured output."""
        from .config import get_chat_settings

        chat = get_chat_settings()
        request = {"model": chat.model, "max_tokens": chat.max_tokens, "system": system, "messages": messages}
        if not chat.model.startswith("claude-haiku"):  # Haiku 4.5 has neither adaptive thinking nor effort
            request["thinking"] = {"type": "adaptive"}
            request["output_config"] = {"effort": chat.effort}
        message = self._send(request)
        return ChatResult(
            text=self._text(message),
            model=message.model,
            stop_reason=message.stop_reason,
            usage=_usage_dict(message.usage),
            request_id=getattr(message, "_request_id", None),
        )
