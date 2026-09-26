"""The twelve rashi hub bodies for the English tree (`/horoscope/{sign}`).

One essay per rashi, not one essay with the sign's name substituted twelve times. What genuinely differs between
them is the material: the sign lord and the houses it also owns, which grahas are exalted or debilitated there,
the element and the quality, the nakshatras the sign spans, which three signs Saturn has to be sitting in for
this rashi to be in sade sati, and what the sign tends to do when its own lord's mahadasha is running.

House counting on every page here is from the MOON sign, which is how an Indian horoscope column is read.
Nothing here is dated: which rashis are in sade sati right now is computed from Saturn's real position and
printed higher up the same page, so this copy stays true without an edit.

Voice: the content brief. Keywords: the keyword map's English column ("{sign} horoscope", "{latin} rashi").
Trust requirement: no section may name AI without naming Swiss Ephemeris in the same section.
"""

from app.web.pages import RashiBody, Section

# Shared closer, varied per rashi by what precedes it. Kept as a function rather than a constant so no two
# rashis end on an identical paragraph.
def _how_made(sign: str, detail: str) -> Section:
    return Section(f"How the {sign} horoscopes here are put together", (
        f"Every number behind these pages comes from the Swiss Ephemeris, the astronomical library professional "
        f"astrology software runs on, using the sidereal zodiac and the Lahiri ayanamsa that Indian panchangs "
        f"follow. {detail}",
        "The written reading is the second step. AI turns that calculated position list into plain English, and "
        "it only ever reads what the Swiss Ephemeris worked out: it is not allowed to place a graha, date a "
        "transit or decide a dasha for itself. So the dates on these pages are arithmetic, and only the wording "
        "around them is interpretation.",
    ))


