"""The refresh job: transit brief -> Claude -> checks -> store. One AI call per (rashi, period) page,
returning every configured language at once.

Rules:
- The AI sees only the engine brief; its output is checked for structure, safety (app/ai/safety.py) and
  facts (app/ai/validator.py) in every language. A failed page is regenerated once with the checker's
  feedback. After the last attempt, a language that still has a blocking problem is NOT published; if no
  language is clean the page fails and the stored content for that URL stays exactly as it was.
- Idempotent: a page whose stored content already covers the current window (same window start, all
  configured languages) is skipped unless `force`. A page that is current but lacks a language (it failed its
  checks last time) gets a job for the missing languages only, merged into the stored page - the clean
  languages stay published and are not paid for again. A page is "complete" only with every configured language.
- One failing page never stops the others. `RefreshSummary.ok` is False if any page failed.
- Work runs in rounds (all first attempts, then all retries) so the same code drives plain calls
  (a small thread pool) and the Message Batches API (one batch per round, 50% cheaper). Batching is used for
  rounds of BATCH_MIN_JOBS or more; a single page (`--rashi dhanu --period today`) is called directly.
"""

import dataclasses
import datetime as dt
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from app.ai.client import AIError, AINotConfigured, ClaudeClient, LLMResult
from app.ai.config import estimate_cost_usd, get_settings
from app.ai.safety import screen_text
from app.ai.language import language_problems, names_a_house, normalise_digits
from app.ai.validator import REDACT_KINDS, Facts, check_text, collect_facts

from . import store
from .brief import brief_hash, build_brief
from .config import RashifalSettings, client_settings, get_rashifal_settings
from .periods import PERIOD_SLUGS, RASHI_SLUGS, Window, to_ist, window_for
from .prompts import SECTION_IDS, SYSTEM_PROMPT, build_user_prompt, rashifal_schema

log = logging.getLogger(__name__)

LEASE_NAME = "rashifal-refresh"
LEASE_TTL_SECONDS = 30 * 60  # renewed after every page / batch poll
MAX_KEY_DATES = 8
BATCH_MIN_JOBS = 4
MAX_SUMMARY_WORDS = 70
# Floor on the WRITTEN reading only - `_word_count` counts the overview and the section paragraphs, never
# the engine blocks, which are most of what a long page renders. The floor used to be about 40% of what
# the prompt asked for (180 against "420-520"), so a reading could come back less than half the intended
# length and pass. These sit just under each period's requested range: high enough that a thin draft is
# caught, low enough that a draft inside the range is never rejected for a word or two.
_MIN_WORDS = {"today": 60, "weekly": 120, "monthly": 160, "6-months": 580, "yearly": 700}


def min_words(period: str, language: str) -> int:
    """The floor for ONE language. English-referenced, scaled by prompts.LANGUAGE_WORD_SCALE.

    A single floor across all three languages is not a single standard. Measured on 60 stored pages
    holding all three languages written from the same brief, Marathi runs 0.51 of English's word count
    and Hindi 0.78 for the same facts - Marathi compounds what Hindi writes separately. A 580-word floor
    therefore passed English, squeezed Hindi and failed Marathi TWICE on the 6-month test run of
    2026-09-27, which kept the previous content and would have repeated across all 12 rashis on 1
    October. The floors below are the same standard expressed in each language.
    """
    from .prompts import LANGUAGE_WORD_SCALE

    return round(_MIN_WORDS[period] * LANGUAGE_WORD_SCALE.get(language, 1.0))
# today / weekly / monthly are left where they were: the same gap exists there (monthly asks for
# 340-420 and floors at 160) but those pages regenerate daily, weekly and monthly, so raising their
# floor buys depth on the cheap pages at the price of retries on the frequent ones. Decide separately.
_USAGE_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")

# The script and vocabulary checks moved to app/ai/language.py on 2026-09-29 so the PAID BOOK could use
# them too: they had run on the free rashifal and on nothing else, which is how a Rs 299 Marathi book came
# to ship राहु, शनि and "पंचम भावात" - words this page would have rejected outright.


