"""JSON API over the calculation engine. No AI calls here. Shapes are documented in docs/API.md."""

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Discriminator, Field, Tag, model_validator

from app import engine
from app.engine import namakshar

router = APIRouter(prefix="/api")


class BirthDetails(BaseModel):
    """Birth date/time plus a place: either `city` from GET /api/cities, or `lat` + `lon`."""

    date: dt.date
    time: dt.time
    city: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    timezone: str | None = Field(
        default=None,
        description='IANA name or UTC offset ("+05:30"). Default: the city\'s timezone, else Asia/Kolkata.',
    )

    @model_validator(mode="after")
    def _resolve_place(self):
        if self.lat is not None and self.lon is not None:
            return self
        if self.lat is not None or self.lon is not None:
            raise ValueError("lat and lon must be given together")
        if not self.city:
            raise ValueError("give either city or lat + lon")
        city = engine.find_city(self.city)
        if city is None:
            raise ValueError(f"unknown city {self.city!r} - use a name from GET /api/cities, or send lat + lon")
        self.city, self.lat, self.lon = city["name"], city["lat"], city["lon"]
        self.timezone = self.timezone or city["tz"]
        return self


class MatchingRequest(BaseModel):
    mode: Literal["birth"] = "birth"
    boy: BirthDetails
    girl: BirthDetails


class NamePerson(BaseModel):
    name: str = Field(min_length=1, max_length=80, description="Latin transliteration or Devanagari")
    syllable: str | None = Field(default=None, max_length=8, description=(
        "Optional explicit choice of the name's first sound, as a Devanagari syllable of the Avakahada chakra "
        "(normally one of `name_match.candidates[].syllable` from a previous response)."))


class NameMatchingRequest(BaseModel):
    """By-name matching ("kundli milan by name"): free, no birth details, no AI."""

    mode: Literal["name"]
    boy: NamePerson
    girl: NamePerson


def _matching_mode(value) -> str:
    mode = value.get("mode", "birth") if isinstance(value, dict) else getattr(value, "mode", "birth")
    return mode if mode in ("birth", "name") else "birth"  # an unknown mode then fails MatchingRequest's Literal


AnyMatchingRequest = Annotated[
    Annotated[MatchingRequest, Tag("birth")] | Annotated[NameMatchingRequest, Tag("name")],
    Discriminator(_matching_mode),
]


def _chart(details: BirthDetails, detail: str = "basic", as_of: dt.datetime | None = None) -> dict:
    try:
        chart = engine.compute_chart(details.date, details.time, details.lat, details.lon,
                                     details.timezone, as_of=as_of, detail=detail)
    except ValueError as exc:  # bad timezone string etc.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    chart["input"]["city"] = details.city
    return chart


@router.post("/chart")
def chart(
    details: BirthDetails,
    detail: Literal["basic", "full"] = Query(
        default="basic",
        description='"full" adds the `report` block: navamsa, dignity, aspects, yogas, highlights, '
                    "gemstone, dhaiya and the dated timeline the paid Kundali report is written against. "
                    "Roughly 400 KB of JSON - the free pages want the default."),
    as_of: dt.datetime | None = Query(
        default=None,
        description="Moment the current dasha, sade-sati and the timeline are evaluated for. "
                    "Default now; without an offset it is read as IST."),
) -> dict:
    return _chart(details, detail, as_of)


@router.post("/mangal-dosha")
def mangal_dosha(details: BirthDetails) -> dict:
    full = _chart(details)
    return {
        "input": full["input"],
        "lagna": full["lagna"],
        "moon_rashi": full["moon_rashi"],
        "mars": full["grahas"]["Mars"],
        "mangal_dosha": full["mangal_dosha"],
    }


@router.post("/sade-sati")
def sade_sati(details: BirthDetails) -> dict:
    full = _chart(details)
    return {
        "input": full["input"],
        "moon_rashi": full["moon_rashi"],
        "janma_nakshatra": full["janma_nakshatra"],
        "sade_sati": full["sade_sati"],
    }


def _name_error(who: str, exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail={"error": "name_unreadable", "who": who, "message": str(exc)})


@router.post("/matching")
def matching(request: AnyMatchingRequest) -> dict:
    if isinstance(request, NameMatchingRequest):
        for who in ("boy", "girl"):  # attribute a bad name / syllable to the right form field
            person = getattr(request, who)
            try:
                namakshar.from_name(person.name, person.syllable)
            except namakshar.NameError_ as exc:
                raise _name_error(who, exc) from exc
        return engine.match_names(request.boy.name, request.girl.name, request.boy.syllable, request.girl.syllable)
    boy, girl = _chart(request.boy), _chart(request.girl)
    result = engine.match_charts(boy, girl)
    result["boy"]["input"], result["girl"]["input"] = boy["input"], girl["input"]
    result["basis"] = "birth"
    return result


@router.get("/transits")
def transits(
    at: dt.datetime | None = Query(default=None, description="Default now. Without an offset it is read as IST."),
    rashi: str | None = Query(default=None, description='Moon sign: 1-12, "Leo", "Simha" or "simha".'),
    end: dt.datetime | None = Query(default=None, description="If given, also list events between `at` and `end`."),
) -> dict:
    try:
        result = engine.current_transits(at, rashi)
        if end is not None:
            start = dt.datetime.fromisoformat(result["datetime_utc"])
            result["events"] = engine.transit_events(start, end, rashi)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get("/cities")
def cities() -> dict:
    return {"cities": engine.CITIES}
