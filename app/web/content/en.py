"""English copy (the `/` tree). Keywords for this tree: birth chart, horoscope matching (for marriage / by
name), ai astrology / free astrologer chat, horoscope today / weekly horoscope. Placeholders: see app/web/pages.py.
"""

from markupsafe import Markup

from app.web.content.rashi_en import RASHI_BODIES  # the twelve per-rashi hub bodies (pages.RashiBody)
from app.web.pages import PageCopy, Product, Section

__all__ = ["PAGES", "LOCAL_PAGES", "UI", "RASHI_BODIES"]

UI = {
    # site chrome
    "skip": "Skip to content", "nav_aria": "Main", "footer_aria": "Footer", "lang_aria": "Language",
    "home": "Home", "nav_rashifal": "Horoscope", "breadcrumb_aria": "Breadcrumb",
    "menu": "Menu",
    "tagline": "Vedic astrology, calculated with Swiss Ephemeris",
    # The brand line, which is identity rather than a claim. It belongs to the HOME HERO alone - one flourish
    # per visit. It used to sit under the wordmark on every page as well, stacked above the trust line, which
    # read as two competing subtitles in the chrome. `tagline` above is the engine trust line and must stay
    # where it is: the trust sweep asserts the engine is named in the header of all 246 pages.
    "brand_tagline": "Stars guide, karma decides your destiny",
    "disclaimer_label": "Disclaimer:",
    "disclaimer": "Astrology is a traditional faith-based practice. Everything on this site is offered for guidance and "
                  "reflection only and is not a substitute for professional advice - please consult qualified "
                  "professionals for health, legal or financial decisions.",
    "footer_meta": "Calculations: Swiss Ephemeris, sidereal zodiac, Lahiri ayanamsa.",
    "footer_trust": "Swiss Ephemeris does the calculation; AI only explains what it found, in your language.",
    "source_link": "Source code (AGPL)",
    # birth form (tool pages + consultation)
    "legend": "Birth details", "boy_legend": "Boy's details", "girl_legend": "Girl's details",
    "name": "Name", "optional": "(optional)", "date": "Date of birth", "time": "Time of birth",
    "city": "Place of birth (city)", "city_placeholder": "Start typing, e.g. Pune", "cities": "Cities",
    "year_jump": "Year",
    "echo_prefix": "You entered:",
    "city_hint": "Town not listed? Choose the nearest city.",
    "form_note": "Free · no sign-up · your details are used only to calculate this result.",
    "trust_form": "Every figure below is computed with the Swiss Ephemeris (sidereal zodiac, Lahiri ayanamsa) - the precision standard professional astrologers work to. Nothing on this page is estimated.",
    "noscript": "Please enable JavaScript to calculate your result.",
    "faq_heading": "Frequently asked questions", "more_heading": "More free tools",
    # staged form: three steps on a single-person form, two (one per person) on the matching page
    "step_date": "Date of birth", "step_time": "Time of birth", "step_place": "Place of birth",
    "step_date_hint": "The calendar date you were born on. Use the date on the birth record if you have it.",
    "step_time_hint": "As close to the minute as you can manage. The rising sign turns over about every two "
                      "hours, so this is the field that decides the most.",
    "step_place_hint": "The town or city, not the hospital. Pick the nearest listed city if yours is not there.",
    "step_next": "Next", "step_back": "Back", "step_count": "Step",
    # the time presets, and the honest note that goes with them
    "time_unsure": "Not sure of the exact time?",
    "time_presets_lead": "Pick the closest part of the day. It gets you a result now, with one caveat.",
    "time_approx_note": "A preset puts you at most ninety minutes from the real time, and that still costs more "
                        "than it looks. Sade sati barely moves and your Moon sign usually holds, though neither "
                        "is fixed. The lagna, everything counted from it, the mangal dosha verdict and the dasha "
                        "dates are not reliable at this granularity: over ninety minutes the ascendant changes "
                        "on about three charts in four, and a little under half move their dasha dates by over a "
                        "year. The result spells this out.",
    "preset_midnight": "12 AM", "preset_small_hours": "3 AM", "preset_early": "6 AM",
    "preset_morning": "9 AM", "preset_noon": "12 PM",
    "preset_afternoon": "3 PM", "preset_evening": "6 PM", "preset_night": "9 PM",
    # "use my location": the coordinates stay in the browser (see static/js/app.js)
    "location_button": "Use my location",
    "location_hint": "Only helps if you still live where you were born. Your coordinates stay in this browser: "
                     "the nearest city is picked here and only its name is sent.",
    "location_searching": "Finding the nearest city…",
    "location_denied": "No location permission, which is fine - type the city instead.",
    "location_unavailable": "Could not get a location just now. Typing the city works the same.",
    "location_found": "Nearest listed city:",
    # error pages
    "error_home": "Go to the home page",
}

_ACCURACY_POINTS = [
    "Sidereal zodiac with Lahiri (Chitrapaksha) ayanamsa, the standard used for Indian panchangs.",
    "Whole-sign houses: the lagna sign is the first house, the next sign the second, and so on.",
    "Mean Rahu and Ketu, which are always retrograde.",
    "Your local birth time is converted to UTC using the historical timezone of the birth place.",
    "Vimshottari dasha of 120 years, started from the Moon's exact position in its nakshatra.",
]

HOME = PageCopy(
    nav_label="Home",
    title="Free Birth Chart, Horoscope Matching & Daily Horoscope - Vedic Astrology",
    meta_description=(
        "Free, accurate Vedic astrology: birth chart (janam kundali), horoscope matching for marriage, mangal dosha and "
        "sade sati calculators, daily horoscope for all 12 signs and an AI astrologer. Swiss Ephemeris, Lahiri ayanamsa."
    ),
    h1="Free Vedic Astrology You Can Trust",
    intro=(
        "Create your birth chart, match horoscopes for marriage, check mangal dosha or sade sati and read today's "
        "horoscope - free, instant and without sign-up. Every number is calculated with the Swiss Ephemeris."
    ),
    sections=(
        Section("Accurate by design", (
            "Every chart, date and degree on this site is calculated with the Swiss Ephemeris - the astronomical "
            "library used by professional astrology software - using the sidereal zodiac and the Lahiri ayanamsa "
            "followed by Indian panchangs. Nothing in the free tools is estimated or generated by AI.",
            ["Planet positions accurate to a fraction of an arc-second for modern dates.",
             "Historical timezones handled for each birth place.",
             "Sade sati dates from Saturn's real transits, including retrograde re-entries.",
             "Available in English, हिन्दी and मराठी - each written for its own readers, not machine-translated."],
        )),
        Section("Calculation first, interpretation second", (
            "The site keeps two layers strictly apart. The calculation layer is the Swiss Ephemeris doing "
            "astronomy: lagna, planets, nakshatras, dasha dates, doshas and transits. The interpretation layer - the paid reports, the AI "
            "astrologer and the horoscope columns - only ever explains those calculated facts; it is never allowed to "
            "work out a position or a date by itself.",
        )),
        Section("Which tool do you actually need?", (
            "Most people arrive wanting one of four things, and it is worth naming them plainly rather than "
            "sending you through a menu.",
            ["You want to see your own chart: start with the free birth chart. It gives you your lagna, Moon sign, "
             "nakshatra, all nine planet positions and your full Vimshottari dasha timeline with dates.",
             "You are matching two horoscopes for a marriage: horoscope matching scores all eight kootas out of 36 "
             "and compares mangal dosha for both people. It also works from two names when birth details are not "
             "available, which is what most families actually have to hand at first.",
             "Somebody told you that you are manglik, or that sade sati has started: the mangal dosha and sade sati "
             "checkers answer those two questions directly, with the classical cancellation rules listed rather "
             "than hidden.",
             "You just want today's reading: the horoscope pages cover all twelve signs for today, this week, this "
             "month, six months and the year."],
            "None of the four needs an account, an email address or a payment. The paid reports exist for people "
            "who want the interpretation written out at length, and every calculation behind them is on the free "
            "pages already.",
        )),
        Section("Moon sign, sun sign, ascendant: the question everybody asks first", (
            "Here's the thing that trips up almost everyone. Your rashi in Indian astrology is your Moon sign, not "
            "your Sun sign, and Indian horoscope columns are written for it. The sign you have been calling yours "
            "from a Western magazine is usually the Sun sign, and in the sidereal zodiac it is often one sign "
            "earlier anyway.",
            "The ascendant, or lagna, is a third thing again: the sign that was rising on the eastern horizon at "
            "the moment you were born. It changes roughly every two hours, which is why two people born on the same "
            "day in the same city can have completely different charts. Your lagna decides the house layout of your "
            "whole chart, so it matters more than either of the other two for anything personal.",
            "If you have never checked which is which, the free birth chart shows all three side by side in a few "
            "seconds, and it takes your date, time and city rather than an email address.",
        )),
        Section("Why birth time matters more than people expect", (
            "A four minute difference in recorded birth time can move the Moon across a nakshatra pada boundary, "
            "and the pada is what sets the starting point of your entire dasha sequence. Half an hour can move the "
            "lagna into the next sign.",
            "This is the single place where manual calculation goes wrong most often: a birth time rounded to the "
            "nearest half hour, an ayanamsa applied from the wrong year, a digit copied across a page. The Swiss "
            "Ephemeris removes that whole class of error, because the positions come from the same astronomical "
            "model observatories use rather than from a printed table and arithmetic by hand.",
            "If your birth time is genuinely uncertain, the chart still tells you a great deal. Your Moon sign, "
            "nakshatra and dasha dates are usually safe; the lagna and the house placements are the parts to hold "
            "loosely, and the free chart flags it when a birth falls close to a boundary.",
        )),
    ),
    faqs=(
        ("Is all of this really free?",
         "The birth chart, horoscope matching, mangal dosha, sade sati and every horoscope page are free with no "
         "sign-up and no email address. The only paid things are the written PDF reports and the consultation "
         "question packs, and the calculations inside them are the same ones the free pages already show you."),
        ("Do I need to know my exact birth time?",
         "For the Moon sign, an approximate time is usually enough: if you are within ninety minutes, which is "
         "the most a preset can be out, it moves for about one chart in forty. The nakshatra is usually right "
         "too, though about one in eighteen lands elsewhere. The ascendant, the house positions, the mangal "
         "dosha verdict and the dasha dates all need the real time - the lagna changes on about three charts "
         "in four over that window, and a little under half shift their dasha dates by more than a year. The "
         "chart tells you when your birth falls close to a boundary rather than quietly picking one side."),
        ("Is my rashi the same as my star sign?",
         "Usually not. Indian astrology reads the Moon sign in the sidereal zodiac; a Western star sign is the Sun "
         "sign in the tropical zodiac. The two zodiacs are about 24 degrees apart today, so your Vedic Moon sign is "
         "frequently a different sign entirely."),
        ("Are the readings written by AI?",
         "The interpretation is, and the calculation is not. Every position, date and dosha status comes from the "
         "Swiss Ephemeris with the Lahiri ayanamsa; AI reads that finished chart and explains it in plain language. "
         "It is not permitted to work out a placement or a date itself, and each report is checked against the "
         "chart data before it is delivered."),
        ("Which languages can I use?",
         "English, Hindi and Marathi, and each one is written for its own readers rather than translated from the "
         "others. You can switch language on any page from the header and land on the same page in the new "
         "language."),
        ("How often are the horoscope pages updated?",
         "Daily readings refresh shortly after midnight Indian time, weekly ones on Monday, and the monthly, six "
         "month and yearly pages at the start of their period. Every page prints the date it was last updated, and "
         "the planetary transit tables on it are calculated live rather than stored."),
        ("What happens to the birth details I enter?",
         "For the free tools they are used to calculate the result and are not stored against your identity. If you "
         "buy a report they are kept with that order so the report can be generated and downloaded again. There is "
         "no account and no advertising profile."),
    ),
    extra={
        "hero_trust": "Swiss Ephemeris precision, AI explanation - accurate by design.",
        "card_open": "Open tool", "card_open_aria": "Open {name}", "card_chat_button": "Start chat",
        "card_rashifal_title": "Horoscope for All 12 Signs",
        "card_rashifal_text": "Today, this week, this month, 6 months and the year ahead for your Moon sign - always "
                              "free, refreshed from exact planetary transits.",
        "card_rashifal_button": "Read today's horoscope",
        "strip_heading": "Today's horoscope by sign", "strip_weekly": "Weekly horoscope for all signs",
    },
)

