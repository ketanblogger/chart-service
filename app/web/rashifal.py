"""Rashifal pages in three language trees - 180 reading pages, 36 per-rashi hubs, 3 daily hubs
and 3 weekly hubs. Paths come from the registry (app/web/i18n.py):

    /horoscope                /hi/rashifal                 /mr/rashi-bhavishya                 daily hub (all 12 rashis)
    /horoscope/weekly         /hi/rashifal/saptahik        /mr/rashi-bhavishya/saptahik        weekly hub
    /horoscope/{sign}         /hi/rashifal/{rashi}         /mr/rashi-bhavishya/{rashi}         one rashi, five periods
    /horoscope/{sign}/{p}     /hi/rashifal/{rashi}/{p}     /mr/rashi-bhavishya/{rashi}/{p}     one reading

The weekly-hub route is registered BEFORE the {rashi} route of its tree, and every handler resolves its path through
the registry (exact match or 404), so "weekly" / "saptahik" can never be taken for a rashi, and a slug of another
language tree (/horoscope/tula, /hi/rashifal/libra) is a 404, not a duplicate page.

Server-rendered from the content store (app/rashifal/store.py) and the calculation engine. A page view NEVER calls the
AI: this module does not import app.rashifal.generate or the AI client, and tests/test_rashifal_web.py proves a request
cannot reach the AI client. If a page has no stored reading yet (or not in this language) it still returns 200 with the
engine's transit facts for that rashi and period - never an empty shell.

Words: titles / H1 / meta of the readings and the two hubs are the query-pattern templates of app/rashifal/i18n.py
(calc-engine), as are the fact labels and sentences; intros, long-form sections, FAQs, link labels and CTAs are the
page-config copy (app/web/content/<lang>.py: "rashifal-hub", "rashifal-weekly", "rashifal-rashi", "rashifal-reading").
One language per URL: self-referencing canonical + the reciprocal hreflang set, no ?lang=, no cookie switching.
Internal links list the rashis by search demand for that language (i18n.rashis_by_demand).
"""

import datetime as dt
from email.utils import format_datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.rashifal import i18n as words
from app.rashifal import periods as _periods
from app.rashifal import store, year_facts
from app.rashifal.brief import build_brief
from app.rashifal.periods import DATED_MONTHS, base_period, is_dated_month, to_ist, window_for
from app.rashifal.prompts import SECTION_IDS, sections_for
from app.web import i18n, pages, seo, sharing, site
from app.web.routes import _json_ld, _preview, account_menu, page_context, templates

router = APIRouter(include_in_schema=False)

AD_SLOTS = ("rashifal-top", "rashifal-mid", "rashifal-bottom")  # empty containers; no ad network code yet
_CACHE_CONTROL = "public, max-age=300"


def _now() -> dt.datetime:
    """The moment a page is rendered for (tests replace this)."""
    return to_ist(None)


def _breadcrumbs(items: list[tuple[str, str]]) -> dict:
    base = site.base_url()
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": n, "name": name, "item": base + path} for n, (name, path) in enumerate(items, 1)]}


def _respond(request: Request, template: str, context: dict, last_modified: dt.datetime | None = None):
    # THE SAME CHROME AS EVERY OTHER PAGE. This file has its own responder - the rashifal pages carry cache
    # and Last-Modified headers that nothing else does - and that made it the one route the account menu was
    # missing from: 216 pages, the most visited on the site, with no way to reach a sign-in. Anything the
    # shared header needs is added HERE as well, which is the cost of having a second funnel at all.
    context.setdefault("auth", pages.auth_copy(context.get("lang", "en")))
    context.setdefault("account_menu", account_menu(request, context.get("lang", "en"),
                                                    request.url.path or "/"))
    # The `?design=v2` prototype, through the same helper the rest of the web layer uses, so a rashifal page
    # behaves like every other page under the flag and this file needs to know nothing else about it.
    template, context = _preview(request, template, context)
    response = templates.TemplateResponse(request, template, context)
    response.headers["Cache-Control"] = _CACHE_CONTROL
    response.headers["Content-Language"] = context["html_lang"]
    if last_modified:
        response.headers["Last-Modified"] = format_datetime(last_modified.astimezone(dt.timezone.utc), usegmt=True)
    return response


def _resolve(request: Request, expected: str) -> tuple[str, dict]:
    """(lang, params) of the requested path, or 404 - only the registry's exact paths are pages."""
    found = i18n.resolve(request.url.path)
    if not found or found[0] != expected:
        raise HTTPException(status_code=404, detail="unknown rashifal page")
    return found[1], found[2]


def _symbol(rashi: str, lang: str, names: dict) -> dict:
    """The sign's symbol: its file and its alt text in this language.

    DRAWN IN THIS REPOSITORY - scripts/make_rashi_art.py builds all twelve from the same primitives as
    the glyph set, inside the brand mark's ring. Nothing traced, nothing stock, and nothing figurative.
    The slug is the rashi key, which is also the filename, so a sign that somehow had no file would be
    a missing image rather than the wrong sign's symbol.
    """
    # pages.ui() IS the string table, and reading it directly means a language that has not got the
    # key raises here rather than quietly shipping a worse alt text to that tree only.
    template = pages.ui(lang)["rashi_symbol_alt"]
    return {"slug": rashi, "alt": template.format(rashi=names["rashi"])}


def _labels(copy: pages.PageCopy, names: dict) -> dict:
    return {key: pages.fill(text, **names) for key, text in copy.extra.items()}


def _link_labels(page_key: str, lang: str) -> dict:
    """The label templates with their {rashi}/{latin} placeholders still IN them.

    `pages.get(key, lang, **names)` fills the copy for the sign being read, and `_labels` fills whatever is
    left. That is right for nearly every label on a reading page, because nearly every label is about that
    one sign - and it is exactly wrong for the two templates that have to be filled twelve different ways.
    Filling `rashi_label` from the page's own copy left all eleven "other signs" links reading the CURRENT
    sign's name while pointing at the other eleven, on 180 reading pages and 36 rashi hubs."""
    return pages.get(page_key, lang).extra


_MOON_LINE = {
    "en": "{moon} is in {sign} today - the {ordinal} house from your rashi.",
    "hi": "आज {moon} {sign} में है - आपकी राशि से {ordinal} भाव।",
    "mr": "आज {moon} {sign} मध्ये आहे - तुमच्या राशीपासून {ordinal} स्थान.",
}
_EN_ORDINAL = {1: "1st", 2: "2nd", 3: "3rd"}


def _moon_line(brief: dict, lang: str) -> str | None:
    """Where the Moon is for this rashi today. Always available, because the Moon is always somewhere."""
    moon = (brief or {}).get("moon_at_sunrise") or {}
    sign, house = moon.get("sign"), moon.get("house")
    if not sign or not house:
        return None
    ordinal = (_EN_ORDINAL.get(house, f"{house}th") if lang == "en" else words.ordinal(house, lang))
    return _MOON_LINE[lang].format(
        # `graha_name` takes the graha BLOCK, not its key. The teaser swallows exceptions so that a hub
        # page never fails over a decorative line - which also means a mistake in here is silent, and the
        # only way to see it is to call this directly. That is how this one was found.
        moon=words.graha_name(moon["graha"], lang),
        # `sign_name` takes the sign block too, and gives an English reader "Cancer" rather than "Karka" -
        # which is what every other English line on these pages says.
        sign=words.sign_name(sign, lang),
        ordinal=ordinal)