class RefreshBusy(Exception):
    """Another process holds the refresh lease."""


@dataclass
class PageOutcome:
    rashi: str
    period: str
    status: str  # generated | partial | skipped | failed
    detail: str = ""
    languages: tuple[str, ...] = ()
    attempts: int = 0
    cost_usd: float | None = None


@dataclass
class RefreshSummary:
    outcomes: list[PageOutcome] = field(default_factory=list)
    rejections: list[dict] = field(default_factory=list)  # {rashi, period, attempt, language, message}: every failed check
    usage: dict = field(default_factory=dict)  # token totals over every call of the run, rejected drafts included
    calls: int = 0
    batches: int = 0
    run_id: str = ""

    def count(self, status: str) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status == status)

    @property
    def ok(self) -> bool:
        return self.count("failed") == 0

    @property
    def cost_usd(self) -> float:
        return round(sum(outcome.cost_usd or 0 for outcome in self.outcomes), 4)


@dataclass
class _Job:
    rashi: str
    period: str
    window: Window
    brief: dict
    facts: Facts
    languages: tuple[str, ...] = ()
    merge: bool = False  # add to the stored page (same brief) instead of replacing it
    subset: bool = False  # a deliberate one-language run: top up whatever is stored, whichever run wrote it
    model: str = ""
    batched: bool = False
    feedback: list[str] | None = None
    calls: list[LLMResult] = field(default_factory=list)
    attempts: int = 0
    last_error: str = ""

    @property
    def custom_id(self) -> str:
        return f"{self.rashi}__{self.period}__{'-'.join(self.languages)}"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---- checks --------------------------------------------------------------------------------------


def _text_slots(page: dict):
    """(location, text) for every AI-written string of one language version."""
    yield "headline", page.get("headline", "")
    yield "summary", page.get("summary", "")
    yield "overview", page.get("overview", "")
    for section_id in SECTION_IDS:
        for n, text in enumerate((page.get("sections") or {}).get(section_id) or [], 1):
            yield f"{section_id} paragraph {n}", text
    for n, item in enumerate(page.get("key_dates") or [], 1):
        yield f"key_dates note {n}", item.get("note", "")
    yield "tip", page.get("tip", "")


def _word_count(page: dict) -> int:
    body = [page.get("overview", "")] + [p for s in SECTION_IDS for p in (page.get("sections") or {}).get(s) or []]
    return sum(len(text.split()) for text in body)


def structure_problems(page: dict, language: str, brief: dict) -> list[str]:
    """What the JSON schema cannot enforce, for one language version."""
    problems = []
    if not isinstance(page, dict):
        return ["missing"]
    if len((page.get("summary") or "").split()) > MAX_SUMMARY_WORDS:
        problems.append(f"summary is longer than {MAX_SUMMARY_WORDS} words")
    for key in ("headline", "summary", "overview", "tip"):
        if not (page.get(key) or "").strip():
            problems.append(f"{key} is empty")
    for section_id in SECTION_IDS:
        paragraphs = (page.get("sections") or {}).get(section_id) or []
        if not any((p or "").strip() for p in paragraphs):
            problems.append(f"section {section_id} has no text")
    minimum = min_words(brief["period"]["slug"], language)
    if _word_count(page) < minimum:
        problems.append(f"too short: under {minimum} words")
    known = {event["id"] for event in brief["events"]}
    unknown = [item.get("event_id") for item in page.get("key_dates") or [] if item.get("event_id") not in known]
    if unknown:
        problems.append(f"key_dates uses event ids that are not in the brief: {unknown}")

    text = " ".join(text for _, text in _text_slots(page))
    problems += language_problems(text, language)
    body = " ".join([page.get("overview") or ""] + [p or "" for s in SECTION_IDS for p in (page.get("sections") or {}).get(s) or []])
    if not names_a_house(body, language):
        problems.append("the reading names no house: build it on the placements and houses in the brief")
    return problems