RASHI_BODIES: dict[str, RashiBody] = {

    # ---------------------------------------------------------------- 1. Mesha / Aries
    "mesha": RashiBody(
        intro="Aries horoscopes, read from the Moon in Mesh rashi ({deva}). Sign lord: {lord}, the graha that also "
              "owns your 8th house from here, which is why Aries readings so often turn on how Mars is placed.",
        sections=(
            Section("What being an Aries Moon actually means", (
                "Your rashi is the sign the Moon occupied at your birth, and an Indian horoscope column is written "
                "for that, not for your Sun sign. Aries is the first sign of the sidereal zodiac, a fire sign and a "
                "movable one, which in practice means Aries readings are about starts rather than maintenance.",
                "Movable (chara) signs take initiative and lose interest at roughly the same speed. That is the "
                "honest version of the Aries description, and it is why a good Aries horoscope talks about what you "
                "begin this week more than what you finish.",
            )),
            Section("Mars, and why an Aries reading watches it so closely", (
                "Mars rules Mesh rashi, so wherever Mars is sitting on a given day is the single most useful fact "
                "in an Aries horoscope. Mars is comfortable in its own sign and in Scorpio, at its strongest in "
                "Capricorn where it is exalted, and weakest in Cancer.",
                "Here is the part most people miss: Mars also owns your 8th house counted from Aries. That is the "
                "house of upheaval and of things that arrive without notice. A Mars transit that looks purely "
                "energetic from one angle can read quite differently from the other, which is why two Aries "
                "horoscopes on two sites can disagree without either being careless.",
            )),
            Section("The nakshatras inside Mesh rashi", (
                "Aries spans Ashwini, Bharani and the first quarter of Krittika. Which one your Moon fell in "
                "decides where your Vimshottari dasha starts, and that is a much sharper piece of information than "
                "the sign alone.",
                ["Ashwini, ruled by Ketu: quick, restless, good at the first ten minutes of anything.",
                 "Bharani, ruled by Venus: holds more than it shows, and carries things through discomfort.",
                 "Krittika's first pada, ruled by the Sun: cutting, precise, not especially patient with vagueness.",
                 "A Moon near 26 degrees of Aries is close to the Krittika boundary, so a few minutes of birth time "
                 "can move the dasha sequence entirely."],
            )),
            Section("Sade sati and Saturn for Aries", (
                "Sade sati runs when Saturn transits the sign before your rashi, your rashi itself, and the sign "
                "after. For Mesh rashi that means Saturn in Pisces, Aries or Taurus, and it is roughly seven and a "
                "half years from end to end.",
                "The smaller Saturn phase, dhaiya, runs when Saturn is in the 4th or 8th from your Moon, which for "
                "Aries means Cancer or Scorpio. Whether either is running for you today is worked out from "
                "Saturn's real position and printed further up this page, including the retrograde re-entries that "
                "hand calculation usually rounds away.",
            )),
            Section("Aries under its own mahadasha", (
                "A Mars mahadasha lasts seven years. For an Aries Moon it tends to be the period where things that "
                "were being tolerated stop being tolerated: job changes, moves, arguments that had been postponed.",
                "It is not a period to read as good or bad on its own. What matters is which houses Mars owns in "
                "your birth chart and where it actually sits, and that needs the real chart rather than the sign. "
                "The free birth chart will give you your mahadasha sequence with dates.",
            )),
            _how_made("Aries", "That means the Moon's position to the arc-second, every sign change and retrograde "
                               "station inside the period, and Saturn's phases counted from Mesh rashi."),
        ),
        faqs=(
            ("What is today's Aries horoscope based on?",
             "The Moon's exact position, the nine grahas' positions for the day, and Saturn's standing counted from "
             "Mesh rashi. All of it is calculated with the Swiss Ephemeris rather than estimated, and the reading "
             "interprets those facts for an Aries Moon sign."),
            ("Is Aries my rashi or my sun sign?",
             "In Vedic astrology your rashi is your Moon sign. Plenty of people who call themselves Aries from a "
             "Western horoscope have a different Vedic Moon sign, because the sidereal zodiac sits about 24 degrees "
             "away from the tropical one. The free birth chart settles it in a few seconds."),
            ("Which signs suit Mesh rashi for marriage?",
             "Traditionally Leo and Sagittarius sit easily with Aries, both being fire signs, and Gemini and "
             "Aquarius are usually workable. But guna milan scores eight factors, not sign compatibility alone, and "
             "mangal dosha is checked separately. Run both charts through the matching tool for a real answer."),
            ("How long does sade sati last for Aries?",
             "About seven and a half years, while Saturn crosses Pisces, Aries and Taurus. It is not continuous "
             "difficulty. The middle stretch, with Saturn on the Moon itself, is the one classical texts treat as "
             "heaviest."),
            ("Why does my Aries horoscope differ from another site's?",
             "Usually the zodiac. Most Western sites use the tropical zodiac; Indian astrology uses the sidereal "
             "one with Lahiri ayanamsa, and the two disagree by roughly a sign for many birthdays. Some sites also "
             "write for the Sun sign rather than the Moon sign."),
            ("What is the lucky number and colour shown on the Aries pages?",
             "They come from the graha ruling the day and from Mars as the sign lord, which is the traditional "
             "basis. Treat them as a custom worth keeping rather than a rule that decides anything."),
        ),
    ),

    # ---------------------------------------------------------------- 2. Vrishabha / Taurus
    "vrishabha": RashiBody(
        intro="Taurus horoscopes, read from the Moon in Vrishabh rashi ({deva}). Sign lord: {lord}. This is the sign "
              "the Moon is happiest in, which changes the whole tone of a Taurus reading.",
        sections=(
            Section("The Moon is exalted in Taurus, and it shows", (
                "Of the twelve rashis, this is the one where the Moon is strongest. The Moon reaches exact "
                "exaltation at 3 degrees of Taurus, and a Moon anywhere in the sign is considered well placed.",
                "Practically, that tends to mean steadiness rather than calm. A Taurus Moon holds a mood for a long "
                "time, pleasant or otherwise, which is why Taurus horoscopes talk about pace and patience where an "
                "Aries reading talks about starts.",
            )),
            Section("Venus, the sign lord, and where it stands", (
                "Venus rules Vrishabh rashi and is exalted in Pisces, at home in Libra, and weakest in Virgo. When "
                "Venus is retrograde or close to the Sun, a Taurus reading usually turns quieter: money and "
                "relationship matters slow down rather than break.",
                "Venus also owns your 6th house from Taurus, the house of work, debts and health routines. That "
                "second ownership is why a strong Venus period for Taurus often shows up as steady earning rather "
                "than as romance, which surprises people.",
            )),
            Section("Sade sati, dhaiya and Vrishabh rashi", (
                "For a Taurus Moon, sade sati runs while Saturn is in Aries, Taurus or Gemini. Dhaiya runs when "
                "Saturn reaches Leo or Sagittarius, the 4th and 8th from your sign.",
                "Saturn also owns the 9th and 10th houses from Taurus, which are the two most career-relevant "
                "houses in the chart. That is a genuine difference between signs: the same Saturn transit does not "
                "mean the same thing for Taurus as it does for a sign where Saturn owns nothing useful.",
            )),
            Section("The nakshatras Taurus covers", (
                "Vrishabh rashi runs from the second quarter of Krittika through Rohini and into the first half of "
                "Mrigashira. Rohini is the Moon's own nakshatra and sits entirely inside Taurus, which is part of "
                "why this sign carries the Moon so well.",
                "If your Moon is in the first three degrees of Taurus you are in Krittika, ruled by the Sun, and "
                "your dasha sequence starts somewhere quite different from a Rohini birth. Birth time matters here: "
                "the Moon moves about one degree every two hours.",
            )),
            Section("What a Venus mahadasha tends to bring a Taurus Moon", (
                "Venus mahadasha runs twenty years, the longest of the nine. For Vrishabh rashi it is usually the "
                "stretch where comfort becomes possible rather than aspirational: property, vehicles, marriage, the "
                "things that take years rather than weeks.",
                "As always the sign is only half the story. Whether that period actually delivers depends on where "
                "Venus sits in your own chart and what it aspects, which the free birth chart lays out with dates "
                "for every mahadasha and antardasha.",
            )),
            _how_made("Taurus", "Rohini's boundaries, the Moon's exaltation degree and Saturn's entry and exit "
                                "dates for Vrishabh rashi all come out of that calculation rather than a table."),
        ),
        faqs=(
            ("Why is Taurus called the Moon's best sign?",
             "The Moon is exalted in Taurus, reaching its exact exaltation degree at 3 degrees of the sign. In "
             "classical terms that is the placement where the Moon gives its steadiest results, which is why Taurus "
             "Moon readings lean towards endurance rather than volatility."),
            ("What does today's Taurus horoscope actually use?",
             "The day's planetary positions computed with the Swiss Ephemeris, counted as houses from Vrishabh "
             "rashi, plus the tithi and the Moon's nakshatra. The reading explains those; it does not invent them."),
            ("When is sade sati for Vrishabh rashi?",
             "While Saturn transits Aries, Taurus and Gemini, about seven and a half years in total. The exact "
             "dates, including retrograde re-entries, are calculated from Saturn's real motion and shown on this "
             "page rather than rounded to whole months."),
            ("Is Taurus a good match with Scorpio?",
             "They sit opposite each other, which traditional matching treats as intense rather than easy. Guna "
             "milan looks at nakshatra pairs rather than sign pairs, so the score can be high or low for the same "
             "sign combination. Check both birth details in the matching tool."),
            ("My Western horoscope says Taurus but this site says Aries. Which is right?",
             "Both, under their own conventions. Western astrology uses the tropical zodiac and Indian astrology "
             "the sidereal one, and the gap between them is roughly 24 degrees at the moment. Dashas, nakshatras "
             "and dosha checks all need the sidereal chart."),
            ("Which body parts does Taurus rule?",
             "The face, throat and neck, in the traditional kalapurusha scheme where Aries is the head and the "
             "signs run downwards. It is a traditional correspondence, not medical advice."),
        ),
    ),

    # ---------------------------------------------------------------- 3. Mithuna / Gemini
    "mithuna": RashiBody(
        intro="Gemini horoscopes, read from the Moon in Mithun rashi ({deva}). Sign lord: {lord}, which is also "
              "the fastest graha in the chart, so Gemini readings change tone more often than most.",
        sections=(
            Section("A dual sign, and what that changes", (
                "Gemini is an air sign and a dual (dwisvabhava) sign. Movable signs start things and fixed signs "
                "hold them; dual signs adapt, which is a genuinely different pattern rather than a softer version "
                "of either.",
                "Most people don't realise how much of a Gemini reading follows Mercury's speed. Mercury can cover "
                "a sign in a fortnight or sit in one for two months when it turns retrograde. That is why Gemini "
                "horoscopes are often more useful weekly than daily.",
            )),
            Section("Mercury retrograde, minus the folklore", (
                "Mercury turns retrograde three or four times a year for about three weeks. For Mithun rashi that "
                "matters more than for most signs, because Mercury is your sign lord and also owns the 4th house "
                "from here.",
                "What the classical texts actually say is narrower than the internet version: a retrograde graha is "
                "not weak, it is turned inward, and results tend to arrive late rather than not at all. The exact "
                "station dates are calculated, not estimated, and they appear on the transit table above.",
            )),
            Section("Nakshatras, and the Ardra question", (
                "Mithun rashi spans the last half of Mrigashira, all of Ardra and three quarters of Punarvasu. "
                "Ardra, ruled by Rahu, sits squarely in the middle of the sign and carries a reputation it only "
                "half deserves.",
                "Ardra is associated with disruption, but in dasha terms it starts your Vimshottari cycle with "
                "Rahu, which is an eighteen year period. Whether that reads as disruption or as unusual opportunity "
                "depends on your chart, not on the nakshatra's reputation.",
            )),
            Section("Saturn's phases counted from Gemini", (
                "Sade sati for Gemini means Saturn in Taurus, Gemini or Cancer. Dhaiya means Saturn in Virgo or "
                "Capricorn, the 4th and 8th from your Moon.",
                "Saturn owns the 8th and 9th houses from Mithun rashi, an awkward pairing: one house of sudden "
                "change and one of fortune and father. Readings that treat Saturn as uniformly heavy miss that the "
                "same transit carries both meanings for this sign.",
            )),
            Section("Gemini and the sign it is most often confused with", (
                "Here's the thing: Gemini and Virgo share a lord. Both are ruled by Mercury, and people read "
                "descriptions of one and recognise themselves in the other.",
                "The difference is element and quality. Gemini is air and dual, Virgo is earth and dual, and "
                "Mercury is exalted in Virgo but merely at home in Gemini. If you are unsure which is actually your "
                "rashi, the free birth chart gives the Moon's degree rather than a guess.",
            )),
            _how_made("Gemini", "Mercury's stations, the Moon's nakshatra pada and every sign change inside the "
                                "period come from that calculation, to the minute."),
        ),
        faqs=(
            ("What does the Gemini horoscope today use as its basis?",
             "The nine grahas' positions for the day, computed with the Swiss Ephemeris and counted as houses from "
             "Mithun rashi, together with the Moon's nakshatra and the day's tithi. AI writes the explanation from "
             "those calculated facts and nothing else."),
            ("Does Mercury retrograde really affect Gemini more?",
             "It is your sign lord, so it carries more weight for Mithun rashi than for a sign Mercury does not "
             "rule. Classical texts describe a retrograde graha as inward-turned rather than broken, and the "
             "practical reading is delay rather than denial."),
            ("When does sade sati start for Mithun rashi?",
             "When Saturn enters Taurus, the sign before yours, and it ends when Saturn leaves Cancer. The real "
             "dates come from Saturn's actual transit including its retrograde re-entries, which is what the sade "
             "sati calculator works out from your birth details."),
            ("Which nakshatras fall in Gemini?",
             "The second half of Mrigashira, all four quarters of Ardra, and the first three quarters of Punarvasu. "
             "Your Vimshottari dasha begins from whichever one the Moon was in, and from how far through it the "
             "Moon had travelled."),
            ("Is Gemini compatible with Sagittarius?",
             "They are opposite signs, which traditional matching treats as complementary but demanding. Ashtakoota "
             "scoring works from nakshatras rather than signs, so two Gemini and Sagittarius pairs can score very "
             "differently."),
            ("Why do Gemini daily horoscopes change so much?",
             "Because the Moon moves through a sign in roughly two and a quarter days and Mercury is quick too. A "
             "daily reading for a Mercury-ruled sign genuinely has more moving parts than one for a Saturn-ruled "
             "sign."),
        ),
    ),

    # ---------------------------------------------------------------- 4. Karka / Cancer
    "karka": RashiBody(
        intro="Cancer horoscopes, read from the Moon in Kark rashi ({deva}). Sign lord: {lord}, the Moon itself, which "
              "makes this the one rashi whose lord changes sign every two and a half days.",
        sections=(
            Section("The only sign ruled by the Moon", (
                "Cancer is a water sign, a movable one, and the only rashi whose lord is the Moon. That single fact "
                "explains most of what is distinctive about Cancer readings.",
                "Your sign lord completes the whole zodiac in about 27 days. Every other rashi has a lord that "
                "stays put for weeks, months or years. So a Cancer horoscope has a genuine monthly rhythm built "
                "into it, and the waxing and waning of the Moon matters more here than anywhere else.",
            )),
            Section("Jupiter is exalted in Cancer", (
                "Jupiter reaches exact exaltation at 5 degrees of Cancer, and a Jupiter transit through Kark rashi "
                "is one of the more genuinely favourable things that happens to this sign, roughly once every "
                "twelve years.",
                "Mars, by contrast, is debilitated in Cancer at 28 degrees. Both facts are about the sign itself "
                "rather than about you, but they are why Cancer readings treat Jupiter and Mars transits so "
                "differently from one another.",
            )),
            Section("Sade sati, dhaiya and Kark rashi", (
                "For a Cancer Moon, sade sati runs while Saturn is in Gemini, Cancer or Leo. Dhaiya arrives when "
                "Saturn reaches Libra or Aquarius.",
                "Saturn owns the 7th and 8th houses from Cancer, which is the classical reason Cancer's sade sati "
                "is often described in terms of partnerships and of things ending. That is a description of "
                "pressure, not a prediction, and how it lands depends on the birth chart underneath.",
            )),
            Section("Pushya, and the nakshatras in Cancer", (
                "Kark rashi covers the last quarter of Punarvasu, all of Pushya and all of Ashlesha. Pushya is "
                "widely treated as the most benefic of the twenty-seven nakshatras, and it sits entirely inside "
                "this sign.",
                ["Punarvasu's fourth pada, ruled by Jupiter: returns, second attempts, things coming back around.",
                 "Pushya, ruled by Saturn: patient, nourishing, the nakshatra chosen for starting things that need "
                 "to last.",
                 "Ashlesha, ruled by Mercury: sharp and self-protective, and the boundary into Leo falls inside it.",
                 "A Moon in the last degrees of Ashlesha is close to Gandanta, a junction classical texts treat "
                 "with care. Getting the birth time right matters more than usual there."],
            )),
            Section("Reading a Cancer horoscope without overreading it", (
                "A general rashifal is written for everybody whose Moon is in one of thirty degrees of the zodiac. "
                "That is a real signal, and it is a broad one.",
                "The narrower reading comes from your own chart: your lagna, the houses each graha owns for you, "
                "and which dasha is actually running. Astrology is a traditional, faith-based practice and this "
                "page is for reflection rather than instruction, so use it alongside your own judgement and take "
                "health, legal or money decisions to a qualified professional.",
            )),
            _how_made("Cancer", "The Moon's exact degree, Jupiter's exaltation point and Saturn's phases counted "
                                "from Kark rashi all come out of that calculation."),
        ),
        faqs=(
            ("Why is the Cancer horoscope different every day?",
             "Because the Moon rules Cancer and moves roughly 13 degrees a day, changing sign every two and a bit "
             "days. Its position is computed with the Swiss Ephemeris for the moment the page is refreshed, and "
             "the reading follows that."),
            ("What is special about Pushya nakshatra?",
             "It sits entirely within Cancer and is traditionally considered the most auspicious of the twenty-"
             "seven, which is why so many muhurtas are chosen in it. Its lord is Saturn, which is why a Pushya "
             "birth starts the Vimshottari dasha with a nineteen year Saturn period."),
            ("When is sade sati for Cancer?",
             "While Saturn crosses Gemini, Cancer and Leo. Whether it is running for you today, and the exact "
             "phase, is calculated from Saturn's real position rather than looked up in a table."),
            ("Is Cancer or Karka the same as Kark rashi?",
             "Yes. Karka, Kark and Cancer are the same sign written three ways. The slug on this site is the "
             "spelling people search for in each language, and the sign itself is identical."),
            ("Which planets are strong and weak in Cancer?",
             "Jupiter is exalted here and Mars is debilitated. The Moon rules the sign, so it is at home. These are "
             "properties of the sign, and what they mean for you depends on where those grahas sit in your own "
             "birth chart."),
            ("Can I read the Cancer horoscope if my sun sign is Cancer?",
             "You can, but it is not the reading meant for you. Indian horoscope columns are written for the Moon "
             "sign. The free birth chart will tell you your actual rashi in a few seconds, and it is often not the "
             "sign people expect."),
        ),
    ),

    # ---------------------------------------------------------------- 5. Simha / Leo
    "simha": RashiBody(
        intro="Leo horoscopes, read from the Moon in Singh rashi ({deva}). Sign lord: {lord}, the one graha that "
              "never turns retrograde, which gives Leo readings a steadier spine than most.",
        sections=(
            Section("A fixed fire sign with a fixed lord", (
                "Leo is fire and fixed (sthira). Fire gives the drive, fixed gives the refusal to be moved, and the "
                "combination is why Leo readings talk about position and standing more than about novelty.",
                "The Sun rules Singh rashi and is the only graha with no retrograde motion at all. It moves about "
                "one degree a day, every day, without pause. Your sign lord is the most predictable object in the "
                "chart.",
            )),
            Section("Leo has no exalted graha, and that is the point", (
                "Several signs have a graha that is exalted in them. Leo has none. Saturn, which opposes the Sun in "
                "most classical schemes, is the graha that sits least easily here.",
                "Really, this is less of a problem than it sounds. It means a Leo reading is driven by the Sun's "
                "own condition, by which house the Sun occupies in your birth chart, and by whether it is combust "
                "with anything, rather than by a transit lottery.",
            )),
            Section("Magha, and the nakshatras of Singh rashi", (
                "Leo spans Magha, Purva Phalguni and the first quarter of Uttara Phalguni. Magha opens the sign and "
                "is ruled by Ketu, which starts the Vimshottari dasha with a seven year Ketu period.",
                "Magha's first degrees are Gandanta, the junction between a water sign and a fire sign, and "
                "classical texts treat births there with more care than usual. A four minute difference in recorded "
                "birth time can move the Moon across a pada boundary, which is exactly the kind of error that "
                "manual calculation introduces and an ephemeris does not.",
            )),
            Section("Saturn, sade sati and the Sun's sign", (
                "Sade sati for Leo means Saturn in Cancer, Leo or Virgo. Dhaiya means Saturn in Scorpio or Taurus, "
                "the 4th and 8th from Singh rashi.",
                "Saturn owns the 6th and 7th houses from Leo. The classical reading of that is competition and "
                "partnership rather than loss, and the standard advice for Leo's sade sati is about sharing "
                "authority rather than about misfortune.",
            )),
            Section("What a Sun mahadasha does for a Leo Moon", (
                "The Sun's mahadasha is short, six years, the shortest of the nine. For Singh rashi it usually "
                "reads as a period of visibility: recognition, responsibility, being the person a decision waits "
                "on.",
                "Short periods are easy to underrate. Six years of a well placed Sun can settle a career, and six "
                "years of a weak one can be a long argument with authority. The free birth chart dates yours "
                "exactly, along with the antardashas inside it.",
            )),
            _how_made("Leo", "The Sun's position to the arc-second, Magha's Gandanta boundary and Saturn's phases "
                             "from Singh rashi are all calculated rather than looked up."),
        ),
        faqs=(
            ("What is the Leo horoscope today based on?",
             "The positions of all nine grahas for the day, worked out with the Swiss Ephemeris and counted as "
             "houses from Singh rashi, plus the Moon's nakshatra and the tithi. The written part explains those "
             "calculated facts in plain language."),
            ("Why is no planet exalted in Leo?",
             "That is simply how the classical scheme falls: the twelve exaltation signs do not include Leo. In "
             "practice a Leo reading leans harder on the Sun's own placement and strength in your chart than on "
             "which graha happens to be visiting."),
            ("When does sade sati begin for Singh rashi?",
             "When Saturn enters Cancer, and it ends when Saturn leaves Virgo. The calculator on this site works "
             "out the phase dates from Saturn's real motion, including the retrograde re-entries that shift the "
             "boundaries by months."),
            ("Is Leo compatible with Aquarius?",
             "They are opposite signs and share the Sun and Saturn as lords, which traditional texts read as a "
             "strong but demanding pairing. Guna milan scores nakshatras rather than signs, so run both birth "
             "details through the matching tool for an actual number."),
            ("Which nakshatra is at the start of Leo?",
             "Magha, ruled by Ketu. Its opening degrees are Gandanta, the sensitive junction between Cancer and "
             "Leo, so a birth right at the start of the sign needs an accurate birth time to place correctly."),
            ("Does the Sun ever go retrograde and change a Leo reading?",
             "No. The Sun never turns retrograde. That makes the sign lord's motion entirely regular, which is one "
             "reason Leo readings hold their shape across a month better than readings for Mercury-ruled signs."),
        ),
    ),

    # ---------------------------------------------------------------- 6. Kanya / Virgo
    "kanya": RashiBody(
        intro="Virgo horoscopes, read from the Moon in Kanya rashi ({deva}). Sign lord: {lord}, which is also "
              "exalted here, making Virgo the only sign whose lord is at its strongest in its own house.",
        sections=(
            Section("The one sign where the lord is also exalted", (
                "Mercury rules Virgo and is exalted in it, reaching its exact exaltation degree at 15 degrees of "
                "the sign. No other rashi has that arrangement.",
                "It is the reason Virgo readings so often come out in terms of accuracy, detail and correction. A "
                "well placed Mercury does not make life easier, it makes the difference between a right answer and "
                "a nearly right one more obvious to you than to other people.",
            )),
            Section("Venus is debilitated in Kanya rashi", (
                "Venus falls to its lowest point at 27 degrees of Virgo. That is a property of the sign, and it "
                "shapes how Virgo readings handle relationship and comfort themes: as things that need work rather "
                "than things that arrive.",
                "The classical texts also give the cancellation conditions, neecha bhanga, under which a debilitated "
                "graha recovers most of its strength. Whether any of them apply needs your actual chart, which is "
                "the kind of thing a general sign reading cannot tell you.",
            )),
            Section("Hasta, Chitra and the nakshatras here", (
                "Kanya rashi runs from the second quarter of Uttara Phalguni through Hasta and into the first half "
                "of Chitra.",
                ["Uttara Phalguni's last three padas, ruled by the Sun: steady, contractual, good at arrangements "
                 "that have to hold.",
                 "Hasta, ruled by the Moon: skilled with the hands, and the nakshatra most associated with craft.",
                 "Chitra's first half, ruled by Mars: design and precision with an edge to it.",
                 "The Virgo and Libra boundary falls in the middle of Chitra, so a late Virgo Moon and an early "
                 "Libra Moon can be a few minutes of birth time apart."],
            )),
            Section("Saturn's long phases for Virgo", (
                "Sade sati for Kanya rashi runs while Saturn transits Leo, Virgo or Libra. Dhaiya runs with Saturn "
                "in Sagittarius or Gemini.",
                "Saturn owns the 5th and 6th houses counted from Virgo. That gives its transits a distinctly "
                "practical flavour for this sign: study, children, work, health and the things you are in dispute "
                "with. The dates come from Saturn's real motion and are shown higher on this page.",
            )),
            Section("Virgo, Gemini and a common mix-up", (
                "Both signs are ruled by Mercury, so Virgo and Gemini descriptions borrow from each other and "
                "readers end up unsure which they are.",
                "Virgo is earth and dual, Gemini is air and dual. Mercury is exalted in Virgo and only at home in "
                "Gemini. If you have been reading the wrong one for years, that is worth two minutes with the free "
                "birth chart, which gives the Moon's exact degree rather than an approximation from your birth "
                "date.",
            )),
            _how_made("Virgo", "Mercury's exaltation degree, the Chitra boundary and every retrograde station "
                               "inside the period come from that calculation."),
        ),
        faqs=(
            ("What is the Virgo horoscope today calculated from?",
             "The day's positions of all nine grahas, computed with the Swiss Ephemeris and counted as houses from "
             "Kanya rashi, with the Moon's nakshatra and the tithi alongside. The written reading interprets those "
             "figures rather than producing them."),
            ("Why is Mercury strongest in Virgo?",
             "Virgo is both Mercury's own sign and its exaltation sign, with the exact degree at 15 Virgo. That "
             "combination is unique among the twelve rashis and is the main thing that separates Virgo readings "
             "from Gemini ones."),
            ("When is sade sati for Kanya rashi?",
             "While Saturn crosses Leo, Virgo and Libra, roughly seven and a half years. The precise phase dates "
             "for your birth details, including retrograde re-entries, come from the sade sati calculator."),
            ("What does a debilitated Venus in Virgo mean for me?",
             "On its own, very little. It is a property of the sign, not of your chart. It matters when Venus "
             "actually sits in Virgo in your birth chart, and even then classical texts describe conditions that "
             "cancel much of the weakness."),
            ("Which nakshatras belong to Virgo?",
             "The last three quarters of Uttara Phalguni, all of Hasta, and the first half of Chitra. Your "
             "Vimshottari dasha starts from whichever the Moon occupied and from how far into it the Moon had "
             "moved."),
            ("Is Kanya rashi the same as the Virgo star sign?",
             "It is the same sign, but not always the same people. Western star signs use the tropical zodiac and "
             "Indian astrology the sidereal one, so your Vedic rashi is often the sign before your Western sun "
             "sign."),
        ),
    ),

    # ---------------------------------------------------------------- 7. Tula / Libra
    "tula": RashiBody(
        intro="Libra horoscopes, read from the Moon in Tula rashi ({deva}). Sign lord: {lord}. This is also the sign "
              "where Saturn is exalted, which is why Libra handles Saturn transits better than its reputation says.",
        sections=(
            Section("Saturn is exalted in Libra, and Libra benefits", (
                "Saturn reaches its exaltation degree at 20 degrees of Libra. For most signs a Saturn transit is "
                "described as a period to get through; for Tula rashi the same graha is at its most constructive.",
                "That does not make sade sati painless for Libra, because sade sati is about Saturn's position "
                "relative to your Moon rather than about the sign Saturn is in. But it does mean the stretch when "
                "Saturn is actually crossing Libra is usually the most productive of the three.",
            )),
            Section("Venus, and the second house it owns for you", (
                "Venus rules Tula rashi and also owns your 8th house from here. That is the same double ownership "
                "Aries has with Mars, and it produces the same effect: a Venus period for Libra rarely arrives as "
                "straightforward pleasure.",
                "Venus is exalted in Pisces and weakest in Virgo. When it is retrograde, Libra readings usually "
                "turn towards renegotiation rather than new arrangements, which is a narrower claim than the "
                "folklore makes and closer to what the classical texts actually describe.",
            )),
            Section("The Sun is debilitated here", (
                "The Sun falls to its lowest point at 10 degrees of Libra, once a year, around the middle of "
                "October in sidereal terms. For Tula rashi that is the annual stretch when the sign lord of your "
                "12th house is weak.",
                "Most people don't realise that a debilitated graha is not a forecast of trouble. It describes a "
                "graha working without its usual support, which in the Sun's case tends to read as less appetite "
                "for confrontation rather than as failure.",
            )),
            Section("Chitra, Swati, Vishakha", (
                "Tula rashi runs from the second half of Chitra through Swati and into the first three quarters of "
                "Vishakha.",
                ["Chitra's last two padas, ruled by Mars: design, craft, an eye that notices what is slightly off.",
                 "Swati, ruled by Rahu: independent, mobile, the nakshatra associated with wind and with trade.",
                 "Vishakha's first three padas, ruled by Jupiter: goal-directed, and patient in a way the rest of "
                 "the sign is not.",
                 "Because the Virgo boundary sits inside Chitra, an early Libra Moon is minutes of birth time away "
                 "from being a Virgo one."],
            )),
            Section("Sade sati and dhaiya counted from Tula rashi", (
                "Sade sati for Libra runs while Saturn transits Virgo, Libra or Scorpio. Dhaiya arrives when Saturn "
                "reaches Capricorn or Taurus, the 4th and 8th from your Moon.",
                "Saturn owns the 4th and 5th houses from Libra, home and study, which is the classical reason "
                "Libra's Saturn periods are so often described in terms of property and of children's education "
                "rather than of career. The dates on this page come from Saturn's real transit, retrograde "
                "re-entries included.",
            )),
            _how_made("Libra", "Saturn's exaltation degree, the Chitra boundary and the Sun's annual debilitation "
                               "window are all computed, not approximated."),
        ),
        faqs=(
            ("What is the Libra horoscope today based on?",
             "The nine grahas' positions for the day, calculated with the Swiss Ephemeris and counted as houses "
             "from Tula rashi, with the Moon's nakshatra and the tithi. The reading explains those numbers and does "
             "not generate them."),
            ("Is sade sati easier for Libra because Saturn is exalted there?",
             "The middle phase, when Saturn actually crosses Libra, is usually the most workable of the three. The "
             "phases either side are ordinary sade sati. Exaltation improves how Saturn gives its results, it does "
             "not remove the transit."),
            ("When is sade sati for Tula rashi?",
             "While Saturn transits Virgo, Libra and Scorpio, about seven and a half years end to end. Whether it "
             "is running for you now is calculated from Saturn's actual position and shown above."),
            ("Why is the Sun weak in Libra?",
             "It is the Sun's debilitation sign, with the exact point at 10 degrees. It happens once a year for "
             "about a month. On its own it says nothing about your chart unless your own Sun sits there."),
            ("Which rashi is best matched with Tula?",
             "Traditionally Gemini and Aquarius, the other air signs, and Leo and Sagittarius are usually "
             "comfortable. Ashtakoota matching scores nakshatras rather than signs though, so two Libra pairings "
             "can score very differently. The matching tool gives the actual number."),
            ("What does Tula rashi rule in the body?",
             "The lower back and the kidneys, in the traditional kalapurusha correspondence where the signs run "
             "from the head at Aries to the feet at Pisces. It is a traditional association and not medical "
             "guidance."),
        ),
    ),

    # ---------------------------------------------------------------- 8. Vrishchika / Scorpio
    "vrishchika": RashiBody(
        intro="Scorpio horoscopes, read from the Moon in Vrishchik rashi ({deva}). Sign lord: {lord}, with Ketu "
              "treated as a co-lord in several classical schools. The Moon is debilitated here, which colours "
              "everything about how these readings are written.",
        sections=(
            Section("The Moon is debilitated in Scorpio", (
                "The Moon falls to its exact debilitation at 3 degrees of Scorpio. Since your rashi is your Moon "
                "sign, that fact is about you in a way that most sign properties are not.",
                "It is worth being plain about what it means and what it does not. Classical texts describe a "
                "debilitated Moon as one that works without its usual ease, not one that fails. Several "
                "cancellation conditions exist, and whether any apply is a question about your birth chart rather "
                "than about the sign.",
            )),
            Section("Mars and Ketu, the two lords of Vrishchik rashi", (
                "Mars rules Scorpio in the standard scheme, and a number of classical authorities give Ketu a "
                "share. Mars also owns your 6th house from here, so a Mars transit carries both sign lordship and "
                "the house of conflict and health.",
                "That combination is the real reason Scorpio readings come out more intense than Aries ones, even "
                "though both signs share a lord. Aries is fire and movable; Scorpio is water and fixed, and a fixed "
                "water sign holds on to whatever Mars stirs up.",
            )),
            Section("Jyeshtha and the Gandanta at the end of the sign", (
                "Vrishchik rashi covers the last quarter of Vishakha, all of Anuradha and all of Jyeshtha. The sign "
                "ends at the Scorpio and Sagittarius junction, one of the three Gandanta points where a water sign "
                "meets a fire sign.",
                "A Moon in the final degrees of Jyeshtha sits right in it. Classical texts treat those births with "
                "care, and it is the clearest example of why birth time accuracy matters: the Moon covers about one "
                "degree every two hours, so a recorded time that is half an hour out can move a chart across the "
                "boundary.",
            )),
            Section("Saturn's phases for Scorpio", (
                "Sade sati for Vrishchik rashi runs while Saturn transits Libra, Scorpio or Sagittarius. Dhaiya "
                "runs with Saturn in Aquarius or Leo.",
                "Saturn owns the 3rd and 4th houses from Scorpio, effort and home. Readings for this sign therefore "
                "tend to describe Saturn periods as demanding rather than damaging: more work for the same result, "
                "and attention pulled towards the household. The exact dates come from Saturn's real motion.",
            )),
            Section("Reading a Scorpio horoscope honestly", (
                "Scorpio attracts more dramatic writing than any other sign, and that is worth resisting. A general "
                "rashifal is written for roughly one twelfth of everybody, from one calculated position.",
                "Astrology is a traditional, faith-based practice. Nothing here predicts illness, accident or loss, "
                "and it should not be read as though it could. For anything that matters medically, legally or "
                "financially, take it to a qualified professional and use this page for reflection.",
            )),
            _how_made("Scorpio", "The Moon's debilitation degree, the Jyeshtha Gandanta boundary and Saturn's "
                                 "phases from Vrishchik rashi are all calculated rather than tabulated."),
        ),
        faqs=(
            ("Does a debilitated Moon in Scorpio mean bad luck?",
             "No. It describes a Moon working without its usual support, and classical texts list several "
             "conditions that cancel most of the weakness. Whether any of them apply is a question about your own "
             "birth chart, not about the sign."),
            ("What is the Scorpio horoscope today calculated from?",
             "The day's positions of all nine grahas, worked out with the Swiss Ephemeris and counted as houses "
             "from Vrishchik rashi, plus the Moon's nakshatra and the tithi. AI writes the explanation from those "
             "calculated facts only."),
            ("Who rules Scorpio, Mars or Ketu?",
             "Mars in the standard scheme. Several classical authorities also treat Ketu as a co-lord of Vrishchik "
             "rashi, which is why you will see both named. This site counts houses and doshas from Mars as the "
             "sign lord."),
            ("When does sade sati run for Vrishchik rashi?",
             "While Saturn crosses Libra, Scorpio and Sagittarius. The phase you are in, and the dates, come from "
             "Saturn's real position including its retrograde re-entries rather than from a rounded table."),
            ("What is Gandanta and does it affect Scorpio?",
             "Gandanta is the junction where a water sign meets a fire sign. Scorpio ends at one, in the last "
             "degrees of Jyeshtha. Births there are traditionally treated with care and need an accurate birth "
             "time to place correctly."),
            ("Is Scorpio manglik more often than other signs?",
             "Mangal dosha depends on which house Mars occupies from your lagna, Moon and Venus, not on your rashi. "
             "Scorpio being Mars-ruled does not make it more likely. The mangal dosha checker works it out from "
             "your birth details and lists the cancellation rules that apply."),
        ),
    ),

    # ---------------------------------------------------------------- 9. Dhanu / Sagittarius
    "dhanu": RashiBody(
        intro="Sagittarius horoscopes, read from the Moon in Dhanu rashi ({deva}). Sign lord: {lord}, the slowest "
              "of the visible benefics, which gives these readings a longer arc than most.",
        sections=(
            Section("A dual fire sign ruled by the slowest benefic", (
                "Sagittarius is fire and dual. Jupiter rules it, and Jupiter takes about a year to cross one sign, "
                "so your sign lord's position is a fact about your year rather than about your week.",
                "That is genuinely different from a Mercury-ruled or Moon-ruled sign. A Sagittarius reading is "
                "usually more useful at the monthly and yearly length than at the daily one, and the six month and "
                "yearly pages on this site are the ones to bookmark.",
            )),
            Section("Mula, and the Gandanta that opens the sign", (
                "Dhanu rashi begins with Mula, runs through Purva Ashadha and takes the first quarter of Uttara "
                "Ashadha. Mula's opening degrees are Gandanta, the junction from Scorpio.",
                "Mula is ruled by Ketu, so a Mula birth starts the Vimshottari dasha with a seven year Ketu period "
                "before anything else runs. That is a substantial difference from a Purva Ashadha birth, which "
                "starts with twenty years of Venus. Same sign, entirely different life timeline.",
            )),
            Section("What a Jupiter mahadasha does here", (
                "Jupiter's mahadasha runs sixteen years. For a Sagittarius Moon it is the period when the sign lord "
                "is also the dasha lord, which classical texts treat as significant on its own.",
                "It tends to show up as expansion that is slow enough to keep: study, teaching, travel, the kind of "
                "advancement that comes from being trusted rather than from pushing. Whether it delivers depends on "
                "where Jupiter sits in your own chart, which the free birth chart dates for you exactly.",
            )),
            Section("Saturn, sade sati and Dhanu rashi", (
                "Sade sati for Sagittarius runs while Saturn transits Scorpio, Sagittarius or Capricorn. Dhaiya "
                "arrives when Saturn reaches Pisces or Virgo.",
                "Saturn owns the 2nd and 3rd houses from Dhanu rashi, money and effort. Saturn periods for this "
                "sign are classically read as a tightening of resources that rewards persistence, rather than as "
                "loss. Which phase is running today is computed from Saturn's actual position above.",
            )),
            Section("Sagittarius and the sign it borrows from", (
                "Jupiter rules both Sagittarius and Pisces, so the two share a lord and a good deal of description. "
                "People who are one often recognise themselves in the other.",
                "The separation is element and quality: Sagittarius is fire and dual, Pisces is water and dual, and "
                "Jupiter is debilitated in Capricorn but exalted in Cancer, which affects the two signs' transits "
                "differently. If you are not sure which rashi is yours, the free birth chart gives the Moon's "
                "degree rather than an estimate from your birth month.",
            )),
            _how_made("Sagittarius", "Jupiter's sign changes, the Mula Gandanta boundary and Saturn's phases from "
                                     "Dhanu rashi all come out of that calculation."),
        ),
        faqs=(
            ("What is the Sagittarius horoscope today based on?",
             "The positions of all nine grahas for the day, computed with the Swiss Ephemeris and counted as houses "
             "from Dhanu rashi, together with the Moon's nakshatra and the day's tithi. The written reading "
             "interprets those and nothing else."),
            ("Why does the Sagittarius yearly horoscope matter more than the daily one?",
             "Because Jupiter, your sign lord, spends about a year in each sign. Its position is the single biggest "
             "factor in a Sagittarius reading and it barely moves week to week, so the longer pages carry more of "
             "the real signal."),
            ("What is Mula nakshatra and why is it treated carefully?",
             "Mula opens Sagittarius and is ruled by Ketu. Its first degrees are Gandanta, the junction from "
             "Scorpio, which classical texts treat with care. A Mula birth also begins the Vimshottari dasha with a "
             "seven year Ketu period."),
            ("When is sade sati for Dhanu rashi?",
             "While Saturn crosses Scorpio, Sagittarius and Capricorn. The exact phase dates for your birth "
             "details, including retrograde re-entries, come from the sade sati calculator rather than from a "
             "generic table."),
            ("Which signs are compatible with Sagittarius?",
             "Aries and Leo traditionally, both fire, and Libra and Aquarius usually work. Guna milan scores eight "
             "factors from the two nakshatras though, so the sign pairing alone will not tell you the score."),
            ("Is Dhanu rashi the same as the Sagittarius sun sign?",
             "The sign is the same but the people often are not. Indian astrology reads the Moon sign in the "
             "sidereal zodiac, while a Western sun sign uses the tropical one, and the two are about 24 degrees "
             "apart today."),
        ),
    ),

    # ---------------------------------------------------------------- 10. Makara / Capricorn
    "makara": RashiBody(
        intro="Capricorn horoscopes, read from the Moon in Makar rashi ({deva}). Sign lord: {lord}. Mars is exalted "
              "here and Jupiter is debilitated, which makes Capricorn a sign of unusually mixed transits.",
        sections=(
            Section("Saturn rules it, so sade sati reads differently", (
                "Capricorn is earth and movable, and Saturn rules it. That matters for sade sati: the graha "
                "everybody dreads is your own sign lord, not a visitor.",
                "Classical texts are consistent on this. Saturn's transit over its own sign is steadier than over a "
                "sign it has no relationship with, which is why Capricorn and Aquarius readings during sade sati "
                "talk about workload rather than about disruption.",
            )),
            Section("Mars exalted, Jupiter debilitated, in the same sign", (
                "Mars reaches its exaltation at 28 degrees of Capricorn and Jupiter falls to its debilitation at 5 "
                "degrees. Two of the most consequential grahas in the chart are at opposite extremes in Makar "
                "rashi.",
                "In practice that means a Mars transit through your sign is one of the more productive things in "
                "the Capricorn year, and the Jupiter transit that comes round every twelve years is the one to plan "
                "conservatively around. Both are properties of the sign; what they do for you depends on the birth "
                "chart underneath.",
            )),
            Section("Shravana and the nakshatras of Makar rashi", (
                "Capricorn runs from the second quarter of Uttara Ashadha through Shravana and into the first half "
                "of Dhanishtha.",
                ["Uttara Ashadha's last three padas, ruled by the Sun: durable, and slow to abandon a position.",
                 "Shravana, ruled by the Moon: listening, learning, the nakshatra most associated with hearing and "
                 "with tradition passed on.",
                 "Dhanishtha's first half, ruled by Mars: energetic, rhythmic, and the boundary into Aquarius falls "
                 "inside it.",
                 "A Moon in the last degrees of Capricorn is minutes of birth time from being an Aquarius one, so "
                 "an accurate time matters here more than the date does."],
            )),
            Section("Sade sati and dhaiya from Capricorn", (
                "Sade sati for Makar rashi runs while Saturn transits Sagittarius, Capricorn or Aquarius. Dhaiya "
                "runs with Saturn in Aries or Libra, the 4th and 8th from your Moon.",
                "Because Saturn owns both your 1st and 2nd houses from here, its phases touch identity and income "
                "at the same time. Whether either phase is running for you today, and where in it you are, is "
                "worked out from Saturn's real position and shown higher on this page.",
            )),
            Section("Capricorn under a Saturn mahadasha", (
                "Saturn's mahadasha is nineteen years, the second longest. For a Capricorn Moon it is the stretch "
                "when your sign lord also runs the dasha, which classical texts treat as a period of consolidation "
                "rather than of luck.",
                "Nineteen years is long enough that its antardashas matter more than the period itself. The free "
                "birth chart lists every one of them with start and end dates, calculated from the Moon's exact "
                "position in its nakshatra rather than from the birth date alone.",
            )),
            _how_made("Capricorn", "Mars's exaltation point, Jupiter's debilitation degree and Saturn's own transit "
                                   "through Makar rashi are all computed to the day."),
        ),
        faqs=(
            ("Is sade sati easier for Capricorn?",
             "Often steadier, because Saturn is your own sign lord rather than an outsider. It is still a seven and "
             "a half year transit and the middle phase is still the heaviest. Exactly where you are in it is "
             "calculated from Saturn's real position."),
            ("What does today's Capricorn horoscope use?",
             "The day's positions of the nine grahas, computed with the Swiss Ephemeris and counted as houses from "
             "Makar rashi, with the Moon's nakshatra and the tithi. The reading explains those figures rather than "
             "producing them."),
            ("Why is Jupiter weak in Capricorn?",
             "Capricorn is Jupiter's debilitation sign, with the exact point at 5 degrees. Jupiter passes through "
             "roughly once every twelve years. It is a property of the sign, and classical texts describe "
             "conditions under which the weakness is cancelled."),
            ("When is sade sati for Makar rashi?",
             "While Saturn crosses Sagittarius, Capricorn and Aquarius, around seven and a half years in total. The "
             "sade sati calculator gives your phase dates from your own birth details."),
            ("Which nakshatras fall in Capricorn?",
             "The last three quarters of Uttara Ashadha, all of Shravana, and the first half of Dhanishtha. Your "
             "Vimshottari dasha starts from whichever the Moon was in and how far through it the Moon had gone."),
            ("Is Capricorn compatible with Cancer?",
             "They are opposite signs, which traditional matching reads as complementary but requiring effort. "
             "Ashtakoota scoring works from the two nakshatras rather than the two signs, so the number varies a "
             "lot within the same sign pairing."),
        ),
    ),

    # ---------------------------------------------------------------- 11. Kumbha / Aquarius
    "kumbha": RashiBody(
        intro="Aquarius horoscopes, read from the Moon in Kumbh rashi ({deva}). Sign lord: {lord}, with Rahu given "
              "a share in several classical schools. A fixed air sign, which is a rarer combination than it sounds.",
        sections=(
            Section("Fixed air, and two lords", (
                "Aquarius is an air sign and a fixed one. Air moves, fixed holds, and Aquarius readings live in "
                "that contradiction: ideas that do not change once they have been settled on.",
                "Saturn rules Kumbh rashi and a number of classical authorities give Rahu a co-lordship. Saturn "
                "also owns your 12th house from here, which is the classical reason Aquarius readings so often turn "
                "on expense, distance and things happening out of sight.",
            )),
            Section("Shatabhisha, and the nakshatras here", (
                "Kumbh rashi runs from the second half of Dhanishtha through Shatabhisha and into the first three "
                "quarters of Purva Bhadrapada. Shatabhisha, ruled by Rahu, sits entirely inside the sign.",
                "Shatabhisha is the nakshatra of the hundred healers, associated with medicine and with things that "
                "work in private. A birth there begins the Vimshottari dasha with an eighteen year Rahu period, "
                "which is the longest opening of any nakshatra and shapes the whole sequence that follows.",
            )),
            Section("Sade sati counted from Aquarius", (
                "For an Aquarius Moon, sade sati runs while Saturn transits Capricorn, Aquarius or Pisces. Dhaiya "
                "arrives when Saturn reaches Taurus or Scorpio.",
                "As with Capricorn, Saturn here is your own sign lord. The middle phase, Saturn crossing your Moon, "
                "is still the demanding one, but Aquarius readings for sade sati are traditionally about "
                "responsibility arriving rather than about things being taken away. The dates come from Saturn's "
                "real transit above.",
            )),
            Section("What Rahu does to an Aquarius reading", (
                "Rahu takes about eighteen months to cross a sign and always moves backwards. For Kumbh rashi it "
                "carries more weight than for most signs, given the co-lordship.",
                "Really, the useful version is simpler than the mythology: Rahu periods correlate with unfamiliar "
                "territory, and unfamiliar territory is where mistakes and opportunities both live. A Rahu transit "
                "date is calculated to the day, and how it reads depends on the chart it lands on.",
            )),
            Section("Aquarius and Capricorn, one lord and two temperaments", (
                "Both signs are ruled by Saturn, so the descriptions overlap and people mix them up. The difference "
                "is element and quality: Capricorn is earth and movable, Aquarius is air and fixed.",
                "Here is why that matters for a reading: the same Saturn transit lands on the 1st and 2nd houses "
                "for Capricorn and on the 1st and 12th for Aquarius. Same graha, same dates, different houses. If "
                "you are unsure which is your rashi, the free birth chart gives your Moon's exact degree.",
            )),
            _how_made("Aquarius", "Saturn's own transit through Kumbh rashi, Rahu's sign changes and the Moon's "
                                  "nakshatra pada are all computed rather than estimated."),
        ),
        faqs=(
            ("What is the Aquarius horoscope today based on?",
             "The day's positions of all nine grahas, calculated with the Swiss Ephemeris and counted as houses "
             "from Kumbh rashi, with the Moon's nakshatra and the tithi alongside. AI puts those calculated facts "
             "into plain language and does not work any of them out itself."),
            ("Who rules Aquarius, Saturn or Rahu?",
             "Saturn in the standard scheme, with Rahu given a share by several classical authorities. This site "
             "counts houses and doshas from Saturn as the sign lord of Kumbh rashi."),
            ("When does sade sati start for Kumbh rashi?",
             "When Saturn enters Capricorn, and it ends when Saturn leaves Pisces. Your exact phase dates come from "
             "Saturn's real motion, including the retrograde re-entries that move the boundaries."),
            ("What is Shatabhisha nakshatra known for?",
             "Healing and privacy, traditionally. It lies entirely within Aquarius and is ruled by Rahu, so a birth "
             "there opens the Vimshottari dasha with eighteen years of Rahu."),
            ("Which signs suit Aquarius for marriage?",
             "Gemini and Libra traditionally, the other air signs, with Aries and Sagittarius usually workable. "
             "Guna milan scores the two nakshatras rather than the two signs, so run both birth details through "
             "the matching tool for the real number."),
            ("Does Aquarius get sade sati at the same time as Capricorn?",
             "They overlap but do not match. Capricorn's runs with Saturn in Sagittarius, Capricorn and Aquarius; "
             "Aquarius's runs with Saturn in Capricorn, Aquarius and Pisces. So the two signs share two of the "
             "three phases, offset by about two and a half years."),
        ),
    ),

    # ---------------------------------------------------------------- 12. Meena / Pisces
    "meena": RashiBody(
        intro="Pisces horoscopes, read from the Moon in Meen rashi ({deva}). Sign lord: {lord}. Venus is exalted "
              "here, and the sign ends at the Gandanta point that closes the whole zodiac.",
        sections=(
            Section("The last sign, and what that means for a reading", (
                "Pisces is water and dual, and it closes the zodiac. Jupiter rules it and Venus is exalted in it, "
                "reaching the exact degree at 27 Pisces, which makes this the sign where the two natural benefics "
                "are both comfortable.",
                "That is the substance behind the usual Pisces description. It is not softness so much as a lack of "
                "hard edges: a sign that absorbs rather than resists, which reads well in some periods and less "
                "well in others.",
            )),
            Section("Revati, and the end of the zodiac", (
                "Meen rashi covers the last quarter of Purva Bhadrapada, all of Uttara Bhadrapada and all of "
                "Revati. Revati closes the sign and the zodiac together.",
                "Its final degrees are Gandanta, the junction back into Aries. Classical texts treat births there "
                "with particular care, and it is the sharpest illustration of why birth time matters: the Moon "
                "crosses about one degree every two hours, so half an hour of uncertainty can move a chart out of "
                "Revati altogether. The Swiss Ephemeris places it to the arc-second; a hand calculation from a "
                "printed panchang usually cannot.",
            )),
            Section("Mercury is debilitated in Pisces", (
                "Mercury falls to its lowest point at 15 degrees of Pisces, the mirror of its exaltation in Virgo. "
                "Mercury passes through two or three times a year.",
                "For Meen rashi that reads as periods when detail and paperwork go slower than they should, "
                "particularly if Mercury is also retrograde at the time. The classical cancellation conditions can "
                "apply, and whether they do is a question about your own chart rather than about the sign.",
            )),
            Section("Saturn's phases for Pisces", (
                "Sade sati for Meen rashi runs while Saturn transits Aquarius, Pisces or Aries. Dhaiya arrives when "
                "Saturn reaches Gemini or Sagittarius.",
                "Saturn owns your 11th and 12th houses from Pisces, gains and expense. That is the classical reason "
                "Pisces sade sati readings talk about money moving in both directions at once rather than about "
                "simple loss. Whether it is running for you today is computed from Saturn's actual position and "
                "printed above.",
            )),
            Section("Pisces under a Jupiter mahadasha", (
                "Jupiter's mahadasha runs sixteen years, and for a Pisces Moon it is the period when the sign lord "
                "runs the dasha. Classically that is read as a period of growth that arrives through people rather "
                "than through effort alone.",
                "Sixteen years is a long time to describe in one sentence, which is the honest limit of a sign "
                "reading. The antardashas inside it are where the actual timing sits, and the free birth chart "
                "dates every one of them from your Moon's exact position in its nakshatra.",
            )),
            _how_made("Pisces", "Venus's exaltation degree, the Revati Gandanta boundary and Saturn's phases "
                                "counted from Meen rashi all come out of that calculation."),
        ),
        faqs=(
            ("What is the Pisces horoscope today based on?",
             "The nine grahas' positions for the day, computed with the Swiss Ephemeris and counted as houses from "
             "Meen rashi, plus the Moon's nakshatra and the tithi. The written reading interprets those calculated "
             "facts and never works one out itself."),
            ("What is Revati nakshatra and why does it need an accurate birth time?",
             "Revati closes Pisces and the zodiac. Its last degrees are Gandanta, the junction into Aries, and the "
             "Moon moves about one degree every two hours, so a birth time that is half an hour out can place the "
             "chart in a different sign entirely."),
            ("When is sade sati for Meen rashi?",
             "While Saturn transits Aquarius, Pisces and Aries, roughly seven and a half years. The sade sati "
             "calculator works out your phase and its dates from your birth details and Saturn's real motion."),
            ("Why is Venus exalted in Pisces?",
             "Pisces is Venus's exaltation sign in the classical scheme, with the exact degree at 27 Pisces. It "
             "means a Venus transit through your sign is one of the more comfortable things in the Pisces year, "
             "though what it does for you depends on your own chart."),
            ("Is Meen rashi the same as the Pisces star sign?",
             "The sign is the same, the people often are not. Indian astrology uses the sidereal zodiac and reads "
             "the Moon sign; a Western star sign uses the tropical zodiac and the Sun. The free birth chart will "
             "tell you your actual rashi."),
            ("Which planets are strong or weak in Pisces?",
             "Venus is exalted and Mercury is debilitated, and Jupiter rules the sign. These describe the sign "
             "itself. What they mean for you depends on where those grahas actually sit in your birth chart."),
        ),
    ),
}
