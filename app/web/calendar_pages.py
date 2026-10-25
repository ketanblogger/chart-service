"""Diwali, the year's calendar, and the ekadashis - all computed, none written.

NOT `festival_pages.py`, which already exists and serves /muhurat/{festival}-{year}: the per-city
puja windows for one named festival on one named evening. This module is the year-wide view -
every festival's date, the ekadashis, the amavasyas and the purnimas - and it imports that module's
answer for Dhanteras and Lakshmi puja rather than computing those two a second way.

The dates come from app/engine/hindu_calendar.py and the Lakshmi puja windows from
app/engine/festivals.py, which is the module that decides an evening observance by the tithi at
pradosh. Nothing on these pages is stored or generated, so a year rolls over by adding it to
i18n.YEAR_PAGES and nothing else.

WHERE PANCHANGS DISAGREE, THE PAGE SAYS SO rather than picking one and sounding certain. A family
acts on these dates. Two things are said out loud: that a festival is dated by the tithi at sunrise
while an evening observance is decided at pradosh, and that local panchangs can differ by a day.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from app.engine import festivals as festival_engine
from app.engine import hindu_calendar as calendar
from app.web import i18n
from app.web.muhurat_year import MONTH_NAMES

CITIES = festival_engine.MAJOR_CITIES

TITLES = {
    "diwali-year": {
        "en": ("Diwali {year}: date and Lakshmi Puja muhurat",
               "Diwali {year} - Date and Lakshmi Puja Muhurat by City"),
        "hi": ("दिवाली {year}: तारीख़ और लक्ष्मी पूजा मुहूर्त",
               "दिवाली {year} - Diwali Date aur Lakshmi Puja Muhurat"),
        "mr": ("दिवाळी {year}: तारीख आणि लक्ष्मी पूजन मुहूर्त",
               "दिवाळी {year} - Diwali Tarikh ani Lakshmi Pujan Muhurat"),
    },
    "hindu-calendar": {
        "en": ("Hindu calendar {year}: every festival, month by month",
               "Hindu Calendar {year} - Festival Dates, Ekadashi, Purnima"),
        "hi": ("हिंदू कैलेंडर {year}: सभी त्योहार, महीने के अनुसार",
               "हिंदू कैलेंडर {year} - Hindu Calendar aur Tyohar"),
        "mr": ("हिंदू दिनदर्शिका {year}: सर्व सण, महिन्यानुसार",
               "हिंदू दिनदर्शिका {year} - Hindu Calendar ani San"),
    },
    "ekadashi-year": {
        "en": ("Ekadashi {year}: every fasting date",
               "Ekadashi {year} - All Dates, Shukla and Krishna Paksha"),
        "hi": ("एकादशी {year}: सभी व्रत तिथियाँ",
               "एकादशी {year} - Ekadashi Vrat Dates"),
        "mr": ("एकादशी {year}: सर्व व्रत तारखा",
               "एकादशी {year} - Ekadashi Vrat Tarkha"),
    },
}

COPY = {
    "en": {
        "diwali_lede": "Diwali {year} falls on {date}. The Lakshmi Puja muhurat below is computed "
                       "for each city from its own sunset, because the window is decided by the "
                       "tithi at pradosh and that moment is not the same in Mumbai and Kolkata.",
        "calendar_lede": "Every major festival of {year} with its date, month by month, plus the "
                         "year's ekadashis, amavasyas and purnimas. Computed with Swiss Ephemeris.",
        "ekadashi_lede": "All {n} ekadashis of {year}, with the paksha each one falls in.",
        "ekadashi_meta": "Every ekadashi date in {year} - all {n} of them, shukla and krishna "
                         "paksha, computed with Swiss Ephemeris from the tithi at sunrise.",
        "diwali_meta": "Diwali {year} is on {date}. Lakshmi Puja muhurat computed for eight major "
                       "cities from each one's own sunset, with the pradosh window.",
        "calendar_meta": "Every Hindu festival of {year} month by month, with the ekadashi, "
                         "amavasya and purnima dates - computed, not copied.",
        "muhurat_heading": "Lakshmi Puja muhurat by city",
        "city": "City", "from": "From", "to": "To", "date": "Date", "festival": "Festival",
        "paksha": "Paksha", "tithi": "Tithi",
        "ekadashi_heading": "Ekadashi dates",
        "amavasya_heading": "Amavasya dates",
        "purnima_heading": "Purnima dates",
        "convention_heading": "How these dates are decided",
        "convention": "A festival is dated by the tithi running at sunrise, which is how a panchang "
                      "names a day. An observance done in the evening - Dhanteras and Lakshmi Puja "
                      "- is decided by the tithi at pradosh instead, because a tithi lasts about "
                      "23 hours 37 minutes and the one at sunset is often the next one. Local "
                      "panchangs can still differ by a day; where yours does, follow it.",
        "print": "Printable calendar (PDF)",
        "cta_panchang": "Today's panchang",
        "cta_muhurat": "Auspicious dates for {year}",
    },
    "hi": {
        "diwali_lede": "दिवाली {year} को {date} है। नीचे दिया लक्ष्मी पूजा मुहूर्त हर शहर के अपने "
                       "सूर्यास्त से निकाला गया है, क्योंकि यह समय प्रदोष की तिथि से तय होता है और "
                       "वह क्षण मुंबई और कोलकाता में एक नहीं होता।",
        "calendar_lede": "{year} के सभी प्रमुख त्योहार तिथि सहित, महीने के अनुसार, और साथ में वर्ष "
                         "की एकादशियाँ, अमावस्याएँ और पूर्णिमाएँ। Swiss Ephemeris से गणना की गई।",
        "ekadashi_lede": "{year} की सभी {n} एकादशियाँ, हर एक का पक्ष सहित।",
        "ekadashi_meta": "{year} की हर एकादशी तिथि - कुल {n}, शुक्ल और कृष्ण पक्ष दोनों, "
                         "सूर्योदय की तिथि से Swiss Ephemeris द्वारा गणना की गई।",
        "diwali_meta": "दिवाली {year} {date} को है। आठ बड़े शहरों के अपने सूर्यास्त से निकाला गया "
                       "लक्ष्मी पूजा मुहूर्त, प्रदोष काल सहित।",
        "calendar_meta": "{year} के सभी हिंदू त्योहार महीने के अनुसार, साथ में एकादशी, अमावस्या "
                         "और पूर्णिमा की तिथियाँ - गणना की गई, कहीं से ली नहीं।",
        "muhurat_heading": "शहर के अनुसार लक्ष्मी पूजा मुहूर्त",
        "city": "शहर", "from": "से", "to": "तक", "date": "तारीख़", "festival": "त्योहार",
        "paksha": "पक्ष", "tithi": "तिथि",
        "ekadashi_heading": "एकादशी तिथियाँ",
        "amavasya_heading": "अमावस्या तिथियाँ",
        "purnima_heading": "पूर्णिमा तिथियाँ",
        "convention_heading": "ये तिथियाँ कैसे तय होती हैं",
        "convention": "त्योहार की तिथि सूर्योदय के समय चल रही तिथि से तय होती है - पंचांग इसी तरह "
                      "दिन का नाम रखता है। शाम को किया जाने वाला अनुष्ठान - धनतेरस और लक्ष्मी पूजा "
                      "- प्रदोष की तिथि से तय होता है, क्योंकि तिथि लगभग 23 घंटे 37 मिनट चलती है "
                      "और सूर्यास्त की तिथि अक्सर अगली होती है। स्थानीय पंचांग एक दिन अलग हो सकता "
                      "है; जहाँ आपका अलग हो, उसी का पालन करें।",
        "print": "छपाई योग्य कैलेंडर (PDF)",
        "cta_panchang": "आज का पंचांग",
        "cta_muhurat": "{year} के शुभ मुहूर्त",
    },
    "mr": {
        "diwali_lede": "दिवाळी {year} ही {date} रोजी आहे. खालील लक्ष्मी पूजन मुहूर्त प्रत्येक "
                       "शहराच्या स्वतःच्या सूर्यास्तावरून काढला आहे, कारण ही वेळ प्रदोषाच्या "
                       "तिथीवरून ठरते आणि तो क्षण मुंबई आणि कोलकात्यात एकसारखा नसतो.",
        "calendar_lede": "{year} मधील सर्व प्रमुख सण तारखेसह, महिन्यानुसार, आणि सोबत वर्षातील "
                         "एकादशी, अमावस्या आणि पौर्णिमा. Swiss Ephemeris ने गणना केलेली.",
        "ekadashi_lede": "{year} मधील सर्व {n} एकादशी, प्रत्येकीच्या पक्षासह.",
        "ekadashi_meta": "{year} मधील प्रत्येक एकादशी तारीख - एकूण {n}, शुक्ल आणि कृष्ण दोन्ही "
                         "पक्ष, सूर्योदयाच्या तिथीवरून Swiss Ephemeris ने गणना केलेली.",
        "diwali_meta": "दिवाळी {year} ही {date} रोजी आहे. आठ मोठ्या शहरांच्या स्वतःच्या "
                       "सूर्यास्तावरून काढलेला लक्ष्मी पूजन मुहूर्त, प्रदोष काळासह.",
        "calendar_meta": "{year} मधील सर्व हिंदू सण महिन्यानुसार, सोबत एकादशी, अमावस्या आणि "
                         "पौर्णिमेच्या तारखा - गणना केलेली, कुठूनही घेतलेली नाही.",
        "muhurat_heading": "शहरानुसार लक्ष्मी पूजन मुहूर्त",
        "city": "शहर", "from": "पासून", "to": "पर्यंत", "date": "तारीख", "festival": "सण",
        "paksha": "पक्ष", "tithi": "तिथी",
        "ekadashi_heading": "एकादशी तारखा",
        "amavasya_heading": "अमावस्या तारखा",
        "purnima_heading": "पौर्णिमा तारखा",
        "convention_heading": "या तारखा कशा ठरतात",
        "convention": "सणाची तारीख सूर्योदयाच्या वेळी चालू असलेल्या तिथीवरून ठरते - पंचांग अशाच "
                      "प्रकारे दिवसाला नाव देते. संध्याकाळी केले जाणारे व्रत - धनत्रयोदशी आणि "
                      "लक्ष्मी पूजन - प्रदोषाच्या तिथीवरून ठरते, कारण तिथी सुमारे 23 तास 37 मिनिटे "
                      "चालते आणि सूर्यास्ताची तिथी अनेकदा पुढची असते. स्थानिक पंचांग एक दिवस वेगळे "
                      "असू शकते; तुमचे वेगळे असेल तिथे त्याचेच पालन करा.",
        "print": "छापण्यायोग्य दिनदर्शिका (PDF)",
        "cta_panchang": "आजचे पंचांग",
        "cta_muhurat": "{year} चे शुभ मुहूर्त",
    },
}


def _clock(moment) -> str:
    """HH:MM in the moment's own zone, or "" - the muhurta windows are datetimes."""
    return moment.strftime("%H:%M") if moment is not None else ""


