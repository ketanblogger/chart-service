"""PDF downloads. Shapes and errors are documented in docs/API.md ("Report PDFs").

Two routes, and the difference between them is the product:

- `GET /api/report/{id}/pdf` - the PAID report as a book. Entitlement-gated, exactly like the JSON report.
- `POST /api/chart/pdf` - the FREE Basic Chart PDF. **No gate, and no AI call on the path.** It takes
  birth details, computes the chart here with `detail="basic"`, and prints app/pdf/basic.py's document.

The free route recomputes the chart from the birth details rather than accepting a chart from the
caller. That is not an optimisation: a client-supplied chart would be attacker-controlled text arriving
straight into a PDF we put our name on. The only thing a caller may choose is the birth details, the
language, the script and the name on the sheet.

Neither route calls the AI. The paid one reads a report that was generated and paid for long before;
the free one has no report at all.
"""

import logging

import datetime as dt
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import Field

from app.ai.entitlement import require_entitlement
from app.ai.report import load_report
from app.api import BirthDetails

from .browser import PdfBusy, PdfError
from .render import MAX_NAME_LENGTH
from .service import (TooManyVariants, basic_download_name, download_name, ensure_basic_pdf, ensure_pdf)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_Name = Query(default=None, max_length=MAX_NAME_LENGTH)


def pdf_url(report_id: str) -> str:
    """Relative download link for a report id; POST /api/report and GET /api/report/{id} return it as `pdf_url`."""
    return f"/api/report/{report_id}/pdf"


@router.get("/report/{rid}/pdf", response_class=FileResponse)
def get_report_pdf(rid: str, request: Request, name: str | None = _Name, boy_name: str | None = _Name,
                   girl_name: str | None = _Name) -> FileResponse:
    """The report as a PDF. Same gate as the JSON report; rendered once, then served from var/pdfs.
    Never calls the AI. Sync on purpose: Chromium runs in FastAPI's threadpool, not on the event loop."""
    report = load_report(rid)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    require_entitlement(request, report["product"], rid)
    names = {"boy": boy_name, "girl": girl_name} if "matching" in (report.get("data") or {}) else {"self": name}
    try:
        path = ensure_pdf(report, names)
    except TooManyVariants:
        raise HTTPException(status_code=429, detail={
            "error": "too_many_name_variants",
            "message": "This report was already downloaded with several different names. Use one of those, or omit the name."})
    except PdfError as exc:
        log.error("PDF generation failed for report %s: %s", rid, exc)
        raise HTTPException(status_code=503, detail={
            "error": "pdf_unavailable",
            "message": "The PDF could not be prepared right now. Please try again in a minute."}) from exc
    return FileResponse(path, media_type="application/pdf", filename=download_name(report),
                        headers={"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex"})


# ---- the free Basic Chart PDF -------------------------------------------------------------------

# Per client IP per hour, and it counts RENDERS, not requests - a cache hit is free (see `ensure_basic_pdf`).
# 30 rather than a dozen because India's mobile carriers run large-scale CGNAT: thousands of subscribers can
# share one public IPv4, and this is the top of the funnel. The marginal cost of being wrong here is CPU, and
# `PDF_MAX_CONCURRENT` is the thing that actually protects the box.
DEFAULT_BASIC_HOURLY_LIMIT = 30


class BasicChartPdfRequest(BirthDetails):
    """Birth details (as POST /api/chart), plus how to print them."""

    language: Literal["en", "hi", "mr"] = "en"
    script: Literal["en", "deva"] | None = Field(
        default=None, description="Chart labels: Latin or Devanagari. Default: follows `language`.")
    name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH,
                             description="Printed on the sheet. Optional.")
    as_of: dt.datetime | None = Field(
        default=None, description="Moment the current dasha and sade sati are evaluated for. Default now.")
    approximate_time: bool = Field(default=False, description=(
        "True when `time` was picked from a range (the form's tap-to-select presets) rather than recorded. "
        "It changes nothing about the calculation - the chart is computed from the time given either way - "
        "and adds a caveat saying what a three-hour bucket does and does not move."))