def content_problems(page: dict, facts: Facts) -> tuple[list[str], list[str]]:
    """(blocking, warnings) for one language version: safety hits and fact mismatches."""
    blocking, warnings = [], []
    for where, text in _text_slots(page):
        for hit in screen_text(text):
            blocking.append(f"{where}: forbidden topic ({hit.category}): '{hit.term}'")
        for issue in check_text(text, facts):
            (blocking if issue.kind in REDACT_KINDS else warnings).append(f"{where}: {issue.message}")
    return blocking, warnings


def check_output(data: dict, languages: tuple[str, ...], brief: dict, facts: Facts) -> dict[str, dict]:
    """Per language: {"blocking": [...], "warnings": [...]}; blocking empty = publishable."""
    report = {}
    for code in languages:
        page = data.get(code) if isinstance(data, dict) else None
        structure = structure_problems(page, code, brief)
        blocking, warnings = content_problems(page, facts) if isinstance(page, dict) else ([], [])
        report[code] = {"blocking": structure + blocking, "warnings": warnings}
    return report


_LATIN_GLOSS = re.compile(r"\s*\((?:[A-Za-z][A-Za-z .,'/-]*)\)")  # "शनि (Shani)", "मकर (Capricorn / Makara)"


def _tidy(text: str, language: str) -> str:
    """Deterministic clean-up BEFORE the checks, for slips that are cheaper to fix than to regenerate."""
    text = (text or "").strip()
    if language in ("hi", "mr"):
        text = _LATIN_GLOSS.sub("", text)  # bracketed romanised names the prompt forbids; the Devanagari name stays
        text = normalise_digits(text)  # ०-९ -> 0-9 (B8): the prompt asks for Latin digits and does not always get them
    if language == "mr":  # Marathi ends sentences with a full stop; models trained on Hindi slip in the danda
        text = re.sub(r"\s*।", ".", text)
    return text


def tidy_output(data: dict, languages: tuple[str, ...]) -> dict:
    """`data` with every AI string of every language tidied; tolerant of missing / malformed parts (checked next)."""
    result = dict(data) if isinstance(data, dict) else {}
    for code in languages:
        page = result.get(code)
        if not isinstance(page, dict):
            continue
        page = dict(page)
        for key in ("headline", "summary", "overview", "tip"):
            if isinstance(page.get(key), str):
                page[key] = _tidy(page[key], code)
        if isinstance(page.get("sections"), dict):
            page["sections"] = {s: [_tidy(p, code) for p in paragraphs if isinstance(p, str)] if isinstance(paragraphs, list) else paragraphs
                                for s, paragraphs in page["sections"].items()}
        if isinstance(page.get("key_dates"), list):
            page["key_dates"] = [{**item, "note": _tidy(item.get("note"), code)} for item in page["key_dates"] if isinstance(item, dict)]
        result[code] = page
    return result


def _clean_page(page: dict, brief: dict, language: str = "en") -> dict:
    """The stored shape. key_dates keep only known, distinct events, in the brief's (time) order."""
    order = {event["id"]: n for n, event in enumerate(brief["events"])}
    seen, key_dates = set(), []
    for item in page.get("key_dates") or []:
        event_id, note = item.get("event_id"), (item.get("note") or "").strip()
        if event_id in order and event_id not in seen and note:
            seen.add(event_id)
            key_dates.append({"event_id": event_id, "note": note})
    key_dates.sort(key=lambda item: order[item["event_id"]])
    return {
        "headline": page["headline"].strip(),
        "summary": page["summary"].strip(),
        "overview": page["overview"].strip(),
        "sections": {s: [p.strip() for p in page["sections"][s] if (p or "").strip()] for s in SECTION_IDS},
        "key_dates": key_dates[:MAX_KEY_DATES],
        "tip": page["tip"].strip(),
    }


# ---- planning ------------------------------------------------------------------------------------


def is_current(stored: dict | None, window: Window, languages: tuple[str, ...]) -> bool:
    """True when the stored page already covers this window in every configured language."""
    return bool(stored) and stored["period_start"] == window.key and set(languages) <= set(stored["languages"])


