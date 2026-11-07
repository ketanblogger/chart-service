"""JSON API over the calculation engine. No AI calls here. Shapes are documented in docs/API.md."""

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
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
        # The curated list first - it carries the hand-checked spellings and the "(Belgaum)" style
        # labels - then the full GeoNames set, which is what the form now offers.
        from app.engine import places as place_table

        city = engine.find_city(self.city) or place_table.find(self.city)
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


@router.post("/seen", status_code=204)
def seen(request: Request, response: Response, path: str = Query(default="", max_length=200)) -> Response:
    """A real browser ran a page. Carries nothing and answers nothing.

    This is the one signal that separates the 450-580 visitors the dashboard counts from the 7 search
    clicks a day Search Console reports: a crawler fetches the HTML and stops, a browser runs the page and
    reaches this. It cannot identify anybody - the server recomputes the same daily-salted visitor hash it
    already stored, so there is no id to issue and nothing new kept - and it cannot refuse anybody, because
    nothing on the site is gated on it. 204, always, whatever happens.
    """
    try:
        from app import analytics

        analytics.confirm_browser(
            ip=(request.client.host if request.client else ""),
            user_agent=request.headers.get("user-agent", ""),
            path=path or request.headers.get("referer", ""))
    except Exception:  # noqa: BLE001 - a beacon is never a reason to return an error
        pass
    return Response(status_code=204)


#: THE ONLY STEPS THIS ENDPOINT WILL RECORD. An allowlist rather than a pattern, because the whole
#: safety of this route is that nothing a page sends can become free text in the database: a step that
#: is not one of these is dropped, so a bug or a tampered page cannot write anything of a reader's.
FUNNEL_STEPS = frozenset({
    "form_seen",        # the form entered the viewport - the denominator for everything below
    "first_touch",      # the first field anybody put a cursor in
    "field_done",       # a field left with something in it (the FIELD NAME, never the value)
    "place_typed",      # somebody started typing a birth place
    "place_none",       # ...and the search had nothing to offer them
    "place_picked",     # ...or they chose one
    "submit",           # the button was pressed
    "invalid",          # the form came back at them, and which field it blamed
    "result",           # a chart was actually shown
    # The paid report's offer, which nothing recorded at all. "34 paywalls shown" came from the chat;
    # the report offer under a free chart was invisible, so its view and its click were the two steps
    # between a free user and a paying one that no number covered.
    "offer_seen",
    "offer_click",
    # The match card: offered, ticked, and shared. NO NAMES AND NO SCORE COME HERE - the card is
    # drawn in the browser and these say only that the step happened.
    "match_card_seen",
    "match_card_named",
    "match_card_shared",
})

#: The field names a step may name. Also an allowlist: these are the form's own fields and no value of
#: any of them is ever sent - "city" says which box, never which city.
FUNNEL_FIELDS = frozenset({"name", "date", "time", "city", "year", "window", "unknown"})


@router.post("/funnel", status_code=204)
def funnel(request: Request, response: Response,
           step: str = Query(default="", max_length=24),
           field: str = Query(default="", max_length=16),
           w: int = Query(default=0, ge=0, le=20000)) -> Response:
    """One step of the birth-details form. Carries nothing about the person and answers nothing.

    WHY THIS EXISTS. 6,372 people arrived on the kundli page in thirty days and 999 charts were run.
    Five in six left without one, and no measurement on this site could say at which field - so every
    explanation for it was a guess, including the plausible ones.

    WHAT IT MAY RECORD: a step name from FUNNEL_STEPS, a field name from FUNNEL_FIELDS, and a viewport
    WIDTH bucketed to "mobile" or "desktop". Not the width itself, not a user agent, not a value a
    reader typed, not an id. Anything else is dropped rather than stored.

    It answers 204 whatever happens, like the `seen` beacon above: measurement must never be the reason
    somebody cannot use the form it is measuring.
    """
    try:
        if step not in FUNNEL_STEPS:
            return Response(status_code=204)
        from app import analytics

        # The entry cookie is one word from a fixed list and is already set on every visit; reading it
        # here is what lets a form step be joined to the page somebody arrived on.
        entry = (request.cookies.get(analytics.ENTRY_COOKIE) or "")[:16]
        # WHICH PAGE THE STEP HAPPENED ON, for the offer events. They were recorded with no page at
        # all, so "34 offers seen" could not be split between the chart tool and the matching tool -
        # and the matching page's whole problem is that nobody reaches it. The page key comes from
        # the referring path through the registry, never from anything the caller asserts.
        feature = ("offer" if step.startswith("offer_")
                   else "match_card" if step.startswith("match_card_")
                   else "kundli_form")
        analytics.record_event(
            feature, step,
            detail=(f"field={field}" if field in FUNNEL_FIELDS
                    else (f"page={_funnel_page(request)}" if step.startswith("offer_") else "")),
            lang=_funnel_lang(request),
            entry=entry,
            device="mobile" if 0 < w < 768 else ("desktop" if w else ""))
    except Exception:  # noqa: BLE001 - a beacon is never a reason to return an error
        pass
    return Response(status_code=204)