def _engine_teaser(rashi: str, period: str, lang: str, now: dt.datetime, today_brief: dict,
                   avoid: "set[str] | None" = None) -> str | None:
    """A one-line teaser for a period card when no WRITTEN headline is current for that period.

    EVERY PERIOD, not just today and this week. The month, six-month and year cards sat with a date
    range and then a blank where their neighbours had a sentence, which reads as a card that failed to
    load rather than one with nothing to say.

    The written headline is only shown while the stored page matches the period's window, and those windows
    are wildly different lengths: a monthly page stays current for most of a month, a today page for one day
    and a weekly page for a week. So the Today and This Week cards were the two that routinely sat with only
    a date under them while the Month and Next 6 Months cards beside them read as finished.

    This fills them from the transit events the reading itself is built from - already calculated for the
    Saturn block on the same page in the `today` case, already translated by `describe_event`, and no AI call
    either way. A slow graha is preferred over the Moon, which changes sign every two and a bit days and is
    the least interesting thing in a week.
    """
    try:
        brief = today_brief if period == "today" else build_brief(rashi, period, now)
        events = brief.get("events") or []
        slow = [event for event in events if event["graha"]["key"] != "Moon"]
        # SOMETHING THIS CARD'S NEIGHBOURS ARE NOT ALREADY SAYING. The windows nest - a month sits
        # inside the six months, which sits inside the year - so the first slow event is very often
        # the SAME event, and two cards side by side carrying one identical sentence reads as a bug
        # rather than as a coincidence. Each card takes the first event nobody above it has used.
        taken = avoid or set()
        for event in (slow or events):
            line = words.describe_event(event, lang)
            if line and line not in taken:
                return line
        if slow or events:
            return words.describe_event((slow or events)[0], lang)
        # NO EVENT TODAY IS AN ORDINARY DAY, not a reason to show a bare date. A graha changes sign or
        # direction only now and then, so on most days this list is empty - which is exactly when the card
        # was left looking unfinished, and exactly what the first version of this got wrong. The Moon's
        # place is always there, always computed, and is what a panchang would lead with anyway.
        #
        # ONLY FOR THE SHORT WINDOWS, though. Where the Moon is right now is a fact about today; on a
        # card covering a year it would be a sentence that stops being true in two days, which is a
        # worse answer than the date alone. Those windows are long enough that they effectively always
        # have a slow-graha event in them, so this falls through only in a case that should not arise.
        return _moon_line(brief, lang) if period in ("today", "weekly") else None
    except Exception:  # noqa: BLE001 - a teaser must never be why a hub page fails to render
        return None


def _rashi_link(key: str, lang: str, labels: dict, page_key: str, **params) -> dict:
    names = i18n.rashi_names(key, lang)
    return {**names, "label": pages.fill(labels["rashi_label"], **names), "sub": pages.fill(labels["rashi_sub"], **names),
            "path": i18n.url_for(page_key, lang, rashi=key, **params)}


def _titles(kind: str, lang: str, fallback: pages.PageCopy, *args, year: int | None = None,
            month: str = "", covers: str = "") -> tuple[str, str, str]:
    """(title, h1, meta) from calc-engine's query-pattern templates; the page-config copy if a template is missing.

    `year` is the calendar year of a yearly page's window - the yearly templates print it, because the query
    is "<sign> rashifal 2027". It comes from the window, not from today, so a page cached before the
    20 November turnover keeps saying the year it was written for.

    `covers` is that window as months ("Sep 2026-Feb 2027"). Same rule and for the same reason: a 6-month page
    whose title said "Next 6 Months" was true forever and informative never, and it has to name the months the
    page was WRITTEN for rather than the months it happens to be read in."""
    try:
        if kind == "hub":
            return (words.hub_title(args[0], lang, covers), words.hub_h1(args[0], lang, covers),
                    words.hub_meta(args[0], lang, covers))
        return (words.page_title(*args, lang, year, month, covers),
                words.page_h1(*args, lang, year, month, covers),
                words.page_meta(*args, lang, year, month, covers))
    except (KeyError, AttributeError):
        if kind == "hub":
            return fallback.title, fallback.h1, fallback.meta_description
        period = args[1]
        return fallback.extra[f"title_{period}"], fallback.extra[f"h1_{period}"], fallback.extra[f"meta_{period}"]


# ---- facts (engine brief -> display rows) ---------------------------------------------------------


def _facts(brief: dict, language: str, rashi_label: str) -> dict:
    t = words.UI[language]
    start = brief["period"]["start_date"]
    facts = {
        "as_of": t["facts_as_of"].format(date=words.format_date(start, language), rashi=rashi_label),
        "positions": [{
            "graha": words.graha_name(p["graha"], language), "sign": words.sign_name(p["sign"], language),
            "nakshatra": words.nakshatra_name(p["nakshatra"], language), "house": p["house"],
            "motion": t["retrograde"] if p["retrograde"] else t["direct"], "retrograde": p["retrograde"],
        } for p in brief["positions_at_start"]],
        "events": [{
            "date": words.format_date(e["date"], language), "time": e["time_ist"],
            "text": words.describe_event(e, language),
        } for e in brief["events"]],
        "stays": [{
            "graha": words.graha_name(s["graha"], language), "sign": words.sign_name(s["sign"], language), "house": s["house"],
            "from": words.format_date(s["from"], language), "to": words.format_date(s["to"], language),
        } for s in brief.get("slow_graha_stays", [])],
        "saturn": _saturn_lines(brief["saturn"], language, rashi_label),
        "eclipses": _eclipse_lines(brief.get("eclipses") or (), language),
    }
    moon = _moon(brief, language)
    if moon:
        facts["moon"] = moon
    panchang = brief.get("panchang")
    if panchang:
        day = panchang["date"]
        until = lambda iso: f"{t['until']} {words.format_time(iso, language, day)}" if language == "en" \
            else f"{words.format_time(iso, language, day)} {t['until']}"
        facts["panchang"] = {
            "vara": words.weekday_name(dt.date.fromisoformat(day), language),
            "tithi": words.tithi_name(panchang["tithi"], language), "tithi_until": until(panchang["tithi"]["ends_at"]),
            "nakshatra": words.nakshatra_name(panchang["nakshatra"], language),
            "nakshatra_until": until(panchang["nakshatra"]["ends_at"]),
            "sunrise": words.format_time(panchang["sunrise"], language, day),
            "note": t["panchang_note"].format(place=words.place_name(panchang["place"]["name"], language)),
        }
    lucky = brief.get("lucky")
    if lucky:
        facts["lucky"] = {
            "colour": lucky["colour"][language], "colour_key": lucky["colour"]["key"], "number": lucky["number"],
            "why": t["lucky_" + lucky["basis"]].format(graha=words.graha_name(lucky["graha"], language)),
        }
    return facts


def _moon(brief: dict, language: str) -> dict | None:
    t = words.UI[language]
    moon = brief.get("moon_at_sunrise") or brief.get("moon_at_start")
    if not moon:
        return None
    nakshatra = (brief.get("panchang") or {}).get("nakshatra") or moon.get("nakshatra")
    return {
        "line": t["moon_line"].format(sign=words.sign_name(moon["sign"], language), house=moon["house"],
                                      nakshatra=words.nakshatra_name(nakshatra, language)),
        "favourable": moon["chandra_bala"]["favourable"],
        "bala": t["chandra_bala_good"] if moon["chandra_bala"]["favourable"] else t["chandra_bala_quiet"],
    }