def plan(periods: list[str], rashis: list[str], moment: dt.datetime, languages: tuple[str, ...],
         force: bool, split: bool = False,
         only: tuple[str, ...] | None = None) -> tuple[list[_Job], list[PageOutcome]]:
    """`languages` is what a complete page needs; `only` narrows what this run actually writes.

    The two are separate on purpose. Regenerating just the Marathi of every page must not re-pay for English
    and Hindi, and must not make the pages look incomplete either - a job whose languages are a subset saves
    with merge=True (see _publish), so the versions it does not write are left exactly as they are."""
    jobs, skipped = [], []
    stored = store.list_pages()
    for period in periods:
        window = window_for(period, moment)
        for rashi in rashis:
            row = stored.get((rashi, period))
            if not force and is_current(row, window, languages):
                skipped.append(PageOutcome(rashi, period, "skipped", f"already covers {window.key}"))
                continue
            brief = build_brief(rashi, period, moment)
            wanted, merge = languages, False
            if not force and row and row["period_start"] == window.key and row["brief_hash"] == brief_hash(brief):
                wanted, merge = tuple(code for code in languages if code not in row["languages"]), True  # fill the gaps only
            if only is not None:
                wanted = tuple(code for code in wanted if code in only)
                if not wanted:
                    skipped.append(PageOutcome(rashi, period, "skipped", f"nothing to write for {','.join(only)}"))
                    continue
                # Writing ONE language into a page whose other languages came from a different brief would leave
                # the versions disagreeing about the facts. Refuse rather than merge or clobber: the operator
                # wanted one language rewritten, and neither a mixed page nor a page stripped to one language is
                # what they asked for. A full run is the way to move a page onto a new brief.
                if row and row["brief_hash"] != brief_hash(brief):
                    skipped.append(PageOutcome(rashi, period, "skipped",
                                               "stored page was written from a different brief; regenerate every "
                                               "language instead of one"))
                    continue
            facts = collect_facts(brief)
            for group in ([(code,) for code in wanted] if split else [wanted]):
                jobs.append(_Job(rashi, period, window, brief, facts, languages=group, merge=merge,
                                 subset=only is not None))
    return jobs, skipped


class _Clients:
    """One ClaudeClient per model in use (a per-language model override means two). An injected client serves all."""

    def __init__(self, settings: RashifalSettings, injected=None):
        self.settings, self.injected, self._by_model = settings, injected, {}
        if injected is None:
            self.get(settings.model)  # raises AINotConfigured before any AI work

    def get(self, model: str):
        if self.injected is not None:
            return self.injected
        if model not in self._by_model:
            self._by_model[model] = ClaudeClient(client_settings(dataclasses.replace(self.settings, model=model)))
        return self._by_model[model]


# ---- running -------------------------------------------------------------------------------------


def _call_one(client, job: _Job):
    try:
        return client.generate_json(system=SYSTEM_PROMPT, user=build_user_prompt(job.brief, job.languages, job.feedback),
                                    schema=rashifal_schema(job.languages))
    except AIError as exc:
        return exc


def _run_batch(client, jobs: list[_Job], settings: RashifalSettings, on_progress) -> dict:
    requests = [{"custom_id": job.custom_id, "system": SYSTEM_PROMPT, "schema": rashifal_schema(job.languages),
                 "user": build_user_prompt(job.brief, job.languages, job.feedback)} for job in jobs]
    try:
        return client.generate_json_batch(requests, timeout_seconds=settings.batch_timeout_minutes * 60, on_poll=on_progress)
    except AIError as exc:
        return {job.custom_id: exc for job in jobs}