def _basic_hourly_limit() -> int:
    try:
        return max(1, int(os.getenv("BASIC_PDF_HOURLY_LIMIT", str(DEFAULT_BASIC_HOURLY_LIMIT))))
    except ValueError:
        return DEFAULT_BASIC_HOURLY_LIMIT


@router.post("/chart/pdf", response_class=FileResponse)
def get_basic_chart_pdf(body: BasicChartPdfRequest, request: Request) -> FileResponse:
    """The free Basic Chart PDF: both charts, the graha table, the doshas and the running dasha.

    Free and ungated on purpose - and therefore rate limited, because a Chromium render is the most
    expensive thing this server does (app/pdf/browser.py holds it to one at a time machine-wide) and
    this is the only route that will run one for somebody who has not paid. The limit counts RENDERS,
    not requests (`BASIC_PDF_HOURLY_LIMIT` per client IP per hour, charged inside `ensure_basic_pdf`
    only when a browser is about to start), so a repeat download served from cache is free. Carrier
    CGNAT puts thousands of phones behind one IPv4, and this is the top of the funnel: the budget has to
    be spent on Chromium, not on HTTP.

    **Never calls the AI**: it computes the chart, renders app/pdf/basic.py's template and prints it.
    Sync on purpose: Chromium runs in FastAPI's threadpool, not on the event loop. Because that
    threadpool is shared with EVERY route on the site, a queued request here holds a worker thread for
    the whole render - and this is the ungated route, so unbounded queueing is how an anonymous visitor
    starves the site rather than merely delaying a PDF. So it queues for a BOUNDED
    `PDF_FREE_WAIT_SECONDS` (2 s) and then returns 503 `pdf_busy`. Two seconds clears nearly every
    collision, because the free sheet mostly contends with OTHER FREE SHEETS (0.71 s each) rather than
    with books. (The argument for the bound is thread accounting, not courtesy to paying customers - a
    render is only a few seconds, so the paid path tolerates unbounded queueing fine. Do not remove the
    bound on the strength of that number.)"""
    from app.ai import chat_store
    from app.ai.chat_identity import client_ip
    from app import engine

    try:
        chart = engine.compute_chart(body.date, body.time, body.lat, body.lon, body.timezone,
                                     as_of=body.as_of, detail="basic")  # never "full": nothing here needs it
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    chart["input"]["city"] = body.city

    def charge_for_a_render() -> None:
        """Called only when a browser is actually about to run, so a cache hit is never charged."""
        try:
            chat_store.check_rate(f"basicpdf:{client_ip(request)}", _basic_hourly_limit(), 3600)
        except chat_store.RateLimited as exc:
            raise HTTPException(status_code=429, headers={"Retry-After": str(exc.retry_after)}, detail={
                "error": "rate_limited",
                "message": "Several new chart PDFs have been prepared from this connection in the last "
                           "hour. Please try again a little later - the chart on the page is always free "
                           "to read."}) from exc

    try:
        path = ensure_basic_pdf(chart, language=body.language, name=body.name, chart_script=body.script,
                                approximate_time=body.approximate_time, before_render=charge_for_a_render)
    except PdfBusy as exc:
        # 10 s, not a minute: what this route is standing behind is one other render, and the longest
        # of those is a 60-page book in single figures of seconds.
        raise HTTPException(status_code=503, headers={"Retry-After": "10"}, detail={
            "error": "pdf_busy",
            "message": "The chart PDF could not be prepared just now - the server is printing something "
                       "else. Please try again in a moment."}) from exc
    except PdfError as exc:
        log.error("free chart PDF generation failed: %s", exc)
        raise HTTPException(status_code=503, detail={
            "error": "pdf_unavailable",
            "message": "The PDF could not be prepared right now. Please try again in a minute."}) from exc
    return FileResponse(path, media_type="application/pdf",
                        filename=basic_download_name(chart, body.language),
                        headers={"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex"})