def _eclipse_lines(eclipses, language: str) -> list[str]:
    """One line per eclipse, saying what a reader HERE will see.

    These facts are identical for all twelve rashis - the magnitude and the time do not depend on
    the sign - so they are rendered once from the engine rather than written into each reading. The
    prose then says only what the eclipse means for that house, which is the part that differs.
    """
    from app.rashifal.brief import india_kind_of

    t, out = words.UI[language], []
    for one in eclipses:
        # DERIVED WHEN ABSENT. A page stores the brief it was written from, so a reading saved
        # before this field existed carries a brief without it - and defaulting to "none" told
        # every reader that every eclipse was invisible from India, which is its own wrong answer.
        kind = one.get("india_kind") or india_kind_of(one)
        key = {"partial": "eclipse_partial", "total": "eclipse_partial",
               "penumbral": "eclipse_penumbral"}.get(kind, "eclipse_none")
        out.append(t[key].format(
            date=words.format_date(one["date"], language),
            house=one["house_from_rashi"],
            ordinal=words.ordinal_oblique(one["house_from_rashi"], language),
            what=t.get("eclipse_" + one["what"], ""),
            percent=round(one.get("india_magnitude", 0) * 100),
            time=one.get("india_time_ist", "")))
    return out


def _saturn_lines(saturn: dict, language: str, rashi_label: str) -> list[str]:
    t, lines = words.UI[language], []
    fmt = lambda value: words.format_date(value, language)
    sade_sati, house = saturn["sade_sati"], saturn["saturn_house_from_moon"]
    if sade_sati["active"] and sade_sati["current_phase_period"]:
        period = sade_sati["current_phase_period"]
        lines.append(t["sade_sati_active"].format(rashi=rashi_label, phase=t["phase_" + sade_sati["phase"]], house=house,
                                                  start=fmt(period["start"]), end=fmt(period["end"])))
    elif sade_sati["cycle"]["which"] == "current":
        lines.append(t["sade_sati_paused"].format(rashi=rashi_label, start=fmt(sade_sati["cycle"]["start"]),
                                                  end=fmt(sade_sati["cycle"]["end"])))
    else:
        lines.append(t["sade_sati_inactive"].format(rashi=rashi_label, house=house))
    dhaiya = saturn["dhaiya"]
    if dhaiya["active"]:
        lines.append(t["dhaiya_active"].format(house=house, start=fmt(dhaiya["period"]["start"]), end=fmt(dhaiya["period"]["end"])))
    return lines


#: Short, stable anchors per generated section, newest first. The first is the id the section carries;
#: the rest are extra anchors on the same section, so a link to any of them lands in the right place.
#: The OLD ids (career-money, love-family, health-wellbeing) are kept as aliases: they are in the wild,
#: on this site and possibly in somebody's bookmark, and a rename that breaks them buys nothing.
_SECTION_ANCHORS = {
    "career_money": ("career", "money", "career-money"),
    "love_family": ("relationships", "love-family"),
    "health_wellbeing": ("health", "health-wellbeing"),
    # The long-form sections (yearly and monthly). The first anchor of each is the one older links
    # and the on-page jump list use, so it stays short and stable.
    "career_job": ("career-job", "job"),
    "business": ("business",),
    "money_finance": ("money", "finance"),
    "property_vehicle": ("property", "vehicle"),
    "education": ("education", "exams"),
    "foreign_travel": ("foreign-travel", "travel"),
    "love": ("love",),
    "marriage": ("marriage",),
    "family": ("family",),
    "santati": ("santati", "children"),
    "bhagyoday": ("bhagyoday",),
    "best_periods": ("best-periods",),
    "caution_periods": ("caution-periods",),
    "upay": ("upay", "remedies"),
    "gemstone": ("gemstone",),
}


#: The chips, in reading order, with the glyph each one uses. career and money both point at the one
#: generated section: the model writes career_money as a single piece, and splitting it would mean
#: changing what it writes, which this item explicitly does not do. Two chips landing in the same place
#: is honest - a reader looking for money finds the paragraph that discusses it.
JUMP_CHIPS = (
    ("career", "career", "g-surya"),
    ("money", "career", "g-shukra"),
    ("relationships", "relationships", "g-chandra"),
    ("health", "health", "g-mangal"),
    ("dates", "dates", "g-guru"),
    ("remedy", "remedy", "g-shani"),
)


#: The topics an ask link may carry, derived from the chips so the two cannot drift apart. The route that
#: records them checks against this set before anything is stored: the value arrives in a URL anyone can
#: edit, and `detail` on an event is meant to be structural.
#: Topics that may ride to the astrologer on a link. The rashifal chips give most of them; a page built
#: around one question adds its own, and "marriage" is the shadi-kab-hogi tool's. Kept as one set so the
#: consultation route has a single thing to check against.
PAGE_TOPICS = frozenset({"marriage"})
#: The chips a MONTHLY or YEARLY page shows. Those pages carry sixteen sections, so the six chips
#: above point at anchors (#career, #relationships) that are not on the page at all - a chip row
#: that scrolls nowhere. Eight is as many as fits on a phone without wrapping twice.
LONG_JUMP_CHIPS = (
    ("career", "career-job", "g-surya"),
    ("money", "money", "g-shukra"),
    ("property", "property", "g-mangal"),
    ("education", "education", "g-budha"),
    ("marriage", "marriage", "g-chandra"),
    ("health", "health", "g-mangal"),
    ("dates", "dates", "g-guru"),
    ("remedy", "upay", "g-shani"),
)

#: Topics an ask link may carry. They ride in a URL anyone can edit and are stored as structural
#: detail, so the route checks against this set. A topic is always hyphen-free: `job`, not
#: `career-job`, because the funnel's own validation is [a-z]+.
ASK_TOPICS = (frozenset(anchor for _key, anchor, _icon in JUMP_CHIPS)
              | frozenset({"job", "money", "marriage", "upay", "business", "education",
                           "property", "travel", "family", "children", "love"})
              | PAGE_TOPICS)


def _jump_chips(language: str, period: str = "", reading: dict | None = None) -> list[dict]:
    """The chip row, filtered to anchors the page actually renders.

    The period alone is not enough to decide. A monthly page's stored reading may still be the
    three-section text generated before the long sections existed, and a chip row pointing at
    #career-job on a page whose section is #career scrolls nowhere. So the period picks the
    CANDIDATES and the reading decides which of them survive - which also means a page that is
    half-migrated still gets a working chip row rather than a broken one.
    """
    t = words.UI[language]
    chips = LONG_JUMP_CHIPS if period in ("monthly", "yearly") else JUMP_CHIPS
    out = [{"key": key, "anchor": anchor, "icon": icon, "label": t[f"jump_{key}"]}
           for key, anchor, icon in chips]
    if reading is None:
        return out
    present = {anchor for section in reading.get("sections", []) for anchor in section["anchors"]}
    present |= {"dates", "remedy"}          # rendered outside the section loop, always there
    # Both sets are tried and the one that fits this reading better wins. No threshold to tune:
    # a sixteen-section reading matches the long set almost entirely, a three-section one matches
    # the short set, and a page carrying something in between still gets the fuller row.
    def fitting(candidates):
        return [{"key": k, "anchor": a, "icon": i, "label": t[f"jump_{k}"]}
                for k, a, i in candidates if a in present]

    first, second = fitting(chips), fitting(JUMP_CHIPS if chips is LONG_JUMP_CHIPS else LONG_JUMP_CHIPS)
    return first if len(first) >= len(second) else second