KUNDALI = PageCopy(
    nav_label="Birth Chart",
    title="Free Birth Chart - Vedic Astrology Birth Chart (Janam Kundali) Online",
    meta_description=(
        "Create your free birth chart in seconds. Accurate Vedic astrology birth chart with ascendant (lagna), Moon "
        "sign, nakshatra, planet positions and Vimshottari dasha - calculated with Swiss Ephemeris, Lahiri ayanamsa."
    ),
    h1="Free Vedic Birth Chart (Janam Kundali)",
    intro=(
        "Enter your date, time and place of birth to get an accurate Vedic astrology chart - ascendant, Moon sign, "
        "nakshatra, all nine planets and your Vimshottari dasha timeline. Free, instant, no sign-up."
    ),
    form_heading="Enter birth details",
    submit_label="Create birth chart",
    result_heading="Your birth chart",
    card_blurb="North Indian style Vedic birth chart with lagna, rashi, nakshatra, planet positions and dasha timeline.",
    product=Product(
        heading="Have this chart read for you (PDF)",
        text="A personalised, easy-to-read interpretation of this exact chart, written for your own placements and "
             "delivered as a PDF you can keep, print and share. Choose how deep you want to go.",
        points=(
            "Personality, strengths and career direction from your lagna and planets",
            "What your current mahadasha and antardasha are asking of you",
            "Simple, practical remedies suited to your chart",
        ),
    ),
    # the two tiers this page sells (pages.PURCHASE_OPTIONS): what each one buys, in one line each
    extra={
        "cta_disclaimer":
            "The chart above is calculated; the reading is written. Swiss Ephemeris works out every position and date, "
                           "and AI writes the interpretation from that finished chart. Astrology is a traditional, faith-based "
                           "practice, offered here for reflection rather than instruction - take health, legal or money decisions to "
                           "a qualified professional.",

        # The free Basic Chart PDF (POST /api/chart/pdf - no gate, no AI on that path). Prices are the
        # catalogue's, like every other number in this file.
        "download_button": "Download chart PDF - free",
        "download_text": "About five A5 pages, ready to print: your birth details and the lagna, rashi and "
                         "nakshatra summary, both charts (lagna and navamsa), the full planet table, mangal "
                         "dosha, sade sati and your current dasha period. No sign-up, and no AI - every value "
                         "in it is calculated by the Swiss Ephemeris, not interpreted. Want to know what it all "
                         "means? The Simple report (₹{price_kundali_simple}) adds a written reading; the "
                         "Detailed book (₹{price_kundali}) adds the dated timeline, remedies and gemstone "
                         "guidance.",
        "download_working": "Preparing your PDF…",
        "download_busy": "The PDF could not be prepared just now - the server is printing something else. Try "
                         "again in a minute; the chart on this page is always free to read.",
        "download_limit": "Several chart PDFs have already been prepared from this connection in the last hour. "
                          "Please try again a little later - the chart on this page is always free to read.",
        "download_failed": "The download could not be started. Please check your connection and try again - the "
                           "chart on this page is always free to read.",
        "buy_simple": "Get the ₹{price_kundali_simple} report",
        "gets_simple": "A concise PDF: your chart, your dasha periods and your remedies.",
        "buy_detailed": "Get the ₹{price_kundali} book",
        "gets_detailed": "35-45 pages, print-and-bind ready. Every year of the next twenty dated for you, and career, "
                         "marriage, money and health each read in depth.",
    },
    sections=(
        Section("What is a Vedic birth chart?", (
            "A birth chart - called a natal chart in Western astrology and a janam kundali or janam patrika in India - "
            "is a map of the sky at the exact moment and place you were born. Vedic astrology, or Jyotish, divides the "
            "sky into twelve signs (rashis) and twelve houses (bhavas), and records where the Sun, Moon, Mars, Mercury, "
            "Jupiter, Venus, Saturn, Rahu and Ketu were placed at that moment.",
            "Three points of the astrology chart are used most often. The ascendant (lagna) is the sign that was rising "
            "on the eastern horizon when you were born; it becomes your first house and sets the layout of the whole "
            "chart. The rashi is the sign occupied by the Moon - the sign Indian horoscope columns are written for. The "
            "janma nakshatra is the lunar mansion the Moon was in, and it decides the starting point of your "
            "Vimshottari dasha.",
        )),
        Section("Vedic chart or Western natal chart?", (
            Markup('A free natal chart from a Western site uses the tropical zodiac, which is tied to the seasons. '
                   'A Vedic astrology birth chart uses the sidereal zodiac, which is tied to the fixed stars; the two '
                   'differ today by about 24 degrees (the ayanamsa). That is why your Vedic Sun or Moon sign is often '
                   'one sign earlier than the Western one. Neither is a mistake - they are different conventions - but '
                   'dashas, nakshatras, doshas and horoscope matching all require the sidereal chart shown here. If it '
                   'is that difference you came to understand rather than the chart itself, the '
                   '<a href="{url_sidereal}">sidereal birth chart calculator</a> takes the same figures and starts '
                   'from the ayanamsa instead.'),
        )),
        Section("How this birth chart is calculated", (
            "Accuracy is the whole point of a birth chart, so every number on this page comes from the Swiss "
            "Ephemeris - the same high-precision astronomical library used by professional astrology software. No "
            "value is estimated or generated by AI.",
            _ACCURACY_POINTS,
        )),
        Section("How to read the North Indian chart", (
            "The diamond-style chart used across North and West India keeps the houses fixed. The top-centre diamond "
            "is always the first house (lagna), and the houses run anticlockwise from there. The number written inside "
            "each house is the sign number - 1 for Aries (Mesha), 2 for Taurus (Vrishabha) up to 12 for Pisces "
            "(Meena). So if the top diamond shows 5, your ascendant is Leo (Simha).",
            "Planets are shown by short codes: Su (Sun), Mo (Moon), Ma (Mars), Me (Mercury), Ju (Jupiter), Ve (Venus), "
            "Sa (Saturn), Ra (Rahu) and Ke (Ketu). A small R next to a planet means it was retrograde at birth. The "
            "table under the chart lists the exact degree, nakshatra and pada of each planet, so you can cross-check "
            "the chart against any kundali you already have.",
        )),
        Section("Why birth time and place matter", (
            "The ascendant changes sign roughly every two hours and moves about one degree every four minutes, so a "
            "small error in birth time can shift the houses of the whole chart. Use the time written on your birth "
            "certificate or hospital record wherever possible. The Moon moves more slowly - about 13 degrees a day - "
            "so your Moon sign and nakshatra are usually reliable even when the time is approximate.",
            "Place of birth matters because sunrise and the rising sign differ with latitude and longitude. Pick your "
            "birth city from the list; if your town is not listed, choose the nearest city - a distance of 50-100 km "
            "changes the ascendant by well under one degree.",
        )),
        Section("Understanding your dasha timeline", (
            "The Vimshottari dasha system divides life into nine mahadashas (major periods), each ruled by a planet and "
            "lasting between 6 and 20 years, and each mahadasha into nine antardashas (sub-periods). The period you are "
            "born into depends on your janma nakshatra, and the balance left at birth depends on how far the Moon had "
            "travelled through it. The timeline on this page shows every mahadasha with its start and end date, with "
            "your current period highlighted.",
            Markup('Every date in that timeline comes from the Swiss Ephemeris, not from a written interpretation. '
                   'Once you have your chart, you can <a href="{url_matching}">match it with a partner\'s horoscope</a>, '
                   'check <a href="{url_mangal_dosha}">mangal dosha</a> or <a href="{url_sade_sati}">sade sati</a>, or '
                   '<a href="{url_consultation}">ask the AI astrologer</a> a question about it.'),
        )),
    ),
    faqs=(
        ("Is this birth chart really free?",
         "Yes. The chart, planet positions, ascendant, Moon sign, nakshatra and the complete mahadasha timeline are "
         "free, with no sign-up. Only the written PDF reading is paid - ₹{price_kundali_simple} for the concise "
         "report, ₹{price_kundali} for the detailed book."),
        ("How accurate is this online birth chart?",
         "All positions are calculated with the Swiss Ephemeris using the Lahiri ayanamsa, which is accurate to a "
         "fraction of an arc-second for modern dates. The result is only as accurate as the birth time and place you "
         "enter, so use your recorded birth time."),
        ("What if I do not know my exact birth time?",
         "Enter your best estimate, and read the result knowing what an estimate costs. The Moon moves slowly, so "
         "your Moon sign usually survives and the nakshatra usually does. The ascendant does not: across a "
         "ninety-minute window it changes on about three charts in four, taking the house positions and the mangal "
         "dosha verdict with it, and the dasha dates shift by more than a year on a little under half. If you only know "
         "the day, 12:00 noon is a common placeholder - but treat everything except the Moon sign as provisional "
         "until the recorded time turns up."),
        ("Which ayanamsa and house system do you use?",
         "Lahiri (Chitrapaksha) ayanamsa with the sidereal zodiac and whole-sign houses, which is the most widely "
         "followed convention in Indian Vedic astrology. Rahu and Ketu are mean nodes."),
        ("What is the difference between ascendant (lagna) and Moon sign (rashi)?",
         "The ascendant is the zodiac sign rising on the eastern horizon at your birth and forms the first house of "
         "your chart. The rashi is the sign in which the Moon was placed. Both matter: the ascendant describes your "
         "outer life and body, and the Moon sign describes the mind and emotions."),
        ("My town is not in the city list. What should I do?",
         "Choose the nearest listed city. A difference of 50-100 km changes the ascendant by less than one degree, "
         "which does not affect the chart unless the ascendant falls at the very edge of a sign."),
        # Covers the transliterated way this is searched in English - "janam kundali online free", "kundli in
        # English", "janam kundli" - without a second page competing with this one for the same intent.
        ("Is a janam kundali the same thing, and can I read my kundli in English?",
         "Yes to both. Janam kundali, janam kundli, kundli, janma patrika and birth chart are all names for the same "
         "document, and this is the free online version of it in English: the same Lahiri sidereal calculation an "
         "Indian astrologer works from, with the grahas, houses, nakshatra and dasha periods written out in English "
         "beside their Sanskrit names. Nothing on the page has to be read in Hindi or Marathi. If you would rather "
         "read it in one of those, the same calculator is one tap away in the language switcher at the top."),
    ),
)

