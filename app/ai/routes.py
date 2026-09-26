"""Paid report API. The only routes in the app that call the AI. Shapes are documented in docs/API.md."""

import datetime as dt
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, model_validator

from app.api import BirthDetails

from .client import AIBadOutput, AIError, AINotConfigured
from .entitlement import require_entitlement
from .products import PRODUCTS
from .report import Birth, generate_report, load_report, report_id, today_ist

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class ReportRequest(BaseModel):
    """`birth` for single-person products; `boy` + `girl` for matching-report. Same birth-details
    objects as POST /api/chart and POST /api/matching."""

    product: Literal["kundali-report", "kundali-report-simple", "matching-report",
                     "mangal-dosha-remedy", "sade-sati-guide"]
    language: Literal["en", "hi", "mr"] = "en"
    birth: BirthDetails | None = None
    boy: BirthDetails | None = None
    girl: BirthDetails | None = None
    as_of: dt.date | None = None  # default: today (IST). Pins "current" dasha / sade-sati and the cache key.

    @model_validator(mode="after")
    def _right_people(self):
        if PRODUCTS[self.product].kind == "pair":
            if self.boy is None or self.girl is None:
                raise ValueError("matching-report needs `boy` and `girl` birth details")
        elif self.birth is None:
            raise ValueError(f"{self.product} needs `birth` details")
        return self

    def births(self) -> list[Birth]:
        people = [self.boy, self.girl] if PRODUCTS[self.product].kind == "pair" else [self.birth]
        return [Birth(p.date, p.time, p.lat, p.lon, p.timezone, p.city) for p in people]


def _with_pdf_url(report: dict) -> dict:
    """Phase 4: the download link for the PDF of this report (app/pdf/routes.py). Not stored in the cache."""
    report["pdf_url"] = f"/api/report/{report['id']}/pdf"
    return report


def _ai_http_error(exc: AIError) -> HTTPException:
    log.error("report generation failed: %s", exc)
    status = 502 if isinstance(exc, AIBadOutput) else 503
    code = "ai_not_configured" if isinstance(exc, AINotConfigured) else "ai_unavailable"
    return HTTPException(status_code=status, detail={"error": code, "message": exc.public_message})


@router.post("/report")
def create_report(body: ReportRequest, request: Request) -> dict:
    births, as_of = body.births(), body.as_of or today_ist()
    require_entitlement(request, body.product, report_id(body.product, body.language, births, as_of))
    try:
        return _with_pdf_url(generate_report(body.product, body.language, births, as_of=as_of))
    except ValueError as exc:  # bad timezone string etc. from the engine
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIError as exc:
        raise _ai_http_error(exc) from exc


@router.get("/report/{rid}")
def get_report(rid: str, request: Request) -> dict:
    """Re-download a generated report. Reads the disk cache only - never calls the AI."""
    report = load_report(rid)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    require_entitlement(request, report["product"], rid)
    report["meta"]["cache_hit"] = True
    return _with_pdf_url(report)