def _ask_link(topic: str, rashi: str, language: str) -> dict | None:
    """"Ask about YOUR Makar career" - one small link per section, to the astrologer, about that topic
    for this sign.

    The topic rides on the query string so the funnel can tell which section sent the reader. It carries
    no reader in it: a topic from a fixed set of six, and nothing else.
    """
    names = i18n.rashi_names(rashi, language)
    phrase = words.UI[language].get(f"ask_{topic}")
    if not phrase:
        return None
    label = pages.fill(phrase, **names)
    return {"path": f"{i18n.url_for('consultation', language)}?topic={topic}", "label": label}


def _month_links(months: list[dict], rashi: str, language: str, year: str) -> list[dict]:
    """The yearly page's twelve month blocks, each linking to its dated page when one exists.

    Only when a reading has been written for it in THIS language: a link to a page with nothing on
    it is worse than no link, and the reader who follows it has been sent nowhere.
    """
    out = []
    for position, month in enumerate(months, 1):
        if not month.get("text"):
            continue
        row = dict(month)
        period = f"{year}-{position:02d}"
        if period in DATED_MONTHS:
            stored = store.get_page(rashi, period)
            if stored and language in ((stored.get("content") or {})):
                row["path"] = i18n.url_for("rashifal-reading", language, rashi=rashi, period=period)
        out.append(row)
    return out


def _section_order(period: str, content: dict) -> tuple[str, ...]:
    """Every section this reading carries, in a sensible order.

    The period's own list comes first, then anything else the stored reading has - a reading
    written before the long sections existed, or one written after a section was retired. A page
    must print what it was given; a list of expected ids is for generating and checking, never for
    deciding what a reader sees.
    """
    have = content.get("sections") or {}
    # A reading written in the three-section shape reads in ITS order - career and money, then love
    # and family, then health. Leading with health because that id also happens to be in the
    # long-form list puts the page's weakest section first.
    # base_period: a dated month ("2027-01") has a monthly page's sixteen sections.
    shape = base_period(period)
    legacy = [key for key in SECTION_IDS if key not in sections_for(shape)]
    order = (SECTION_IDS if any(have.get(key) for key in legacy) else ()) + tuple(sections_for(shape))
    seen, out = set(), []
    for key in (*order, *have):
        if key not in seen:
            seen.add(key)
            out.append(key)
    return tuple(out)


def _reading(stored: dict, language: str) -> dict | None:
    """The stored AI reading for display; key dates are joined to the brief it was written from."""
    content = stored["content"].get(language)
    if not content:
        return None
    events = {event["id"]: event for event in stored["brief"]["events"]}
    t = words.UI[language]
    return {
        "headline": content["headline"],
        # THE SUMMARY WAS GENERATED AND NEVER SHOWN. Every reading has carried one since the first
        # version - the checker even enforces a 70-word limit on it - and no template rendered it. It is
        # the ten-second read, which is the thing most readers want, and we were paying for it and
        # throwing it away.
        "summary": content.get("summary") or "",
        "overview": content["overview"],
        "sections": [{"id": s, "heading": t[s], "paragraphs": content["sections"][s],
                      # The anchors a reader and a search engine can link to. career_money is ONE
                      # generated section, so it answers at both #career and #money rather than being
                      # split - splitting it would mean changing what the model writes, which this item
                      # explicitly does not do.
                      "anchors": _SECTION_ANCHORS[s]}
                     # WHAT THE READING ACTUALLY HAS, not a fixed list: a yearly page carries
                     # sixteen sections and a daily one three, and a stored reading from before a
                     # section was added simply does not have it. Printing an empty heading for a
                     # section nobody wrote is worse than leaving it out.
                     # WHAT THE READING HAS, not what its period is supposed to have. The period
                     # gives the ORDER; the content decides what is printed. Reading the period's
                     # list alone silently dropped career_money and love_family from every stored
                     # monthly page - those ids are not in the long-form list, so two of three
                     # sections vanished from a live page the moment monthly grew to sixteen.
                     for s in _section_order(stored.get("period") or "", content)
                     if (content.get("sections") or {}).get(s)],
        # Whether the reading carries its own remedies section. The template keys the standalone
        # tip block on this: a page with sixteen sections already has one, and printing the tip too
        # repeated it almost verbatim.
        "has_upay": bool((content.get("sections") or {}).get("upay")),
        # One practical line under the Saturn status box. The box states the facts - which phase,
        # which dates - and this says what a reader is supposed to DO with them, which the facts
        # alone never answer.
        "saturn_note": content.get("saturn_note") or "",
        # [question, answer] pairs, answered from THIS page's own content. Rendered through the
        # site's own FAQ macro and its own FAQPage schema, not a third way of writing a list.
        "faq": [(pair[0], pair[1]) for pair in (content.get("faq") or ()) if len(pair) == 2],
        "key_dates": [{
            "date": words.format_date(events[item["event_id"]]["date"], language),
            "event": words.describe_event(events[item["event_id"]], language),
            "note": item["note"],
        } for item in content["key_dates"] if item["event_id"] in events],
        "tip": content["tip"],
        # MONTH BY MONTH, ON THE YEARLY PAGE. Absent from every other period and from any yearly
        # reading written before the schema asked for it, so `.get` rather than a key - an older
        # stored page must keep rendering rather than 500.
        # EACH MONTH LINKS TO ITS OWN PAGE where one has been written. This is the yearly-to-monthly
        # half of the internal linking, and it is also what stops a dated page being an orphan: the
        # orphan guard caught /hi/rashifal/dhanu/january-2027 reachable from the sitemap and nothing
        # else, which is a page Google is told to crawl and no reader can find.
        "months": _month_links(content.get("months") or [], stored["rashi"], language,
                               str(stored["period_start"])[:4]),
        # The heading carries the year, and the year is the STORED window's - the same reason the
        # title does: a page still showing last year's reading must not head it with this year.
        "months_heading": t["months_heading"].format(year=str(stored["period_start"])[:4]),
        "range": words.format_range(stored["period_start"], stored["period_end"], language),
        "updated": words.format_timestamp(stored["generated_at"], language),
    }


def _period_links(rashi: str, lang: str, labels: dict, skip: str | None = None) -> list[dict]:
    links = [{"period": period, "label": labels[f"period_{period}"],
              "path": i18n.url_for("rashifal-reading", lang, rashi=rashi, period=period)}
             for period in i18n.PERIOD_KEYS if period != skip]
    # THE DECLARED DATED MONTHS, from every other period of the same rashi. Their only other inbound
    # link is the month block on the yearly page, and that block exists only when a yearly reading is
    # STORED - so a rashi whose yearly generation failed would take its twelve month pages down with
    # it, and the test suite (which runs on an empty store) could never see them reachable at all.
    #
    # A published URL should not depend on a database row for its way in. This link comes from the
    # declaration, so it is there whether or not anything has been generated yet.
    for month in _periods.DATED_MONTHS:
        if month == skip or lang not in (_periods.DATED_MONTH_LANGS.get(month) or ()):
            continue
        links.append({"period": month,
                      "label": words.period_label(month, lang),
                      "path": i18n.url_for("rashifal-reading", lang, rashi=rashi, period=month)})
    # THE PERMANENT YEAR PAGES, from the rolling yearly one. Somebody reading "this year" is the reader
    # most likely to want next year, and a page nothing links to is a page the crawler reaches late or
    # never. Only from the yearly reading, where it is the obvious next click rather than clutter.
    #
    # WHICHEVER OF THE TWO IS A PAGE IN THIS TREE. In English that is the per-rashi year page. In
    # Hindi and Marathi it 301s, so the link goes to the year HUB instead - "2027 for all twelve",
    # which is a real page and the one those trees still have.
    #
    # Gating this to English alone, as the first version did, stranded eight pages: the hi and mr
    # year hubs were reached through the per-rashi year pages' breadcrumbs, and those pages became
    # redirects. The hubs took their three gochar pages down with them. Nobody noticed because the
    # orphan guard was already red about the six festival pages - a red test hides the next failure,
    # which is the whole argument for the known-failure list in the deploy gate.
    if skip == "yearly":
        for year in i18n.YEAR_PAGES:
            links.append({
                "period": str(year),
                "label": pages.fill(labels["year_link"], year=str(year)),
                "path": (i18n.url_for("rashifal-year", lang, rashi=rashi, year=year)
                         if lang in i18n.YEAR_PAGE_LANGS
                         else i18n.url_for("rashifal-year-hub", lang, year=year)),
            })
    return links