MATCHING = PageCopy(
    nav_label="Horoscope Matching",
    title="Horoscope Matching for Marriage - Free Kundali Matching by Birth Date or by Name",
    meta_description=(
        "Free horoscope matching for marriage: Ashtakoota guna milan score out of 36, all eight kootas, nadi and "
        "bhakoot dosha checks and a mangal dosha comparison. Match by date of birth, or do marriage matching by name."
    ),
    h1="Horoscope Matching for Marriage",
    intro=(
        "Match two horoscopes by birth details for the full Ashtakoota guna milan score out of 36, a koota-by-koota "
        "breakdown and a mangal dosha comparison - or, if you do not have birth details, try marriage matching by "
        "name. Free and instant."
    ),
    form_heading="Enter the details of both partners",
    submit_label="Match horoscopes",
    result_heading="Horoscope matching result",
    card_blurb="Ashtakoota guna milan out of 36 with all eight kootas and a mangal dosha comparison - by birth details or by name.",
    product=Product(
        heading="Get the full compatibility report",
        text="Go beyond the score - a detailed, balanced reading of this match based on both charts, as a PDF.",
        button="Get matching report - ₹{price}",
        points=(
            "What each koota result means for this couple in day-to-day life",
            "Strengths of the match and the areas that need understanding",
            "Dosha analysis with traditional remedies where they apply",
        ),
    ),
    sections=(
        Section("What is horoscope matching?", (
            "Horoscope matching - known as kundali matching or guna milan in the north, jataka matching (jathaka "
            "porutham) in the south and patrika matching in Maharashtra - is the traditional Vedic way of checking the "
            "compatibility of two people before marriage. The most widely used method is the Ashtakoota system, which "
            "compares the Moon sign and janma nakshatra of the boy and the girl across eight factors (kootas) and "
            "gives a score out of 36 gunas.",
        )),
        Section("Marriage matching by name", (
            "No birth details to hand? Traditional astrology has a by-name method for exactly this case. Every "
            "nakshatra pada is linked to a starting syllable - the same table families use to choose a baby's name - "
            "so the first sound of a name points to a nakshatra and a Moon sign. Switch the form to \"By name\", type "
            "the two names, and the tool derives the rashi and nakshatra for each name and runs the same 36-point "
            "Ashtakoota comparison.",
            "Name matching is a good first check, and it is the right method when a person was named by their "
            "nakshatra. But many people are not, and a name cannot show the ascendant, Mars or the other planets - "
            "so matching by birth details is always more accurate, and the mangal dosha comparison is only available "
            "there. If a name's first sound fits more than one syllable, the tool asks you to pick the right one.",
        ), anchor="by-name"),
        Section("The eight kootas and their points", (
            "Each koota looks at a different side of married life. Points increase from Varna to Nadi, which reflects "
            "the weight tradition gives to each factor.",
            ["Varna (1 point) - outlook and spiritual compatibility.",
             "Vashya (2 points) - mutual attraction and influence.",
             "Tara (3 points) - fortune and well-being, from the birth stars.",
             "Yoni (4 points) - physical and intimate compatibility.",
             "Graha Maitri (5 points) - friendship between the Moon sign lords; mental compatibility.",
             "Gana (6 points) - temperament: Deva, Manushya or Rakshasa.",
             "Bhakoot (7 points) - the relative position of the two Moon signs; family harmony and prosperity.",
             "Nadi (8 points) - constitution and progeny; carries the highest weight."],
        )),
        Section("How to read the guna milan score", (
            "A score of 18 or more out of 36 is traditionally considered acceptable for marriage. This tool groups the "
            "total as follows:",
            ["Below 18 - below average. The match needs a careful, detailed look at both charts.",
             "18 to 24.5 - average. Acceptable, with some areas that need understanding.",
             "25 to 32.5 - good. A well-suited match by traditional standards.",
             "33 and above - excellent."],
            "The total is a starting point, not a verdict. Two results deserve separate attention even when the total "
            "is high: Nadi dosha (0 out of 8 in Nadi) and Bhakoot dosha (0 out of 7 in Bhakoot). Classical texts list "
            "conditions under which these doshas are cancelled - for example when both Moon signs share the same lord - "
            "and the result shows whether such a cancellation applies.",
        )),
        Section("Mangal dosha in horoscope matching", (
            Markup("Alongside guna milan, families usually compare mangal dosha (manglik status) in the two charts. The "
                   "traditional view is that the match is balanced when either both partners have mangal dosha or "
                   "neither has it. The birth-details result shows the status of each partner, the intensity, and "
                   'whether the two charts are considered compatible on this point. For one chart on its own, use the '
                   '<a href="{url_mangal_dosha}">mangal dosha calculator</a>.'),
        )),
        Section("Beyond the score", (
            "Guna milan uses only the Moon's position in both charts. It does not look at the ascendant, the seventh "
            "house, Venus and Jupiter, or the dashas running at the time of marriage, all of which an experienced "
            "astrologer would weigh. Many happy marriages have modest scores, and mutual respect, shared values and "
            "communication matter more than any number. Use the score as one helpful input alongside your own "
            "judgement and your family's.",
            Markup('Guna milan scores the two Moon charts against each other, which means it says nothing '
                   'about either chart on its own. If you have not looked at yours yet, the '
                   '<a href="{url_kundali}">free birth chart</a> gives the lagna, nakshatra and dasha '
                   'timeline that this score is calculated from.'),
        )),
    ),
    faqs=(
        ("How many gunas should match for marriage?",
         "Traditionally at least 18 out of 36 gunas should match. 18 to 24 is considered average, 25 to 32 good and 33 "
         "or more excellent. A score below 18 is a reason to study both charts in more detail, not an automatic "
         "rejection."),
        ("Can I do marriage matching by name only?",
         "Yes. Choose \"By name\" above the form and enter both names. The first syllable of each name is mapped to its "
         "nakshatra and Moon sign using the traditional naming-syllable table, and the same Ashtakoota score out of 36 "
         "is calculated. It is free and needs no birth details."),
        ("Is matching by name as accurate as matching by date of birth?",
         "No. A name gives the right nakshatra only if the person was named according to their birth star. Matching by "
         "birth details uses the Moon's actual position and also compares mangal dosha, so use it whenever the birth "
         "date, time and place are known."),
        ("Can horoscope matching be done without birth time?",
         "Guna milan depends on the Moon's sign and nakshatra, which change slowly, so an approximate time often gives "
         "the same score. However, if the Moon changed nakshatra or sign on that day the score can differ, and the "
         "mangal dosha check needs the ascendant, which requires an accurate birth time."),
        ("What is nadi dosha, and can it be cancelled?",
         "Nadi dosha occurs when both partners have the same nadi (Aadi, Madhya or Antya), giving 0 out of 8 in the "
         "Nadi koota. Classical exceptions exist - for instance when both have the same rashi but different "
         "nakshatras, or the same nakshatra but different rashis. The result indicates when an exception applies."),
        ("Is a low guna milan score a reason to reject a match?",
         "Not by itself. The Ashtakoota score looks only at the Moon. A full compatibility reading also considers the "
         "ascendant, seventh house, Venus, Jupiter and the dashas of both people. Treat the score as guidance rather "
         "than a final decision."),
    ),
    extra={
        "cta_disclaimer":
            "Guna milan is arithmetic: Swiss Ephemeris places both Moons and the eight kootas are scored from that, "
                           "and AI only explains what the score means. A number out of 36 is one input to a marriage decision and not "
                           "a verdict on it. Astrology is a traditional, faith-based practice; use it alongside your own judgement "
                           "and the people involved.",

        "mode_aria": "Matching method", "mode_birth": "By birth details", "mode_name": "By name",
        "name_heading": "Enter both names", "name_boy": "Boy's name", "name_girl": "Girl's name",
        "name_placeholder": "First name, e.g. Rahul", "name_placeholder_girl": "First name, e.g. Priya", "name_submit": "Match by name",
        "name_hint": "Use the first name as it is spoken. English or Devanagari letters both work.",
        "name_note": "Matching by name uses the first syllable of each name to find its nakshatra and rashi. It is a "
                     "quick traditional check - matching by birth details is more accurate and also compares mangal dosha.",
    },
)