def _date_text(day, lang: str) -> str:
    return f"{day.day} {MONTH_NAMES[lang][day.month - 1]} {day.year}"


def by_month(year: int, lang: str) -> list[dict]:
    """The year's festivals grouped into months, every month present."""
    items = calendar.festivals(year)
    months = {number: [] for number in range(1, 13)}
    for item in items:
        months[item["date"].month].append({
            "day": item["date"].day,
            "date_text": _date_text(item["date"], lang),
            "name": item["names"][lang],
            "basis": item["basis"],
        })
    # NOT "items". Jinja resolves `month.items` to the DICT'S OWN .items METHOD before it looks at
    # the key, so the template iterated a bound method and raised. A key named after something every
    # mapping already has is a key that works everywhere except in a template.
    return [{"number": number, "name": MONTH_NAMES[lang][number - 1], "festivals": entries}
            for number, entries in sorted(months.items())]


def add_routes(router, page_context, respond, _json_ld) -> None:
    for lang in i18n.LANGS:
        for year in i18n.YEAR_PAGES:
            _add_diwali(router, page_context, respond, _json_ld, lang, year)
            _add_calendar(router, page_context, respond, _json_ld, lang, year)
            _add_ekadashi(router, page_context, respond, _json_ld, lang, year)


def _shell(page_context, _json_ld, key: str, lang: str, year: int, path: str) -> dict:
    from app.web import seo as _seo

    h1, title = (text.format(year=year) for text in TITLES[key][lang])
    context = page_context(key, lang, year=year)
    context.update({
        "words": COPY[lang], "year": year, "h1": h1, "title": title,
        "panchang_path": i18n.url_for("panchang", lang),
        "muhurat_path": i18n.url_for("muhurat-year", lang, purpose="vivah", year=year),
        "calendar_path": i18n.url_for("hindu-calendar", lang, year=year),
        "diwali_path": i18n.url_for("diwali-year", lang, year=year),
        "diwali_label": TITLES["diwali-year"][lang][0].format(year=year),
        "calendar_label": TITLES["hindu-calendar"][lang][0].format(year=year),
        "ekadashi_path": i18n.url_for("ekadashi-year", lang, year=year),
        "json_ld": [_json_ld(_seo.breadcrumbs([
            (context["ui"]["home"], i18n.url_for("home", lang)), (h1, path)]))],
    })
    return context