# ---- daily + weekly hubs (all 12 rashis on one page) -----------------------------------------------------------


def _hub(request: Request, page_key: str, period: str):
    lang, _ = _resolve(request, page_key)
    now = _now()
    window = window_for(period, now)
    copy = pages.get(page_key, lang)
    # A hub is about all twelve rashis, so a label written with {rashi} becomes the language's "your" here.
    # ONLY the CTA labels: `pending_summary` carries {rashi} as well and is filled per CARD below, with the
    # real rashi name - filling it here would put "your rashi" on all twelve cards.
    raw_labels = dict(copy.extra)
    labels = {key: (pages.fill(text, rashi=raw_labels.get("rashi_any", "")) if key.startswith("cta_") else text)
              for key, text in raw_labels.items()}
    try:
        rows = store.hub_rows(period)
    except Exception:  # noqa: BLE001 - a hub must render from engine facts even if the store is unavailable
        rows = {}
    cards, newest = [], None
    for key in i18n.rashis_by_demand(lang):
        card = _rashi_link(key, lang, labels, "rashifal-reading", period=period)
        row = rows.get(key)
        current = bool(row) and row["period_start"] == window.key
        card["headline"] = (row["headlines"].get(lang) or None) if current else None
        card["summary"] = (row["summaries"].get(lang) or None) if current else None
        if current and card["summary"]:
            newest = max(newest or row["generated_at"], row["generated_at"])
        else:  # facts fallback: never an empty card, and never an AI call
            moon = _moon(build_brief(key, period, now), lang)
            card["fact"] = f"{moon['bala']}. {moon['line']}" if moon else None
            card["pending"] = pages.fill(labels["pending_summary"], **i18n.rashi_names(key, lang))
        card["hub_path"] = i18n.url_for("rashifal-rashi", lang, rashi=key)
        cards.append(card)
    # The week the hub is about, in this tree's own words, and the SAME string the page prints as its range -
    # a title that dated the week differently from the line under the heading would be one of them wrong.
    # THE FESTIVAL PAGES GET THEIR INBOUND LINK HERE, and only while the festival is still ahead. Six
    # pages were reachable from the sitemap alone, which is how a page stays "discovered, not indexed".
    # This hub is the busiest indexed page on the site. After the date the link goes, because a muhurat
    # that has passed is not something to send a reader to.
    festival_links = _upcoming_festivals(lang, now)
    week = words.format_range(window.start_date.isoformat(), window.end_date.isoformat(), lang, compact=True)
    title, h1, meta = _titles("hub", lang, copy, period, covers=week if period == "weekly" else "")
    other_key = "rashifal-weekly" if page_key == "rashifal-hub" else "rashifal-hub"
    context = page_context(page_key, lang)
    crumbs = [(context["ui"]["home"], context["home_path"]), (context["ui"]["nav_rashifal"], i18n.url_for("rashifal-hub", lang))]
    if page_key == "rashifal-weekly":
        crumbs.append((copy.nav_label, i18n.url_for(page_key, lang)))
    context.update(
        copy=copy, labels=labels, title=title, h1=h1, meta_description=meta, period=period, cards=cards,
        festival_links=festival_links,
        # The weekly hub prints the same compact range its title carries; the daily hub keeps the full form,
        # which is one date and has nothing to compact.
        current_range=(week if period == "weekly" else
                       words.format_range(window.start_date.isoformat(), window.end_date.isoformat(), lang)),
        range_label=labels["date_label"] if period == "today" else labels["week_label"],
        updated=words.format_timestamp(newest, lang) if newest else None,
        other_hub={"path": i18n.url_for(other_key, lang),
                   "label": labels["weekly_link"] if other_key == "rashifal-weekly" else labels["hub_link"]},
        crumbs=crumbs[:-1], ad_slots=AD_SLOTS,
        json_ld=[_json_ld({"@context": "https://schema.org", "@type": "CollectionPage", "name": h1, "description": meta,
                           "url": context["canonical"], "inLanguage": i18n.HTML_LANG[lang], "isAccessibleForFree": True,
                           "dateModified": (dt.datetime.fromisoformat(newest) if newest else window.start)
                           .astimezone(dt.timezone.utc).isoformat(timespec="seconds")}),
                 _json_ld(_breadcrumbs(crumbs))],
    )
    modified = dt.datetime.fromisoformat(newest) if newest else window.start
    return _respond(request, "rashifal_index.html", context, last_modified=modified)


def daily_hub(request: Request):
    return _hub(request, "rashifal-hub", "today")


def weekly_hub(request: Request):
    return _hub(request, "rashifal-weekly", "weekly")


# ---- one rashi: its five permanent period pages --------------------------------------------------------------------


def rashi_hub(request: Request):
    lang, params = _resolve(request, "rashifal-rashi")
    rashi = params["rashi"]
    now = _now()
    names = i18n.rashi_names(rashi, lang)
    copy = pages.get("rashifal-rashi", lang, **names)
    labels = _labels(copy, names)
    stored = store.list_pages()
    today_brief = build_brief(rashi, "today", now)
    cards = []
    used_lines: set[str] = set()
    for link in _period_links(rashi, lang, labels):
        window = window_for(link["period"], now)
        row = stored.get((rashi, link["period"]))
        headline = None
        if row and row["period_start"] == window.key:
            page = store.get_page(rashi, link["period"])
            headline = (page["content"].get(lang) or {}).get("headline")
        if not headline:
            headline = _engine_teaser(rashi, link["period"], lang, now, today_brief, avoid=used_lines)
        if headline:
            used_lines.add(headline)
        _, h1, _ = _titles("page", lang, pages.get("rashifal-reading", lang, **names), rashi, link["period"],
                           year=window.year, month=words.month_name(window.start_date.month, lang),
                           covers=words.date_range(window.start_date, window.end_date))
        cards.append({**link, "title": h1, "headline": headline,
                      "range": words.format_range(window.start_date.isoformat(), window.end_date.isoformat(), lang)})
    saturn = today_brief["saturn"]
    context = page_context("rashifal-rashi", lang, rashi=rashi)
    crumbs = [(context["ui"]["home"], context["home_path"]), (context["ui"]["nav_rashifal"], i18n.url_for("rashifal-hub", lang)),
              (labels["rashi_label"], i18n.url_for("rashifal-rashi", lang, rashi=rashi))]
    # WHERE THE NEW FAMILIES GET THEIR INBOUND LINK. The rashi-in-english and Sade Sati pages were built
    # in this batch and NOTHING linked to them - 42 pages reachable only from the sitemap, which is how a
    # page ends up "discovered, currently not indexed". This hub is the right parent: it is indexed, it
    # is linked from every reading of its sign, and both pages are about this same sign. Descriptive
    # anchors, not "click here": the anchor text is what tells a crawler what the page is.
    context.update(
        copy=copy, labels=labels, names=names, cards=cards, crumbs=crumbs[:-1],
        symbol=_symbol(rashi, lang, names),
        more_about_rashi=[
            {"path": i18n.url_for("rashi-in-english", lang, rashi=rashi),
             "label": pages.fill(labels["in_english_link"], **names)},
            {"path": i18n.url_for("sade-sati-rashi", lang, rashi=rashi),
             "label": pages.fill(labels["sade_sati_link"], **names)},
            # The love rashifal for this sign. Same reasoning as the two above, and the same mistake
            # avoided: 36 of these shipped in the October batch with nothing linking to them.
            {"path": i18n.url_for("love-rashifal", lang, rashi=rashi),
             "label": pages.fill(labels["love_link"], **names)},
        ],
        saturn_lines=_saturn_lines(saturn, lang, names["rashi"]),
        others=[_rashi_link(key, lang, _link_labels("rashifal-rashi", lang), "rashifal-rashi")
                for key in i18n.rashis_by_demand(lang) if key != rashi],
        json_ld=[_json_ld({"@context": "https://schema.org", "@type": "CollectionPage", "name": copy.h1,
                           "description": copy.meta_description, "url": context["canonical"],
                           "inLanguage": i18n.HTML_LANG[lang], "isAccessibleForFree": True}),
                 _json_ld(_breadcrumbs(crumbs)),
                 *([_json_ld({**seo.faq_page(copy.faqs), "inLanguage": i18n.HTML_LANG[lang]})] if copy.faqs else [])],
    )
    return _respond(request, "rashifal_rashi.html", context)