MANGAL_DOSHA = PageCopy(
    nav_label="Mangal Dosha",
    title="Mangal Dosha Calculator - Free Manglik Check by Date of Birth",
    meta_description=(
        "Check mangal dosha (manglik dosha) free by date of birth. See Mars' house from lagna, Moon and Venus, the "
        "intensity of the dosha and which classical cancellation rules apply to your chart."
    ),
    h1="Mangal Dosha Calculator (Manglik Check)",
    intro=(
        "Find out whether your kundali has mangal dosha. We check the position of Mars from your lagna, Moon and "
        "Venus, grade the intensity, and show which traditional cancellation rules apply."
    ),
    form_heading="Enter birth details",
    submit_label="Check Mangal Dosha",
    result_heading="Your Mangal Dosha Result",
    card_blurb="Manglik check from lagna, Moon and Venus with intensity and cancellation rules.",
    extra={
        "cta_disclaimer":
            "Whether Mars sits in one of those houses is calculated by Swiss Ephemeris, and the cancellation rules are "
                           "classical; AI only puts the result into words. About half of all charts show this dosha, so it is not a "
                           "verdict on a marriage. Astrology is a traditional, faith-based practice - for anything medical, legal or "
                           "financial, ask a qualified professional.",
    },
    product=Product(
        heading="Get your Mangal dosha remedy guide",
        text="A calm, practical guide written for your chart - what the dosha means for you and what tradition recommends.",
        button="Get remedy guide - ₹{price}",
        points=(
            "What Mars' placement means in your chart, in plain language",
            "Traditional remedies: mantra, vrat, daan and temple worship",
            "Guidance for horoscope matching when one or both partners are manglik",
        ),
    ),
    sections=(
        Section("What is mangal dosha?", (
            "Mangal dosha - also called manglik dosha, kuja dosha or bhauma dosha - is a condition in a kundali where "
            "Mars (Mangal) occupies the 1st, 2nd, 4th, 7th, 8th or 12th house. Mars is a graha of energy, drive and "
            "assertiveness. In these houses, which relate to self, family, home, spouse and married life, tradition "
            "holds that this fiery energy needs to be understood and balanced within a marriage. A person with this "
            "placement is called manglik.",
            "Mangal dosha is very common - by simple arithmetic Mars sits in one of these six houses in about half of "
            "all charts - and it is not a bad omen. Mars in these houses also gives courage, initiative and "
            "determination.",
        )),
        Section("How this calculator checks for mangal dosha", (
            "Different traditions count the houses from different reference points, so this tool checks all three "
            "commonly used ones, using whole-sign houses:",
            ["From the lagna (ascendant) - considered the strongest.",
             "From the Moon (Chandra lagna).",
             "From Venus (Shukra), the karaka of marriage."],
            "The intensity shown is based on how many of the three references trigger the dosha: low for one, medium "
            "for two and high for all three. Planet positions are calculated with the Swiss Ephemeris and Lahiri "
            "ayanamsa, so the houses shown will match a professionally cast kundali.",
        )),
        Section("When mangal dosha is cancelled or reduced", (
            "Classical texts list several conditions under which mangal dosha is considered cancelled (dosha bhanga) "
            "or much weaker. This tool checks the following and tells you which apply:",
            ["Mars in its own sign (Mesha, Vrishchika) or its exaltation sign (Makara).",
             "Jupiter placed with Mars or aspecting it.",
             "Specific house and sign combinations, such as Mars in the 2nd house in Mithuna or Kanya, or in the 12th "
             "house in Vrishabha or Tula.",
             "Karka (Cancer) or Simha (Leo) lagna, for which Mars is a yogakaraka."],
            "Two further points are widely accepted: when both partners are manglik the doshas are considered to "
            "balance each other, and the effect of Mars is said to soften after the age of 28, when Mars matures. When "
            "a cancellation applies, the result reads as 'dosha present, with mitigating factors' - the placement is "
            "still there, but tradition treats it as far less of a concern.",
        )),
        Section("Mangal dosha and marriage", (
            Markup('In <a href="{url_matching}">horoscope matching</a>, families usually prefer that both partners are '
                   "manglik or that neither is. If only one partner has the dosha, astrologers look at the cancellation "
                   "rules above, the overall strength of both charts and the guna milan score before advising. "
                   "Traditional remedies - such as Mangal mantra japa, Hanuman worship on Tuesdays or a Kumbh vivah "
                   "ceremony - are commonly suggested. A mangal dosha on its own is never a reason to fear marriage."),
            Markup('This check reads one placement out of a whole chart. The '
                   '<a href="{url_kundali}">free birth chart</a> shows where Mars actually sits along with '
                   'everything else, and if the worry behind the question is timing rather than marriage, '
                   '<a href="{url_sade_sati}">sade sati</a> is the period people usually mean.'),
        )),
    ),
    faqs=(
        ("How do I know if I am manglik?",
         "You are considered manglik if Mars is in the 1st, 2nd, 4th, 7th, 8th or 12th house of your kundali. Enter "
         "your birth details above and the calculator checks this from your lagna, Moon and Venus."),
        ("Which houses cause mangal dosha?",
         "The 1st, 2nd, 4th, 7th, 8th and 12th houses. Some traditions leave out the 2nd house; this calculator follows "
         "the widely used six-house rule and shows Mars' exact house so you can apply your own tradition."),
        ("Does mangal dosha end after the age of 28?",
         "Tradition holds that Mars matures at 28 and that the effect of mangal dosha weakens after that age. The "
         "placement in the chart does not change, but many astrologers treat it as much less significant for marriages "
         "after 28."),
        ("Can a manglik marry a non-manglik?",
         "Yes. Astrologers first check whether the dosha is cancelled in the manglik partner's chart and look at the "
         "overall compatibility. Where needed, traditional remedies are suggested before marriage. Many happily "
         "married couples have this combination."),
        ("What does low, medium or high intensity mean here?",
         "It is the number of reference points from which Mars triggers the dosha: one of lagna, Moon and Venus is low, "
         "two is medium and all three is high. Dosha from the lagna is given the most weight."),
    ),
)