def _add_diwali(router, page_context, respond, _json_ld, lang: str, year: int) -> None:
    path = i18n.url_for("diwali-year", lang, year=year)

    def diwali_page(request: Request):
        rows = []
        day = None
        for city in CITIES:
            answer = festival_engine.windows("lakshmi-puja", year, city)
            if not answer:
                continue
            day = day or answer["date"]
            # `windows()` hands back real datetimes, with keys `start` and `end` - not ISO
            # strings and not `from`/`to`. Slicing a datetime raises rather than quietly
            # producing nonsense, which is the better failure of the two.
            window = answer.get("muhurta") or {}
            rows.append({"city": city,
                         "from": _clock(window.get("start")),
                         "to": _clock(window.get("end")),
                         "sunset": _clock(answer.get("sunset"))})
        context = _shell(page_context, _json_ld, "diwali-year", lang, year, path)
        context.update({
            "cities": rows,
            "diwali_date": _date_text(day, lang) if day else "",
            "lede": COPY[lang]["diwali_lede"].format(
                year=year, date=_date_text(day, lang) if day else ""),
            "meta_description": COPY[lang]["diwali_meta"].format(
                year=year, date=_date_text(day, lang) if day else "")[:180],
        })
        return respond(request, "diwali_year.html", context)

    router.add_api_route(path, diwali_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"diwali-{year}-{lang}", include_in_schema=False)