# ---- one reading -------------------------------------------------------------------------------------------------------


def _faq_when(period: str, window, shown_year: int, language: str) -> str:
    """What the FAQ heading calls the period it is about.

    A monthly page's questions are about THAT MONTH, so the heading has to say so - it read
    "धनु राशि 2027: आम सवाल" on a January page, which is the year and not the month. A yearly page
    keeps naming the year, which is what its questions are about.

    The year used to be the literal "2027" inside all three labels, so every FAQ heading on the site
    would still have said 2027 in 2028 - a page dated by a constant nobody would think to grep for.
    It comes from the window the page is actually showing now.
    """
    if base_period(period) == "yearly":
        return str(shown_year)
    if is_dated_month(period):
        return words.period_label(period, language)        # "जनवरी 2027" / "जानेवारी 2027"
    # the rolling /masik, which is whichever month it is today
    return f"{words.month_name(window.start_date.month, language)} {window.start_date.year}"


def reading_page(request: Request):
    lang, params = _resolve(request, "rashifal-reading")
    rashi, period = params["rashi"], params["period"]
    now = _now()
    window = window_for(period, now)
    names = i18n.rashi_names(rashi, lang)
    copy = pages.get("rashifal-reading", lang, **names)
    labels, t = _labels(copy, names), words.UI[lang]
    rashi_label = names["rashi"]

    stored = store.get_page(rashi, period)
    reading = _reading(stored, lang) if stored else None
    if reading:
        # The ask link belongs to the SECTION, so it is attached here where both the reading and the
        # rashi are in hand rather than being threaded through the template.
        for section in reading["sections"]:
            # ONLY WHERE THERE IS A LABEL FOR IT. The three short-period sections each carry an
            # "ask about this" link; a yearly page has sixteen sections, and sixteen CTAs down one
            # page is not persuasion, it is noise. A section without a label simply has no link.
            # The TOPIC rides in a URL and is validated as [a-z]+, so "career-job" cannot be
            # one. Each section's anchor list carries a plain alternative ("job") for exactly this.
            plain = next((a for a in section["anchors"] if a.isalpha()), section["anchors"][0])
            ask = _ask_link(plain, rashi, lang)
            if ask:
                section["ask"] = ask
    is_current = bool(stored) and stored["period_start"] == window.key
    brief = stored["brief"] if (reading and is_current) else build_brief(rashi, period, now)
    modified = dt.datetime.fromisoformat(stored["generated_at"]) if reading else window.start

    # THE YEAR IN THE TITLE FOLLOWS THE READING, NOT THE CALENDAR.
    #
    # The yearly page turns over on 5 November, but turning over is a date and writing twelve rashis
    # in three languages is a batch job that can fail for one of them. Without this, a rashi whose
    # 2027 reading had not been written - or had been written in English and not yet in Marathi -
    # would serve a page titled 2027 over the 2026 text, which is worse than being a few days late:
    # a reader cannot tell, and neither can a crawler.
    #
    # So when the stored reading is for the previous window, or has nothing in this language, the
    # page keeps saying the year it is actually showing. It catches up by itself the moment the
    # content lands, per rashi and per language.
    shown_year = window.year
    if period == "yearly" and stored and reading and not is_current:
        try:
            shown_year = int(str(stored["period_start"])[:4])
        except (TypeError, ValueError):
            pass

    title, h1, meta = _titles("page", lang, copy, rashi, period, year=shown_year,
                              month=words.month_name(window.start_date.month, lang),
                              covers=words.date_range(window.start_date, window.end_date))
    context = page_context("rashifal-reading", lang, rashi=rashi, period=period)
    canonical = context["canonical"]
    # THE DATED MONTH IS THE CANONICAL ONE. /masik is whatever month it is today, so two URLs carry
    # the same reading whenever a dated page exists for the current month - and the dated one is the
    # address worth indexing, because it still means January in June. The rolling page keeps serving
    # (a reader who typed /masik gets an answer) and points its canonical at the dated page.
    #
    # Only when that month HAS a page. Pointing a canonical at a URL with nothing written on it
    # would ask Google to prefer an emptier page than the one it is looking at.
    if period == "monthly":
        current = f"{window.start_date.year}-{window.start_date.month:02d}"
        if current in DATED_MONTHS and store.get_page(rashi, current):
            canonical = site.base_url() + i18n.url_for(
                "rashifal-reading", lang, rashi=rashi, period=current)
    schema = {
        "@context": "https://schema.org", "@type": "Article" if reading else "WebPage",
        "headline" if reading else "name": h1, "description": meta, "inLanguage": i18n.HTML_LANG[lang],
        "mainEntityOfPage": canonical, "url": canonical, "isAccessibleForFree": True,
        "dateModified": modified.astimezone(dt.timezone.utc).isoformat(timespec="seconds"),
        "publisher": {"@type": "Organization", "name": site.SITE_NAME, "url": site.base_url() + "/"},
    }
    if reading:
        schema["datePublished"] = stored["first_published_at"]
        schema["author"] = {"@type": "Organization", "name": site.SITE_NAME}

    hub_path = i18n.url_for("rashifal-rashi", lang, rashi=rashi)
    crumbs = [(context["ui"]["home"], context["home_path"]), (context["ui"]["nav_rashifal"], i18n.url_for("rashifal-hub", lang)),
              (labels["rashi_label"], hub_path), (words.period_label(period, lang), i18n.url_for("rashifal-reading", lang, rashi=rashi, period=period))]
    context.update(
        # The page's own title, never a reader's anything - app/web/sharing.py refuses to carry more.
        share=sharing.share(i18n.url_for("rashifal-reading", lang, rashi=rashi, period=period),
                            "rashifal", lang, title=h1),
        canonical=canonical,
        copy=copy, labels=labels, language=lang, t=t, names=names, rashi_label=rashi_label, period=period,
        # NAMES THE MONTH for a dated page. labels[f"period_{period}"] has no entry for "2027-01",
        # and "मासिक" would be the wrong word anyway: january-2027 exists so a reader can see which
        # month they are reading.
        period_label=words.period_label(period, lang), title=title, h1=h1, meta_description=meta,
        current_range=words.format_range(window.start_date.isoformat(), window.end_date.isoformat(), lang),
        range_label=labels["date_label"] if period == "today" else t["period_covers"],
        reading=reading, stale=bool(reading) and not is_current,
        facts=_facts(brief, lang, rashi_label),
        facts_heading=t["facts_heading"].format(rashi=rashi_label),
        house_heading=t["col_house"].format(rashi=rashi_label),
        jump_chips=_jump_chips(lang, base_period(period), reading),
        remedy_ask=_ask_link("remedy", rashi, lang),
        # The gemstone section's standing caveat links here. Two other routes already passed this;
        # the reading page did not, so the note silently never rendered - an undefined name in a
        # Jinja condition is simply falsy.
        kundali_path=i18n.url_for("kundali", lang),
        other_periods=_period_links(rashi, lang, labels, skip=base_period(period)),
        other_rashis=[_rashi_link(key, lang, _link_labels("rashifal-reading", lang), "rashifal-reading", period=period)
                      for key in i18n.rashis_by_demand(lang) if key != rashi],
        all_signs={"path": i18n.url_for("rashifal-weekly" if period == "weekly" else "rashifal-hub", lang),
                   "label": labels["weekly_link"] if period == "weekly" else labels["hub_link"]},
        crumbs=crumbs[:-1], ad_slots=AD_SLOTS,
        faq_heading=t["faq_heading"].format(rashi=rashi_label, when=_faq_when(period, window, shown_year, lang)),
        saturn_note_label=t["saturn_note_label"],
        # THE SCHEMA MIRRORS THE VISIBLE FAQ and is omitted when there is none. FAQPage markup for
        # questions a reader cannot see on the page is exactly what the guidelines call out.
        json_ld=([_json_ld(schema), _json_ld(_breadcrumbs(crumbs))]
                 + ([_json_ld(seo.faq_page(reading["faq"]))] if reading and reading.get("faq") else [])),
    )
    return _respond(request, "rashifal_page.html", context, last_modified=modified)