SADE_SATI = PageCopy(
    nav_label="Sade Sati",
    title="Sade Sati Calculator - Check Shani Sade Sati Status and Dates Free",
    meta_description=(
        "Free Shani sade sati calculator. Find out if sade sati is running for your Moon sign, which phase you are in, "
        "and the exact start and end dates of your current or next sade sati."
    ),
    h1="Sade Sati Calculator",
    intro=(
        "Check whether Shani's sade sati is active for you today, which of the three phases you are in, and the exact "
        "dates of your current or next sade sati - calculated from Saturn's real transits."
    ),
    form_heading="Enter birth details",
    submit_label="Check Sade Sati",
    result_heading="Your Sade Sati Result",
    card_blurb="Is Shani's sade sati running for you? Phase, start and end dates from real Saturn transits.",
    extra={
        "cta_disclaimer":
            "Saturn's dates come from its real transit, computed by Swiss Ephemeris, and AI writes the explanation "
                           "around them. Sade sati is a period classical texts describe as demanding, not as misfortune, and nothing "
                           "here predicts illness or loss. Astrology is a traditional, faith-based practice; keep professional advice "
                           "for professional questions.",
    },
    product=Product(
        heading="Get your personal Sade Sati guide",
        text="A reassuring, practical guide to your sade sati - what each phase asks of you and how to make the most of it.",
        button="Get Sade Sati guide - ₹{price}",
        points=(
            "What each phase means for your Moon sign",
            "Phase-by-phase dates with practical do's and don'ts",
            "Traditional Shani remedies: mantra, daan and Saturday observances",
        ),
    ),
    sections=(
        Section("What is sade sati?", (
            "Sade sati (literally 'seven and a half') is the period of roughly seven and a half years during which "
            "Saturn (Shani) transits the sign before your Moon sign, your Moon sign itself, and the sign after it. "
            "Saturn takes about two and a half years to cross one sign, and about 29.5 years to go around the zodiac, "
            "so most people experience sade sati two or three times in life.",
            "Because the Moon represents the mind, Saturn's slow passage over it is felt as a serious, reflective "
            "time. Shani is the graha of discipline, responsibility and karma: sade sati is traditionally a period of "
            "hard work, maturity and lasting achievement rather than something to be afraid of. Many people build "
            "careers, homes and families during their sade sati.",
        )),
        Section("The three phases of sade sati", (
            ["Rising phase - Saturn in the 12th sign from your Moon. A time of changes in routine, expenses and "
             "travel; a good period for planning and letting go of what no longer serves you.",
             "Peak phase - Saturn over your Moon sign. The most inward-looking phase, asking for patience, steady "
             "effort and care for your well-being and relationships.",
             "Setting phase - Saturn in the 2nd sign from your Moon. Focus shifts to finances, family and speech; the "
             "lessons of the earlier phases begin to pay off."],
        )),
        Section("How the dates are calculated", (
            "This calculator first finds your Moon sign from your birth details using the Swiss Ephemeris and Lahiri "
            "ayanamsa. It then tracks Saturn's actual sidereal transits and records the date of every sign change. "
            "Saturn turns retrograde for a few months each year, so it often steps back into the previous sign before "
            "moving forward again. That is why a phase may appear as two or more date ranges in the result, and why "
            "there can be a short gap inside a sade sati when Saturn briefly leaves the three-sign zone. Tools that "
            "simply add two and a half years per sign will not show these details.",
            "If sade sati is not running for you today, the result shows the dates of your next one instead.",
        )),
        Section("Making the most of sade sati", (
            "Traditional advice for Shani periods is simple and practical: keep your commitments, work steadily, avoid "
            "shortcuts, respect elders and those who work for you, and live within your means. Common remedies include "
            "reciting the Hanuman Chalisa or Shani mantra, lighting a sesame oil lamp on Saturdays, and giving to "
            "people in need. The effects of sade sati also depend on Saturn's role in your own kundali and the dasha "
            "you are running, so the same transit is experienced very differently by different people.",
            Markup('To see Saturn\'s place in your own chart, create your <a href="{url_kundali}">free birth chart</a>; '
                   'the <a href="{url_rashifal_hub}">daily horoscope</a> for your Moon sign also notes its current sade '
                   "sati status."),
            Markup('Saturn is one graha. If somebody has also told you that Mars is a problem in your chart, '
                   'the <a href="{url_mangal_dosha}">mangal dosha checker</a> settles that separately, with the '
                   'cancellation rules listed. To ask what a particular phase means for your own placements, the '
                   '<a href="{url_consultation}">AI astrologer</a> reads the Swiss Ephemeris chart these dates '
                   'came from.'),
        )),
    ),
    faqs=(
        ("How long does sade sati last?",
         "About seven and a half years - roughly two and a half years for each of the three signs Saturn crosses. The "
         "exact length varies a little because of Saturn's retrograde motion, which is why this calculator shows real "
         "dates rather than round numbers."),
        ("Is sade sati always bad?",
         "No. Sade sati is a period of responsibility, effort and maturity. Many people achieve major, lasting "
         "milestones during it. How it feels depends on Saturn's position in your own kundali and on your running "
         "dasha."),
        ("Is sade sati counted from the Moon sign or the lagna?",
         "From the Moon sign (janma rashi). This calculator works out your Moon sign from your birth details, so you "
         "do not need to know it in advance."),
        ("Why are there several date ranges for the same phase?",
         "Saturn turns retrograde every year and sometimes moves back into the previous sign for a few months before "
         "going forward again. Each entry into a sign is listed separately so the dates are exact."),
        ("How many times does sade sati come in a lifetime?",
         "Saturn takes about 29.5 years to circle the zodiac, so sade sati returns roughly every 30 years. Most people "
         "experience it two or three times."),
        ("What is the difference between sade sati and dhaiya?",
         "Sade sati is Saturn's transit through the 12th, 1st and 2nd signs from the Moon. Dhaiya (small panoti) is the "
         "two-and-a-half-year transit of Saturn through the 4th or 8th sign from the Moon. This page covers sade sati."),
    ),
)

