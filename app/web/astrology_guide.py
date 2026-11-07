"""The pillar page: /astrology, /hi/jyotish, /mr/jyotish.

"ज्योतिष" is 50K a month on its own and the query behind it is not transactional - somebody wants to
understand the thing, not calculate anything. Every tool on this site is a leaf; this is the trunk, and
the one page that can answer "what IS this" at the length the question deserves.

IT IS NOT A KEYWORD PAGE. The test of a pillar is whether somebody who reads it comes away actually
knowing how a chart is put together, so it is written to answer the questions in the order a beginner
hits them, and it links to the tool that does each thing rather than describing a tool it does not have.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.web import i18n


@dataclass(frozen=True)
class Part:
    """One anchored section of the guide."""

    anchor: str
    heading: str
    paragraphs: tuple[str, ...]
    #: A registry key to link to from this section, where one of our tools does the thing just described.
    tool: str | None = None
    tool_label: str = ""


EN = {
    "title": "Vedic Astrology: A Complete, Honest Guide (Jyotish)",
    "h1": "Vedic astrology, explained properly",
    "intro": "Jyotish is a 2,000-year-old system for reading the sky at the moment somebody was born. "
             "This page explains how it actually works - the zodiac it uses and why it differs from the "
             "Western one, the nine grahas, the twelve houses, the nakshatras, the dasha system that "
             "times everything, and the doshas people worry about. No predictions, no fear, and nothing "
             "you have to pay for to follow along.",
    "toc": "On this page",
    "faq": "Common questions",
    "parts": (
        Part("what-it-is", "What Vedic astrology actually is", (
            "Vedic astrology - jyotish, 'the science of light' - is a method for describing a moment in "
            "time by where the planets stood in it. Its claim is narrow and specific: that the sky at "
            "your birth describes the shape of your life the way a map describes terrain. Not what will "
            "happen, but what the ground is like.",
            "It is built on arithmetic, not intuition. The positions of nine grahas, twelve signs and "
            "twelve houses are calculated from the date, time and place of birth, and two astrologers "
            "working from the same birth details will produce the same chart. Where they differ is in "
            "reading it - and that difference is interpretation, which is a different kind of claim "
            "from calculation.",
            "What it is not: a mechanism anyone has demonstrated under controlled conditions. It is a "
            "traditional, faith-based practice with a long literature and a large number of people who "
            "find it useful for reflection. That is how it is offered on this site, and anyone telling "
            "you a chart guarantees an outcome is selling something.",
        )),
        Part("sidereal", "Why your Indian sign is not your Western sign", (
            "This is the first thing that confuses people, and it has a precise answer. Western "
            "astrology uses the TROPICAL zodiac, which starts at the spring equinox. Vedic astrology "
            "uses the SIDEREAL zodiac, which starts from a fixed point among the actual stars.",
            "The Earth wobbles on its axis over about 26,000 years - the precession of the equinoxes - "
            "so the equinox slowly drifts against the star background. The two zodiacs agreed around "
            "the 3rd to 5th century CE and have been separating since. Today the gap is about 24 "
            "degrees, which is most of a 30-degree sign.",
            "That is why somebody who has been told all their life they are a Leo is usually a Karka "
            "(Cancer) in a Vedic chart. Neither system is making an error; they are measuring from "
            "different zero points. The amount of the difference is called the ayanamsa, and this site "
            "uses the Lahiri ayanamsa, which is the one Indian government panchangs follow.",
        ), tool="kundli", tool_label="See your own sidereal chart"),
        Part("grahas", "The nine grahas", (
            "Graha means 'the one that grasps' rather than 'planet', which is why the list includes the "
            "Sun and Moon and two points that are not bodies at all.",
            "SURYA (Sun) is the self, the father, authority, vitality and the spine. CHANDRA (Moon) is "
            "the mind, the mother, and how you take things in - in Vedic astrology the Moon's sign is "
            "the one Indians mean when they ask your rashi, not the Sun's.",
            "MANGAL (Mars) is energy, courage, land, brothers, surgery and accident. BUDHA (Mercury) is "
            "speech, trade, calculation and the nerves. GURU (Jupiter) is wisdom, teachers, children, "
            "lasting wealth, and the most protective influence in a chart. SHUKRA (Venus) is marriage, "
            "comfort, art and vehicles. SHANI (Saturn) is discipline, delay, labour and old age - the "
            "lessons that arrive slowly and do not leave.",
            "RAHU and KETU are the two points where the Moon's orbit crosses the Sun's apparent path - "
            "the eclipse points. They are always exactly opposite each other and always retrograde. "
            "Rahu is hunger, foreign things and sudden rise; Ketu is detachment, research, and the thing "
            "you are strangely good at without having tried.",
        )),
        Part("rashis", "The twelve rashis", (
            "The twelve signs are the same twelve as in Western astrology - Mesha is Aries, Vrishabha "
            "is Taurus, and so on - measured from a different starting point. Each is 30 degrees and "
            "each has a ruling graha, an element and a quality.",
            "Mesha (Aries, Mars), Vrishabha (Taurus, Venus), Mithuna (Gemini, Mercury), Karka (Cancer, "
            "Moon), Simha (Leo, Sun), Kanya (Virgo, Mercury), Tula (Libra, Venus), Vrishchika (Scorpio, "
            "Mars), Dhanu (Sagittarius, Jupiter), Makara (Capricorn, Saturn), Kumbha (Aquarius, Saturn) "
            "and Meena (Pisces, Jupiter).",
            "A sign on its own says less than people expect. What matters is which sign is rising at "
            "birth, which house each sign therefore occupies, and where that sign's ruler has gone.",
        ), tool="rashifal-hub", tool_label="Today's reading for your rashi"),
        Part("houses", "The twelve bhavas, and why the birth time matters", (
            "The houses are the twelve divisions of the sky as seen from your birthplace at your birth "
            "minute. The first house begins at the lagna - the degree of the zodiac climbing over the "
            "eastern horizon at that moment.",
            "The lagna moves through all twelve signs in a day, which means it changes sign roughly "
            "every two hours. This is the single reason a birth time matters so much: the grahas barely "
            "move in an hour, but the houses rotate completely underneath them. Two people born the "
            "same morning in the same city, three hours apart, share nearly every planetary position "
            "and have substantially different charts.",
            "First house: body, temperament, appearance. Second: earned money, speech, family of "
            "origin. Third: effort, courage, younger siblings. Fourth: mother, home, land, peace of "
            "mind. Fifth: children, learning, creativity. Sixth: illness, debt, enemies, daily work. "
            "Seventh: marriage and partnership. Eighth: inheritance, the hidden, sudden change. Ninth: "
            "fortune, father, teacher, belief. Tenth: career and standing. Eleventh: gains, income, "
            "networks. Twelfth: expense, sleep, foreign places, release.",
        ), tool="kundli", tool_label="Find your lagna and houses"),
        Part("nakshatras", "The twenty-seven nakshatras", (
            "Before the twelve-sign zodiac, India divided the sky into twenty-seven lunar mansions of "
            "13 degrees 20 minutes each - roughly one day of the Moon's travel. The nakshatras are "
            "older than the rashis and in practice carry more specific meaning.",
            "The nakshatra the Moon occupied at your birth is the most important single fact in a "
            "Vedic chart after the lagna. It sets your janma nakshatra, it decides the first letter "
            "traditionally used for naming a child, and - most consequentially - it determines where "
            "your dasha sequence begins.",
            "Each nakshatra is divided into four padas of 3 degrees 20 minutes, and each has a ruling "
            "graha, a deity and a symbol. Three of them - Ashwini, Magha and Mula - begin a new cycle "
            "of the dasha lords, and a birth in the junction between some of them is called gandmool, "
            "about which more below.",
        )),
        Part("dasha", "Dasha: the system that times everything", (
            "A chart is fixed at birth and never changes. What changes is which graha is currently "
            "running, and that is the dasha system - the part of Vedic astrology that has no Western "
            "equivalent and does most of the work.",
            "The Vimshottari dasha divides 120 years among the nine grahas in a fixed sequence: Ketu 7 "
            "years, Venus 20, Sun 6, Moon 10, Mars 7, Rahu 18, Jupiter 16, Saturn 19, Mercury 17. "
            "Where you start in that sequence, and how much of the first period is already spent when "
            "you are born, comes from exactly how far the Moon had travelled through its nakshatra.",
            "Each mahadasha divides into nine antardashas in the same proportion, and those divide "
            "again. The reading of a year is usually the combination: a Jupiter mahadasha with a "
            "Saturn antardasha is a different year from a Jupiter mahadasha with a Venus one.",
            "This is also why an approximate birth time is not good enough for dasha work. The balance "
            "at birth is read from the Moon's exact degree, and an hour's error shifts every date in "
            "the sequence by months.",
        )),
        Part("drishti", "Aspects: how grahas reach across a chart", (
            "A graha does not only affect the house it sits in. Every graha aspects the seventh house "
            "from itself - the one directly opposite - and four of them have additional special "
            "aspects that are not symmetrical.",
            "Mars aspects the 4th and 8th from itself as well as the 7th. Jupiter aspects the 5th and "
            "9th. Saturn aspects the 3rd and 10th. Rahu and Ketu are given the 5th and 9th by many "
            "traditions. This is one of the clearest differences from Western practice, where aspects "
            "are measured by angular distance between two bodies and are mutual; in Vedic practice an "
            "aspect is counted in whole houses and often runs one way only.",
            "The practical consequence is that a house can be strongly influenced by a graha nowhere "
            "near it. An empty seventh house is not an empty subject if Saturn is looking at it from "
            "the fourth.",
        )),
        Part("dignity", "Strength: exaltation, debilitation and what they actually mean", (
            "The same graha behaves differently depending on which sign it occupies. Each has a sign "
            "of exaltation where it is considered strongest, a sign of debilitation exactly opposite, "
            "and signs it owns or is friendly to.",
            "The Sun is exalted in Mesha and debilitated in Tula. The Moon is exalted in Vrishabha, "
            "Mars in Makara, Mercury in Kanya, Jupiter in Karka, Venus in Meena and Saturn in Tula - "
            "and each is debilitated in the sign opposite.",
            "Debilitation is not doom and exaltation is not a guarantee. A debilitated graha with a "
            "cancellation - neechabhanga - is read by many astrologers as unusually strong precisely "
            "because of what it had to overcome, and an exalted graha in a difficult house can be a "
            "powerful source of trouble. Reading a single placement without the rest of the chart is "
            "the commonest beginner error.",
            "Retrogradation and combustion matter too. A retrograde graha is turned inward rather than "
            "weakened; a graha too close to the Sun is called combust and is traditionally read as "
            "having its significations obscured.",
        )),
        Part("varga", "Divisional charts, and the navamsa", (
            "A Vedic chart is not one diagram but a family of them. Each divisional chart - varga - "
            "subdivides every sign and re-maps the result, and each is read for a particular area of "
            "life.",
            "The most used by far is the NAVAMSA, the D9, which divides each sign into nine parts. It "
            "is read for marriage and for the deeper strength of every graha: a graha weak in the main "
            "chart but strong in the navamsa is read as coming into its own later in life, which is "
            "called vargottama when it holds the same sign in both.",
            "Others in common use are the D10 for career, the D7 for children, the D4 for property and "
            "the D12 for parents. A practitioner who reads only the main chart is working with a "
            "fraction of the system; one who produces sixteen divisional charts for a routine question "
            "is usually padding.",
        )),
        Part("yogas", "Yogas: combinations with names", (
            "A yoga is a named combination that classical texts single out. There are hundreds, most "
            "of them rare, and a handful that come up constantly.",
            "RAJ YOGAS form when the lord of a trine house (1, 5, 9) connects with the lord of an "
            "angle (1, 4, 7, 10) - by conjunction, aspect or exchange. They are read as the structural "
            "basis of success. DHANA YOGAS involve the lords of the 2nd and 11th and concern wealth.",
            "GAJAKESARI forms when Jupiter is in an angle from the Moon. PANCHA MAHAPURUSHA yogas form "
            "when Mars, Mercury, Jupiter, Venus or Saturn sits in its own or exalted sign in an angle - "
            "five yogas, one per graha, each with its own name and temperament.",
            "The caution is the same one that applies everywhere in this system: a yoga is a factor, "
            "not a verdict. Almost every chart contains some yoga that sounds impressive when quoted "
            "on its own, which is exactly why they are quoted on their own.",
        )),
        Part("remedies", "Remedies, and how to think about them", (
            "Traditional remedies fall into a few groups: mantra, charity, fasting on a particular "
            "weekday, gemstones, and simple acts of service associated with a graha. They are offered "
            "as ways of orienting attention rather than as mechanisms.",
            "The honest position is this. Nobody has demonstrated that a gemstone changes an outcome. "
            "What a remedy reliably does is give somebody a structure during a period they find "
            "difficult, and for many people that is worth having. Giving food on a Saturday because "
            "Saturn is heavy in your chart is harmless and may well be good for you and for whoever "
            "receives it.",
            "Where it stops being harmless is money. Expensive gemstones, paid pujas sold against a "
            "dosha, and 'remedies' that must be bought from the person who found the problem are the "
            "oldest commercial pattern in this field. A remedy that costs nothing but attention is "
            "the one tradition actually emphasises.",
        )),
        Part("doshas", "Doshas: mangal, kaal sarp, sade sati", (
            "A dosha is a configuration traditional texts treat as a difficulty. They are the part of "
            "astrology most used to frighten people, and the honest handling of them is to say exactly "
            "what the configuration is and exactly how much disagreement there is about it.",
            "MANGAL DOSHA (manglik) is Mars in the 1st, 2nd, 4th, 7th, 8th or 12th house. It is "
            "classically read as a strain on marriage. Which houses count varies between traditions - "
            "the 2nd is counted in some regions and not others - and several standard cancellations "
            "apply, including Mars in its own sign or both partners having it.",
            "KAAL SARP occurs when all seven classical grahas fall between Rahu and Ketu. It is a late "
            "addition to the literature, absent from the classical texts, and treated far more "
            "seriously in popular astrology than in scholarly practice.",
            "SADE SATI is the seven-and-a-half years Saturn spends transiting the sign before your "
            "Moon, your Moon's sign, and the one after. It is not a dosha in the chart at all - it is a "
            "transit, it happens to everybody roughly every thirty years, and it is read as a period "
            "of work and consolidation rather than disaster.",
        ), tool="sade-sati", tool_label="Check your sade sati dates"),
        Part("matching", "Kundali matching for marriage", (
            "Ashtakoota guna milan scores two charts against each other on eight factors worth 36 "
            "points in total: varna 1, vashya 2, tara 3, yoni 4, graha maitri 5, gana 6, bhakoot 7 and "
            "nadi 8.",
            "The total is the famous number and it is the least useful part. Two of the eight carry "
            "most of the traditional weight: nadi, worth 8 points, and bhakoot, worth 7. A pair can "
            "score 28 out of 36 and still have a nadi dosha, and a pair can score 20 with everything "
            "that matters intact.",
            "Guna milan compares Moon nakshatras only. It says nothing about either person's seventh "
            "house, their Venus, their dasha periods, or whether they have met. It is one input.",
        ), tool="matching", tool_label="Match two charts, koota by koota"),
        Part("panchang", "The panchang and muhurta", (
            "A panchang is the Hindu calendar for a day at a place, and its name means 'five limbs': "
            "the vara (weekday), the tithi (lunar day), the nakshatra, the yoga and the karana, all "
            "read at sunrise.",
            "Because they are read at sunrise and sunrise depends on where you are, a panchang is "
            "always for a place. Sunrise at Pune and Delhi differs by about twenty minutes, which on a "
            "day when a tithi ends near dawn gives two different and equally correct answers.",
            "Muhurta is the use of the panchang to choose a time for something - a wedding, a business "
            "opening, a journey. The commonest practical use is the opposite: avoiding rahu kaal, "
            "yamaganda and gulika, the three inauspicious eighths of the day.",
        ), tool="panchang", tool_label="Today's panchang for your city"),
        Part("history", "Where it came from", (
            "The oldest surviving systematic text is the Brihat Parashara Hora Shastra, attributed to "
            "the sage Parashara and compiled over a long period. Varahamihira's Brihat Jataka, around "
            "the 6th century CE, is the other foundation most practitioners work from, and it is "
            "unusually clear about its own Greek borrowings.",
            "That borrowing is worth stating plainly, because it is often hidden. Indian astrology and "
            "Hellenistic astrology exchanged a great deal during the first centuries CE - the Sanskrit "
            "words for hora, kendra and several others are Greek in origin. What India developed "
            "independently and kept is the nakshatra system, which is older than the contact, and the "
            "dasha methods, which have no Greek parallel.",
            "The practical result is that the twelve signs and the aspects are a shared inheritance, "
            "and the parts of jyotish that feel most distinctive - the lunar mansions and the timing "
            "systems - are the parts that are genuinely Indian.",
        )),
        Part("reading", "What a reading actually looks like", (
            "A competent reading goes in an order, and knowing the order is the best defence against "
            "a bad one. First the lagna and its lord: where it sits, how strong it is. Then the Moon, "
            "its sign and nakshatra, because that is the mind and the dasha origin.",
            "Then the houses relevant to the question, their lords, and whatever aspects them. Then "
            "the navamsa, to see whether what the main chart shows holds up underneath. Only then the "
            "dasha, to ask when - and the transits, to ask what is happening right now against that "
            "background.",
            "An astrologer who opens with a dosha, or who asks no questions about your life before "
            "pronouncing on it, is working backwards. The chart constrains the reading; it does not "
            "replace knowing anything about the person.",
        )),
        Part("transits", "Gochar: what is happening now", (
            "The birth chart is fixed. Gochar - transit - is where the grahas are today, read against "
            "where they were at birth. Most day-to-day astrology, including every rashifal on this "
            "site, is transit work.",
            "Transits are read from the Moon's sign rather than the lagna in most Indian practice, "
            "which is why a rashifal asks for your rashi rather than your rising sign. The slow grahas "
            "matter most: Saturn takes two and a half years per sign, Jupiter about one, and Rahu and "
            "Ketu about eighteen months.",
            "A transit on its own is weak. The standard rule is that a transit can only deliver what "
            "the birth chart and the running dasha already allow - which is why two people with the "
            "same Moon sign have quite different years despite reading the same rashifal.",
        ), tool="rashifal-hub", tool_label="Today's transit reading for your rashi"),
        Part("honest", "How to use this honestly", (
            "Astrology is a traditional practice, not a demonstrated mechanism. Nothing on this site is "
            "evidence that a planet affects an outcome, and we do not claim it is.",
            "What a chart is genuinely good for is reflection: a structured vocabulary for thinking "
            "about your own tendencies, and a calendar that encourages patience in difficult periods "
            "and effort in supported ones. Many people find that useful. Treating it as a decision "
            "procedure for medicine, law or money is where it does harm.",
            "Be particularly careful of anyone who gives you a date for an event, charges for a remedy "
            "to 'cancel' a dosha, or tells you a chart is cursed. The configurations are public "
            "knowledge, the calculations are arithmetic anybody can check, and fear is not a reading.",
        ), tool="consultation", tool_label="Ask about your own chart"),
    ),
    "faqs": (
        ("Is Vedic astrology different from Western astrology?",
         "Yes, in two structural ways. It uses the sidereal zodiac rather than the tropical one, which "
         "shifts most people back one sign, and it has the dasha system for timing, which Western "
         "astrology has no equivalent of. The Moon's sign also matters more than the Sun's."),
        ("What is the most important part of a chart?",
         "The lagna and the Moon. The lagna sets all twelve houses and needs an accurate birth time; "
         "the Moon's nakshatra sets the entire dasha sequence."),
        ("Do I need my exact birth time?",
         "For the lagna, the houses and the dasha dates, yes - the lagna changes sign every two hours. "
         "Without a time you can still have the Sun's sign, the slow grahas, and the Moon's sign on "
         "about three days in five."),
        ("Is being manglik a serious problem?",
         "It is a configuration, not a verdict, and which houses count varies between traditions. "
         "Several standard cancellations apply. Anyone charging you to remove it is selling fear."),
        ("Can astrology predict the future?",
         "No chart names a date, and anyone who gives you one is guessing. What classical practice "
         "times is a supportive or difficult PERIOD, which is a statement about the chart rather than "
         "about your life."),
    ),
}


HI = {
    "title": "ज्योतिष: पूरी और ईमानदार जानकारी (Jyotish)",
    "h1": "ज्योतिष, ठीक से समझाया हुआ",
    "intro": "ज्योतिष दो हज़ार साल पुरानी वह पद्धति है जिससे जन्म के समय का आकाश पढ़ा जाता है। यह "
             "पन्ना बताता है कि वह असल में काम कैसे करता है - कौन सा राशिचक्र, पाश्चात्य से अलग क्यों, "
             "नौ ग्रह, बारह भाव, नक्षत्र, दशा और वे दोष जिनसे लोग डरते हैं। न भविष्यवाणी, न डर, और "
             "पढ़ने के लिए कुछ भी चुकाना नहीं पड़ता।",
    "toc": "इस पन्ने पर",
    "faq": "आम सवाल",
    "parts": (
        Part("what-it-is", "ज्योतिष असल में है क्या", (
            "ज्योतिष यानी 'प्रकाश का विज्ञान' - एक समय को इस आधार पर वर्णित करने की पद्धति कि उस "
            "क्षण ग्रह कहाँ थे। इसका दावा सीमित और स्पष्ट है: जन्म का आकाश जीवन का नक्शा बताता है, "
            "वैसे ही जैसे नक्शा ज़मीन बताता है। क्या होगा यह नहीं - ज़मीन कैसी है यह।",
            "यह गणित पर खड़ा है, अंतर्ज्ञान पर नहीं। नौ ग्रह, बारह राशियाँ और बारह भाव जन्म की "
            "तारीख़, समय और स्थान से निकाले जाते हैं, और एक ही जन्म विवरण से दो ज्योतिषी एक ही "
            "कुंडली बनाएँगे। फ़र्क़ पढ़ने में आता है - और वह व्याख्या है, गणना नहीं।",
            "यह क्या नहीं है: कोई ऐसा तंत्र जिसे नियंत्रित परिस्थितियों में सिद्ध किया गया हो। यह "
            "एक पारंपरिक, आस्था-आधारित विद्या है। इसी रूप में यह यहाँ दी गई है, और जो कोई कहे कि "
            "कुंडली परिणाम की गारंटी देती है, वह कुछ बेच रहा है।",
        )),
        Part("sidereal", "आपकी भारतीय राशि पाश्चात्य राशि से अलग क्यों है", (
            "यह पहली उलझन है और इसका ठीक-ठीक उत्तर है। पाश्चात्य ज्योतिष सायन राशिचक्र लेता है, जो "
            "वसंत विषुव से शुरू होता है। वैदिक ज्योतिष निरयण राशिचक्र लेता है, जो वास्तविक तारों के "
            "बीच एक स्थिर बिंदु से शुरू होता है।",
            "पृथ्वी की धुरी लगभग 26,000 वर्ष में एक चक्कर डोलती है, इसलिए विषुव तारों की पृष्ठभूमि "
            "पर धीरे-धीरे खिसकता है। दोनों राशिचक्र तीसरी से पाँचवीं शताब्दी के आसपास मिलते थे और "
            "तब से अलग होते गए हैं। आज अंतर लगभग 24 अंश है, जो 30 अंश की राशि का अधिकांश है।",
            "इसीलिए जिसे जीवन भर 'सिंह' बताया गया, वैदिक कुंडली में प्राय: कर्क निकलता है। दोनों में "
            "कोई ग़लत नहीं; दोनों अलग शून्य से नापते हैं। इस अंतर को अयनांश कहते हैं, और यह साइट "
            "लाहिड़ी अयनांश लेती है - वही जो भारतीय पंचांग मानते हैं।",
        ), tool="kundali", tool_label="अपनी कुंडली देखिए"),
        Part("grahas", "नौ ग्रह", (
            "'ग्रह' का अर्थ 'पकड़ने वाला' है, 'planet' नहीं - इसीलिए सूची में सूर्य और चंद्र भी हैं "
            "और दो ऐसे बिंदु भी जो पिंड हैं ही नहीं।",
            "सूर्य: आत्मा, पिता, अधिकार, ओज, रीढ़। चंद्र: मन, माता, और बातें लेने का ढंग - वैदिक "
            "ज्योतिष में 'आपकी राशि' चंद्र की राशि है, सूर्य की नहीं।",
            "मंगल: ऊर्जा, साहस, भूमि, भाई, शल्यक्रिया। बुध: वाणी, व्यापार, गणना, स्नायु। गुरु: ज्ञान, "
            "गुरुजन, संतान, टिकने वाला धन - कुंडली का सबसे रक्षक प्रभाव। शुक्र: विवाह, सुख, कला, "
            "वाहन। शनि: अनुशासन, विलंब, श्रम, वृद्धावस्था।",
            "राहु और केतु वे दो बिंदु हैं जहाँ चंद्र की कक्षा सूर्य के मार्ग को काटती है - ग्रहण "
            "बिंदु। ये सदा आमने-सामने और सदा वक्री रहते हैं। राहु: भूख, विदेश, अचानक उठान। केतु: "
            "वैराग्य, शोध, और वह कौशल जो बिना प्रयास आता है।",
        )),
        Part("houses", "बारह भाव, और जन्म समय क्यों इतना मायने रखता है", (
            "भाव वे बारह विभाजन हैं जो आपके जन्मस्थान से, जन्म के मिनट पर, आकाश के बनते हैं। पहला "
            "भाव लग्न से शुरू होता है - वह अंश जो उस क्षण पूर्वी क्षितिज पर चढ़ रहा था।",
            "लग्न एक दिन में बारहों राशियों से गुज़रता है, यानी लगभग हर दो घंटे में राशि बदलता है। "
            "जन्म समय इसीलिए इतना ज़रूरी है: एक घंटे में ग्रह मुश्किल से हिलते हैं, पर भाव उनके नीचे "
            "पूरे घूम जाते हैं।",
            "पहला: शरीर, स्वभाव। दूसरा: धन, वाणी, कुल। तीसरा: पराक्रम, छोटे भाई-बहन। चौथा: माता, घर, "
            "भूमि, मन:शांति। पाँचवाँ: संतान, विद्या। छठा: रोग, ऋण, शत्रु। सातवाँ: विवाह, साझेदारी। "
            "आठवाँ: आयु, गुप्त, आकस्मिक परिवर्तन। नवाँ: भाग्य, पिता, गुरु। दसवाँ: कर्म, प्रतिष्ठा। "
            "ग्यारहवाँ: लाभ, आय। बारहवाँ: व्यय, निद्रा, विदेश।",
        ), tool="kundali", tool_label="अपना लग्न और भाव देखिए"),
        Part("nakshatras", "सत्ताईस नक्षत्र", (
            "बारह राशियों से पहले भारत ने आकाश को सत्ताईस नक्षत्रों में बाँटा - हर एक 13 अंश 20 कला, "
            "लगभग चंद्र की एक दिन की यात्रा। नक्षत्र राशियों से पुराने हैं और व्यवहार में अधिक "
            "विशिष्ट अर्थ रखते हैं।",
            "जन्म के समय चंद्र जिस नक्षत्र में था, वह लग्न के बाद कुंडली का सबसे महत्वपूर्ण तथ्य है। "
            "वही जन्म नक्षत्र है, वही नामकरण का अक्षर देता है, और सबसे बड़ी बात - वही तय करता है कि "
            "आपकी दशा कहाँ से शुरू होती है।",
            "हर नक्षत्र चार पादों में बँटा है और हर एक का स्वामी ग्रह, देवता और प्रतीक है।",
        )),
        Part("dasha", "दशा: समय बताने वाली पद्धति", (
            "कुंडली जन्म पर स्थिर हो जाती है और कभी नहीं बदलती। जो बदलता है वह यह कि इस समय कौन सा "
            "ग्रह चल रहा है - और वही दशा पद्धति है, ज्योतिष का वह हिस्सा जिसका पाश्चात्य ज्योतिष में "
            "कोई समकक्ष नहीं।",
            "विंशोत्तरी दशा 120 वर्ष नौ ग्रहों में बाँटती है: केतु 7, शुक्र 20, सूर्य 6, चंद्र 10, "
            "मंगल 7, राहु 18, गुरु 16, शनि 19, बुध 17। आप उस क्रम में कहाँ से शुरू करते हैं, यह चंद्र "
            "के नक्षत्र में ठीक-ठीक कितनी दूरी तय करने से निकलता है।",
            "हर महादशा उसी अनुपात में नौ अंतर्दशाओं में बँटती है। किसी वर्ष का पाठ प्राय: दोनों का "
            "मेल होता है - गुरु महादशा में शनि की अंतर्दशा और गुरु महादशा में शुक्र की अंतर्दशा दो "
            "अलग वर्ष हैं।",
            "इसीलिए अनुमानित जन्म समय दशा के लिए पर्याप्त नहीं। एक घंटे की भूल हर तारीख़ को महीनों "
            "खिसका देती है।",
        )),
        Part("doshas", "दोष: मंगल, कालसर्प, साढ़े साती", (
            "दोष वह योग है जिसे शास्त्र कठिनाई मानते हैं। ज्योतिष का यही हिस्सा लोगों को डराने में "
            "सबसे ज़्यादा इस्तेमाल होता है, और ईमानदार तरीक़ा यह है कि योग क्या है यह ठीक-ठीक बताया "
            "जाए और यह भी कि उस पर मतभेद कितना है।",
            "मंगल दोष: मंगल का पहले, दूसरे, चौथे, सातवें, आठवें या बारहवें भाव में होना। कौन से भाव "
            "गिने जाएँ यह परंपरा से बदलता है, और कई मानक निवारण हैं - मंगल का अपनी राशि में होना, या "
            "दोनों पक्षों में दोष होना।",
            "कालसर्प तब बनता है जब सातों ग्रह राहु और केतु के बीच आ जाएँ। यह शास्त्रों में नहीं है, "
            "बाद का जोड़ है, और लोकप्रिय ज्योतिष में जितना गंभीर माना जाता है विद्वत परंपरा में उतना "
            "नहीं।",
            "साढ़े साती कुंडली का दोष है ही नहीं - यह गोचर है। शनि आपकी चंद्र राशि से पहले वाली, "
            "चंद्र राशि, और अगली राशि से गुज़रता है, कुल साढ़े सात वर्ष। यह हर किसी को लगभग हर तीस "
            "वर्ष में आती है, और इसे आपदा नहीं, परिश्रम और ठोस होने का काल माना जाता है।",
        ), tool="sade-sati", tool_label="अपनी साढ़े साती देखिए"),
        Part("matching", "विवाह के लिए कुंडली मिलान", (
            "अष्टकूट गुण मिलान दो कुंडलियों को आठ कसौटियों पर 36 अंक में जाँचता है: वर्ण 1, वश्य 2, "
            "तारा 3, योनि 4, ग्रह मैत्री 5, गण 6, भकूट 7, नाड़ी 8।",
            "कुल अंक प्रसिद्ध है और सबसे कम उपयोगी। आठ में से दो सबसे भारी हैं: नाड़ी (8) और भकूट (7)। "
            "36 में से 28 पाकर भी नाड़ी दोष हो सकता है, और 20 पाकर भी ज़रूरी सब ठीक हो सकता है।",
            "गुण मिलान केवल चंद्र नक्षत्रों की तुलना करता है। यह किसी के सातवें भाव, शुक्र, दशा या "
            "इस बात पर कुछ नहीं कहता कि दोनों मिले भी हैं या नहीं। यह एक इनपुट है।",
        ), tool="matching", tool_label="दोनों कुंडलियाँ मिलाइए"),
        Part("panchang", "पंचांग और मुहूर्त", (
            "पंचांग किसी दिन और स्थान का हिंदू कैलेंडर है, और नाम का अर्थ है 'पाँच अंग': वार, तिथि, "
            "नक्षत्र, योग और करण - सभी सूर्योदय के समय।",
            "ये सूर्योदय पर पढ़े जाते हैं और सूर्योदय स्थान पर निर्भर है, इसलिए पंचांग हमेशा किसी "
            "स्थान का होता है। पुणे और दिल्ली के सूर्योदय में लगभग बीस मिनट का अंतर है।",
            "मुहूर्त पंचांग का उपयोग है किसी काम का समय चुनने के लिए। सबसे आम व्यावहारिक उपयोग उल्टा "
            "है: राहु काल, यमगंड और गुलिक से बचना।",
        ), tool="panchang", tool_label="आपके शहर का आज का पंचांग"),
        Part("honest", "इसे ईमानदारी से कैसे बरतें", (
            "ज्योतिष एक पारंपरिक विद्या है, सिद्ध तंत्र नहीं। इस साइट पर कुछ भी इस बात का प्रमाण "
            "नहीं है कि कोई ग्रह किसी परिणाम को बदलता है, और हम ऐसा दावा करते भी नहीं।",
            "कुंडली जिस काम में वाक़ई अच्छी है वह है आत्मचिंतन: अपनी प्रवृत्तियों के बारे में सोचने "
            "की एक व्यवस्थित शब्दावली, और एक ऐसा कैलेंडर जो कठिन समय में धैर्य और अनुकूल समय में "
            "प्रयास की ओर ले जाता है। इसे चिकित्सा, क़ानून या पैसे के निर्णय की जगह रख देना वहीं है "
            "जहाँ यह नुक़सान करता है।",
            "उससे ख़ास सावधान रहिए जो घटना की तारीख़ दे, दोष 'काटने' के लिए उपाय बेचे, या कहे कि "
            "कुंडली शापित है। योग सार्वजनिक जानकारी हैं, गणना कोई भी जाँच सकता है, और डर कोई पाठ "
            "नहीं है।",
        ), tool="consultation", tool_label="अपनी कुंडली के बारे में पूछिए"),
    ),
    "faqs": (
        ("क्या वैदिक ज्योतिष पाश्चात्य ज्योतिष से अलग है?",
         "हाँ, दो बुनियादी तरीक़ों से। यह निरयण राशिचक्र लेता है, जिससे अधिकांश लोग एक राशि पीछे "
         "चले जाते हैं, और इसमें दशा पद्धति है, जिसका पाश्चात्य ज्योतिष में कोई समकक्ष नहीं। चंद्र "
         "राशि भी सूर्य राशि से अधिक मायने रखती है।"),
        ("कुंडली का सबसे महत्वपूर्ण हिस्सा क्या है?",
         "लग्न और चंद्र। लग्न बारहों भाव तय करता है और सही जन्म समय माँगता है; चंद्र का नक्षत्र "
         "पूरी दशा शृंखला तय करता है।"),
        ("क्या सही जन्म समय ज़रूरी है?",
         "लग्न, भाव और दशा की तारीख़ों के लिए हाँ - लग्न हर दो घंटे में बदलता है। समय के बिना भी "
         "सूर्य राशि, धीमे ग्रह, और पाँच में से लगभग तीन दिन चंद्र राशि मिल जाती है।"),
        ("मांगलिक होना क्या गंभीर समस्या है?",
         "यह एक योग है, निर्णय नहीं, और कौन से भाव गिने जाएँ यह परंपरा से बदलता है। कई मानक निवारण "
         "हैं। जो इसे हटाने का पैसा माँगे, वह डर बेच रहा है।"),
        ("क्या ज्योतिष भविष्य बता सकता है?",
         "कोई कुंडली तारीख़ नहीं बताती, और जो बता दे वह अनुमान लगा रहा है। शास्त्र अनुकूल या कठिन "
         "काल बताते हैं, जो कुंडली के बारे में कथन है, आपके जीवन के बारे में नहीं।"),
    ),
}


MR = {
    "title": "ज्योतिष: संपूर्ण आणि प्रामाणिक माहिती (Jyotish)",
    "h1": "ज्योतिष, नीट समजावून",
    "intro": "ज्योतिष ही दोन हजार वर्षे जुनी पद्धत आहे, जी जन्माच्या क्षणीचे आकाश वाचते. हे पान "
             "सांगते की ते खरोखर कसे चालते - कोणते राशिचक्र आणि पाश्चात्त्यापेक्षा वेगळे का, नऊ ग्रह, "
             "बारा स्थाने, नक्षत्रे, दशा, आणि ज्या दोषांची लोकांना भीती वाटते ते. भाकीत नाही, भीती "
             "नाही, आणि वाचण्यासाठी काहीही द्यावे लागत नाही.",
    "toc": "या पानावर",
    "faq": "नेहमीचे प्रश्न",
    "parts": (
        Part("what-it-is", "ज्योतिष म्हणजे नेमके काय", (
            "ज्योतिष म्हणजे 'प्रकाशाचे शास्त्र' - एखादा क्षण त्या वेळी ग्रह कुठे होते यावरून वर्णन "
            "करण्याची पद्धत. तिचा दावा मर्यादित आणि नेमका आहे: जन्मावेळचे आकाश आयुष्याचा नकाशा "
            "सांगते, जसा नकाशा जमीन सांगतो. काय घडेल हे नाही - जमीन कशी आहे हे.",
            "हे गणितावर उभे आहे, अंतःप्रेरणेवर नाही. नऊ ग्रह, बारा राशी आणि बारा स्थाने जन्मतारीख, "
            "वेळ आणि ठिकाणावरून निघतात, आणि एकाच तपशिलावरून दोन ज्योतिषी एकच पत्रिका काढतील. फरक "
            "वाचण्यात येतो - आणि ते भाष्य आहे, गणित नाही.",
            "हे काय नाही: नियंत्रित परिस्थितीत सिद्ध झालेली यंत्रणा. ही पारंपरिक, श्रद्धेवर आधारित "
            "विद्या आहे. याच स्वरूपात ती इथे दिली आहे, आणि पत्रिका निकालाची हमी देते असे सांगणारा "
            "कोणीही काहीतरी विकतो आहे.",
        )),
        Part("sidereal", "तुमची भारतीय रास पाश्चात्त्य राशीपेक्षा वेगळी का", (
            "हा पहिला गोंधळ आहे आणि त्याचे नेमके उत्तर आहे. पाश्चात्त्य ज्योतिष सायन राशिचक्र घेते, "
            "जे वसंत संपातापासून सुरू होते. वैदिक ज्योतिष निरयण राशिचक्र घेते, जे प्रत्यक्ष "
            "ताऱ्यांमधील स्थिर बिंदूपासून सुरू होते.",
            "पृथ्वीचा अक्ष सुमारे 26,000 वर्षांत एक फेरा डोलतो, त्यामुळे संपातबिंदू ताऱ्यांच्या "
            "पार्श्वभूमीवर हळूहळू सरकतो. दोन्ही राशिचक्रे तिसऱ्या ते पाचव्या शतकाच्या सुमारास जुळत "
            "होती आणि तेव्हापासून वेगळी होत गेली. आज फरक सुमारे 24 अंश आहे - 30 अंशांच्या राशीचा "
            "बहुतांश भाग.",
            "म्हणूनच ज्याला आयुष्यभर 'सिंह' सांगितले, तो वैदिक पत्रिकेत बहुधा कर्क निघतो. दोन्हींपैकी "
            "काहीही चुकीचे नाही; दोन्ही वेगळ्या शून्यापासून मोजतात. या फरकाला अयनांश म्हणतात, आणि "
            "ही साइट लाहिरी अयनांश घेते - तोच जो भारतीय पंचांगे मानतात.",
        ), tool="kundali", tool_label="तुमची पत्रिका पाहा"),
        Part("grahas", "नऊ ग्रह", (
            "'ग्रह' म्हणजे 'धरणारा', 'planet' नव्हे - म्हणूनच यादीत सूर्य आणि चंद्रही आहेत आणि दोन "
            "असे बिंदूही आहेत जे पिंडच नाहीत.",
            "सूर्य: आत्मा, वडील, अधिकार, तेज. चंद्र: मन, आई, आणि गोष्टी घेण्याची पद्धत - वैदिक "
            "ज्योतिषात 'तुमची रास' ही चंद्राची रास असते, सूर्याची नाही.",
            "मंगळ: ऊर्जा, धैर्य, जमीन, भाऊ. बुध: वाणी, व्यापार, गणित, मज्जासंस्था. गुरू: ज्ञान, "
            "गुरुजन, संतती, टिकणारी संपत्ती - पत्रिकेतील सर्वात रक्षक प्रभाव. शुक्र: विवाह, सुख, कला. "
            "शनी: शिस्त, विलंब, कष्ट, वृद्धापकाळ.",
            "राहू आणि केतू हे चंद्राची कक्षा सूर्याचा मार्ग छेदते ते दोन बिंदू - ग्रहणबिंदू. ते सदा "
            "समोरासमोर आणि सदा वक्री असतात. राहू: भूक, परदेश, अचानक उन्नती. केतू: विरक्ती, संशोधन.",
        )),
        Part("houses", "बारा स्थाने, आणि जन्मवेळ इतकी महत्त्वाची का", (
            "स्थाने ही तुमच्या जन्मस्थळावरून, जन्माच्या मिनिटाला, आकाशाची बारा विभागणी आहे. पहिले "
            "स्थान लग्नापासून सुरू होते - त्या क्षणी पूर्व क्षितिजावर चढणारा अंश.",
            "लग्न एका दिवसात बाराही राशींतून जाते, म्हणजे दर सुमारे दोन तासांनी रास बदलते. जन्मवेळ "
            "इतकी महत्त्वाची याचसाठी आहे: तासाभरात ग्रह जवळजवळ हलत नाहीत, पण स्थाने त्यांच्याखालून "
            "पूर्ण फिरतात.",
            "पहिले: शरीर, स्वभाव. दुसरे: धन, वाणी, कुटुंब. तिसरे: पराक्रम, धाकटी भावंडे. चौथे: आई, "
            "घर, जमीन, मनःशांती. पाचवे: संतती, विद्या. सहावे: रोग, कर्ज, शत्रू. सातवे: विवाह, "
            "भागीदारी. आठवे: आयुष्य, गुप्त, अचानक बदल. नववे: भाग्य, वडील, गुरू. दहावे: कर्म, "
            "प्रतिष्ठा. अकरावे: लाभ, उत्पन्न. बारावे: खर्च, निद्रा, परदेश.",
        ), tool="kundali", tool_label="तुमचे लग्न आणि स्थाने पाहा"),
        Part("nakshatras", "सत्तावीस नक्षत्रे", (
            "बारा राशींच्या आधी भारताने आकाश सत्तावीस नक्षत्रांत वाटले - प्रत्येक 13 अंश 20 कला, "
            "म्हणजे चंद्राचा सुमारे एका दिवसाचा प्रवास. नक्षत्रे राशींपेक्षा जुनी आहेत आणि व्यवहारात "
            "अधिक नेमका अर्थ देतात.",
            "जन्मावेळी चंद्र ज्या नक्षत्रात होता, ते लग्नानंतरचे पत्रिकेतील सर्वात महत्त्वाचे तथ्य "
            "आहे. तेच जन्मनक्षत्र, तेच नामकरणाचे अक्षर देते, आणि सर्वात महत्त्वाचे - तेच ठरवते की "
            "तुमची दशा कुठून सुरू होते.",
            "प्रत्येक नक्षत्र चार चरणांत विभागले आहे आणि प्रत्येकाचा स्वामी ग्रह, देवता आणि चिन्ह आहे.",
        )),
        Part("dasha", "दशा: वेळ सांगणारी पद्धत", (
            "पत्रिका जन्मावेळी ठरते आणि कधीही बदलत नाही. बदलते ते म्हणजे सध्या कोणता ग्रह चालू आहे - "
            "तीच दशा पद्धत, ज्योतिषाचा तो भाग ज्याला पाश्चात्त्य ज्योतिषात समकक्ष काहीच नाही.",
            "विंशोत्तरी दशा 120 वर्षे नऊ ग्रहांत वाटते: केतू 7, शुक्र 20, सूर्य 6, चंद्र 10, मंगळ 7, "
            "राहू 18, गुरू 16, शनी 19, बुध 17. त्या क्रमात तुम्ही कुठून सुरू करता हे चंद्राने "
            "नक्षत्रात नेमका किती प्रवास केला यावरून निघते.",
            "प्रत्येक महादशा त्याच प्रमाणात नऊ अंतर्दशांत विभागते. एखाद्या वर्षाचे वाचन बहुधा "
            "दोघांचे मिश्रण असते.",
            "म्हणूनच अंदाजे जन्मवेळ दशेसाठी पुरेशी नाही. एका तासाची चूक प्रत्येक तारीख महिन्यांनी "
            "सरकवते.",
        )),
        Part("doshas", "दोष: मंगळ, कालसर्प, साडेसाती", (
            "दोष म्हणजे शास्त्रे ज्याला अडचण मानतात तो योग. ज्योतिषाचा हाच भाग लोकांना घाबरवायला "
            "सर्वात जास्त वापरला जातो, आणि प्रामाणिक मार्ग म्हणजे योग नेमका काय आहे हे सांगणे आणि "
            "त्यावर किती मतभेद आहेत हेही सांगणे.",
            "मंगळ दोष: मंगळ पहिल्या, दुसऱ्या, चौथ्या, सातव्या, आठव्या किंवा बाराव्या स्थानात असणे. "
            "कोणती स्थाने धरायची हे परंपरेनुसार बदलते, आणि अनेक मानक परिहार आहेत.",
            "कालसर्प तेव्हा होतो जेव्हा सातही ग्रह राहू आणि केतूच्या मध्ये येतात. हे शास्त्रांत नाही, "
            "नंतरची भर आहे, आणि लोकप्रिय ज्योतिषात जितके गंभीर मानले जाते तितके विद्वत परंपरेत नाही.",
            "साडेसाती हा पत्रिकेतील दोषच नाही - ते गोचर आहे. शनी तुमच्या चंद्रराशीच्या आधीची रास, "
            "चंद्ररास, आणि पुढची रास ओलांडतो, एकूण साडेसात वर्षे. ती प्रत्येकाला सुमारे दर तीस "
            "वर्षांनी येते, आणि ती आपत्ती नव्हे तर कष्ट आणि स्थिरावण्याचा काळ मानली जाते.",
        ), tool="sade-sati", tool_label="तुमची साडेसाती पाहा"),
        Part("matching", "विवाहासाठी पत्रिका जुळवणी", (
            "अष्टकूट गुणमेलन दोन पत्रिका आठ कसोट्यांवर 36 गुणांत तपासते: वर्ण 1, वश्य 2, तारा 3, "
            "योनी 4, ग्रहमैत्री 5, गण 6, भकूट 7, नाडी 8.",
            "एकूण गुण प्रसिद्ध आहेत आणि सर्वात कमी उपयोगी. आठांपैकी दोन सर्वात वजनदार: नाडी (8) आणि "
            "भकूट (7). 36 पैकी 28 मिळूनही नाडी दोष असू शकतो.",
            "गुणमेलन फक्त चंद्रनक्षत्रांची तुलना करते. ते कोणाच्या सातव्या स्थानाबद्दल, शुक्राबद्दल "
            "किंवा दशेबद्दल काहीच सांगत नाही. तो एक घटक आहे.",
        ), tool="matching", tool_label="दोन्ही पत्रिका जुळवा"),
        Part("panchang", "पंचांग आणि मुहूर्त", (
            "पंचांग म्हणजे एका दिवसाचे आणि ठिकाणाचे हिंदू दिनदर्शिका, आणि नावाचा अर्थ 'पाच अंगे': "
            "वार, तिथी, नक्षत्र, योग आणि करण - सर्व सूर्योदयाच्या वेळी.",
            "ही सूर्योदयावर वाचली जातात आणि सूर्योदय ठिकाणावर अवलंबून असतो, म्हणून पंचांग नेहमी "
            "एखाद्या ठिकाणाचे असते. पुणे आणि दिल्लीच्या सूर्योदयात सुमारे वीस मिनिटांचा फरक आहे.",
            "मुहूर्त म्हणजे पंचांग वापरून कामाची वेळ निवडणे. सर्वात सामान्य प्रत्यक्ष उपयोग उलट आहे: "
            "राहू काळ, यमगंड आणि गुलिक टाळणे.",
        ), tool="panchang", tool_label="तुमच्या शहराचे आजचे पंचांग"),
        Part("honest", "हे प्रामाणिकपणे कसे वापरावे", (
            "ज्योतिष ही पारंपरिक विद्या आहे, सिद्ध झालेली यंत्रणा नाही. या साइटवरचे काहीही ग्रह "
            "निकाल बदलतात याचा पुरावा नाही, आणि आम्ही तसा दावाही करत नाही.",
            "पत्रिका ज्यात खरोखर उपयोगी आहे ते म्हणजे आत्मपरीक्षण: स्वतःच्या प्रवृत्तींबद्दल "
            "विचार करण्याची एक रचलेली भाषा, आणि कठीण काळात संयम व अनुकूल काळात प्रयत्न यांकडे नेणारे "
            "दिनदर्शिका. ती वैद्यकीय, कायदेशीर किंवा आर्थिक निर्णयाच्या जागी ठेवणे तिथेच ती नुकसान "
            "करते.",
            "जो घटनेची तारीख देतो, दोष 'कापण्यासाठी' उपाय विकतो, किंवा पत्रिका शापित आहे असे सांगतो "
            "त्याच्यापासून विशेष सावध राहा. योग सार्वजनिक माहिती आहे, गणित कोणीही तपासू शकतो, आणि "
            "भीती हे वाचन नव्हे.",
        ), tool="consultation", tool_label="तुमच्या पत्रिकेबद्दल विचारा"),
    ),
    "faqs": (
        ("वैदिक ज्योतिष पाश्चात्त्य ज्योतिषापेक्षा वेगळे आहे का?",
         "होय, दोन मूलभूत प्रकारे. ते निरयण राशिचक्र घेते, त्यामुळे बहुतेक लोक एक रास मागे जातात, "
         "आणि त्यात दशा पद्धत आहे, जिला पाश्चात्त्य ज्योतिषात समकक्ष नाही. चंद्ररासही सूर्यराशीपेक्षा "
         "जास्त महत्त्वाची असते."),
        ("पत्रिकेतील सर्वात महत्त्वाचा भाग कोणता?",
         "लग्न आणि चंद्र. लग्न बाराही स्थाने ठरवते आणि अचूक जन्मवेळ मागते; चंद्राचे नक्षत्र संपूर्ण "
         "दशा मालिका ठरवते."),
        ("अचूक जन्मवेळ लागतेच का?",
         "लग्न, स्थाने आणि दशेच्या तारखांसाठी होय - लग्न दर दोन तासांनी बदलते. वेळेशिवायही सूर्यरास, "
         "मंद ग्रह, आणि पाचांपैकी सुमारे तीन दिवस चंद्ररास मिळते."),
        ("मंगळ असणे गंभीर अडचण आहे का?",
         "तो एक योग आहे, निर्णय नव्हे, आणि कोणती स्थाने धरायची हे परंपरेनुसार बदलते. अनेक मानक "
         "परिहार आहेत. तो काढण्यासाठी पैसे मागणारा भीती विकतो आहे."),
        ("ज्योतिष भविष्य सांगू शकते का?",
         "कोणतीही पत्रिका तारीख सांगत नाही, आणि जो सांगतो तो अंदाज लावतो आहे. शास्त्रे अनुकूल किंवा "
         "कठीण काळ सांगतात, जे पत्रिकेबद्दलचे विधान आहे, तुमच्या आयुष्याबद्दल नाही."),
    ),
}


GUIDES = {"en": EN, "hi": HI, "mr": MR}


def add_routes(router, page_context, respond, _json_ld) -> None:
    for lang in i18n.PAGES["astrology"]:
        _add(router, page_context, respond, _json_ld, lang)


def _add(router, page_context, respond, _json_ld, lang: str) -> None:
    def guide_page(request: Request):
        from app.web import seo as _seo

        guide = GUIDES[lang]
        context = page_context("astrology", lang)
        path = i18n.url_for("astrology", lang)
        parts = []
        for part in guide["parts"]:
            link = None
            if part.tool and lang in i18n.page_langs(part.tool):
                link = {"href": i18n.url_for(part.tool, lang), "label": part.tool_label}
            parts.append({"anchor": part.anchor, "heading": part.heading,
                          "paragraphs": part.paragraphs, "link": link})
        context.update(
            guide=guide, parts=parts,
            json_ld=[_json_ld(_seo.breadcrumbs([(context["ui"]["home"], i18n.url_for("home", lang)),
                                                (guide["h1"], path)])),
                     _json_ld({**_seo.faq_page(guide["faqs"]), "inLanguage": i18n.HTML_LANG[lang]})])
        return respond(request, "astrology_guide.html", context)

    router.add_api_route(i18n.url_for("astrology", lang), guide_page, methods=["GET"],
                         response_class=HTMLResponse, name=f"astrology-{lang}")