def _add_calendar(router, page_context, respond, _json_ld, lang: str, year: int) -> None:
    path = i18n.url_for("hindu-calendar", lang, year=year)

    def calendar_page(request: Request):
        if request.query_params.get("print") == "1":
            from starlette.concurrency import run_in_threadpool

            return _print_pdf(lang, year)
        context = _shell(page_context, _json_ld, "hindu-calendar", lang, year, path)
        context.update({
            "months": by_month(year, lang),
            "amavasyas": [_date_text(item["date"], lang) for item in calendar.amavasyas(year)],
            "purnimas": [_date_text(item["date"], lang) for item in calendar.purnimas(year)],
            "lede": COPY[lang]["calendar_lede"].format(year=year),
            "meta_description": COPY[lang]["calendar_meta"].format(year=year)[:180],
            "print_path": path + "?print=1",
        })
        return respond(request, "hindu_calendar.html", context)

    router.add_api_route(path, calendar_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"hindu-calendar-{year}-{lang}", include_in_schema=False)


def _add_ekadashi(router, page_context, respond, _json_ld, lang: str, year: int) -> None:
    path = i18n.url_for("ekadashi-year", lang, year=year)

    def ekadashi_page(request: Request):
        items = calendar.ekadashis(year)
        context = _shell(page_context, _json_ld, "ekadashi-year", lang, year, path)
        context.update({
            "ekadashis": [{"date_text": _date_text(item["date"], lang),
                           "paksha": item["paksha"]["devanagari"] if lang != "en"
                                     else item["paksha"]["name"]}
                          for item in items],
            "lede": COPY[lang]["ekadashi_lede"].format(year=year, n=len(items)),
            "meta_description": COPY[lang]["ekadashi_meta"].format(year=year, n=len(items))[:180],
        })
        return respond(request, "ekadashi_year.html", context)

    router.add_api_route(path, ekadashi_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"ekadashi-{year}-{lang}", include_in_schema=False)


def _print_pdf(lang: str, year: int) -> Response:
    """The printable calendar. Rendered from the same month grouping the page shows, so a reader who
    prints it gets what they just read rather than a second list that might disagree."""
    from markupsafe import Markup

    from app.pdf import browser
    from app.pdf.render import PDF_DIR, env

    css = Markup((PDF_DIR.parent / "biodata" / "sheet.css").read_text(encoding="utf-8"))
    html = env(lang).get_template("hindu_calendar_print.html").render(
        css=css, lang=lang, year=year, months=by_month(year, lang), words=COPY[lang],
        title=TITLES["hindu-calendar"][lang][0].format(year=year))
    return Response(browser.html_to_pdf(html), media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="hindu-calendar-{year}-{lang}.pdf"'})