def _run_round(clients: "_Clients", jobs: list[_Job], settings: RashifalSettings, workers: int, on_progress, summary=None):
    """Yield (job, LLMResult | AIError) for one attempt of every job. One batch per model when batching."""
    by_model: dict[str, list[_Job]] = {}
    for job in jobs:
        job.model = settings.model_for(job.languages)
        by_model.setdefault(job.model, []).append(job)
    batchable = settings.batch and len(jobs) >= BATCH_MIN_JOBS
    if batchable and all(hasattr(clients.get(model), "generate_json_batch") for model in by_model):
        for job in jobs:
            job.batched = True
        if summary is not None:
            summary.batches += len(by_model)
        with ThreadPoolExecutor(max_workers=len(by_model)) as pool:  # the models' batches run side by side
            futures = {model: pool.submit(_run_batch, clients.get(model), group, settings, on_progress)
                       for model, group in by_model.items()}
            results = {model: future.result() for model, future in futures.items()}
        for job in jobs:
            yield job, results[job.model][job.custom_id]
        return
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [(job, pool.submit(_call_one, clients.get(job.model), job)) for job in jobs]
        for job, future in futures:
            yield job, future.result()


def _usage(job: _Job) -> dict:
    return {key: sum(call.usage.get(key, 0) for call in job.calls) for key in _USAGE_KEYS}


def _cost(job: _Job, settings: RashifalSettings) -> float | None:
    if not job.calls:
        return None
    usage = _usage(job)
    cost = estimate_cost_usd(job.calls[-1].model, usage)  # the API may answer with a dated id that is not in the table
    if cost is None:
        cost = estimate_cost_usd(job.model or settings.model, usage)
    if cost is not None and job.batched:
        cost = round(cost / 2, 6)  # Batches API: 50% of standard prices (retries of 1-3 pages go direct; close enough)
    return cost


def _publish(job: _Job, data: dict, report: dict, good: tuple[str, ...], settings: RashifalSettings, run_id: str,
             force: bool) -> PageOutcome:
    content = {code: _clean_page(data[code], job.brief, code) for code in good}
    dropped = [code for code in job.languages if code not in good]
    cost = _cost(job, settings)
    meta = {
        "requested_model": job.model or settings.model,
        "effort": settings.effort,
        "batch": job.batched,
        "run_id": run_id,
        "languages_written": list(good),
        "attempts": job.attempts,
        "usage": _usage(job),
        "cost_estimate_usd": cost,
        "cost_estimate_inr": None if cost is None else round(cost * get_settings().usd_inr, 2),
        "request_ids": [call.request_id for call in job.calls if call.request_id],
        "warnings": {code: report[code]["warnings"] for code in good if report[code]["warnings"]},
        "dropped_languages": {code: report[code]["blocking"] for code in dropped},
        "words": {code: _word_count(content[code]) for code in good},
    }
    split = len(job.languages) < len(settings.languages) and not job.merge
    stored_languages = store.save_page(
        job.rashi, job.period, merge=job.merge or split,
        merge_run_id=run_id if (split and not job.subset) else None,
        period_start=job.window.start_date.isoformat(), period_end=job.window.end_date.isoformat(),
        generated_at=_utcnow().isoformat(timespec="seconds"), model=job.calls[-1].model,
        brief_hash=brief_hash(job.brief), content=content, brief=job.brief, meta=meta,
    )
    complete = set(settings.languages) <= set(stored_languages)
    # a single-language job that published its language did its work; page completeness is rashifal_check's business
    status = "generated" if complete or (len(job.languages) < len(settings.languages) and not dropped) else "partial"
    detail = f"dropped {dropped}: {report[dropped[0]]['blocking'][0]}" if dropped else ""
    return PageOutcome(job.rashi, job.period, status, detail, good, job.attempts, cost)