def _funnel_page(request: Request) -> str:
    """The page key of the referring path, or "" - resolved through the registry, never trusted."""
    from app.web import i18n

    referer = request.headers.get("referer", "")
    path = referer.split("://", 1)[-1].split("/", 1)[-1] if "://" in referer else referer
    found = i18n.resolve("/" + path.split("?", 1)[0].lstrip("/"))
    return (found[0] if found else "")[:24]


def _funnel_lang(request: Request) -> str:
    """Which tree the form was on, from the referring path - not from a header the reader cannot see."""
    referer = request.headers.get("referer", "")
    for code in ("hi", "mr"):
        if f"/{code}/" in referer or referer.rstrip("/").endswith(f"/{code}"):
            return code
    return "en"


class BirthDetailsNoTime(BaseModel):
    """A birth with no clock time: the date and the city, and nothing that pretends to be an hour."""

    date: dt.date
    city: str
    name: str | None = None
    # OPTIONAL, and both or neither. "Born between 07:00 and 07:40" is a different question from "the
    # time is unknown", and answering the first with the second's answer throws away the lagna.
    from_time: dt.time | None = Field(default=None, description="start of the window the birth is inside")
    to_time: dt.time | None = Field(default=None, description="end of that window")

    @model_validator(mode="after")
    def _both_or_neither(self):
        if bool(self.from_time) != bool(self.to_time):
            raise ValueError("give both from_time and to_time, or neither")
        return self


@router.post("/share", status_code=204)
def share_tapped(response: Response, source: str = Query(default="", max_length=20)) -> Response:
    """Somebody tapped a WhatsApp share button. Carries nothing about them and answers nothing.

    A share LEAVES this site, so unlike the rashifal ask-click there is no destination page of ours to
    record it on - this is the only moment it can be seen. The arrivals that come back are already
    counted by utm_source, which means the two halves of "was it shared, and did anyone come" are
    measured independently rather than one being inferred from the other.

    `source` is checked against the fixed set in app/web/sharing.py before it is stored, so a crafted
    URL cannot put a string of its own choosing into the table. Anything else is ignored silently: a
    counter is never a reason to return an error.
    """
    try:
        from app import analytics
        from app.web import sharing

        if source in sharing.SOURCES:
            analytics.record_event("share", "whatsapp", detail=source, cost_inr=0.0)
    except Exception:  # noqa: BLE001 - counting never fails a request
        pass
    return Response(status_code=204)


@router.post("/chart/without-time")
def chart_without_time(details: "BirthDetailsNoTime") -> dict:
    """What a chart can honestly say when the birth TIME is unknown.

    A SEPARATE ENDPOINT, NOT A FLAG ON /chart, because it returns a different KIND of answer. /chart
    returns a chart: a lagna, twelve houses, dasha dates. This returns a list of what is settled, a list
    of what the hour would decide, and the named things it refuses to compute at all. Folding that into
    the same response shape would mean a caller could read `lagna` off it and get a noon assumption -
    which is the exact failure this exists to prevent.
    """
    from app.engine.cities import find_city
    from app.engine.without_time import what_is_known

    city = find_city(details.city or "")
    if not city:
        raise HTTPException(status_code=422, detail="unknown city")
    answer = what_is_known(details.date, city.get("tz") or "Asia/Kolkata")

    # A WINDOW IS A DIFFERENT KIND OF NOT-KNOWING from no time at all, and it settles much more.
    # "Some time in the morning" checked across the whole day throws away the lagna; checked across
    # forty minutes it usually does not move at all, and then the lagna and the houses are KNOWN.
    # Optional, so the endpoint answers exactly as before when no window is given.
    if details.from_time and details.to_time:
        from app.engine.time_window import lagna_in_window

        window = lagna_in_window(details.date, details.from_time, details.to_time,
                                 float(city["lat"]), float(city["lon"]),
                                 city.get("tz") or "Asia/Kolkata")
        if window.get("error"):
            raise HTTPException(status_code=422, detail=window)
        answer["window"] = window
        # The refusals shrink when the window settles them, and they shrink HERE rather than in the
        # engine so that what_is_known() keeps meaning exactly one thing: what a date alone settles.
        if window["settled"]:
            answer["needs_birth_time"] = [name for name in answer["needs_birth_time"]
                                          if name not in ("lagna", "houses", "bhava_positions")]
        if window["dasha"]["available"]:
            answer["needs_birth_time"] = [name for name in answer["needs_birth_time"] if name != "dasha"]
    return answer


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
    request: Request = None,
) -> dict:
    result = _chart(details, detail, as_of)
    # A CHART WAS ACTUALLY MADE. The page view was already counted, but a view is somebody arriving and
    # this is somebody using the thing - the step between them is where a funnel either holds or leaks,
    # and it was the one step nothing recorded.
    try:
        from app import analytics

        analytics.record_event("kundali", "generated", cost_inr=0.0,
                               lang=(getattr(details, "language", "") or ""),
                               entry=entry_of(request))
    except Exception:  # noqa: BLE001 - counting never fails a chart
        pass
    return result


