"""Paid report API. The only routes in the app that call the AI. Shapes are documented in docs/API.md."""

import datetime as dt
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

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
                     "mangal-dosha-remedy", "sade-sati-guide", "numerology-report"]
    language: Literal["en", "hi", "mr"] = "en"
    birth: BirthDetails | None = None
    boy: BirthDetails | None = None
    girl: BirthDetails | None = None
    as_of: dt.date | None = None  # default: today (IST). Pins "current" dasha / sade-sati and the cache key.

    # THE NUMEROLOGY REPORT'S OWN FIELDS. A name and a date, and numbers the reader would like
    # looked at. No birth time and no place: this product does not cast a chart, and asking for the
    # hour of somebody's birth to add up digits is asking for something we will not use.
    name: str | None = Field(default=None, max_length=60)
    born: dt.date | None = None
    numbers: list[str] | None = Field(default=None, max_length=4)

    @model_validator(mode="after")
    def _right_people(self):
        kind = PRODUCTS[self.product].kind
        if kind == "numerology":
            # EVERY OTHER PRODUCT'S RULE IS UNTOUCHED - this is a new branch, not a relaxation of
            # the existing one. A chart report that arrives without a birth time still fails, which
            # is what the test beside this asserts.
            if not self.born:
                raise ValueError("numerology-report needs `born` (the date of birth)")
            if not (self.name or "").strip():
                raise ValueError("numerology-report needs `name`")
            if self.birth is not None:
                raise ValueError(
                    "numerology-report takes `name` and `born`, not `birth` - it does not cast a "
                    "chart and has no use for a birth time or place")
            return self
        if kind == "pair":
            if self.boy is None or self.girl is None:
                raise ValueError("matching-report needs `boy` and `girl` birth details")
        elif self.birth is None:
            raise ValueError(f"{self.product} needs `birth` details")
        return self

    def births(self) -> list[Birth]:
        """The people whose charts this report needs. Empty for numerology, which casts none."""
        if PRODUCTS[self.product].kind == "numerology":
            return []
        people = [self.boy, self.girl] if PRODUCTS[self.product].kind == "pair" else [self.birth]
        return [Birth(p.date, p.time, p.lat, p.lon, p.timezone, p.city) for p in people]

    def numerology_facts(self) -> dict:
        """The numbers this report is written from - computed here, by the same module the free
        calculator uses, so the report and the page cannot disagree."""
        from app.numerology import core

        facts = core.for_chat(self.born, self.name or "")
        checked = []
        for value in (self.numbers or []):
            found = core.check_number(value, mulank=facts["mulank"], bhagyank=facts["bhagyank"])
            if found["usable"]:
                checked.append(found)
        if checked:
            facts["numbers_checked"] = checked
        return facts


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
        return _with_pdf_url(generate_report(
            body.product, body.language, births, as_of=as_of,
            numerology_facts=(body.numerology_facts()
                              if PRODUCTS[body.product].kind == "numerology" else None)))
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