CONSULTATION = PageCopy(
    nav_label="AI Astrologer",
    title="AI Astrology - Chat with an AI Astrologer Free, From Your Own Birth Chart",
    meta_description=(
        "Vedic astrologer online, free to start: an AI chat that reads your real Swiss Ephemeris birth chart for "
        "career, marriage or your dasha, in English, Hindi or Marathi. First {free_messages} answers free."
    ),
    h1="AI Astrologer - Chat About Your Own Birth Chart",
    intro=(
        "Enter your birth details and ask anything about your chart - career, marriage, your current dasha, the months "
        "ahead. Answers are based on your exact Swiss Ephemeris chart, in English, हिंदी or मराठी. Your first "
        "{free_messages} questions are free."
    ),
    form_heading="Enter birth details to begin",
    submit_label="Start free chat",
    result_heading="Your consultation",
    card_blurb="Chat with an AI astrologer that reads your own Swiss Ephemeris chart - career, marriage, dasha, "
               "this year. First {free_messages} answers free.",
    sections=(
        Section("How AI astrology works here", (
            "First we calculate your birth chart with the Swiss Ephemeris and the Lahiri ayanamsa - ascendant, all "
            "nine planets, nakshatras, your Vimshottari dasha dates, mangal dosha, sade sati and the current planetary "
            "transits. That calculation is pure astronomy; no AI is involved in it.",
            "The AI astrologer then reads that chart and answers your questions from it. It is instructed to use only "
            "your calculated chart - it never works out positions or dates itself - so every answer points to a real "
            "placement or dasha period in your kundali rather than a general sun-sign forecast.",
        )),
        Section("A free astrologer chat - what you can ask", (
            ["Career and work: which fields suit your chart, and what the current dasha favours.",
             "Marriage and relationships: what your 7th house, Venus and Moon say about partnership.",
             "Timing: what your current mahadasha and antardasha ask of you, and when they change.",
             "The months ahead: how Jupiter's and Saturn's transits fall from your Moon sign.",
             "Simple remedies: mantras, charity and habits that cost little or nothing."],
            "There is no waiting for an astrologer to come online and no per-minute meter: the chat is available at "
            "any hour. You can write in English, Hindi or Marathi - in Devanagari or in English letters - and the "
            "astrologer replies in the same language.",
        )),
        Section("What it will not do", (
            "The consultation never predicts death, serious illness, accidents or similar events, and it does not "
            "recommend gemstones or paid rituals. For health, legal or financial decisions it will point you to a "
            "qualified professional. Astrology is a traditional faith-based practice; use it for reflection and "
            "guidance alongside your own judgement.",
        )),
        Section("Pricing: {pack_messages} questions with a Kundali PDF, from ₹{price_pack}", (
            "Your first {free_messages} questions are free. After that there are two ways to carry on, and both give "
            "you {pack_messages} more questions and a Kundali PDF for the same birth details - a report is always "
            "included, there is nothing extra to buy.",
            ["₹{price_pack}: {pack_messages} questions and the concise report - your chart, your dashas, your remedies.",
             "₹{price_premium}: the same {pack_messages} questions with the detailed book instead - every year of the "
             "next twenty dated for you, and career, marriage, money and health each read in depth."],
            "No subscription and no sign-up; unused questions stay available in this browser.",
        )),
    ),
    faqs=(
        ("Is the AI astrologer accurate?",
         "Your chart is calculated with the Swiss Ephemeris and Lahiri ayanamsa, the same standard used by "
         "professional astrology software, so positions and dasha dates are exact. The AI only interprets that chart; "
         "it is not allowed to calculate or guess positions or dates."),
        ("Is the astrologer chat really free?",
         "The first {free_messages} questions are free, with no sign-up. After that, ₹{price_pack} buys "
         "{pack_messages} further questions and includes a Kundali PDF report for the same birth details."),
        ("What is the difference between the ₹{price_pack} and ₹{price_premium} options?",
         "The questions are the same: {pack_messages} of them, about your own chart. What differs is the report that "
         "comes with them. ₹{price_pack} includes the concise Kundali PDF; ₹{price_premium} includes the detailed "
         "book instead (₹{price_kundali} on its own), which dates the next twenty years of your life year by year and "
         "reads career, marriage, money and health in depth. There is no chat-only pack - a PDF always comes with the "
         "questions."),
        ("Can I ask in Marathi or Hindi?",
         "Yes. Ask in English, Hindi or Marathi, in Devanagari or in English letters, and the reply comes in the same "
         "language."),
        ("Does it remember my earlier questions?",
         "Yes. Within a consultation the astrologer sees the whole conversation and your chart with every question, so "
         "you can ask follow-up questions naturally."),
        ("Is this a vedic astrologer online, or just a horoscope app?",
         "Neither, quite. A horoscope app gives you the same paragraph as everyone else born in your month. This "
         "reads your own chart: the Swiss Ephemeris computes your exact placements and dasha dates from your "
         "birth details, and the AI answers your questions from that chart rather than from your Sun sign."),
        ("Is this an Indian astrologer or a psychic reader?",
         "It is not a psychic reading and there is no claim of intuition anywhere on this site. Searches for an "
         "indian astrologer and psychic reader usually land somewhere that offers both, so it is worth being "
         "plain: what happens here is arithmetic and explanation. The Swiss Ephemeris calculates the chart, the "
         "AI explains what the placements traditionally mean, and nobody is sensing anything about you."),
        ("What happens to my birth details?",
         "They are used to calculate your chart with the Swiss Ephemeris and to answer your questions. Your name is "
         "never sent to the AI. There is "
         "no account; a cookie keeps track of your free and paid questions."),
    ),
    extra={
        "form_note": "First {free_messages} questions free · no sign-up · your name is never sent to the AI.",
        "noscript": "Please enable JavaScript to use the consultation.",
        "chat_trust": "This chat reads your own chart, computed by the Swiss Ephemeris - not a generic sun-sign "
                      "horoscope. The AI explains that chart; it never works out a position or a date itself.",
        # Gita 2.47, quoted as inspiration and translated honestly. The gloss is marked as ours, because the
        # verse is about action and its fruits and says nothing about astrology - the policy pages hold the
        # same line for the Bhrigu Samhita, and a gloss printed as a translation would be a checkable falsehood.
        "philosophy_verse": "कर्मण्येवाधिकारस्ते - \"yours is the right to action alone.\"",
        "philosophy_gloss": "We read it this way: astrology can show you the path; the decision and the effort "
                            "stay yours.",
        "log_aria": "Conversation", "typing": "The astrologer is reading your chart…",
        "input_label": "Your question", "input_placeholder": "Ask about career, marriage, your dasha, this year…",
        "send": "Send",
        "paywall_heading": "{pack_messages} more questions + your Kundali PDF, from ₹{price_pack}",
        "paywall_text": "You have used your free questions. Continue right where you left off: {pack_messages} more "
                        "answers read from your own chart, with a Kundali report of your own either way.",
        "buy_basic": "₹{price_pack}: {pack_messages} questions + report",
        "gets_basic": "The concise Kundali PDF comes with it - your chart, your dashas, your remedies.",
        "buy_premium": "₹{price_premium}: {pack_messages} questions + book",
        "gets_premium": "The full 35-45 page book instead: the next twenty years dated for you, and career, marriage, "
                        "money and health each read in depth.",
        "paywall_notice": "Online payment is launching soon. Your conversation above stays saved in this browser.",
        "chat_disclaimer": "Astrology is a traditional faith-based practice, offered for guidance and reflection. The "
                           "AI does not predict death, illness or accidents. For health, legal or financial decisions "
                           "please consult a qualified professional.",
        "reset": "Start over with different birth details",
        "more_heading": "Free tools",
    },
)

# ---- horoscope (rashifal) pages. {rashi} = "Libra", {latin} = "Tula", {deva} = "तुला", {lord} = "Venus (Shukra)" --------

_RASHIFAL_LABELS = {
    "period_today": "Today", "period_weekly": "This Week", "period_monthly": "This Month",
    "period_6-months": "Next 6 Months", "period_yearly": "Yearly",
    "rashi_label": "{rashi}", "rashi_sub": "{latin}",  # how a rashi is named in lists: "Libra" + muted "Tula"
    "read_more": "Read the full reading", "updated": "Last updated", "date_label": "Date", "week_label": "Week",
    "hub_link": "Daily horoscope - all signs", "weekly_link": "Weekly horoscope - all signs",
    "pending_summary": "The written reading is being prepared; the page already shows today's exact planetary facts for {rashi}.",
    "cta_kundali_title": "Not sure which sign is yours?",
    "cta_kundali_text": "A Vedic horoscope is read from your Moon sign, not your Sun sign. Your free birth chart shows "
                        "your Moon sign, nakshatra and ascendant in seconds.",
    "cta_kundali_button": "Create free birth chart",
    "cta_chat_title": "Ask about your own chart",
    "cta_chat_text": "Career, marriage, this year - ask our AI astrologer, who reads the exact birth chart the "
                     "Swiss Ephemeris calculates from your details. First {free_messages} answers free.",
    "cta_chat_button": "Chat with the AI astrologer",
    "saturn_heading": "Sade sati and dhaiya status for {rashi}",
    "saturn_link": "Check sade sati from your exact birth details",
    "others_heading": "Other signs", "periods_heading": "All {rashi} horoscopes",
    "others_period_heading": "{period} horoscope for other signs",
    "about_heading": "How this horoscope is made",
    "about_text": "Planet positions, sign changes, retrograde dates, tithi and nakshatra on this page are calculated with "
                  "the Swiss Ephemeris (sidereal zodiac, Lahiri ayanamsa). The written horoscope interprets those "
                  "transits for {rashi} ({latin} rashi) as the Moon sign; it is a general reading, not a personal "
                  "birth-chart reading.",
    "reading_disclaimer": "Astrology is a traditional faith-based practice. This horoscope is a general reading for a "
                          "Moon sign, offered for reflection and guidance only - not a prediction of certain events and "
                          "not a substitute for professional advice. For health, legal or financial matters, please "
                          "consult a qualified professional.",
}