def entry_of(request) -> str:
    """Which kind of page this person arrived on, from the entry cookie, or "" if we never set one.

    One word from a fixed list of six. It is what lets a tool run be joined to an arrival: until this
    was threaded through, "tools run" was a single number that could not be split by anything, so
    6,372 landings and 999 charts could not be told whether they were even the same people.
    """
    try:
        from app import analytics

        return (request.cookies.get(analytics.ENTRY_COOKIE) or "")[:16] if request is not None else ""
    except Exception:  # noqa: BLE001 - never let counting break a calculation
        return ""


def _used(tool: str, lang: str = "", entry: str = "") -> None:
    """One calculator was actually RUN. Never a reason to fail the call.

    /chart has recorded this since the funnel was first looked at; the other three never did, so the
    dashboard could see somebody arrive on the matching page and never see whether they matched anything.
    A funnel with a step that is not recorded is not a funnel with a gap - it is a funnel that quietly
    reports the gap as a drop-off, which is the number somebody then tries to fix.
    """
    try:
        from app import analytics

        analytics.record_event(tool, "generated", cost_inr=0.0, lang=lang, entry=entry)
    except Exception:  # noqa: BLE001 - counting never fails a calculation
        pass


@router.post("/mangal-dosha")
def mangal_dosha(details: BirthDetails, http: Request = None) -> dict:
    full = _chart(details)
    _used("mangal-dosha", getattr(details, "language", "") or "", entry_of(http))
    return {
        "input": full["input"],
        "lagna": full["lagna"],
        "moon_rashi": full["moon_rashi"],
        "mars": full["grahas"]["Mars"],
        "mangal_dosha": full["mangal_dosha"],
    }


@router.post("/sade-sati")
def sade_sati(details: BirthDetails, http: Request = None) -> dict:
    full = _chart(details)
    _used("sade-sati", getattr(details, "language", "") or "", entry_of(http))
    return {
        "input": full["input"],
        "moon_rashi": full["moon_rashi"],
        "janma_nakshatra": full["janma_nakshatra"],
        "sade_sati": full["sade_sati"],
    }


def _name_error(who: str, exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail={"error": "name_unreadable", "who": who, "message": str(exc)})


@router.post("/matching")
def matching(request: AnyMatchingRequest, http: Request = None) -> dict:
    _used("matching", "", entry_of(http))
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
def cities(q: str = Query(default="", max_length=60)) -> dict:
    """The place list, in one of two shapes.

    WITHOUT `q`: every Indian place with a thousand people or more, packed - 104 KB over the wire,
    fetched once, and filtered in the browser as somebody types. That is what the birth-details form
    wants: instant answers on a phone that may have lost its connection since.

    WITH `q`: the matching places, expanded, at most twenty. The muhurta page asks this way and wants
    eight suggestions rather than a national index, and it was already calling with `q` when the old
    137-city answer made the parameter pointless. Leaving it unhonoured broke that page the moment the
    unfiltered shape changed - a caller passing a filter it never received, which nothing noticed
    until the list came back empty.
    """
    from app.engine import places

    if not q.strip():
        return places.payload()
    found = places.search(q, 20)
    return {"cities": [{**place, "label": f"{place['name']}, {place['state']}"} for place in found]}