def year_hub_page(request: Request):
    """/horoscope/2027 - the whole year for all twelve, which "rashifal 2027" is actually asking for.

    The per-rashi pages answer "my sign in 2027"; this one answers "2027". It carries the year's slow
    transits once (they are the same sky for everybody), the year's eclipses, and twelve cards into
    the per-rashi pages - where the house each transit falls in is what differs.
    """
    lang, params = _resolve(request, "rashifal-year-hub")
    year = int(params["year"])
    copy = pages.get("rashifal-year-hub", lang, year=str(year))
    labels = {key: pages.fill(text, year=str(year)) for key, text in (copy.extra or {}).items()}

    from app.engine import eclipses as eclipse_engine
    from app.web import gochar_pages

    cards = []
    for key in i18n.rashis_by_demand(lang):
        names = i18n.rashi_names(key, lang)
        cards.append({
            "rashi": key,
            "name": names["rashi"],
            "latin": names["latin"],
            "label": pages.fill(labels["card_cta"], rashi=names["latin"], year=str(year)),
            # STRAIGHT TO THE PAGE, not to a 301. In hi and mr the per-rashi year URL redirects to
            # the rolling yearly reading, so the hub links there directly - twelve cards into twelve
            # redirects is a hop a reader and a crawler both pay for nothing.
            "path": (i18n.url_for("rashifal-year", lang, rashi=key, year=year)
                     if lang in i18n.YEAR_PAGE_LANGS
                     else i18n.url_for("rashifal-reading", lang, rashi=key, period="yearly")),
        })

    # The eclipses, named in this tree and with the penumbral note where it applies. The engine says
    # what is true; the copy says what it is called and whether sutak applies.
    eclipse_rows = []
    for one in eclipse_engine.eclipses(year):
        # THE SIGN, NAKSHATRA AND CITY NAMES IN THIS TREE. The engine returns both scripts for the
        # first two and the site's language check refuses Latin words in a Devanagari page - which
        # is what caught "Makara / Dhanishta" sitting in the middle of the Hindi one.
        deva = lang in ("hi", "mr")
        eclipse_rows.append({
            **one,
            "sign_label": one["sign"]["devanagari"] if deva else one["sign"]["name"],
            "nakshatra_label": one["nakshatra"]["devanagari"] if deva else one["nakshatra"]["name"],
            "cities": tuple({**city, "label": eclipse_engine.city_name(city["city"], lang)}
                            for city in one["cities"]),
            "kind_label": eclipse_engine.full_name(one, lang),
            "note": (eclipse_engine.PENUMBRAL_NOTE[lang]
                     if one["what"] == "lunar" and one["kind"] == "penumbral" else ""),
        })

    path = i18n.url_for("rashifal-year-hub", lang, year=year)
    context = page_context("rashifal-year-hub", lang, year=str(year))
    crumbs = [(context["ui"]["home"], context["home_path"]),
              (context["ui"]["nav_rashifal"], i18n.url_for("rashifal-hub", lang)),
              (copy.h1, path)]
    context.update(
        copy=copy, labels=labels, year=year, cards=cards, eclipses=eclipse_rows,
        title=copy.title, h1=copy.h1, meta_description=copy.meta_description,
        transits=year_facts.slow_graha_stays(year),
        # THE THREE GOCHAR PAGES. Without this they were reachable only from the sitemap - the third
        # set of orphans this week, caught by the same guard each time - and the hub is where a
        # reader asking about the year would look for them anyway.
        gochar_links=[{
            "slug": slug,
            "label": gochar_pages.COPY[lang]["dates_heading"].format(
                native=gochar_pages.GRAHA_LABELS[slug][lang][0], year=year),
            "path": i18n.url_for("gochar", lang, graha=slug, year=year),
        } for slug in i18n.GOCHAR_GRAHAS],
        kundali_path=i18n.url_for("kundali", lang),
        hub_path=i18n.url_for("rashifal-hub", lang),
        crumbs=crumbs, ad_slots=AD_SLOTS,
        json_ld=[_json_ld(_breadcrumbs(crumbs))],
    )
    return _respond(request, "rashifal_year_hub.html", context)


#: Trees where /<rashi>/<year> 301s to the rolling yearly reading instead of being its own page.
#: The complement of i18n.YEAR_PAGE_LANGS - every tree is in exactly one, which the tests assert.
YEAR_PAGE_REDIRECT_LANGS = tuple(l for l in i18n.LANGS if l not in i18n.YEAR_PAGE_LANGS)