RASHIFAL_HUB = PageCopy(
    nav_label="Horoscope",
    title="Horoscope Today - Free Daily Horoscope for All 12 Zodiac Signs",
    meta_description=(
        "Today's horoscope for all 12 zodiac signs on one page - Aries to Pisces, by Vedic Moon sign. Written every day "
        "from exact planetary transits (Swiss Ephemeris, Lahiri). Free daily, weekly, monthly and yearly horoscopes."
    ),
    h1="Horoscope Today - All 12 Signs",
    intro=(
        "Today's horoscope for every zodiac sign, refreshed each morning from the real positions of the planets "
        "counted from your Moon sign. Pick your sign for the full daily reading - always free."
    ),
    card_blurb="Today's horoscope for all 12 signs, plus weekly, monthly and yearly readings - always free.",
    sections=(
        Section("Which sign should I read?", (
            Markup("Vedic horoscopes are written for your Moon sign (rashi) - the sign the Moon occupied when you were "
                   "born - not the Sun sign used in Western horoscope columns. If you do not know it, create your "
                   '<a href="{url_kundali}">free birth chart</a>: it shows your Moon sign, nakshatra and ascendant in '
                   "seconds. If you only know your Western Sun sign, read that too - but the Moon sign is the one "
                   "these readings are calculated for."),
        )),
        Section("How these daily horoscopes are made", (
            Markup("For each sign and period the Swiss Ephemeris gives us the positions of all nine planets, every "
                   "sign change and "
                   "retrograde station inside the period, the Moon's nakshatra and tithi, and Saturn's sade sati and "
                   "dhaiya status - all counted as houses from that sign. The written horoscope interprets exactly "
                   "those facts. It is a general reading for a Moon sign; for guidance from your own chart, try the "
                   '<a href="{url_consultation}">AI astrologer</a>.'),
        )),
    ),
    faqs=(
        ("When is today's horoscope updated?",
         "Every day shortly after midnight Indian time. The date of the reading is printed on every page, along with "
         "the time it was last updated."),
        ("Is this horoscope by Moon sign or Sun sign?",
         "By Moon sign (janma rashi), as is traditional in Indian astrology. Your free birth chart on this site shows "
         "your Moon sign."),
        ("Are the horoscopes free?",
         "Yes - daily, weekly, monthly, six-monthly and yearly horoscopes for all 12 signs are free and always will be."),
        ("How is this different from other horoscope sites?",
         "Every reading starts from calculated planetary positions (Swiss Ephemeris, Lahiri ayanamsa) that are printed "
         "on the page, so you can see what the horoscope is based on."),
    ),
    extra=_RASHIFAL_LABELS,
)

RASHIFAL_WEEKLY = PageCopy(
    nav_label="Weekly Horoscope",
    title="Weekly Horoscope - This Week's Horoscope for All 12 Zodiac Signs",
    meta_description=(
        "Free weekly horoscope for all 12 zodiac signs, Monday to Sunday: career, money, love and wellbeing by Vedic "
        "Moon sign, with the week's key planetary dates. Updated every Monday."
    ),
    h1="Weekly Horoscope - All 12 Signs",
    intro=(
        "This week's horoscope for every sign, Monday to Sunday, written from the week's real planetary movements "
        "counted from your Moon sign. Pick your sign for the full weekly reading."
    ),
    sections=(
        Section("What the weekly horoscope covers", (
            "Each weekly reading looks at the Moon's journey through the week, any planet changing sign or direction "
            "between Monday and Sunday, and where the slow planets - Jupiter, Saturn, Rahu and Ketu - sit from your "
            "sign. It then turns those facts into practical notes on work and money, love and family, and wellbeing, "
            "with the dates that matter.",
            Markup('For a closer view, read <a href="{url_rashifal_hub}">today\'s horoscope</a>; for the bigger '
                   "picture, every sign also has a monthly, six-monthly and yearly horoscope."),
        )),
    ),
    faqs=(
        ("When does the weekly horoscope change?",
         "Every Monday, shortly after midnight Indian time. The week it covers is printed on each page."),
        ("Which days does a week cover?", "Monday to Sunday."),
        ("Is the weekly horoscope by Moon sign?",
         "Yes. Read the sign your Moon was in at birth (your rashi). Your free birth chart shows it."),
    ),
    extra=_RASHIFAL_LABELS,
)

RASHIFAL_RASHI = PageCopy(
    nav_label="{rashi}",
    title="{rashi} Horoscope - Today, Weekly, Monthly and Yearly ({latin} Rashi)",
    meta_description=(
        "All {rashi} horoscopes in one place: {rashi} horoscope today, this week, this month, the next 6 months and the "
        "year ahead, written from exact planetary transits for {latin} rashi ({deva}). Free."
    ),
    h1="{rashi} Horoscope",
    intro="Horoscopes for {rashi} ({latin} rashi, {deva}) as the Moon sign. Sign lord: {lord}.",
    faqs=(),
    extra=_RASHIFAL_LABELS,
)

RASHIFAL_READING = PageCopy(
    nav_label="{rashi}",
    title="", meta_description="", h1="", intro="",  # per period, below
    extra={
        **_RASHIFAL_LABELS,
        "title_today": "{rashi} Horoscope Today - {latin} Rashi Daily Horoscope",
        "h1_today": "{rashi} Horoscope Today",
        "meta_today": "Free {rashi} horoscope today: career, money, love, family and wellbeing for {rashi} Moon sign "
                      "({latin} rashi), written from today's exact planetary transits (Swiss Ephemeris, Lahiri). "
                      "Updated every day.",
        "title_weekly": "{rashi} Weekly Horoscope - {latin} Rashi This Week",
        "h1_weekly": "{rashi} Weekly Horoscope",
        "meta_weekly": "Free {rashi} weekly horoscope, Monday to Sunday: career, money, love and wellbeing for {rashi} "
                       "Moon sign ({latin} rashi), with the week's key dates from exact planetary transits. Updated "
                       "every Monday.",
        "title_monthly": "{rashi} Monthly Horoscope - {latin} Rashi This Month",
        "h1_monthly": "{rashi} Monthly Horoscope",
        "meta_monthly": "Free {rashi} monthly horoscope: what this month's planetary transits bring to {rashi} Moon "
                        "sign ({latin} rashi) - career, money, love and wellbeing, with dated sign changes and "
                        "retrogrades. Refreshed every month.",
        "title_6-months": "{rashi} Horoscope for the Next 6 Months - {latin} Rashi Half-Yearly",
        "h1_6-months": "{rashi} Horoscope: Next 6 Months",
        "meta_6-months": "{rashi} horoscope for the next 6 months: career, money, family and wellbeing trends for "
                         "{rashi} Moon sign ({latin} rashi) with every major transit date. Free, refreshed every month.",
        "title_yearly": "{rashi} Yearly Horoscope - {latin} Rashi for the Next 12 Months",
        "h1_yearly": "{rashi} Yearly Horoscope",
        "meta_yearly": "{rashi} yearly horoscope: the next 12 months for {rashi} Moon sign ({latin} rashi) - career, "
                       "money, love, wellbeing, sade sati status and all major transit dates. Free, refreshed every "
                       "month.",
    },
)