def refresh(periods: list[str] | None = None, rashis: list[str] | None = None, *, force: bool = False,
            moment: dt.datetime | None = None, client=None, settings: RashifalSettings | None = None,
            workers: int = 3, use_lease: bool = True,
            only_languages: tuple[str, ...] | None = None) -> RefreshSummary:
    """Regenerate the pages that need it. Raises AINotConfigured (nothing generated) or RefreshBusy."""
    periods = list(periods or PERIOD_SLUGS)
    rashis = list(rashis or RASHI_SLUGS)
    for period in periods:
        if period not in PERIOD_SLUGS:
            raise ValueError(f"unknown period {period!r}; use one of {PERIOD_SLUGS}")
    for rashi in rashis:
        if rashi not in RASHI_SLUGS:
            raise ValueError(f"unknown rashi {rashi!r}; use one of {RASHI_SLUGS}")
    settings = settings or get_rashifal_settings()
    moment = to_ist(moment)

    holder = store.new_holder()
    if use_lease and not store.acquire_lease(LEASE_NAME, holder, LEASE_TTL_SECONDS):
        raise RefreshBusy(f"another refresh is running: {store.lease_info(LEASE_NAME)}")
    try:
        if only_languages and not settings.split_languages:
            raise ValueError("only_languages needs RASHIFAL_SPLIT_LANGUAGES=1: one call writes every language")
        jobs, skipped = plan(periods, rashis, moment, settings.languages, force, settings.split_languages,
                             only=only_languages)
        run_id = holder.rsplit(":", 1)[-1] + "-" + _utcnow().strftime("%Y%m%dT%H%M%S")
        summary = RefreshSummary(list(skipped), run_id=run_id, usage=dict.fromkeys(_USAGE_KEYS, 0))
        if not jobs:
            return summary
        clients = _Clients(settings, client)  # raises AINotConfigured before any AI work

        def heartbeat():
            if use_lease:
                store.acquire_lease(LEASE_NAME, holder, LEASE_TTL_SECONDS)

        pending = jobs
        for attempt in range(1, settings.max_attempts + 1):
            last = attempt == settings.max_attempts
            retry = []
            for job, result in _run_round(clients, pending, settings, workers, heartbeat, summary):
                heartbeat()
                job.attempts = attempt
                if isinstance(result, AINotConfigured):
                    raise result  # bad key / unknown model: every other call would fail the same way
                if isinstance(result, AIError):
                    job.last_error = str(result)
                    log.warning("rashifal %s/%s attempt %d: %s", job.rashi, job.period, attempt, result)
                    if last:
                        summary.outcomes.append(PageOutcome(job.rashi, job.period, "failed",
                                                            f"{job.last_error} - previous content kept", (), attempt, _cost(job, settings)))
                    else:
                        retry.append(job)
                    continue
                job.calls.append(result)
                summary.calls += 1
                for key in _USAGE_KEYS:
                    summary.usage[key] += result.usage.get(key, 0)
                result.data = tidy_output(result.data, job.languages)
                report = check_output(result.data, job.languages, job.brief, job.facts)
                good = tuple(code for code in job.languages if not report[code]["blocking"])
                problems = [f"[{code}] {message}" for code in job.languages for message in report[code]["blocking"]]
                summary.rejections += [{"rashi": job.rashi, "period": job.period, "attempt": attempt, "language": code,
                                        "message": message} for code in job.languages for message in report[code]["blocking"]]
                if problems:
                    log.warning("rashifal %s/%s attempt %d rejected: %s", job.rashi, job.period, attempt, problems[:5])
                if not problems or (last and good):
                    outcome = _publish(job, result.data, report, good, settings, run_id, force)
                    log.info("rashifal %s/%s %s (%s, attempt %d)", job.rashi, job.period, outcome.status, ",".join(good), attempt)
                    summary.outcomes.append(outcome)
                elif last:
                    summary.outcomes.append(PageOutcome(job.rashi, job.period, "failed",
                                                        f"{problems[0]} - previous content kept", (), attempt, _cost(job, settings)))
                else:
                    job.feedback = problems
                    retry.append(job)
            pending = retry
            if not pending:
                break
        order = {(r, p): n for n, (p, r) in enumerate((p, r) for p in PERIOD_SLUGS for r in RASHI_SLUGS)}
        summary.outcomes.sort(key=lambda outcome: order[(outcome.rashi, outcome.period)])
        return summary
    finally:
        if use_lease:
            store.release_lease(LEASE_NAME, holder)