def year_page_redirect(request: Request):
    """/hi/rashifal/dhanu/2027 -> /hi/rashifal/dhanu/varshik, permanently.

    THE TWO URLS SAID THE SAME THING AND COMPETED FOR THE SAME QUERY. The rolling yearly page
    carries the written reading AND the year's transit table; this one carried the table alone,
    about four hundred words, and its FAQ promised a written reading that by then existed one URL
    away. It is also the URL Google sends people to, so the thin page was the first thing they saw.

    301 rather than a canonical: a canonical is a hint and leaves the thin page serving, and there is
    nothing here the target does not already have. The year is in the target's title and <h1>, so the
    query it was ranking for still matches.
    """
    # NOT THROUGH _resolve: that answers only for the registry's published paths, and these URLs are
    # deliberately no longer published. Resolving a redirect through the table that says it is gone
    # returned a 404 for all twenty-four of them - the redirect has to work BECAUSE the page is
    # unpublished, not in spite of it.
    #
    # The tree comes from the route this handler was registered under, and the rashi from the path,
    # validated through rashi_key so only the twelve answer and anything else is a 404 as before.
    lang = request.scope["route"].name.rsplit("-", 1)[-1]
    try:
        rashi = i18n.rashi_key(request.path_params["rashi"])
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown rashi") from None
    # ONLY A YEAR THAT EXISTS. Without this the route 301s every integer: /hi/rashifal/mesh/2099 and
    # /hi/rashifal/mesh/9999 both answered "moved permanently", which invents an unbounded space of
    # URLs that all claim to have existed. The English tree got this right for free by going through
    # _resolve, and the test that caught it - test_a_year_without_a_page_is_not_served - says why in
    # one line: "a page for 2099 would be an empty promise with a real URL". A 301 to one is worse,
    # because it asserts the promise was once kept.
    if int(request.path_params["year"]) not in i18n.YEAR_PAGES:
        raise HTTPException(status_code=404, detail="no page for that year")
    return RedirectResponse(
        i18n.url_for("rashifal-reading", lang, rashi=rashi, period="yearly"), status_code=301)


def year_page(request: Request):
    """/horoscope/aries/2027 - a permanent address for one year, which the rolling yearly page has not got.

    The written reading is the store's when there is one. What is always here is the year's slow transits
    as HOUSES from this rashi, because that is the part that is true before anybody writes a word, and it
    is different for each of the twelve from the same sky.
    """
    lang, params = _resolve(request, "rashifal-year")
    rashi, year = params["rashi"], int(params["year"])
    names = i18n.rashi_names(rashi, lang)
    copy = pages.get("rashifal-year", lang, **names, year=str(year))
    labels = _labels(copy, names)

    index = i18n.RASHI_KEYS.index(rashi) + 1
    facts = year_facts.for_rashi(index, year)
    path = i18n.url_for("rashifal-year", lang, rashi=rashi, year=year)

    context = page_context("rashifal-year", lang, rashi=rashi, year=str(year))
    # THE YEAR HUB IS IN THE CHAIN, which is both true and the thing that stops it being an orphan:
    # without it the hub was reachable only from the sitemap, the same guard that caught the by-name
    # matching pages and the nakshatra hub. This page is one rashi's view of a year that has its own
    # page, so the breadcrumb was wrong before as well as incomplete.
    year_hub_path = i18n.url_for("rashifal-year-hub", lang, year=year)
    year_hub_copy = pages.get("rashifal-year-hub", lang, year=str(year))
    crumbs = [(context["ui"]["home"], context["home_path"]),
              (context["ui"]["nav_rashifal"], i18n.url_for("rashifal-hub", lang)),
              (year_hub_copy.nav_label, year_hub_path),
              (names["rashi"], i18n.url_for("rashifal-rashi", lang, rashi=rashi)),
              (copy.h1, path)]
    context.update(
        copy=copy, labels=labels, names=names, rashi=rashi, year=year, facts=facts,
        year_hub_path=year_hub_path, year_hub_label=year_hub_copy.nav_label,
        title=copy.title, h1=copy.h1, meta_description=copy.meta_description,
        phase_labels={key: labels[f"phase_{key}"] for key in ("rising", "peak", "setting")},
        rolling_path=i18n.url_for("rashifal-reading", lang, rashi=rashi, period="yearly"),
        rashi_path=i18n.url_for("rashifal-rashi", lang, rashi=rashi),
        sade_path=i18n.url_for("sade-sati-rashi", lang, rashi=rashi),
        kundali_path=i18n.url_for("kundali", lang),
        chat_path=i18n.url_for("consultation", lang),
        crumbs=crumbs, ad_slots=AD_SLOTS,
        json_ld=[_json_ld(_breadcrumbs(crumbs))],
    )
    return _respond(request, "rashifal_year.html", context)


# Explicit order per tree: hub, WEEKLY hub, then the parameterised routes.
for _lang in i18n.LANGS:
    _root = i18n.RASHIFAL_ROOT[_lang]
    router.add_api_route(i18n.url_for("rashifal-hub", _lang), daily_hub, methods=["GET"], response_class=HTMLResponse,
                         name=f"rashifal-hub-{_lang}")
    router.add_api_route(i18n.url_for("rashifal-weekly", _lang), weekly_hub, methods=["GET"], response_class=HTMLResponse,
                         name=f"rashifal-weekly-{_lang}")
    # BEFORE the "/{rashi}" route, and typed as an int: "/horoscope/2027" must not be read as a rashi
    # slug. Starlette matches in registration order, so the year hub has to be added first.
    router.add_api_route(_root + "/{year:int}", year_hub_page, methods=["GET"],
                         response_class=HTMLResponse, name=f"rashifal-year-hub-{_lang}")
    router.add_api_route(_root + "/{rashi}", rashi_hub, methods=["GET"], response_class=HTMLResponse,
                         name=f"rashifal-rashi-{_lang}")
    # BEFORE the period route, and typed as an int, so "/horoscope/aries/2027" cannot be read as a
    # period slug and "/horoscope/aries/today" cannot be read as a year. Starlette matches in the order
    # routes are added, so this one has to come first; relying on an unknown period 404ing would make the
    # two families depend on which was registered when.
    # The year URL is a PAGE in i18n.YEAR_PAGE_LANGS and a 301 everywhere else. Registered under
    # the same name in both cases, so url_for and _resolve work either way and the redirect knows
    # which rashi it was asked for.
    router.add_api_route(_root + "/{rashi}/{year:int}",
                         year_page if _lang in i18n.YEAR_PAGE_LANGS else year_page_redirect,
                         methods=["GET"],
                         response_class=HTMLResponse if _lang in i18n.YEAR_PAGE_LANGS else RedirectResponse,
                         name=f"rashifal-year-{_lang}")
    router.add_api_route(_root + "/{rashi}/{period}", reading_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"rashifal-reading-{_lang}")


def _upcoming_festivals(lang: str, now) -> list[dict]:
    """The festival pages whose date has not passed, with a dated anchor. Empty once they have.

    Cheap on purpose: the dates come from the festival engine, which caches its ephemeris scan, and the
    whole thing is wrapped because a hub page must not fail over a decorative link.
    """
    try:
        from app.engine import festivals

        from app.web.festival_pages import NAMES

        today = now.date() if hasattr(now, "date") else now
        out = []
        # ALWAYS LINKED, because there is always a next date. This used to skip a festival whose
        # date had passed, which is how /muhurat/dhanteras-2026 and its five siblings became pages
        # nothing on the site pointed at - indexed, answering, and unreachable.
        for festival in i18n.FESTIVAL_SLUGS:
            year, window = festivals.upcoming(festival, today, "Delhi")
            when = window.get("date")
            if not when:
                continue
            out.append({"path": i18n.url_for("festival", lang, festival=festival),
                        "label": f"{NAMES[festival][lang]} {year}: "
                                 f"{words.format_date(when.isoformat(), lang)}"})
        return out
    except Exception:  # noqa: BLE001 - a hub page is not worth failing over a link
        log.warning("could not build the festival links for the %s hub", lang, exc_info=True)
        return []