SIDEREAL = PageCopy(
    nav_label="Sidereal Chart",
    title="Free Sidereal Birth Chart Calculator (Lahiri Ayanamsa)",
    meta_description=(
        "Calculate your free sidereal birth chart in seconds. Lahiri ayanamsa, Swiss Ephemeris precision: "
        "rising sign, Moon sign, nakshatra, grahas and dasha dates."
    ),
    h1="Free Sidereal Birth Chart Calculator",
    intro=(
        "Most people arrive here after noticing something that doesn't add up: a Western horoscope says one Sun "
        "sign, an Indian astrologer says the one before it. A sidereal birth chart is what explains that gap. "
        "Put your birth date, time and city in below and you'll get the sidereal positions of all nine grahas, "
        "your rising sign, your Moon sign with its nakshatra, and your Vimshottari dasha dates. Free, no sign-up, "
        "and not one figure on the page is estimated."
    ),
    form_heading="Enter birth details",
    submit_label="Calculate sidereal chart",
    result_heading="Your sidereal birth chart",
    card_blurb="Sidereal chart on the Lahiri ayanamsa: rising sign, Moon sign, nakshatra, all nine grahas and your dasha dates.",
    product=Product(
        heading="Have this sidereal chart read for you (PDF)",
        text="A written reading of this exact chart, built from your own placements rather than your Sun sign, and "
             "delivered as a PDF you can keep. Two depths, depending on how much you want.",
        points=(
            "What your rising sign and graha placements say about temperament and work",
            "Which mahadasha and antardasha you're in now, with the dates",
            "Remedies that fit this chart rather than a generic list",
        ),
    ),
    extra={
        "cta_disclaimer":
            "The chart is calculated, the reading is written. Swiss Ephemeris works out every degree and every "
            "dasha date, and AI turns that finished chart into plain language. Astrology is a traditional "
            "faith-based practice, offered here for reflection, so take health, legal or money decisions to a "
            "qualified professional.",
        "download_button": "Download chart PDF - free",
        "download_text": "About five A5 pages you can print: your birth details, the rising sign and nakshatra "
                         "summary, both charts (lagna and navamsa), the full graha table with degrees, plus "
                         "mangal dosha, sade sati and your current dasha. No sign-up. There's no AI anywhere in "
                         "it either, because every value is computed by the Swiss Ephemeris rather than "
                         "interpreted. If you want to know what it means, the Simple report "
                         "(₹{price_kundali_simple}) adds a written reading and the Detailed book "
                         "(₹{price_kundali}) adds dated timelines and remedies.",
        "download_working": "Preparing your PDF…",
        "download_busy": "The PDF couldn't be prepared just now, because the server is printing something else. "
                         "Try again in a minute. The chart on this page stays free to read.",
        "download_limit": "Several chart PDFs have already been prepared from this connection in the last hour. "
                          "Please try a little later. The chart on this page stays free to read.",
        "download_failed": "The download couldn't be started. Check your connection and try again. The chart on "
                           "this page stays free to read.",
        "buy_simple": "Get the ₹{price_kundali_simple} report",
        "gets_simple": "A short PDF: this chart, your dasha periods, your remedies.",
        "buy_detailed": "Get the ₹{price_kundali} book",
        "gets_detailed": "35-45 pages, ready to print and bind. Every year of the next twenty dated for you, with "
                         "career, marriage, money and health each read properly.",
    },
    sections=(
        Section("What a sidereal birth chart is", (
            "A sidereal birth chart maps the sky against the fixed stars, which is where the word comes from: "
            "sidus, Latin for star. Your grahas are placed by where they actually sat among the constellations "
            "at the moment you were born, not by where the seasons were.",
            "That's the zodiac Indian astrology has used for a couple of thousand years, so a sidereal chart and "
            "a Vedic kundali are the same object under two names. Jyotish, Vedic astrology, sidereal astrology: "
            "the labels differ by tradition and by continent, and the underlying chart doesn't.",
        )),
        Section("Why your sidereal sign is usually one sign back", (
            "Because the two zodiacs have drifted apart. Tropical astrology fixes 0 degrees Aries to the spring "
            "equinox, and the equinox itself creeps backwards through the constellations at roughly one degree "
            "every 72 years. Sidereal astrology keeps 0 degrees Aries pinned to the stars instead.",
            "In 2026 the gap is about 24 degrees and 13 minutes. That's most of a sign, which is why a Sun at 12 "
            "degrees tropical Leo lands at 17 degrees sidereal Cancer. Most people move back one sign. Anyone "
            "born in roughly the last six days of a tropical sign usually doesn't move at all.",
            "Here's the thing: nothing about the sky changed. Only the ruler being held up against it did.",
        )),
        Section("Sidereal or tropical: is one of them wrong?", (
            "Neither is wrong, and treating this as a contest is the fastest way to misunderstand both. They're "
            "two conventions for measuring the same positions, and each has a body of practice built on top of "
            "it that assumes its own measurement.",
            "What matters is that you can't mix them. Nakshatras, Vimshottari dasha, mangal dosha and guna milan "
            "were all worked out on sidereal positions, so feeding them a tropical chart produces answers that "
            "look plausible and are quietly wrong by nearly a sign. If you're reading Indian astrology, you want "
            "the sidereal chart. If you're reading a Western transit report, you want the tropical one.",
        )),
        Section("Which ayanamsa this calculator uses, and why it matters", (
            "This page uses Lahiri, which is the ayanamsa the Indian government's calendar reform committee "
            "settled on and the one almost all Indian astrologers work with. The ayanamsa is just the size of "
            "that gap between the two zodiacs, and different schools measure it slightly differently.",
            "The disagreements are small but they aren't nothing. Raman and Krishnamurti sit within about a "
            "degree of Lahiri, and a degree is enough to move a planet sitting near a boundary into the next "
            "nakshatra, which changes the pada and can shift a dasha start date by months. So when a chart you "
            "got elsewhere disagrees with this one by a fraction of a degree, the ayanamsa is usually the reason "
            "rather than a mistake by either side.",
        )),
        Section("How this sidereal chart is calculated", (
            "Every position on this page comes from the Swiss Ephemeris, the same high-precision astronomical "
            "library professional astrology software is built on. Positions are computed for your exact "
            "timestamp and coordinates, then the Lahiri ayanamsa is subtracted to give sidereal longitudes. "
            "Nothing is rounded to a sign and nothing is looked up in a table.",
            "No part of that calculation is done by AI, and it's worth being precise about why that distinction "
            "matters: astronomy is deterministic, so a calculation either is right or isn't, and the Swiss "
            "Ephemeris is how you make sure it is. AI is used on this site only to write interpretations of a "
            "chart that has already been computed.",
            _ACCURACY_POINTS,
        )),
        Section("Reading the chart you get back", (
            "Start with three values, because they carry most of the weight. The rising sign (lagna) is the sign "
            "that was climbing over the eastern horizon at your birth, and it sets the whole house layout. The "
            "Moon sign (rashi) is what Indian horoscope columns are actually written for, which surprises people "
            "who expect their Sun sign. The nakshatra is the lunar mansion the Moon occupied, and it decides "
            "where your dasha sequence starts.",
            "Most people don't realise the rashi and the lagna are different things, and that's usually the "
            "first question after a chart appears. Under the chart you'll find a table with each graha's exact "
            "degree, its nakshatra and its pada, so you can check this against any kundali you already have "
            "rather than take it on trust.",
        )),
        Section("Why the birth time matters more than people expect", (
            "The rising sign moves about one degree every four minutes, so it changes sign roughly every two "
            "hours. A birth time that's out by fifteen minutes can leave every house in the chart correct or "
            "shift the lot, depending on how close you were born to a boundary.",
            "Use the time on a birth certificate or hospital record if you can get it. The Moon is far more "
            "forgiving, at about 13 degrees a day, so your Moon sign and usually your nakshatra survive an "
            "approximate time even when the houses don't. Place matters too, though less than people fear: "
            "picking a city 50 to 100 km from your actual town moves the rising sign by well under a degree.",
        )),
        Section("What a sidereal chart won't tell you", (
            "It won't tell you what will happen. A sidereal birth chart is a record of positions and the "
            "periods that follow from them, and the reading built on top of it is interpretation within a "
            "tradition, which is a different kind of claim from the astronomy underneath.",
            "Traditions also disagree with each other on real points, including which ayanamsa is correct and "
            "how much weight a divisional chart deserves, and anyone telling you those questions are settled is "
            "overselling. What you can rely on here is the arithmetic. Calculate your free Vedic astrology chart above, "
            "download the PDF if you want it on paper, or have the reading written if you'd rather someone "
            "walked you through what the placements mean.",
        )),
    ),
    faqs=(
        ("Is a sidereal birth chart the same as a Vedic birth chart?",
         "Yes. Vedic astrology has always used the sidereal zodiac, so a Vedic kundali and a sidereal chart are "
         "the same chart described in different vocabularies. You'll see the same thing called a Jyotish chart, "
         "a janam kundali or a janam patrika."),
        ("Is this the same thing as a free Vedic birth chart?",
         "Yes, and the different names cause more confusion than the astrology does. A free Vedic astrology "
         "chart, a janam kundali and a sidereal birth chart are one calculation described three ways. This page "
         "gives you all of it at no cost: rising sign, Moon sign with its nakshatra, every graha at its exact "
         "degree, and your dasha dates. What costs money is somebody writing about what it means, never the "
         "chart itself."),
        ("Why is my sidereal Sun sign different from my Western one?",
         "Because the tropical zodiac is anchored to the spring equinox and the sidereal one to the stars, and "
         "the two have drifted about 24 degrees apart by 2026. That's most of a sign, so most people's Sun moves "
         "back one. If you were born in the last few days of a tropical sign, it often doesn't move."),
        ("Which ayanamsa should I use?",
         "Lahiri, unless you have a specific reason not to. It's the Indian standard and what this page uses. "
         "Raman and Krishnamurti differ from it by under a degree, which rarely changes a sign but can move a "
         "graha sitting near a nakshatra boundary and shift dasha dates."),
        ("Do I need my exact birth time for a sidereal chart?",
         "For the houses, yes, as close as you can get: the rising sign moves a degree every four minutes. For "
         "your Moon sign and nakshatra an approximate time is usually fine, because the Moon only covers about "
         "13 degrees a day."),
        ("Is this sidereal birth chart calculator free?",
         "The chart is free and so is the printable PDF, with no account and no email needed. The written "
         "interpretations are the paid part, and the calculation behind them is the same Swiss Ephemeris "
         "computation you get for nothing here."),
        ("Does sidereal astrology use the same houses as Western astrology?",
         "Usually not. This chart uses whole-sign houses, where the rising sign is the first house and each "
         "following sign is the next, which is the standard Indian approach. Western charts more often split the "
         "houses unevenly using Placidus, so a planet can sit in different house numbers in the two systems "
         "even when its degree is identical."),
    ),
)

PAGES = {
    "home": HOME, "kundali": KUNDALI, "matching": MATCHING, "mangal-dosha": MANGAL_DOSHA, "sade-sati": SADE_SATI,
    "consultation": CONSULTATION, "rashifal-hub": RASHIFAL_HUB, "rashifal-weekly": RASHIFAL_WEEKLY,
    "rashifal-rashi": RASHIFAL_RASHI, "rashifal-reading": RASHIFAL_READING,
}

# Pages the registry gives THIS tree and not the others, so their copy cannot live in PAGES: every content
# module's PAGES must equal pages.COPY_KEYS exactly, which is what keeps the three trees in step. A page that
# exists in one language is a different thing from a page whose translation is missing, and this is where the
# first kind goes. tests/test_pages_i18n.py pins these keys against i18n.EN_ONLY_TOOL_KEYS.
LOCAL_PAGES = {"sidereal": SIDEREAL}
