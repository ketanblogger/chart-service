/* Result rendering for the tool pages.
 *
 * Pure functions only: JSON from the calculation API in, HTML string out. No DOM, no network -
 * so the same file is executed by tests/test_web.py and tests/test_render_i18n.py (inside an embedded V8) against real API
 * responses. DOM wiring lives in app.js. Field names follow docs/API.md.
 *
 * Every value that reaches the page goes through esc(), including API strings and the user's name.
 */
(function (root) {
  "use strict";

  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  // Display-only reference data (same spellings as app/engine/constants.py). Nothing is calculated here.
  var SIGNS = [
    ["Mesha", "Aries", "मेष"], ["Vrishabha", "Taurus", "वृषभ"], ["Mithuna", "Gemini", "मिथुन"],
    ["Karka", "Cancer", "कर्क"], ["Simha", "Leo", "सिंह"], ["Kanya", "Virgo", "कन्या"],
    ["Tula", "Libra", "तुला"], ["Vrishchika", "Scorpio", "वृश्चिक"], ["Dhanu", "Sagittarius", "धनु"],
    ["Makara", "Capricorn", "मकर"], ["Kumbha", "Aquarius", "कुंभ"], ["Meena", "Pisces", "मीन"]
  ];
  var GRAHA_KEYS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"];
  var GRAHA_ABBR = {
    en: { Lagna: "Lg", Sun: "Su", Moon: "Mo", Mars: "Ma", Mercury: "Me", Jupiter: "Ju", Venus: "Ve", Saturn: "Sa", Rahu: "Ra", Ketu: "Ke" },
    deva: { Lagna: "ल", Sun: "सू", Moon: "चं", Mars: "मं", Mercury: "बु", Jupiter: "गु", Venus: "शु", Saturn: "श", Rahu: "रा", Ketu: "के" }
  };
  var KOOTA_LABELS = {
    varna: ["Varna", "वर्ण", "Outlook and values"],
    vashya: ["Vashya", "वश्य", "Mutual attraction"],
    tara: ["Tara", "तारा", "Fortune and well-being"],
    yoni: ["Yoni", "योनि", "Physical compatibility"],
    graha_maitri: ["Graha Maitri", "ग्रह मैत्री", "Mental compatibility"],
    gana: ["Gana", "गण", "Temperament"],
    bhakoot: ["Bhakoot", "भकूट", "Family harmony and prosperity"],
    nadi: ["Nadi", "नाडी", "Constitution and progeny"]
  };
  // hi / mr koota names + blurbs (same wording as the PDF report, app/pdf/labels.py).
  var KOOTA_LABELS_L = {
    hi: {
      varna: ["वर्ण", "दृष्टिकोण और मूल्य"], vashya: ["वश्य", "परस्पर आकर्षण"], tara: ["तारा", "भाग्य और कल्याण"],
      yoni: ["योनि", "शारीरिक अनुकूलता"], graha_maitri: ["ग्रह मैत्री", "मानसिक अनुकूलता"], gana: ["गण", "स्वभाव"],
      bhakoot: ["भकूट", "पारिवारिक सुख और समृद्धि"], nadi: ["नाड़ी", "प्रकृति और संतान"]
    },
    mr: {
      varna: ["वर्ण", "दृष्टिकोन आणि मूल्ये"], vashya: ["वश्य", "परस्पर आकर्षण"], tara: ["तारा", "भाग्य आणि कल्याण"],
      yoni: ["योनी", "शारीरिक अनुरूपता"], graha_maitri: ["ग्रहमैत्री", "मानसिक अनुरूपता"], gana: ["गण", "स्वभाव"],
      bhakoot: ["भकूट", "कौटुंबिक सौख्य आणि समृद्धी"], nadi: ["नाडी", "प्रकृती आणि संतती"]
    }
  };
  // Engine koota value (English) -> [hi, mr]. The Sanskrit terms are shared by both traditions.
  var KOOTA_VALUES = {
    Brahmin: ["ब्राह्मण", "ब्राह्मण"], Kshatriya: ["क्षत्रिय", "क्षत्रिय"], Vaishya: ["वैश्य", "वैश्य"], Shudra: ["शूद्र", "शूद्र"],
    Chatushpada: ["चतुष्पाद", "चतुष्पाद"], Manava: ["मानव", "मानव"], Jalachara: ["जलचर", "जलचर"], Vanachara: ["वनचर", "वनचर"],
    Keeta: ["कीट", "कीटक"],
    Horse: ["अश्व", "अश्व"], Elephant: ["गज", "गज"], Sheep: ["मेष", "मेष"], Serpent: ["सर्प", "सर्प"], Dog: ["श्वान", "श्वान"],
    Cat: ["मार्जार", "मार्जार"], Rat: ["मूषक", "मूषक"], Cow: ["गौ", "गो"], Buffalo: ["महिष", "महिष"], Tiger: ["व्याघ्र", "व्याघ्र"],
    Deer: ["मृग", "मृग"], Monkey: ["वानर", "वानर"], Mongoose: ["नकुल", "नकुल"], Lion: ["सिंह", "सिंह"],
    Deva: ["देव", "देव"], Manushya: ["मनुष्य", "मनुष्य"], Rakshasa: ["राक्षस", "राक्षस"],
    Aadi: ["आदि", "आद्य"], Madhya: ["मध्य", "मध्य"], Antya: ["अंत्य", "अंत्य"]
  };
  // English nakshatra name (as in kootas[].boy / .girl of the Tara row) -> Devanagari. Same table as app/engine/constants.py.
  var NAKSHATRAS = {
    "Ashwini": "अश्विनी", "Bharani": "भरणी", "Krittika": "कृत्तिका", "Rohini": "रोहिणी", "Mrigashira": "मृगशीर्ष",
    "Ardra": "आर्द्रा", "Punarvasu": "पुनर्वसु", "Pushya": "पुष्य", "Ashlesha": "आश्लेषा", "Magha": "मघा",
    "Purva Phalguni": "पूर्वा फाल्गुनी", "Uttara Phalguni": "उत्तरा फाल्गुनी", "Hasta": "हस्त", "Chitra": "चित्रा",
    "Swati": "स्वाती", "Vishakha": "विशाखा", "Anuradha": "अनुराधा", "Jyeshtha": "ज्येष्ठा", "Mula": "मूल",
    "Purvashadha": "पूर्वाषाढा", "Uttarashadha": "उत्तराषाढा", "Shravana": "श्रवण", "Dhanishta": "धनिष्ठा",
    "Shatabhisha": "शतभिषा", "Purva Bhadrapada": "पूर्वा भाद्रपदा", "Uttara Bhadrapada": "उत्तरा भाद्रपदा", "Revati": "रेवती"
  };

  /* ---------- languages ----------
   * English is the default everywhere. Every renderer, the form validation and the API error messages also speak
   * Hindi and Marathi: the page sets form data-lang="hi|mr" -> app.js passes ctx.lang. Hindi uses the engine's
   * Devanagari forms (मंगल, शनि, गुरु, राहु, केतु, तुला; भाव); Marathi has its own (मंगळ, शनी, गुरू, राहू, केतू, तूळ; स्थान; आहे).
   * Same spellings as app/pdf/labels.py. LANG is set only for the duration of one synchronous render (withLang),
   * so the functions stay pure. */
  var LANG = "en";
  var MONTHS_L = {
    hi: ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
    mr: ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"]
  };
  var GRAHA_NAMES = {
    hi: { Sun: "सूर्य", Moon: "चंद्र", Mars: "मंगल", Mercury: "बुध", Jupiter: "गुरु", Venus: "शुक्र", Saturn: "शनि", Rahu: "राहु", Ketu: "केतु" },
    mr: { Sun: "सूर्य", Moon: "चंद्र", Mars: "मंगळ", Mercury: "बुध", Jupiter: "गुरू", Venus: "शुक्र", Saturn: "शनी", Rahu: "राहू", Ketu: "केतू" }
  };
  var SIGN_NAMES = { // by sign index - 1
    hi: ["मेष", "वृषभ", "मिथुन", "कर्क", "सिंह", "कन्या", "तुला", "वृश्चिक", "धनु", "मकर", "कुंभ", "मीन"],
    mr: ["मेष", "वृषभ", "मिथुन", "कर्क", "सिंह", "कन्या", "तूळ", "वृश्चिक", "धनु", "मकर", "कुंभ", "मीन"]
  };
  var ORDINALS = {
    hi: ["पहला", "दूसरा", "तीसरा", "चौथा", "पाँचवाँ", "छठा", "सातवाँ", "आठवाँ", "नौवाँ", "दसवाँ", "ग्यारहवाँ", "बारहवाँ"],
    mr: ["पहिले", "दुसरे", "तिसरे", "चौथे", "पाचवे", "सहावे", "सातवे", "आठवे", "नववे", "दहावे", "अकरावे", "बारावे"]
  };
  // Mangal dosha cancellation rules by API `key` (the API's own description is English).
  var CANCELLATIONS = {
    hi: {
      mars_in_own_or_exaltation_sign: "मंगल का अपनी राशि (मेष, वृश्चिक) या उच्च राशि (मकर) में होना",
      jupiter_conjunct_or_aspecting_mars: "गुरु का मंगल के साथ उसी राशि में होना, या मंगल पर गुरु की दृष्टि होना (गुरु से 5वाँ, 7वाँ या 9वाँ भाव)",
      house_sign_exception: "लग्न से मंगल का दूसरे भाव में मिथुन/कन्या, चौथे में मेष/वृश्चिक, सातवें में कर्क/मकर, आठवें में धनु/मीन या बारहवें में वृषभ/तुला राशि में होना",
      cancer_or_leo_lagna: "कर्क और सिंह लग्न के लिए मंगल योगकारक है, इसलिए उसका दोष निष्प्रभावी माना जाता है"
    },
    mr: {
      mars_in_own_or_exaltation_sign: "मंगळ स्वराशीत (मेष, वृश्चिक) किंवा उच्च राशीत (मकर) असणे",
      jupiter_conjunct_or_aspecting_mars: "गुरू मंगळाच्याच राशीत असणे, किंवा मंगळावर गुरूची दृष्टी असणे (गुरूपासून 5 वे, 7 वे किंवा 9 वे स्थान)",
      house_sign_exception: "लग्नापासून मंगळ दुसऱ्या स्थानी मिथुन/कन्या, चौथ्या स्थानी मेष/वृश्चिक, सातव्या स्थानी कर्क/मकर, आठव्या स्थानी धनु/मीन किंवा बाराव्या स्थानी वृषभ/तूळ राशीत असणे",
      cancer_or_leo_lagna: "कर्क आणि सिंह लग्नासाठी मंगळ योगकारक असल्याने त्याचा दोष निष्प्रभ मानला जातो"
    }
  };
  // verdict -> [title, text, tone]
  var VERDICTS = {
    en: {
      below_average: ["Below average match", "Fewer than 18 gunas match. Tradition advises a careful, detailed look at both charts before deciding.", "warn"],
      average: ["Average match", "An acceptable score by traditional standards, with some areas that need mutual understanding.", "info"],
      good: ["Good match", "A well-suited match by traditional standards.", "ok"],
      excellent: ["Excellent match", "A very high score - the charts are highly compatible by traditional standards.", "ok"]
    },
    hi: {
      below_average: ["औसत से कम मिलान", "18 से कम गुण मिल रहे हैं। परंपरा के अनुसार निर्णय से पहले दोनों कुंडलियों को ध्यान से, विस्तार में देखना चाहिए।", "warn"],
      average: ["मध्यम मिलान", "पारंपरिक मानकों से स्वीकार्य अंक; कुछ बातों में आपसी समझ की ज़रूरत रहेगी।", "info"],
      good: ["अच्छा मिलान", "पारंपरिक मानकों से यह एक अनुकूल जोड़ी है।", "ok"],
      excellent: ["उत्तम मिलान", "बहुत ऊँचे अंक - पारंपरिक मानकों से दोनों कुंडलियाँ बहुत अनुकूल हैं।", "ok"]
    },
    mr: {
      below_average: ["सरासरीपेक्षा कमी गुणमेलन", "18 पेक्षा कमी गुण जुळतात. परंपरेनुसार निर्णयापूर्वी दोन्ही पत्रिका काळजीपूर्वक आणि सविस्तर पाहाव्यात.", "warn"],
      average: ["मध्यम गुणमेलन", "पारंपरिक निकषांनुसार स्वीकारार्ह गुण; काही बाबतींत परस्पर समजूतदारपणा लागेल.", "info"],
      good: ["चांगले गुणमेलन", "पारंपरिक निकषांनुसार ही जोडी अनुरूप आहे.", "ok"],
      excellent: ["उत्तम गुणमेलन", "खूप जास्त गुण - पारंपरिक निकषांनुसार दोन्ही पत्रिका अतिशय अनुरूप आहेत.", "ok"]
    }
  };
  // phase -> [name, where Saturn is, sign offset from the Moon sign]
  var PHASES = {
    en: {
      rising: ["Rising phase", "Saturn in the 12th sign from your Moon", -1],
      peak: ["Peak phase", "Saturn over your Moon sign", 0],
      setting: ["Setting phase", "Saturn in the 2nd sign from your Moon", 1]
    },
    hi: {
      rising: ["पहला चरण", "शनि आपकी चंद्र राशि से 12वीं राशि में", -1],
      peak: ["मध्य चरण", "शनि आपकी चंद्र राशि में", 0],
      setting: ["अंतिम चरण", "शनि आपकी चंद्र राशि से दूसरी राशि में", 1]
    },
    mr: {
      rising: ["पहिला टप्पा", "शनी तुमच्या चंद्रराशीपासून 12 व्या राशीत", -1],
      peak: ["मधला टप्पा", "शनी तुमच्या चंद्रराशीत", 0],
      setting: ["शेवटचा टप्पा", "शनी तुमच्या चंद्रराशीपासून दुसऱ्या राशीत", 1]
    }
  };
  var INTENSITY = {
    en: { none: "None", low: "Low", medium: "Medium", high: "High" },
    hi: { none: "नहीं", low: "कम", medium: "मध्यम", high: "अधिक" },
    mr: { none: "नाही", low: "कमी", medium: "मध्यम", high: "अधिक" }
  };

  var LABELS = {
    en: {
      born: "Born", lagna: "Lagna (ascendant)", rashi: "Rashi (Moon sign)", nakshatra: "Janma nakshatra", lord: "Lord", pada: "pada",
      padaCap: "Pada", chartHeading: "Lagna chart (North Indian style)", chartLabels: "Chart labels", english: "English",
      chartNote: "The number in each house is the sign (1 = Mesha/Aries &hellip; 12 = Meena/Pisces). The top-centre diamond is the first house.",
      chartAria: "North Indian kundali chart. Lagna {lagna}. Positions are listed in the table below.",
      legendLagna: "Lagna", retrograde: "retrograde", lagnaRow: "Lagna", positions: "Graha positions",
      cols: ["Graha", "Sign (rashi)", "Degree", "Nakshatra", "House", "Retrograde"], yes: "Yes", no: "No", always: "Always",
      dasha: "Vimshottari dasha", currentMaha: "Current mahadasha", currentAntar: "Current antardasha",
      balance: "Dasha balance at birth", balanceFmt: "{y}y {m}m {d}d remaining", timeline: "Mahadasha timeline",
      timelineNote: "Tap a period to see its antardashas. The first period began before birth; only the balance shown above was left at birth.",
      asOf: " Current period as of {date}.", yrs: "yrs", current: "Current", now: "Now", antarCols: ["Antardasha", "From", "To"],
      calc: "Calculated with Swiss Ephemeris &middot; {zodiac} zodiac &middot; {ayanamsa} ayanamsa {degrees}&middot; whole-sign houses &middot; mean Rahu/Ketu.",
      // accuracy notes - shown only when the chart itself says they apply (~6% of charts)
      accHeading: "Worth knowing about this chart",
      accPlace: "The rising sign is close to a boundary here: a birthplace about {km}&nbsp;{unit} from {place} would " +
        "make it {adjacent} instead of {lagna}. Your Moon sign, nakshatra and dasha dates do not depend on the birthplace.",
      accPlaceHere: "The rising sign is close to a boundary here: a birthplace about {km}&nbsp;{unit} from the place " +
        "you entered would make it {adjacent} instead of {lagna}. Your Moon sign, nakshatra and dasha dates do not " +
        "depend on the birthplace.",
      accKm: "km",
      accClock: "This birth was converted on the clock in civil use at the time - {era}, {minutes} minutes {direction} " +
        "today's Indian Standard Time. If the time you have was written down by today's clock, the rising sign may differ.",
      accClockPlain: "This birth was converted on {offset}, which is not today's Indian Standard Time. If the time you " +
        "have was written down by today's clock, the rising sign may differ.",
      accAhead: "ahead of", accBehind: "behind",
      // Shown when the reader picked one of the time presets instead of a recorded birth time.
      //
      // The split below is MEASURED, not assumed, and it is written for the WORST case: somebody who taps a
      // preset cannot know they are near the middle of the bucket. With presets every three hours the worst
      // case is ninety minutes out, and at that width (n=1500) the ascendant changes on 76% of charts, the
      // mangal dosha verdict on 9.2%, the janma nakshatra on 5.7%, the mahadasha lord on 5.3%, the Moon sign
      // on 2.6% and sade sati on 0.5% - with the mahadasha start date moving more than a year on 44% and
      // more than two years on none of them, which is not luck: at 1.5 h the Moon covers at most 0.95
      // degrees, 0.071 of a nakshatra, so against the 20-year Venus period no dasha boundary can shift by
      // more than 1.42 years. Dasha dates read as safe and are not - this is the product that promises real
      // calendar ranges, so that is the sentence to get right. Nothing on the list is zero.
      accApprox: "You picked an approximate birth time, so read this in three parts. A preset puts you at most " +
        "ninety minutes from the real one, and that is the width everything below is measured against. Sade " +
        "sati is the steadiest thing on the page and still not fixed: it is a two-and-a-half-year Saturn " +
        "transit read from your Moon sign, and it flips for about one chart in two hundred. The Moon sign " +
        "itself moves for about one in forty, and the janma nakshatra for about one in eighteen. The rest " +
        "should not be trusted until you have the recorded time. Over ninety minutes the ascendant changes " +
        "on about three charts in four, and with it every house placement counted from the lagna and the " +
        "mangal dosha verdict. The dasha dates move too: a little under half of all charts shift by more " +
        "than a year, so a period dated here to one month can genuinely belong to another. Nothing here is " +
        "independent of your birth time, so if the recorded one turns up, run this again.",
      accEra: {
        madras_time: "Madras time", wartime: "India's wartime clock of 1942-45",
        calcutta_local_mean_time: "Calcutta local mean time"
      },
      // mangal dosha
      mdNoneTitle: "No Mangal dosha", mdNoneText: "Mars is not in the 1st, 2nd, 4th, 7th, 8th or 12th house from the lagna, Moon or Venus.",
      mdCancelTitle: "Mangal dosha present, with mitigating factors",
      mdCancelText: "{intensity} intensity. At least one classical cancellation rule applies to this chart, so tradition treats the dosha as much reduced.",
      mdPresentTitle: "Mangal dosha present",
      mdPresentText: "{intensity} intensity. This is a common placement - about half of all charts have it - and tradition offers simple remedies.",
      mdRefs: ["From Lagna", "From Moon (Chandra)", "From Venus (Shukra)"], mdRefCols: ["Counted", "Mars is in", "Triggers dosha?"],
      houseFmt: "{ord} house", mdStatus: "Status", mdManglik: "Manglik", mdNotManglik: "Not manglik", mdIntensity: "Intensity",
      sumMangal: "Mangal dosha", sumSadeSati: "Sade sati",
      // Sits beside the ONLY warn chip on the page. States what it affects and where the reasoning is,
      // and says nothing about severity - the intensity is a gradation and belongs in the detail.
      sumMangalActive: "This matters for marriage matching. The section below shows which rule applies and which classical exceptions were checked.",
      mdMars: "Mars (Mangal)", mdLagna: "Lagna", mdWhere: "Where Mars falls in your chart", mdRuleUsed: "Rule used: {rule}.",
      mdCancelHeading: "Cancellation rules (dosha bhanga)", mdApplies: "Applies to your chart", mdNotApplies: "Does not apply",
      mdNotesHeading: "Good to know",
      // sade sati
      ssActiveTitle: "Sade sati is active: {phase}", ssRuns: "Your sade sati runs from {start} to {end}.",
      ssPausedTitle: "Sade sati is in progress (brief pause)",
      ssPausedText: "Saturn has temporarily moved out of the three signs around your Moon because of retrograde motion. ",
      ssInactiveTitle: "Sade sati is not active", ssNext: "Your next sade sati begins on {start} and ends on {end}.",
      ssRashi: "Your rashi (Moon sign)", ssSaturnIn: "Saturn (Shani) is now in", ssFromMoon: "{ord} from your Moon", ssAsOf: "Status as of",
      ssCurrent: "Your current sade sati", ssNextHeading: "Your next sade sati", ssCols: ["Phase", "Saturn in", "From", "To"],
      ssNote: "A phase can appear more than once: Saturn turns retrograde each year and sometimes re-enters the previous sign for a few months. Dates are from Saturn's actual sidereal transits.",
      ssPhases: "The three phases",
      // matching
      gunas: "gunas", percentAria: "{percent} percent match", boy: "Boy", girl: "Girl", rashiShort: "Rashi", nakshatraShort: "Nakshatra",
      ashtakoota: "Ashtakoota guna milan", kootaCols: ["Koota", "Boy", "Girl", "Points"], total: "Total",
      nadiBhakoot: "Nadi and Bhakoot dosha", nadiDosha: "Nadi dosha", nadiWhy: "Arises when both partners have the same nadi.",
      bhakootDosha: "Bhakoot dosha", bhakootWhy: "Arises when the Moon signs are 2-12, 5-9 or 6-8 from each other.",
      bhakootHere: " Here the Moon signs are {distance} from each other.",
      notPresent: "Not present", presentCancelled: "Present, cancelled by classical exception", present: "Present",
      mangalCompare: "Mangal dosha comparison", mangalOk: "Mangal dosha: compatible", mangalAttention: "Mangal dosha: needs attention",
      mangalBoth: "Both partners have Mangal dosha, which tradition treats as balancing each other.",
      mangalNeither: "Neither partner has Mangal dosha.",
      mangalOne: "Only one partner has Mangal dosha. Astrologers look at the cancellation rules and overall chart strength before advising; traditional remedies are commonly suggested.",
      intensityLabel: "Intensity: ", mitigating: "Mitigating factors:",
      // matching by name
      fromName: "Derived from the name", conventionNote: "Read by the traditional naming conventions:", syllable: "Name syllable",
      nameNote: "This result is based on the first syllable of each name. Matching by birth details is more accurate, and it also compares Mangal dosha.",
      candidatePrompt: "{who}: this name can start with more than one syllable. Choose the sound that fits:",
      // consultation header
      cLagna: "Lagna", cRashi: "Rashi (Moon sign)", cNakshatra: "Nakshatra", cMaha: "Mahadasha", cAntar: "Antardasha", until: "until {date}"
    },
    hi: {
      born: "जन्म:", lagna: "लग्न", rashi: "राशि (चंद्र राशि)", nakshatra: "जन्म नक्षत्र", lord: "स्वामी", pada: "चरण",
      padaCap: "चरण", chartHeading: "लग्न कुंडली (उत्तर भारतीय शैली)", chartLabels: "कुंडली के अक्षर", english: "अंग्रेज़ी",
      chartNote: "हर भाव में लिखा अंक राशि का क्रमांक है (1 = मेष &hellip; 12 = मीन)। ऊपर बीच का चौकोर पहला भाव है।",
      chartAria: "उत्तर भारतीय शैली की कुंडली। लग्न {lagna}। ग्रहों की स्थिति नीचे तालिका में दी गई है।",
      legendLagna: "लग्न", retrograde: "वक्री", lagnaRow: "लग्न", positions: "ग्रह स्थिति",
      cols: ["ग्रह", "राशि", "अंश", "नक्षत्र", "भाव", "वक्री"], yes: "हाँ", no: "नहीं", always: "सदैव",
      dasha: "विंशोत्तरी दशा", currentMaha: "वर्तमान महादशा", currentAntar: "वर्तमान अंतर्दशा",
      balance: "जन्म के समय शेष दशा", balanceFmt: "{y} वर्ष {m} माह {d} दिन शेष", timeline: "महादशाओं का क्रम",
      timelineNote: "किसी महादशा पर टैप करें तो उसकी अंतर्दशाएँ दिखेंगी। पहली महादशा जन्म से पहले ही शुरू हो चुकी थी; जन्म के समय उसका केवल ऊपर दिखाया गया शेष भाग बचा था।",
      asOf: " वर्तमान दशा {date} के अनुसार।", yrs: "वर्ष", current: "वर्तमान", now: "अभी", antarCols: ["अंतर्दशा", "से", "तक"],
      calc: "गणना: स्विस एफेमेरिस &middot; निरयन राशिचक्र &middot; लाहिरी अयनांश {degrees}&middot; संपूर्ण-राशि भाव पद्धति &middot; मध्यम राहु/केतु।",
      accHeading: "इस कुंडली के बारे में जान लेना अच्छा है",
      accPlace: "यहाँ लग्न राशि की संधि पास है: जन्मस्थान {place} से लगभग {km}&nbsp;{unit} दूर होता तो लग्न {lagna} की जगह " +
        "{adjacent} होता। आपकी चंद्र राशि, नक्षत्र और दशाओं की तिथियाँ जन्मस्थान पर निर्भर नहीं करतीं।",
      accPlaceHere: "यहाँ लग्न राशि की संधि पास है: जन्मस्थान आपके बताए स्थान से लगभग {km}&nbsp;{unit} दूर होता तो लग्न " +
        "{lagna} की जगह {adjacent} होता। आपकी चंद्र राशि, नक्षत्र और दशाओं की तिथियाँ जन्मस्थान पर निर्भर नहीं करतीं।",
      accKm: "किमी",
      accClock: "इस जन्म की गणना उस समय प्रचलित घड़ी के अनुसार की गई है - {era}, जो आज के भारतीय मानक समय से " +
        "{minutes} मिनट {direction} है। यदि आपके पास लिखा समय आज की घड़ी के हिसाब से है, तो लग्न बदल सकता है।",
      accClockPlain: "इस जन्म की गणना {offset} के अनुसार की गई है, जो आज का भारतीय मानक समय नहीं है। यदि आपके पास लिखा " +
        "समय आज की घड़ी के हिसाब से है, तो लग्न बदल सकता है।",
      accAhead: "आगे", accBehind: "पीछे",
      accApprox: "आपने जन्म समय अंदाज़न चुना है, इसलिए इसे तीन हिस्सों में पढ़िए। तैयार विकल्पों से आप असली समय से " +
        "ज़्यादा से ज़्यादा डेढ़ घंटे दूर होते हैं, और नीचे का सब कुछ उसी दायरे पर नापा गया है। साढ़ेसाती इस पेज पर " +
        "सबसे टिकाऊ चीज़ है, फिर भी पक्की नहीं: वह ढाई साल का शनि गोचर है जो चंद्र राशि से पढ़ा जाता है, और क़रीब " +
        "दो सौ में से एक कुंडली में वह बदल जाता है। चंद्र राशि ख़ुद क़रीब चालीस में से एक कुंडली में बदलती है, और " +
        "जन्म नक्षत्र अठारह में से एक में। बाक़ी सब पर असली समय मिलने तक भरोसा मत कीजिए। डेढ़ घंटे के दायरे में " +
        "लग्न चार में से क़रीब तीन कुंडलियों में बदल जाता है, और उसके साथ लग्न से गिने जाने वाले सारे भाव तथा मंगल " +
        "दोष का नतीजा भी। दशा की तारीख़ें भी खिसकती हैं: आधी से कुछ कम कुंडलियों में वे एक साल से ज़्यादा आगे-पीछे " +
        "हो जाती हैं, यानी जो अवधि यहाँ एक महीने की बताई गई है वह सचमुच किसी और महीने की हो सकती है। यहाँ कुछ भी " +
        "आपके जन्म समय से आज़ाद नहीं है, इसलिए लिखा हुआ समय मिले तो यह दोबारा निकालिए।",
      accEra: {
        madras_time: "मद्रास समय", wartime: "1942-45 की युद्धकालीन घड़ी",
        calcutta_local_mean_time: "कलकत्ता का स्थानीय मध्यमान समय"
      },
      mdNoneTitle: "मंगल दोष नहीं है", mdNoneText: "मंगल लग्न, चंद्र या शुक्र से पहले, दूसरे, चौथे, सातवें, आठवें या बारहवें भाव में नहीं है।",
      mdCancelTitle: "मंगल दोष है, पर उसे कम करने वाले कारक मौजूद हैं",
      mdCancelText: "तीव्रता: {intensity}। इस कुंडली पर कम से कम एक शास्त्रीय परिहार नियम लागू होता है, इसलिए परंपरा इस दोष को बहुत हल्का मानती है।",
      mdPresentTitle: "मंगल दोष है",
      mdPresentText: "तीव्रता: {intensity}। यह बहुत आम स्थिति है - लगभग आधी कुंडलियों में होती है - और परंपरा में इसके सरल उपाय बताए गए हैं।",
      mdRefs: ["लग्न से", "चंद्र से", "शुक्र से"], mdRefCols: ["गणना", "मंगल का भाव", "दोष बनता है?"],
      houseFmt: "{ord} भाव", mdStatus: "स्थिति", mdManglik: "मांगलिक", mdNotManglik: "मांगलिक नहीं", mdIntensity: "तीव्रता",
      sumMangal: "मंगल दोष", sumSadeSati: "साढ़ेसाती",
      sumMangalActive: "यह विवाह मिलान के लिए मायने रखता है। नीचे का खंड बताता है कि कौन-सा नियम लगता है और कौन-से शास्त्रीय अपवाद जाँचे गए।",
      mdMars: "मंगल", mdLagna: "लग्न", mdWhere: "आपकी कुंडली में मंगल कहाँ है", mdRuleUsed: "प्रयुक्त नियम: {rule}।",
      mdRule: "लग्न, चंद्र और शुक्र से गिनने पर मंगल का पहले, दूसरे, चौथे, सातवें, आठवें या बारहवें भाव (संपूर्ण-राशि) में होना",
      mdCancelHeading: "परिहार के नियम (दोष भंग)", mdApplies: "आपकी कुंडली पर लागू", mdNotApplies: "लागू नहीं",
      mdNotesHeading: "जानने योग्य बातें",
      mdNotes: ["जब वर और वधू दोनों की कुंडली में मंगल दोष हो, तो परंपरा के अनुसार दोनों दोष एक-दूसरे को संतुलित कर देते हैं।",
        "मान्यता है कि 28 वर्ष की आयु के बाद, जब मंगल परिपक्व होता है, मंगल दोष का प्रभाव कम हो जाता है।",
        "लग्न से बनने वाला दोष सबसे प्रबल माना जाता है, उसके बाद चंद्र से और फिर शुक्र से।"],
      ssActiveTitle: "साढ़ेसाती चल रही है: {phase}", ssRuns: "आपकी साढ़ेसाती {start} से {end} तक है।",
      ssPausedTitle: "साढ़ेसाती जारी है (अल्प विराम)",
      ssPausedText: "वक्री गति के कारण शनि कुछ समय के लिए आपकी चंद्र राशि के आसपास की तीन राशियों से बाहर गया है। ",
      ssInactiveTitle: "अभी साढ़ेसाती नहीं है", ssNext: "आपकी अगली साढ़ेसाती {start} को शुरू होगी और {end} को समाप्त होगी।",
      ssRashi: "आपकी राशि (चंद्र राशि)", ssSaturnIn: "शनि अभी इस राशि में है", ssFromMoon: "आपकी चंद्र राशि से {ord}", ssAsOf: "स्थिति की तिथि",
      ssCurrent: "आपकी वर्तमान साढ़ेसाती", ssNextHeading: "आपकी अगली साढ़ेसाती", ssCols: ["चरण", "शनि की राशि", "से", "तक"],
      ssNote: "एक ही चरण एक से अधिक बार दिख सकता है: शनि हर वर्ष वक्री होता है और कभी-कभी कुछ महीनों के लिए पिछली राशि में लौट आता है। तिथियाँ शनि के वास्तविक निरयन गोचर से ली गई हैं।",
      ssPhases: "साढ़ेसाती के तीन चरण",
      gunas: "गुण", percentAria: "{percent} प्रतिशत मिलान", boy: "वर", girl: "वधू", rashiShort: "राशि", nakshatraShort: "नक्षत्र",
      ashtakoota: "अष्टकूट गुण मिलान", kootaCols: ["कूट", "वर", "वधू", "अंक"], total: "कुल",
      nadiBhakoot: "नाड़ी और भकूट दोष", nadiDosha: "नाड़ी दोष", nadiWhy: "जब वर और वधू दोनों की नाड़ी एक ही हो, तब बनता है।",
      bhakootDosha: "भकूट दोष", bhakootWhy: "जब दोनों चंद्र राशियाँ एक-दूसरे से 2-12, 5-9 या 6-8 की स्थिति में हों, तब बनता है।",
      bhakootHere: " यहाँ चंद्र राशियाँ एक-दूसरे से {distance} की स्थिति में हैं।",
      notPresent: "नहीं है", presentCancelled: "है, पर शास्त्रीय अपवाद से निरस्त", present: "है",
      mangalCompare: "मंगल दोष की तुलना", mangalOk: "मंगल दोष: अनुकूल", mangalAttention: "मंगल दोष: ध्यान देने योग्य",
      mangalBoth: "दोनों की कुंडली में मंगल दोष है; परंपरा के अनुसार ये एक-दूसरे को संतुलित कर देते हैं।",
      mangalNeither: "दोनों में से किसी की कुंडली में मंगल दोष नहीं है।",
      mangalOne: "केवल एक की कुंडली में मंगल दोष है। सलाह देने से पहले ज्योतिषी परिहार के नियम और दोनों कुंडलियों का समग्र बल देखते हैं; प्रायः पारंपरिक उपाय सुझाए जाते हैं।",
      intensityLabel: "तीव्रता: ", mitigating: "दोष को कम करने वाले कारक:",
      fromName: "नाम से निकाला गया", conventionNote: "यह अक्षर नामाक्षर की परंपरागत रीति से माना गया है।", syllable: "नाम का अक्षर",
      nameNote: "यह परिणाम दोनों नामों के पहले अक्षर पर आधारित है। जन्म विवरण से किया गया कुंडली मिलान अधिक सटीक होता है और उसमें मंगल दोष की तुलना भी होती है।",
      candidatePrompt: "{who}: इस नाम की शुरुआत एक से अधिक अक्षरों से मानी जा सकती है। सही उच्चारण चुनें:",
      cLagna: "लग्न", cRashi: "राशि (चंद्र राशि)", cNakshatra: "नक्षत्र", cMaha: "महादशा", cAntar: "अंतर्दशा", until: "{date} तक"
    },
    mr: {
      born: "जन्म:", lagna: "लग्न", rashi: "रास (चंद्ररास)", nakshatra: "जन्मनक्षत्र", lord: "स्वामी", pada: "चरण",
      padaCap: "चरण", chartHeading: "लग्नकुंडली (उत्तर भारतीय पद्धत)", chartLabels: "कुंडलीतील अक्षरे", english: "इंग्रजी",
      chartNote: "प्रत्येक स्थानातील अंक हा राशीचा क्रमांक आहे (1 = मेष &hellip; 12 = मीन). वरचा मधला चौकोन हे पहिले स्थान.",
      chartAria: "उत्तर भारतीय पद्धतीची कुंडली. लग्न {lagna}. ग्रहस्थिती खालील तक्त्यात दिली आहे.",
      legendLagna: "लग्न", retrograde: "वक्री", lagnaRow: "लग्न", positions: "ग्रहस्थिती",
      cols: ["ग्रह", "रास", "अंश", "नक्षत्र", "स्थान", "वक्री"], yes: "होय", no: "नाही", always: "नेहमी",
      dasha: "विंशोत्तरी दशा", currentMaha: "सध्याची महादशा", currentAntar: "सध्याची अंतर्दशा",
      balance: "जन्मवेळी शिल्लक दशा", balanceFmt: "{y} वर्षे {m} महिने {d} दिवस शिल्लक", timeline: "महादशांचा क्रम",
      timelineNote: "एखाद्या महादशेवर टॅप केल्यास तिच्या अंतर्दशा दिसतील. पहिली महादशा जन्मापूर्वीच सुरू झाली होती; जन्मवेळी तिचा फक्त वर दाखवलेला शिल्लक भाग उरला होता.",
      asOf: " सध्याची दशा {date} या तारखेनुसार.", yrs: "वर्षे", current: "सध्या", now: "सध्या", antarCols: ["अंतर्दशा", "पासून", "पर्यंत"],
      calc: "गणित: स्विस एफेमेरिस &middot; निरयन राशिचक्र &middot; लाहिरी अयनांश {degrees}&middot; संपूर्ण-रास स्थानपद्धत &middot; मध्यम राहू/केतू.",
      accHeading: "या कुंडलीबद्दल आवर्जून लक्षात घ्या",
      accPlace: "इथे लग्नराशीची संधी जवळ आहे: जन्मस्थळ {place} पासून सुमारे {km}&nbsp;{unit} दूर असते तर लग्न {lagna} ऐवजी " +
        "{adjacent} आले असते. तुमची चंद्ररास, नक्षत्र आणि दशांच्या तारखा जन्मस्थळावर अवलंबून नाहीत.",
      accPlaceHere: "इथे लग्नराशीची संधी जवळ आहे: जन्मस्थळ तुम्ही दिलेल्या ठिकाणापासून सुमारे {km}&nbsp;{unit} दूर असते तर " +
        "लग्न {lagna} ऐवजी {adjacent} आले असते. तुमची चंद्ररास, नक्षत्र आणि दशांच्या तारखा जन्मस्थळावर अवलंबून नाहीत.",
      accKm: "किमी",
      accApprox: "तुम्ही जन्मवेळ अंदाजाने निवडली आहे, त्यामुळे हे तीन भागांत वाचा. तयार पर्यायांमुळे तुम्ही खऱ्या " +
        "वेळेपासून फार तर दीड तास दूर असता, आणि खालचे सगळे त्याच पट्ट्यावर मोजलेले आहे. साडेसाती या पानावरची " +
        "सर्वात स्थिर गोष्ट आहे, तरीही ती पक्की नाही: तो अडीच वर्षांचा शनीचा गोचर असून चंद्रराशीवरून वाचला जातो, " +
        "आणि साधारण दोनशेतल्या एका कुंडलीत तो बदलतो. चंद्ररास स्वतः साधारण चाळिसातल्या एका कुंडलीत बदलते, आणि " +
        "जन्मनक्षत्र अठरापैकी एकात. बाकीच्या गोष्टींवर खरी वेळ मिळेपर्यंत विश्वास ठेवू नका. दीड तासाच्या पट्ट्यात " +
        "लग्न चारपैकी सुमारे तीन कुंडल्यांत बदलते, आणि त्यासोबत लग्नापासून मोजली जाणारी सगळी स्थाने व मंगळ " +
        "दोषाचा निष्कर्षही. दशांच्या तारखाही सरकतात: निम्म्याहून थोड्या कमी कुंडल्यांत त्या वर्षभरापेक्षा जास्त " +
        "हलतात, म्हणजे इथे एका महिन्याची दाखवलेली दशा प्रत्यक्षात दुसऱ्याच महिन्याची असू शकते. इथले काहीही " +
        "तुमच्या जन्मवेळेपासून स्वतंत्र नाही, त्यामुळे नोंदवलेली वेळ मिळाली तर हे पुन्हा काढा.",
      accClock: "या जन्माची गणना त्या काळी प्रचलित असलेल्या वेळेनुसार केली आहे - {era}, आजच्या भारतीय प्रमाणवेळेपेक्षा " +
        "{minutes} मिनिटे {direction}. तुमच्याकडील वेळ आजच्या घड्याळाने लिहिलेली असेल, तर लग्न वेगळे येऊ शकते.",
      accClockPlain: "या जन्माची गणना {offset} नुसार केली आहे, जी आजची भारतीय प्रमाणवेळ नाही. तुमच्याकडील वेळ आजच्या " +
        "घड्याळाने लिहिलेली असेल, तर लग्न वेगळे येऊ शकते.",
      accAhead: "पुढे", accBehind: "मागे",
      accEra: {
        madras_time: "मद्रास वेळ", wartime: "1942-45 मधील युद्धकाळातील वेळ",
        calcutta_local_mean_time: "कलकत्त्याची स्थानिक मध्यम वेळ"
      },
      mdNoneTitle: "मंगळ दोष नाही", mdNoneText: "मंगळ लग्न, चंद्र किंवा शुक्र यांच्यापासून पहिल्या, दुसऱ्या, चौथ्या, सातव्या, आठव्या किंवा बाराव्या स्थानी नाही.",
      mdCancelTitle: "मंगळ दोष आहे, परंतु तो सौम्य करणारे घटक आहेत",
      mdCancelText: "तीव्रता: {intensity}. या कुंडलीला किमान एक शास्त्रीय परिहार नियम लागू होतो, त्यामुळे परंपरेनुसार हा दोष बराच सौम्य मानला जातो.",
      mdPresentTitle: "मंगळ दोष आहे",
      mdPresentText: "तीव्रता: {intensity}. ही स्थिती अगदी सर्वसामान्य आहे - सुमारे निम्म्या कुंडल्यांत ती असते - आणि परंपरेत तिच्यासाठी सोपे उपाय सांगितले आहेत.",
      mdRefs: ["लग्नापासून", "चंद्रापासून", "शुक्रापासून"], mdRefCols: ["कोठून मोजले", "मंगळाचे स्थान", "दोष होतो का?"],
      houseFmt: "{ord} स्थान", mdStatus: "स्थिती", mdManglik: "मांगलिक", mdNotManglik: "मांगलिक नाही", mdIntensity: "तीव्रता",
      sumMangal: "मंगळ दोष", sumSadeSati: "साडेसाती",
      sumMangalActive: "हे विवाह जुळवणीसाठी महत्त्वाचे आहे. खालचा भाग कोणता नियम लागू होतो आणि कोणते शास्त्रीय अपवाद तपासले गेले हे सांगतो.",
      mdMars: "मंगळ", mdLagna: "लग्न", mdWhere: "तुमच्या कुंडलीत मंगळ कोठे आहे", mdRuleUsed: "वापरलेला नियम: {rule}.",
      mdRule: "लग्न, चंद्र आणि शुक्र यांच्यापासून मोजता मंगळ पहिल्या, दुसऱ्या, चौथ्या, सातव्या, आठव्या किंवा बाराव्या स्थानी (संपूर्ण-रास पद्धत) असणे",
      mdCancelHeading: "परिहाराचे नियम (दोषभंग)", mdApplies: "तुमच्या कुंडलीला लागू", mdNotApplies: "लागू नाही",
      mdNotesHeading: "जाणून घ्या",
      mdNotes: ["वधू आणि वर दोघांच्याही कुंडलीत मंगळ दोष असेल, तर परंपरेनुसार ते दोष एकमेकांना संतुलित करतात.",
        "मंगळ 28 व्या वर्षी परिपक्व होतो आणि त्यानंतर मंगळ दोषाचा प्रभाव कमी होतो, अशी पारंपरिक समजूत आहे.",
        "लग्नापासून होणारा दोष सर्वांत प्रबळ मानला जातो, त्यानंतर चंद्रापासून आणि मग शुक्रापासून."],
      ssActiveTitle: "साडेसाती सुरू आहे: {phase}", ssRuns: "तुमची साडेसाती {start} ते {end} या काळात आहे.",
      ssPausedTitle: "साडेसाती सुरू आहे (तात्पुरता विराम)",
      ssPausedText: "वक्री गतीमुळे शनी काही काळासाठी तुमच्या चंद्रराशीभोवतीच्या तीन राशींच्या बाहेर गेला आहे. ",
      ssInactiveTitle: "सध्या साडेसाती नाही", ssNext: "तुमची पुढची साडेसाती {start} रोजी सुरू होईल आणि {end} रोजी संपेल.",
      ssRashi: "तुमची रास (चंद्ररास)", ssSaturnIn: "शनी सध्या या राशीत आहे", ssFromMoon: "तुमच्या चंद्रराशीपासून {ord}", ssAsOf: "स्थितीची तारीख",
      ssCurrent: "तुमची सध्याची साडेसाती", ssNextHeading: "तुमची पुढची साडेसाती", ssCols: ["टप्पा", "शनीची रास", "पासून", "पर्यंत"],
      ssNote: "एकच टप्पा एकापेक्षा जास्त वेळा दिसू शकतो: शनी दरवर्षी वक्री होतो आणि कधीकधी काही महिन्यांसाठी आधीच्या राशीत परत येतो. तारखा शनीच्या प्रत्यक्ष निरयन गोचरावरून घेतल्या आहेत.",
      ssPhases: "साडेसातीचे तीन टप्पे",
      gunas: "गुण", percentAria: "{percent} टक्के गुणमेलन", boy: "वर", girl: "वधू", rashiShort: "रास", nakshatraShort: "नक्षत्र",
      ashtakoota: "अष्टकूट गुणमेलन", kootaCols: ["कूट", "वर", "वधू", "गुण"], total: "एकूण",
      nadiBhakoot: "नाडी आणि भकूट दोष", nadiDosha: "नाडी दोष", nadiWhy: "वधू आणि वर दोघांची नाडी एकच असेल तेव्हा होतो.",
      bhakootDosha: "भकूट दोष", bhakootWhy: "दोघांच्या चंद्रराशी एकमेकींपासून 2-12, 5-9 किंवा 6-8 अशा स्थितीत असतील तेव्हा होतो.",
      bhakootHere: " येथे चंद्रराशी एकमेकींपासून {distance} अशा स्थितीत आहेत.",
      notPresent: "नाही", presentCancelled: "आहे, पण शास्त्रीय अपवादाने रद्द", present: "आहे",
      mangalCompare: "मंगळ दोषाची तुलना", mangalOk: "मंगळ दोष: अनुरूप", mangalAttention: "मंगळ दोष: लक्ष देण्याजोगे",
      mangalBoth: "दोघांच्याही कुंडलीत मंगळ दोष आहे; परंपरेनुसार ते एकमेकांना संतुलित करतात.",
      mangalNeither: "दोघांपैकी कोणाच्याही कुंडलीत मंगळ दोष नाही.",
      mangalOne: "फक्त एकाच्या कुंडलीत मंगळ दोष आहे. सल्ला देण्यापूर्वी ज्योतिषी परिहाराचे नियम आणि दोन्ही कुंडल्यांचे एकंदर बळ पाहतात; बहुधा पारंपरिक उपाय सुचवले जातात.",
      intensityLabel: "तीव्रता: ", mitigating: "दोष सौम्य करणारे घटक:",
      fromName: "नावावरून काढलेले", conventionNote: "हे अक्षर आद्याक्षराच्या पारंपरिक संकेतानुसार धरले आहे.", syllable: "नावाचे अक्षर",
      nameNote: "हा निकाल दोन्ही नावांच्या पहिल्या अक्षरावर आधारित आहे. जन्मतपशिलांवरून केलेली पत्रिका जुळवणी अधिक अचूक असते आणि तिच्यात मंगळ दोषाचीही तुलना होते.",
      candidatePrompt: "{who}: या नावाची सुरुवात एकापेक्षा जास्त अक्षरांनी मानता येते. योग्य उच्चार निवडा:",
      cLagna: "लग्न", cRashi: "रास (चंद्ररास)", cNakshatra: "नक्षत्र", cMaha: "महादशा", cAntar: "अंतर्दशा", until: "{date} पर्यंत"
    }
  };
  var MESSAGES = {
    en: {
      dateMissing: "Please enter the date of birth.", dateInvalid: "Please enter a valid date.",
      dateOld: "Please enter a date after the year 1800.", dateFuture: "The date of birth cannot be in the future.",
      timeMissing: "Please enter the time of birth (an estimate is fine).", timeInvalid: "Please enter a valid time.",
      cityMissing: "Please choose the place of birth from the list.",
      nameMissing: "Please enter the name.", nameLong: "Please keep the name under 60 characters.",
      nameBad: "We could not read this name. Please check the spelling.",
      server: "Something went wrong on our side. Please try again in a moment.",
      rateLimited: "Too many requests. Please wait a minute and try again.",
      generic: "We could not calculate a result from these details. Please check them and try again.",
      cityUnknown: "We could not find this city. Please choose the nearest city from the list.",
      dateBad: "Please enter a valid date of birth.", timeBad: "Please enter a valid time of birth.",
      calculating: "Calculating…",
      // The trust line under the button while the engine works. A STATEMENT about what is being
      // computed, not reassurance - this page runs the ephemeris and nothing interprets anything, so
      // it says so and claims no more. Built on the phrasing each tree already uses for the engine in
      // its own trust line rather than translated out of the English.
      calculatingEngine: "Calculating with the Swiss Ephemeris…", noMatch: "No match - choose the nearest city",
      offline: "Could not reach the server. Please check your connection and try again.",
      comingSoon: "Paid reports are launching soon. Your free result above is complete and yours to keep.",
      // Shown INSTEAD of the ordinary read-back when the year jump supplied the day and month. The echo's
      // worth is that it reports what the visitor did, so it must not claim they entered a date we wrote.
      yearSet: "Year set to {year} - now choose the day and month",
      // The refusal that makes the echo above binding. Written as the NEXT STEP, not as a mistake: nobody
      // did anything wrong by choosing a year first, they simply have not finished. It says what we filled
      // in and why, so the reader can see that the day and month are ours and not theirs.
      confirmDate: "Please confirm your date of birth. We filled 1 January so the picker could open in that year - now set the day and month you were born."
    },
    hi: {
      dateMissing: "कृपया जन्म तिथि भरें।", dateInvalid: "कृपया सही तिथि भरें।",
      dateOld: "कृपया सन् 1800 के बाद की तिथि भरें।", dateFuture: "जन्म तिथि भविष्य की नहीं हो सकती।",
      timeMissing: "कृपया जन्म समय भरें (अनुमानित समय भी चलेगा)।", timeInvalid: "कृपया सही समय भरें।",
      cityMissing: "कृपया सूची से जन्म स्थान चुनें।",
      nameMissing: "कृपया नाम लिखें।", nameLong: "कृपया नाम 60 अक्षरों से छोटा रखें।",
      nameBad: "यह नाम पढ़ा नहीं जा सका। कृपया वर्तनी जाँच लें।",
      server: "हमारी ओर से कुछ गड़बड़ी हुई। कृपया थोड़ी देर बाद फिर कोशिश करें।",
      rateLimited: "बहुत अधिक अनुरोध हो गए। कृपया एक मिनट रुककर फिर कोशिश करें।",
      generic: "इस जानकारी से परिणाम नहीं निकल सका। कृपया जानकारी जाँचकर फिर कोशिश करें।",
      cityUnknown: "यह शहर नहीं मिला। कृपया सूची से सबसे नज़दीकी शहर चुनें।",
      dateBad: "कृपया सही जन्म तिथि भरें।", timeBad: "कृपया सही जन्म समय भरें।",
      calculating: "गणना हो रही है…",
      calculatingEngine: "स्विस एफेमेरिस से गणना हो रही है…", noMatch: "कोई शहर नहीं मिला - नज़दीकी शहर चुनें",
      offline: "सर्वर से संपर्क नहीं हो सका। कृपया इंटरनेट कनेक्शन जाँचकर फिर कोशिश करें।",
      comingSoon: "सशुल्क रिपोर्ट जल्द शुरू हो रही हैं। ऊपर दिया गया मुफ़्त परिणाम पूरा है और आपका ही है।",
      yearSet: "वर्ष {year} चुना गया है - अब दिन और महीना चुनिए",
      confirmDate: "कृपया अपनी जन्म तिथि की पुष्टि कीजिए। अभी सिर्फ़ वर्ष चुना गया है और दिन-महीना 1 जनवरी रखा गया है - अब अपना असली दिन और महीना चुनिए।"
    },
    mr: {
      dateMissing: "कृपया जन्मतारीख भरा.", dateInvalid: "कृपया योग्य तारीख भरा.",
      dateOld: "कृपया 1800 सालानंतरची तारीख भरा.", dateFuture: "जन्मतारीख भविष्यातील असू शकत नाही.",
      timeMissing: "कृपया जन्मवेळ भरा (अंदाजे वेळही चालेल).", timeInvalid: "कृपया योग्य वेळ भरा.",
      cityMissing: "कृपया यादीतून जन्मस्थळ निवडा.",
      nameMissing: "कृपया नाव लिहा.", nameLong: "कृपया नाव 60 अक्षरांपेक्षा लहान ठेवा.",
      nameBad: "हे नाव वाचता आले नाही. कृपया शुद्धलेखन तपासा.",
      server: "आमच्याकडून काहीतरी चूक झाली. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा.",
      rateLimited: "खूप जास्त विनंत्या झाल्या. कृपया एक मिनिट थांबून पुन्हा प्रयत्न करा.",
      generic: "या माहितीवरून निकाल काढता आला नाही. कृपया माहिती तपासून पुन्हा प्रयत्न करा.",
      cityUnknown: "हे शहर सापडले नाही. कृपया यादीतून जवळचे शहर निवडा.",
      dateBad: "कृपया योग्य जन्मतारीख भरा.", timeBad: "कृपया योग्य जन्मवेळ भरा.",
      calculating: "गणित सुरू आहे…",
      calculatingEngine: "स्विस एफेमेरिसने गणित सुरू आहे…", noMatch: "जुळणारे शहर नाही - जवळचे शहर निवडा",
      offline: "सर्व्हरशी संपर्क होऊ शकला नाही. कृपया इंटरनेट जोडणी तपासून पुन्हा प्रयत्न करा.",
      comingSoon: "सशुल्क अहवाल लवकरच सुरू होत आहेत. वरील मोफत निकाल पूर्ण आहे आणि तो तुमचाच आहे.",
      yearSet: "वर्ष {year} निवडले आहे - आता दिवस आणि महिना निवडा",
      confirmDate: "कृपया तुमची जन्मतारीख निश्चित करा. आत्ता फक्त वर्ष निवडले आहे आणि दिवस-महिना 1 जानेवारी ठेवला आहे - आता तुमचा खरा दिवस आणि महिना निवडा."
    }
  };

  function langOf(value) { return value === "mr" || value === "hi" ? value : "en"; }
  function t(key) { return LABELS[LANG][key]; }
  function messages(lang) { return MESSAGES[langOf(lang)]; }
  function fill(template, values) {
    return template.replace(/\{(\w+)\}/g, function (whole, key) { return values[key] === undefined ? "" : values[key]; });
  }
  function withLang(lang, fn) {
    var previous = LANG;
    LANG = langOf(lang);
    try { return fn(); } finally { LANG = previous; }
  }

  /* Names in the render language. Everything returned here is already escaped. */

  /** Graha key ("Jupiter": sign.lord / nakshatra.lord / graha_maitri koota value) -> display name. */
  function lordName(key) { return LANG === "en" ? esc(key) : esc(GRAHA_NAMES[LANG][key] || key); }

  /** Sign object, 1-12 index, English key ("Libra") or Sanskrit name ("Tula") -> Devanagari name in LANG (hi / mr only). */
  function signNative(sign) {
    var index = -1, i;
    if (sign && typeof sign === "object") {
      index = Number(sign.index) - 1;
      if (!(index >= 0 && index < 12)) for (i = 0; i < 12; i++) if (SIGNS[i][1] === sign.key || SIGNS[i][0] === sign.name) index = i;
      return index >= 0 && index < 12 ? SIGN_NAMES[LANG][index] : (sign.devanagari || sign.name || "");
    }
    if (typeof sign === "number") index = sign - 1;
    else for (i = 0; i < 12; i++) if (SIGNS[i][0] === sign || SIGNS[i][1] === sign) index = i;
    return index >= 0 && index < 12 ? SIGN_NAMES[LANG][index] : String(sign === null || sign === undefined ? "" : sign);
  }

  /** The boy / girl cell of a koota row: English words, nakshatra names, graha keys or Sanskrit sign names. */
  function kootaValue(value) {
    if (LANG === "en" || value === null || value === undefined) return esc(value);
    var pair = KOOTA_VALUES[value];
    if (pair) return esc(pair[LANG === "hi" ? 0 : 1]);
    if (GRAHA_NAMES[LANG][value]) return esc(GRAHA_NAMES[LANG][value]);
    if (NAKSHATRAS[value]) return esc(NAKSHATRAS[value]);
    return esc(signNative(value));
  }

  function houseText(n) {
    var number = Number(n);
    if (LANG === "en") return esc(ordinal(number)) + " house";
    return esc(fill(t("houseFmt"), { ord: ORDINALS[LANG][number - 1] || String(n) }));
  }

  /* ---------- small helpers ---------- */

  function esc(value) {
    if (value === null || value === undefined) return "";
    return String(value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function deva(text) {
    return text ? ' <span class="deva" lang="mr">' + esc(text) + "</span>" : "";
  }

  /** "2024-04-08" -> "8 Apr 2024". Parsed by hand: Date() would shift days across timezones. */
  function fmtDate(iso) {
    var m = /^(-?\d{1,6})-(\d{2})-(\d{2})/.exec(iso || "");
    if (!m) return esc(iso);
    return Number(m[3]) + "\u00a0" + (MONTHS_L[LANG] || MONTHS)[Number(m[2]) - 1] + "\u00a0" + m[1]; // no-break spaces: dates never wrap
  }

  /** "18:45:00" -> "6:45 PM" (en) / "\u0936\u093e\u092e 6:45" (hi) / "\u0938\u0902\u0927\u094d\u092f\u093e\u0915\u093e\u0933\u0940 6:45" (mr).
   *
   * This is the ONLY place a birth time is turned into words, and it is deliberately shared between the
   * echo under the time field and the birth line on the result, so the two can never disagree about what
   * was understood. A birth time read as morning when the customer meant evening moves the lagna by six
   * signs and nothing downstream can detect it: every figure is then internally consistent and wrong.
   *
   * hi and mr used to get a bare 24-hour clock here, on the reasoning that there is no AM/PM to translate.
   * That is true and beside the point - those languages say the part of the day instead, and a reader who
   * thinks in \u0936\u093e\u092e 7:30 does not necessarily notice that "07:30" is not it. So they get the part of the day,
   * which is the form the mistake is visible in. */
  /* Each row is [the hour this part of the day STARTS, the word for it]. Four rows, in order; the last
   * wraps past midnight to the first row's hour. To move a boundary, change the number on the row that
   * names the word it belongs to - there is no logic to read.
   *
   * THE TWO TABLES CURRENTLY HOLD THE SAME HOURS, AND THAT IS NOT AN INVARIANT. They are written out twice
   * because Hindi and Marathi are two languages rather than one translated twice - which is the error this
   * very function made one level up, printing a 24-hour clock for both on the grounds that there is no
   * AM/PM to translate. One table with an exception in it would reproduce that at a lower level. Two tables
   * whose values happen to coincide let a reviewer move one language without touching the other, which is
   * exactly what the open questions below need. Do not merge them because they look redundant.
   *
   * TWO BOUNDARIES ARE UNDER NATIVE-SPEAKER REVIEW, and both are one number on one row:
   *   16:00 - is four in the afternoon already \u0936\u093e\u092e / \u0938\u0902\u0927\u094d\u092f\u093e\u0915\u093e\u0933\u0940, or still \u0926\u094b\u092a\u0939\u0930 / \u0926\u0941\u092a\u093e\u0930\u0940? This is the
   *           consequential one, on two counts. It moves four hours of the clock in both trees at once,
   *           AND it is the boundary where being wrong is least likely to be caught: 4pm rendered \u0926\u094b\u092a\u0939\u0930
   *           instead of \u0936\u093e\u092e still reads as a plausible afternoon and nobody blinks, where 7:30pm
   *           rendered \u0930\u093e\u0924 is jarring enough that a reader doubts the page and checks. Most hours behind
   *           it and least chance of detection - which is this echo's own argument turned on itself.
   *   19:00 - should Marathi be \u0930\u093e\u0924\u094d\u0930\u0940 from seven rather than eight? \u0930\u093e\u0924\u094d\u0930\u0940 \u0938\u093e\u0921\u0947\u0938\u093e\u0924 and \u0938\u0902\u0927\u094d\u092f\u093e\u0915\u093e\u0933\u0940
   *           \u0938\u093e\u0921\u0947\u0938\u093e\u0924 are both ordinary, so this is a genuine boundary case rather than a bug.
   *
   * THE OTHER HALF OF THIS LIVES IN PYTHON. app/pdf/blocks.py:time_of_day() renders the birth time for the
   * paid PDF, and it prints a bare 24-hour clock in all three trees - so the PDF and this have disagreed
   * about English for as long as both have existed, and now about hi and mr too. That divergence predates
   * this table and is not a consequence of it. If a day-part is ever added there, these boundaries will
   * exist in two files with nothing connecting them, and that needs a test linking them the way the
   * manifest's theme colour is tied to the stylesheet's. It will not be free: these are a JS data table,
   * so a Python test has to parse this literal to read them. */
  var DAY_PARTS = {
    en: null,
    hi: [[4, "\u0938\u0941\u092c\u0939"], [12, "\u0926\u094b\u092a\u0939\u0930"], [16, "\u0936\u093e\u092e"], [20, "\u0930\u093e\u0924"]],
    mr: [[4, "\u0938\u0915\u093e\u0933\u0940"], [12, "\u0926\u0941\u092a\u093e\u0930\u0940"], [16, "\u0938\u0902\u0927\u094d\u092f\u093e\u0915\u093e\u0933\u0940"], [20, "\u0930\u093e\u0924\u094d\u0930\u0940"]]
  };

  /** The word for the part of the day `hour` falls in, or "" for a language that uses a meridiem. */
  function dayPartWord(lang, hour) {
    var rows = DAY_PARTS[lang];
    if (!rows) return "";
    // Before the first row's hour is the small hours, which belong to the last row - night wraps midnight.
    var word = rows[rows.length - 1][1];
    for (var i = 0; i < rows.length; i++) {
      if (hour >= rows[i][0]) word = rows[i][1];
    }
    return word;
  }

  function fmtTime(hms) {
    var m = /^(\d{1,2}):(\d{2})/.exec(hms || "");
    if (!m) return esc(hms);
    var h = Number(m[1]), twelve = (h % 12 === 0 ? 12 : h % 12) + ":" + m[2];
    var word = dayPartWord(LANG, h);
    // No-break space: a time and the word that qualifies it must never be split across a line, because
    // half of "\u0936\u093e\u092e 7:30", or of "1:15 AM", is a complete and DIFFERENT time.
    if (word) return esc(word) + "\u00a0" + twelve;
    return twelve + "\u00a0" + (h < 12 ? "AM" : "PM");
  }

  function fmtNum(n) {
    return typeof n === "number" ? String(Math.round(n * 10) / 10) : esc(n);
  }

  function ordinal(n) {
    var s = ["th", "st", "nd", "rd"], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }

  /** "Simha (Leo) सिंह" - the English way of showing a sign or a graha object. */
  function trilingual(item) {
    var english = item.key && item.key !== item.name ? ' <span class="muted">(' + esc(item.key) + ")</span>" : "";
    return esc(item.name) + english + deva(item.devanagari);
  }

  /** Sign object -> "Simha (Leo) सिंह" (en) / "सिंह" (hi, mr: तुला vs तूळ) */
  function signLabel(sign) {
    if (!sign) return "";
    return LANG === "en" ? trilingual(sign) : esc(signNative(sign));
  }

  /** Graha object -> "Chandra (Moon) चंद्र" (en) / "मंगल" (hi) / "मंगळ" (mr) */
  function grahaLabel(graha) {
    if (!graha) return "";
    return LANG === "en" ? trilingual(graha) : esc(GRAHA_NAMES[LANG][graha.key] || graha.devanagari || graha.name);
  }

  function nakshatraLabel(nakshatra, pada) {
    if (!nakshatra) return "";
    var text = LANG !== "en" ? esc(nakshatra.devanagari || NAKSHATRAS[nakshatra.name] || nakshatra.name) : esc(nakshatra.name) + deva(nakshatra.devanagari);
    return pada ? text + ' <span class="muted">' + t("pada") + " " + esc(pada) + "</span>" : text;
  }

  function signByIndex(index) {
    var i = (((index - 1) % 12) + 12) % 12, s = SIGNS[i];
    return { index: i + 1, name: s[0], key: s[1], devanagari: s[2] };
  }

  function table(headers, rows, className) {
    var html = '<div class="table-wrap"><table class="' + (className || "") + '"><thead><tr>';
    headers.forEach(function (h) { html += '<th scope="col">' + h + "</th>"; });
    html += "</tr></thead><tbody>";
    rows.forEach(function (row) {
      var cells = row.cells || row;
      html += "<tr" + (row.className ? ' class="' + row.className + '"' : "") + ">";
      cells.forEach(function (cell, i) {
        html += i === 0 ? '<th scope="row">' + cell + "</th>" : "<td>" + cell + "</td>";
      });
      html += "</tr>";
    });
    return html + "</tbody></table></div>";
  }

  function facts(items) {
    var html = '<dl class="facts">';
    items.forEach(function (item) {
      if (!item) return;
      html += '<div class="fact"><dt>' + item[0] + "</dt><dd>" + item[1] + "</dd></div>";
    });
    return html + "</dl>";
  }

  function banner(tone, title, text) {
    return '<div class="banner banner--' + tone + '"><p class="banner__title">' + title + "</p>" +
      (text ? "<p>" + text + "</p>" : "") + "</div>";
  }

  /** "Born 15 Oct 1931, 1:15 AM, Rameswaram" from the API's echoed `input`. */
  function birthLine(input, name) {
    if (!input) return "";
    var parts = [fmtDate(input.date), fmtTime(input.time)];
    if (input.city) parts.push(esc(input.city));
    else if (typeof input.lat === "number") parts.push(esc(input.lat + ", " + input.lon));
    var who = name ? "<strong>" + esc(name) + "</strong> &middot; " : "";
    return '<p class="birth-line">' + who + t("born") + " " + parts.join(", ") +
      (input.timezone ? ' <span class="muted">(' + esc(input.timezone) + ")</span>" : "") + "</p>";
  }

  /* ---------- North Indian (diamond) chart ---------- */

  // Fixed house geometry on a 400x400 square. House 1 is the top-centre diamond, houses run
  // anticlockwise. c = centre for graha text, n = position of the sign number (near the inner
  // corner), per = grahas per text line (side triangles are narrow).
  var HOUSE_LAYOUT = [
    { c: [200, 95], n: [200, 178], per: 3 },   // 1
    { c: [100, 38], n: [100, 84], per: 3 },    // 2
    { c: [40, 100], n: [84, 105], per: 2 },    // 3
    { c: [100, 200], n: [178, 205], per: 3 },  // 4
    { c: [40, 300], n: [84, 305], per: 2 },    // 5
    { c: [100, 366], n: [100, 326], per: 3 },  // 6
    { c: [200, 305], n: [200, 232], per: 3 },  // 7
    { c: [300, 366], n: [300, 326], per: 3 },  // 8
    { c: [360, 300], n: [316, 305], per: 2 },  // 9
    { c: [300, 200], n: [222, 205], per: 3 },  // 10
    { c: [360, 100], n: [316, 105], per: 2 },  // 11
    { c: [300, 38], n: [300, 84], per: 3 }     // 12
  ];

  /**
   * Inline SVG kundali from the /api/chart response. Uses chart.houses (house -> sign + graha keys)
   * and chart.grahas[key].retrograde. script: "en" (Su, Mo...) or "deva" (सू, चं...).
   */
  function chartSvg(chart, script) {
    var abbr = GRAHA_ABBR[script === "deva" ? "deva" : "en"];
    var lineHeight = 19, step = script === "deva" ? 27 : 29;
    var lagnaSign = chart.lagna && chart.lagna.sign ? chart.lagna.sign : {};
    var svg = '<svg class="kundali" viewBox="0 0 400 400" role="img" xmlns="http://www.w3.org/2000/svg" ' +
      'aria-label="' + esc(fill(t("chartAria"), { lagna: LANG !== "en" ? signNative(lagnaSign) : lagnaSign.name })) + '">' +
      '<rect class="kundali__frame" x="1.5" y="1.5" width="397" height="397"/>' +
      '<path class="kundali__lines" d="M1.5 1.5 398.5 398.5M398.5 1.5 1.5 398.5M200 1.5 398.5 200 200 398.5 1.5 200Z"/>';

    (chart.houses || []).forEach(function (house) {
      var layout = HOUSE_LAYOUT[house.house - 1];
      if (!layout) return;
      svg += '<text class="kundali__sign" x="' + layout.n[0] + '" y="' + layout.n[1] + '">' + esc(house.sign.index) + "</text>";

      var items = house.house === 1 ? [{ key: "Lagna", lagna: true }] : [];
      (house.grahas || []).forEach(function (key) {
        var position = chart.grahas[key] || {};
        // Rahu/Ketu are always retrograde (mean node), so the marker would only add clutter.
        items.push({ key: key, retro: !!position.retrograde && key !== "Rahu" && key !== "Ketu" });
      });

      var lines = [];
      for (var i = 0; i < items.length; i += layout.per) lines.push(items.slice(i, i + layout.per));
      var y0 = layout.c[1] - ((lines.length - 1) * lineHeight) / 2 + 5;
      lines.forEach(function (line, row) {
        var x0 = layout.c[0] - ((line.length - 1) * step) / 2;
        line.forEach(function (item, col) {
          svg += '<text class="kundali__graha' + (item.lagna ? " kundali__graha--lagna" : "") + '" x="' +
            (x0 + col * step) + '" y="' + (y0 + row * lineHeight) + '">' + esc(abbr[item.key] || item.key) +
            (item.retro ? '<tspan class="kundali__retro" dy="-6">R</tspan>' : "") + "</text>";
        });
      });
    });
    return svg + "</svg>";
  }

  function chartLegendHtml(script) {
    var abbr = GRAHA_ABBR[script === "deva" ? "deva" : "en"];
    var parts = ["Lagna"].concat(GRAHA_KEYS).map(function (key) {
      return "<span><b>" + esc(abbr[key]) + "</b> " + (key === "Lagna" ? esc(t("legendLagna")) : lordName(key)) + "</span>";
    });
    return '<p class="legend">' + parts.join(" ") + ' <span><b class="kundali-retro-key">R</b> ' + t("retrograde") + "</span></p>";
  }

  /** Exported: app.js redraws the legend when the chart script is toggled. lang: "en" (default) | "hi" | "mr". */
  function chartLegend(script, lang) {
    return withLang(lang, function () { return chartLegendHtml(script); });
  }

  /* ---------- renderers: one per page `renderer` key ---------- */

  function positionRow(label, position, isLagna) {
    var retro = isLagna ? "&ndash;" : position.retrograde
      ? (position.graha && (position.graha.key === "Rahu" || position.graha.key === "Ketu") ? t("always") : t("yes"))
      : t("no");
    return [
      label,
      signLabel(position.sign),
      esc(position.degree_dms),
      nakshatraLabel(position.nakshatra, position.pada),
      isLagna ? "1" : esc(position.house),
      retro
    ];
  }

  function dashaHtml(dasha) {
    if (!dasha || !dasha.mahadashas) return "";
    var current = dasha.current || null;
    var currentKeyStart = current && current.mahadasha ? current.mahadasha.start : null;
    var html = '<section class="block"><h3>' + t("dasha") + "</h3>";

    if (current && current.mahadasha) {
      html += facts([
        [t("currentMaha"), grahaLabel(current.mahadasha.lord) + '<span class="fact__sub">' +
          fmtDate(current.mahadasha.start) + " &ndash; " + fmtDate(current.mahadasha.end) + "</span>"],
        current.antardasha ? [t("currentAntar"), grahaLabel(current.antardasha.lord) + '<span class="fact__sub">' +
          fmtDate(current.antardasha.start) + " &ndash; " + fmtDate(current.antardasha.end) + "</span>"] : null,
        dasha.balance_at_birth ? [t("balance"), grahaLabel(dasha.balance_at_birth.lord) +
          '<span class="fact__sub">' + fill(t("balanceFmt"), { y: esc(dasha.balance_at_birth.years),
            m: esc(dasha.balance_at_birth.months), d: esc(dasha.balance_at_birth.days) }) + "</span>"] : null
      ]);
    }

    html += "<h4>" + t("timeline") + "</h4>" +
      '<p class="muted small">' + t("timelineNote") + (dasha.as_of ? fill(t("asOf"), { date: fmtDate(dasha.as_of) }) : "") + "</p>" +
      '<div class="timeline">';
    dasha.mahadashas.forEach(function (maha) {
      var isCurrent = currentKeyStart !== null && maha.start === currentKeyStart &&
        maha.lord.key === current.mahadasha.lord.key;
      html += '<details class="timeline__item' + (isCurrent ? " is-current" : "") + '"' + (isCurrent ? " open" : "") + ">" +
        "<summary><span class=\"timeline__lord\">" + grahaLabel(maha.lord) + "</span>" +
        '<span class="timeline__dates">' + fmtDate(maha.start) + " &ndash; " + fmtDate(maha.end) +
        ' <span class="muted">(' + esc(maha.years) + " " + t("yrs") + ")</span>" +
        (isCurrent ? ' <span class="badge badge--info">' + t("current") + "</span>" : "") + "</span></summary>";
      var rows = (maha.antardashas || []).map(function (antar) {
        var running = isCurrent && current.antardasha && antar.start === current.antardasha.start &&
          antar.lord.key === current.antardasha.lord.key;
        return {
          className: running ? "is-current" : "",
          cells: [grahaLabel(antar.lord) + (running ? ' <span class="badge badge--info">' + t("now") + "</span>" : ""),
            fmtDate(antar.start), fmtDate(antar.end)]
        };
      });
      html += table(t("antarCols"), rows, "table--compact") + "</details>";
    });
    return html + "</div></section>";
  }

  /** POST /api/chart -> janam kundali. ctx: {name, script, lang}. lang "hi" / "mr" = everything in that language, Devanagari chart by default. */
  /** Sign object -> "Karka" (en) / "कर्क" (hi, mr) - the bare name, for use inside a sentence. */
  function signInline(sign) {
    return LANG === "en" ? esc(sign && sign.name) : esc(signNative(sign));
  }

  var IST_OFFSET_SECONDS = 19800; // +05:30, today's Indian Standard Time

  /** The two caveats the engine flags on `chart.accuracy`, and nothing at all when it flags neither (~94% of charts).
   *
   * Both are about the LAGNA, the only part of a chart that moves with a few km or a few minutes, so they sit under
   * the facts block and say plainly what does NOT move with them. They are deliberately specific: a reader can tell
   * whether their village is 30 km from the city they picked, while "your birthplace may be approximate" is the kind
   * of line people learn to skip. The clock note translates `era` (the key) rather than `era_label` (English prose
   * from the engine), so a Hindi or Marathi page never shows an English clause. */
  /** The ONE caveat surface on a result. `accuracy` is the ENGINE's verdict about a chart (near-cusp lagna,
   *  non-standard clock); `approx` is a statement about the INPUT, which only the caller knows - so it is
   *  passed separately and never folded into chart.accuracy. Both land in the same block so a result never
   *  grows a second competing caveat box, and the approximate-time note prints FIRST, because a three-hour
   *  bucket moves the lagna on every chart where a birthplace rarely does. Same order as the PDF. */
  function accuracyHtml(accuracy, input, lagna, approx) {
    accuracy = accuracy || {};
    var notes = [], boundary = accuracy.lagna_boundary, clock = accuracy.clock;
    if (approx) notes.push(t("accApprox"));

    if (boundary && boundary.sensitive) {
      // two templates rather than one with a substituted phrase: Marathi attaches its postposition to the noun
      // ("ठिकाणापासून"), which a {place} slot cannot do for both a city name and "the place you entered"
      var city = input && input.city;
      notes.push(fill(t(city ? "accPlace" : "accPlaceHere"), {
        km: esc(Math.round(boundary.km_to_change_sign)), unit: t("accKm"), place: esc(city),
        adjacent: signInline(boundary.adjacent_sign), lagna: signInline(lagna && lagna.sign)
      }));
    }
    if (clock && clock.non_standard) {
      var era = (LABELS[LANG].accEra || {})[clock.era] || (LANG === "en" ? clock.era_label : null);
      var offset = Number(clock.offset_seconds) || 0;
      notes.push(era
        ? fill(t("accClock"), {
            era: esc(era), minutes: esc(Math.round(Math.abs(offset - IST_OFFSET_SECONDS) / 60)),
            direction: offset > IST_OFFSET_SECONDS ? t("accAhead") : t("accBehind")
          })
        : fill(t("accClockPlain"), { offset: esc(clock.offset) }));
    }
    if (!notes.length) return "";
    return '<section class="block accuracy"><h3>' + t("accHeading") + "</h3>" +
      notes.map(function (note) { return "<p>" + note + "</p>"; }).join("") + "</section>";
  }

  function kundali(data, ctx) {
    ctx = ctx || {};
    return withLang(ctx.lang, function () { return kundaliHtml(data, ctx); });
  }

  /* The block a chart result opens with: what the visitor came for, in the order they came for it.
   *
   * PROMINENCE AND VALENCE ARE DIFFERENT INSTRUMENTS, and keeping them apart is the whole design here.
   * Position says "this is what you came for". Colour says "this is a finding". They had been conflated,
   * and the cost was visible in both directions: the current mahadasha - plausibly the single thing most
   * visitors arrive to read - sat below the chart and the positions table, while a chip on every fact would
   * have made the chip mean "here is a thing" rather than "here is a finding", at exactly the moment the
   * dosha line needs it to mean the second.
   *
   * So: lagna, rashi, nakshatra and the running mahadasha are FACTS. They are identity and timing, neither
   * good nor bad, and a green chip on "Rashi: Kanya" would assert something about a fact that has nothing
   * to assert. The two items with a verdict get the chips, and they are the only chips.
   *
   * MANGAL DOSHA HAS THREE STATES AND THREE TREATMENTS, and the middle one is the one a later edit gets
   * wrong, because `present` is true in two of them and the field that separates them is a different one.
   * `cancellation_applies` exists precisely because the dosha does not bite, so painting it in caution
   * colours would alarm someone whose chart is fine - the opposite of what the cancellation means.
   *
   * `intensity` is deliberately NOT here. It is a gradation, and a gradation on a caution invites the
   * reader to escalate their own anxiety; "high" is not read neutrally by anyone about their own marriage
   * prospects. It belongs in the section below, beside the rule that produced it.
   *
   * THE WARN CHIP AND ITS SENTENCE ARE EMITTED TOGETHER, by one function, and that is structural rather
   * than tidy: a chip and a nearby paragraph can be separated by a later edit that moves one of them, and
   * a bare caution badge with no statement of what it means is the fear framing this product does not do.
   */
  /* A warn tone with no note is downgraded rather than emitted. The comment above claims the chip and its
   * sentence cannot be separated, and that was true - one function emits both, so no edit can move one and
   * leave the other - but it is NOT the same as saying a bare caution is impossible: this function would
   * emit whatever note it was handed, including none. Those are different guarantees and the stronger one
   * was the one written down. Today nothing can reach it (app/engine/sadesati.py always returns a cycle
   * with a start and an end, so the sade sati note is never empty), but that is a fact about an engine file
   * this renderer does not mention, and a guarantee resting on it is a guarantee resting on a coincidence.
   *
   * WHY A DOWNGRADE AND NOT A THROW. This runs in a customer's browser inside kundaliHtml, so throwing does
   * not surface a loud error beside a chip - it produces no result at all, and someone who has paid gets a
   * blank page where their chart should be. A renderer refusing to render is a customer-facing outage,
   * where the gate refusing to MEASURE is safe because nobody is waiting on it. So the invariant holds in
   * the direction that cannot hurt: the finding is still stated, in words, with its label, and the section
   * below still carries the full reasoning either way. Only the alarm without the explanation is dropped.
   *
   * THE DEGRADATION IS COVERED, NOT ACCEPTED, and the difference is the whole point. On its own this would
   * be a silent fallback: a real caution whose note went missing would be shown calmly and nothing would
   * say so. Two end-to-end tests close that, and they are named here because a comment claiming coverage
   * without naming what provides it is how the gap arose in the first place:
   *     tests/test_tool_flow.py::test_a_real_active_mangal_dosha_reaches_the_page_as_a_caution
   *     tests/test_tool_flow.py::test_a_real_active_sade_sati_reaches_the_page_as_a_caution
   * Each renders a real payload - one the engine reports as manglik, one found by searching for a birth
   * whose sade sati is running today - and asserts the caution tone reaches the page.
   * So an upstream change that empties a note turns a test red rather than a chart quiet, and the case
   * cannot ship. "Silent" was never a property of this function; it was a property of nobody checking. */
  function verdict(tone, label, text, note) {
    var safe = tone === "warn" && !note ? "info" : tone;
    return '<div class="verdict verdict--' + safe + '"><dt>' + label + "</dt><dd>" +
      '<span class="badge badge--' + safe + '">' + text + "</span>" +
      (note ? '<span class="verdict__note">' + note + "</span>" : "") + "</dd></div>";
  }

  function summaryHtml(data) {
    var html = '<dl class="facts result-summary">';
    html += '<div class="fact"><dt>' + t("lagna") + "</dt><dd>" + signLabel(data.lagna.sign) +
      '<span class="fact__sub">' + esc(data.lagna.degree_dms) + "</span></dd></div>";
    html += '<div class="fact"><dt>' + t("rashi") + "</dt><dd>" + signLabel(data.moon_rashi) +
      '<span class="fact__sub">' + t("lord") + ": " + lordName(data.moon_rashi.lord) + "</span></dd></div>";
    html += '<div class="fact"><dt>' + t("nakshatra") + "</dt><dd>" + nakshatraLabel(data.janma_nakshatra) +
      '<span class="fact__sub">' + t("padaCap") + " " + esc(data.janma_nakshatra.pada) + " &middot; " +
      t("lord") + ": " + lordName(data.janma_nakshatra.lord) + "</span></dd></div>";

    var current = data.dasha && data.dasha.current && data.dasha.current.mahadasha;
    if (current) {
      html += '<div class="fact"><dt>' + t("currentMaha") + "</dt><dd>" + grahaLabel(current.lord) +
        '<span class="fact__sub">' + fmtDate(current.start) + " &ndash; " + fmtDate(current.end) +
        "</span></dd></div>";
    }

    var md = data.mangal_dosha;
    if (md) {
      if (!md.present) html += verdict("ok", t("sumMangal"), t("notPresent"), "");
      else if (md.cancellation_applies) html += verdict("info", t("sumMangal"), t("presentCancelled"), "");
      else html += verdict("warn", t("sumMangal"), t("present"), esc(t("sumMangalActive")));
    }

    var ss = data.sade_sati;
    if (ss) {
      if (!ss.active) html += verdict("ok", t("sumSadeSati"), t("ssInactiveTitle"), "");
      else {
        // Warn, matching the existing sade sati page and the palette's own note that an active sade sati
        // is a caution surface. The sentence is the factual one that page already uses - when it runs -
        // rather than anything about what it portends.
        var cycle = ss.cycle || {};
        var phase = (PHASES[LANG] || {})[ss.phase];
        var runs = cycle.start && cycle.end
          ? fill(t("ssRuns"), { start: fmtDate(cycle.start), end: fmtDate(cycle.end) }) : "";
        html += verdict("warn", t("sumSadeSati"), esc(phase ? phase[0] : ss.phase), runs);
      }
    }
    return html + "</dl>";
  }

  function kundaliHtml(data, ctx) {
    ctx = ctx || {};
    var script = ctx.script ? (ctx.script === "deva" ? "deva" : "en") : (LANG !== "en" ? "deva" : "en");
    var html = birthLine(data.input, ctx.name);

    html += summaryHtml(data);

    html += accuracyHtml(data.accuracy, data.input, data.lagna, ctx.approxTime);

    html += '<section class="block chart-block"><h3>' + t("chartHeading") + "</h3>" +
      '<div class="script-toggle" role="group" aria-label="' + t("chartLabels") + '">' +
      '<button type="button" class="chip" data-chart-script="en" aria-pressed="' + (script === "en") + '">' + t("english") + "</button>" +
      '<button type="button" class="chip" data-chart-script="deva" aria-pressed="' + (script === "deva") + '"><span lang="' + (LANG === "hi" ? "hi" : "mr") + '">देवनागरी</span></button>' +
      "</div>" +
      '<div class="chart-holder" id="chart-holder">' + chartSvg(data, script) + chartLegendHtml(script) + "</div>" +
      '<p class="muted small">' + t("chartNote") + "</p></section>";

    var rows = [positionRow(LANG !== "en" ? t("lagnaRow") : "Lagna" + deva("लग्न"), data.lagna, true)];
    GRAHA_KEYS.forEach(function (key) {
      var position = data.grahas[key];
      if (position) rows.push(positionRow(grahaLabel(position.graha), position, false));
    });
    html += '<section class="block"><h3>' + t("positions") + "</h3>" +
      table(t("cols"), rows, "table--positions") + "</section>";

    html += dashaHtml(data.dasha);

    if (data.meta) {
      html += '<p class="muted small calc-note">' + fill(t("calc"), {
        zodiac: esc(data.meta.zodiac), ayanamsa: esc(data.meta.ayanamsa && data.meta.ayanamsa.name),
        degrees: data.meta.ayanamsa ? esc(Number(data.meta.ayanamsa.degrees).toFixed(4)) + "&deg; " : ""
      }) + "</p>";
    }
    return html;
  }

  /** Body of a mangal dosha result (shared by the mangal dosha page and the matching page). */
  function mangalStatus(dosha) {
    if (!dosha.present) return { tone: "ok", title: t("mdNoneTitle"), text: t("mdNoneText") };
    var intensity = esc(INTENSITY[LANG][dosha.intensity] || dosha.intensity);
    if (dosha.cancellation_applies) {
      return { tone: "info", title: t("mdCancelTitle"), text: fill(t("mdCancelText"), { intensity: intensity }) };
    }
    return { tone: "warn", title: t("mdPresentTitle"), text: fill(t("mdPresentText"), { intensity: intensity }) };
  }

  function mangalReferences(dosha) {
    var labels = t("mdRefs"), refs = [[labels[0], dosha.from_lagna], [labels[1], dosha.from_moon], [labels[2], dosha.from_venus]];
    return table(t("mdRefCols"), refs.map(function (ref) {
      var info = ref[1] || {};
      return {
        className: info.dosha ? "is-flagged" : "",
        cells: [ref[0], houseText(info.mars_house),
          info.dosha ? '<span class="badge badge--warn">' + t("yes") + "</span>" : '<span class="badge badge--ok">' + t("no") + "</span>"]
      };
    }), "table--compact");
  }

  /** A cancellation rule's text: the API's English description, or our hi / mr wording of the same rule (by `key`). */
  function cancellationText(rule) {
    return esc((LANG !== "en" && CANCELLATIONS[LANG][rule.key]) || rule.description);
  }

  /** POST /api/mangal-dosha. ctx: {name, lang} */
  function mangalDosha(data, ctx) {
    ctx = ctx || {};
    return withLang(ctx.lang, function () { return mangalDoshaHtml(data, ctx); });
  }

  function mangalDoshaHtml(data, ctx) {
    var dosha = data.mangal_dosha, status = mangalStatus(dosha);
    var html = birthLine(data.input, ctx.name) + banner(status.tone, status.title, status.text) +
      accuracyHtml(data.accuracy, data.input, data.lagna, ctx.approxTime);

    html += facts([
      [t("mdStatus"), dosha.present ? t("mdManglik") : t("mdNotManglik")],
      [t("mdIntensity"), esc(INTENSITY[LANG][dosha.intensity] || dosha.intensity)],
      [LANG === "en" ? t("mdMars") + deva(data.mars && data.mars.graha && data.mars.graha.devanagari) : t("mdMars"),
        signLabel(data.mars.sign) + '<span class="fact__sub">' + esc(data.mars.degree_dms) + " &middot; " +
        nakshatraLabel(data.mars.nakshatra, data.mars.pada) + (data.mars.retrograde ? " &middot; " + t("retrograde") : "") + "</span>"],
      [t("mdLagna"), signLabel(data.lagna.sign)],
      [t("rashi"), signLabel(data.moon_rashi)]
    ]);

    html += '<section class="block"><h3>' + t("mdWhere") + "</h3>" + mangalReferences(dosha) +
      '<p class="muted small">' + fill(t("mdRuleUsed"), { rule: LANG === "en" ? esc(dosha.rule) : esc(t("mdRule")) }) + "</p></section>";

    // Cancellation rules only mean something when the dosha is present ("applies" with no dosha would confuse).
    if (dosha.present) {
      html += '<section class="block"><h3>' + t("mdCancelHeading") + '</h3><ul class="checks">';
      (dosha.cancellations || []).forEach(function (rule) {
        html += '<li class="' + (rule.applies ? "check check--yes" : "check check--no") + '">' +
          '<span class="check__mark" aria-hidden="true">' + (rule.applies ? "&#10003;" : "&ndash;") + "</span>" +
          "<span>" + cancellationText(rule) + ' <span class="badge ' + (rule.applies ? "badge--ok" : "badge--muted") + '">' +
          (rule.applies ? t("mdApplies") : t("mdNotApplies")) + "</span></span></li>";
      });
      html += "</ul></section>";
    }

    // The API's notes are English sentences; hi / mr print their own fixed wording of the same three notes.
    var notes = dosha.notes && dosha.notes.length ? (LANG === "en" ? dosha.notes : t("mdNotes")) : [];
    if (notes.length) {
      html += '<section class="block"><h3>' + t("mdNotesHeading") + "</h3><ul>";
      notes.forEach(function (note) { html += "<li>" + esc(note) + "</li>"; });
      html += "</ul></section>";
    }
    return html;
  }

  /** POST /api/sade-sati. ctx: {name, lang} */
  function sadeSati(data, ctx) {
    ctx = ctx || {};
    return withLang(ctx.lang, function () { return sadeSatiHtml(data, ctx); });
  }

  function sadeSatiHtml(data, ctx) {
    var phases = PHASES[LANG];
    var ss = data.sade_sati, cycle = ss.cycle || {}, phase = phases[ss.phase];
    var running = cycle.which === "current";
    var html = birthLine(data.input, ctx.name) +
      accuracyHtml(data.accuracy, data.input, null, ctx.approxTime);
    var runs = fill(t("ssRuns"), { start: fmtDate(cycle.start), end: fmtDate(cycle.end) });

    // Brand rule: an ACTIVE sade sati is a caution indicator, so it takes the Warning tone - not the
    // neutral info tone it used to share with "cycle running, Saturn temporarily elsewhere", which is not active.
    if (ss.active && phase) {
      html += banner("warn", fill(t("ssActiveTitle"), { phase: esc(phase[0].toLowerCase()) }), esc(phase[1]) + (LANG === "hi" ? "। " : ". ") + runs);
    } else if (running) {
      html += banner("info", t("ssPausedTitle"), t("ssPausedText") + runs);
    } else {
      html += banner("ok", t("ssInactiveTitle"), fill(t("ssNext"), { start: fmtDate(cycle.start), end: fmtDate(cycle.end) }));
    }

    html += facts([
      [t("ssRashi"), signLabel(ss.moon_sign)],
      data.janma_nakshatra ? [t("nakshatra"), nakshatraLabel(data.janma_nakshatra, data.janma_nakshatra.pada)] : null,
      [t("ssSaturnIn"), signLabel(ss.saturn_sign) + '<span class="fact__sub">' +
        fill(t("ssFromMoon"), { ord: LANG === "en" ? esc(ordinal(ss.saturn_house_from_moon)) : houseText(ss.saturn_house_from_moon) }) + "</span>"],
      [t("ssAsOf"), fmtDate(ss.as_of)]
    ]);

    var rows = (cycle.periods || []).map(function (period) {
      var info = phases[period.phase] || [period.phase, "", 0];
      var now = ss.as_of >= period.start && ss.as_of < period.end;
      return {
        className: now ? "is-current" : "",
        cells: [esc(info[0]) + (now ? ' <span class="badge badge--info">' + t("now") + "</span>" : ""),
          signLabel(signByIndex(ss.moon_sign.index + info[2])), fmtDate(period.start), fmtDate(period.end)]
      };
    });
    html += '<section class="block"><h3>' + (running ? t("ssCurrent") : t("ssNextHeading")) + "</h3>" +
      "<p>" + fmtDate(cycle.start) + " &ndash; " + fmtDate(cycle.end) + "</p>" +
      table(t("ssCols"), rows, "table--compact") +
      '<p class="muted small">' + esc(t("ssNote")) + "</p></section>";

    html += '<section class="block"><h3>' + t("ssPhases") + "</h3><ul>";
    ["rising", "peak", "setting"].forEach(function (key) {
      html += "<li><strong>" + esc(phases[key][0]) + "</strong> &ndash; " + esc(phases[key][1]) + (LANG === "hi" ? "।" : ".") + "</li>";
    });
    return html + "</ul></section>";
  }

  /** One partner of a match. Birth-details mode prints the birth line; name mode prints what the name gave. */
  function personSummary(label, person, name, byName, who) {
    person = person || {};
    var match = person.name_match || {}, input = person.input || {};
    var shown = name || person.name || (byName ? input.name : "");
    var html = '<div class="person-card"><h4>' + esc(label) + (shown ? ": " + esc(shown) : "") + "</h4>";
    if (!byName && person.input) html += birthLine(person.input);
    else {
      var syllable = match.syllable || person.syllable;
      html += '<p class="muted small">' + t("fromName") + "</p>";
      if (syllable) {
        html += '<p><span class="muted">' + t("syllable") + "</span> <strong>" + esc(syllable) + "</strong>" +
          (match.latin ? ' <span class="muted">(' + esc(match.latin) + ")</span>" : "") + "</p>";
      }
    }
    if (byName && (match.confidence === "convention" || match.confidence === "ambiguous") && (match.rules || []).length) {
      // the API's rule texts are English; other languages get a one-line note instead
      html += '<p class="muted small">' + esc(t("conventionNote")) + (LANG === "en" ? " " + match.rules.map(esc).join("; ") + "." : "") + "</p>";
    }
    var sign = person.moon_sign || person.sign || person.rashi, nakshatra = person.moon_nakshatra || person.nakshatra;
    html += '<p><span class="muted">' + t("rashiShort") + "</span> " + signLabel(sign) + "<br>" +
      '<span class="muted">' + t("nakshatraShort") + "</span> " + nakshatraLabel(nakshatra, person.pada || (nakshatra && nakshatra.pada)) + "</p>";
    // Ambiguous first sound (Latin t = त / ट ...): the API used the first reading; offer the others (docs/API.md).
    if (byName && (match.confidence === "ambiguous" || match.confidence === "chosen") && (match.candidates || []).length > 1) {
      html += candidatesInner(who, match.candidates, match.syllable);
    }
    return html + "</div>";
  }

  function doshaLine(label, dosha, explanation) {
    if (!dosha) return "";
    var badge = !dosha.present ? '<span class="badge badge--ok">' + t("notPresent") + "</span>"
      : dosha.cancellation_applies ? '<span class="badge badge--info">' + t("presentCancelled") + "</span>"
      : '<span class="badge badge--warn">' + t("present") + "</span>";
    return "<li><strong>" + label + "</strong> " + badge + '<br><span class="muted small">' + explanation + "</span></li>";
  }

  /** POST /api/matching (birth details or names). ctx: {names: {boy, girl}, lang} */
  function matching(data, ctx) {
    ctx = ctx || {};
    return withLang(ctx.lang, function () { return matchingHtml(data, ctx); });
  }

  function matchingHtml(data, ctx) {
    var names = ctx.names || {};
    var byName = data.basis === "name" || data.mode === "name" || !(data.boy && data.boy.input) || !(data.girl && data.girl.input);
    var range = byName && data.total_range && data.total_range[0] !== data.total_range[1]
      ? ' <span class="score__unit">(' + fmtNum(data.total_range[0]) + "&ndash;" + fmtNum(data.total_range[1]) + ")</span>" : "";
    var verdict = VERDICTS[LANG][data.verdict] || [esc(data.verdict), "", "info"];
    var percent = Math.max(0, Math.min(100, Number(data.percentage) || 0));

    var html = '<div class="score score--' + verdict[2] + '">' +
      '<p class="score__value"><span class="score__total">' + fmtNum(data.total) + "</span> / " + fmtNum(data.max_total) +
      ' <span class="score__unit">' + t("gunas") + "</span>" + range + "</p>" +
      '<div class="meter" role="img" aria-label="' + esc(fill(t("percentAria"), { percent: fmtNum(percent) })) + '"><span style="width:' + percent + '%"></span></div>' +
      '<p class="score__verdict"><strong>' + fmtNum(data.percentage) + "% &middot; " + verdict[0] + "</strong></p>" +
      "<p>" + verdict[1] + "</p></div>";

    html += accuracyHtml(null, null, null, ctx.approxTime);
    html += '<div class="people">' + personSummary(t("boy"), data.boy, names.boy, byName, "boy") +
      personSummary(t("girl"), data.girl, names.girl, byName, "girl") + "</div>";
    if (byName) html += '<p class="banner banner--info name-note">' + esc(t("nameNote")) + "</p>";

    var rows = (data.kootas || []).map(function (k) {
      var label = LANG === "en" ? (KOOTA_LABELS[k.koota] || [k.koota, "", ""]) : null;
      var local = LANG !== "en" ? (KOOTA_LABELS_L[LANG][k.koota] || [k.koota, ""]) : null;
      return {
        className: k.score === 0 ? "is-flagged" : "",
        cells: [(label ? esc(label[0]) + deva(label[1]) + '<span class="cell-sub">' + esc(label[2]) + "</span>"
          : esc(local[0]) + '<span class="cell-sub">' + esc(local[1]) + "</span>"),
          kootaValue(k.boy), kootaValue(k.girl), "<strong>" + fmtNum(k.score) + "</strong> / " + fmtNum(k.max)]
      };
    });
    rows.push({ className: "is-total", cells: [t("total"), "", "", "<strong>" + fmtNum(data.total) + "</strong> / " + fmtNum(data.max_total)] });
    html += '<section class="block"><h3>' + t("ashtakoota") + "</h3>" +
      table(t("kootaCols"), rows, "table--kootas") + "</section>";

    var doshas = data.doshas || {};
    if (doshas.nadi_dosha || doshas.bhakoot_dosha) {
      html += '<section class="block"><h3>' + t("nadiBhakoot") + '</h3><ul class="plain">' +
        doshaLine(t("nadiDosha"), doshas.nadi_dosha, t("nadiWhy")) +
        doshaLine(t("bhakootDosha"), doshas.bhakoot_dosha, t("bhakootWhy") +
          (doshas.bhakoot_dosha && doshas.bhakoot_dosha.sign_distance
            ? fill(t("bhakootHere"), { distance: esc(doshas.bhakoot_dosha.sign_distance.join("-")) }) : "")) +
        "</ul></section>";
    }

    var mangal = data.mangal_dosha;
    if (!mangal) return html; // name mode: a name says nothing about Mars
    html += '<section class="block"><h3>' + t("mangalCompare") + "</h3>" +
      banner(mangal.compatible ? "ok" : "warn",
        mangal.compatible ? t("mangalOk") : t("mangalAttention"),
        mangal.compatible ? (mangal.boy && mangal.boy.present ? t("mangalBoth") : t("mangalNeither")) : t("mangalOne")) +
      '<div class="people">';
    [[t("boy"), mangal.boy, names.boy], [t("girl"), mangal.girl, names.girl]].forEach(function (entry) {
      var dosha = entry[1];
      if (!dosha) return;
      var status = mangalStatus(dosha);
      var applied = (dosha.cancellations || []).filter(function (rule) { return rule.applies; });
      html += '<div class="person-card"><h4>' + entry[0] + (entry[2] ? ": " + esc(entry[2]) : "") + "</h4>" +
        '<p><span class="badge badge--' + status.tone + '">' + status.title + "</span>" +
        (dosha.present ? ' <span class="muted">' + t("intensityLabel") + esc(INTENSITY[LANG][dosha.intensity] || dosha.intensity) + "</span>" : "") + "</p>" +
        mangalReferences(dosha);
      if (dosha.present && applied.length) {
        html += '<p class="small"><strong>' + t("mitigating") + '</strong></p><ul class="small">';
        applied.forEach(function (rule) { html += "<li>" + cancellationText(rule) + "</li>"; });
        html += "</ul>";
      }
      html += "</div>";
    });
    return html + "</div></section>";
  }

  /**
   * Matching by name: picker for a name whose first sound fits more than one naming syllable.
   * person: "boy" | "girl"; candidates: [{syllable, nakshatra: {...}, pada, sign: {...}}] (every field optional).
   * app.js listens for clicks on [data-name-candidate] and resubmits with the chosen candidate (data-index).
   */
  function candidatesHtml(person, candidates, lang, current) {
    return withLang(lang, function () { return candidatesInner(person, candidates, current); });
  }

  function candidatesInner(person, candidates, current) {
    {
      var who = person === "girl" ? t("girl") : t("boy");
      var html = '<div class="name-candidates" data-person="' + esc(person) + '"><p>' +
        esc(fill(t("candidatePrompt"), { who: who })) + '</p><ul class="chip-list">';
      (candidates || []).forEach(function (candidate, index) {
        candidate = candidate || {};
        var sign = candidate.sign || candidate.moon_sign || candidate.rashi, nakshatra = candidate.nakshatra || candidate.moon_nakshatra;
        var details = [];
        if (nakshatra) details.push(nakshatraLabel(nakshatra, candidate.pada));
        if (sign) details.push(signLabel(sign));
        html += '<li><button type="button" class="chip" data-name-candidate data-person="' + esc(person) + '" data-index="' + index + '"' +
          ' aria-pressed="' + (current !== undefined && current !== null && candidate.syllable === current) + '"' +
          (candidate.syllable ? ' data-syllable="' + esc(candidate.syllable) + '"' : "") + ">" +
          (candidate.syllable ? "<strong>" + esc(candidate.syllable) + "</strong>" : "<strong>" + (index + 1) + "</strong>") +
          (details.length ? ' <span class="muted">' + details.join(" &middot; ") + "</span>" : "") + "</button></li>";
      });
      return html + "</ul></div>";
    }
  }

  /* ---------- AI consultation: compact chart header above the chat ---------- */

  /** data = POST /api/consultation/start response ({summary: {input, lagna, moon_rashi, janma_nakshatra, dasha}}). ctx: {name, lang} */
  function consultation(data, ctx) {
    ctx = ctx || {};
    return withLang(ctx.lang, function () { return consultationHtml(data, ctx); });
  }

  function consultationHtml(data, ctx) {
    var s = (data && data.summary) || {}, dasha = s.dasha || {};
    function period(p) {
      return p ? grahaLabel(p.lord) + '<span class="fact__sub">' + fill(t("until"), { date: fmtDate(p.end) }) + "</span>" : "";
    }
    return birthLine(s.input, ctx.name || (data && data.name)) + facts([
      s.lagna ? [t("cLagna"), signLabel(s.lagna.sign)] : null,
      s.moon_rashi ? [t("cRashi"), signLabel(s.moon_rashi)] : null,
      s.janma_nakshatra ? [t("cNakshatra"), nakshatraLabel(s.janma_nakshatra, s.janma_nakshatra.pada)] : null,
      dasha.mahadasha ? [t("cMaha"), period(dasha.mahadasha)] : null,
      dasha.antardasha ? [t("cAntar"), period(dasha.antardasha)] : null
    ]);
  }

  /* ---------- request + error helpers (pure, used by app.js) ---------- */

  /** Form values -> the JSON body the API expects. values: {self|boy|girl: {date, time, city}} */
  function buildPayload(formType, values) {
    function details(person) {
      return { date: person.date, time: person.time, city: (person.city || "").trim() };
    }
    return formType === "pair" ? { boy: details(values.boy), girl: details(values.girl) } : details(values.self);
  }

  /** Client-side checks. Returns [{person, field, message}], empty when valid. today: "YYYY-MM-DD". */
  function validate(formType, values, today, lang) {
    var errors = [], M = messages(lang);
    (formType === "pair" ? ["boy", "girl"] : ["self"]).forEach(function (person) {
      var v = values[person] || {};
      if (!v.date) errors.push({ person: person, field: "date", message: M.dateMissing });
      else if (!/^\d{4}-\d{2}-\d{2}$/.test(v.date)) errors.push({ person: person, field: "date", message: M.dateInvalid });
      else if (v.date < "1800-01-01") errors.push({ person: person, field: "date", message: M.dateOld });
      else if (today && v.date > today) errors.push({ person: person, field: "date", message: M.dateFuture });
      if (!v.time) errors.push({ person: person, field: "time", message: M.timeMissing });
      else if (!/^\d{2}:\d{2}(:\d{2})?$/.test(v.time)) errors.push({ person: person, field: "time", message: M.timeInvalid });
      if (!(v.city || "").trim()) errors.push({ person: person, field: "city", message: M.cityMissing });
    });
    return errors;
  }

  /* Matching by name. Contract: docs/API.md, POST /api/matching "By-name mode"; app.js only ever goes through these two. */

  /** values: {boy: {name}, girl: {name}} -> POST /api/matching body in name mode (docs/API.md "By-name mode").
   *  choices: optional {boy|girl: candidate} - the syllable the visitor picked for an ambiguous first sound. */
  function buildNamePayload(values, choices) {
    function person(key) {
      var body = { name: String((values[key] && values[key].name) || "").trim() };
      var choice = choices && choices[key];
      if (choice && choice.syllable) body.syllable = choice.syllable;
      return body;
    }
    return { mode: "name", boy: person("boy"), girl: person("girl") };
  }

  /** Both names are required, at most 60 characters. Returns [{person, field: "name", message}]. */
  function validateNames(values, lang) {
    var errors = [], M = messages(lang);
    ["boy", "girl"].forEach(function (person) {
      var name = String(((values || {})[person] || {}).name || "").trim();
      if (!name) errors.push({ person: person, field: "name", message: M.nameMissing });
      else if (name.length > 60) errors.push({ person: person, field: "name", message: M.nameLong });
    });
    return errors;
  }

  /**
   * FastAPI error body -> [{person, field, message}]. `detail` is a list of {loc, msg} for
   * validation errors (422) or a plain string. field/person are null for a general error.
   */
  function parseApiError(status, body, formType, lang) {
    var M = messages(lang);
    var fallback = [{ person: null, field: null, message: status >= 500 ? M.server : M.generic }];
    if (!body || body.detail === undefined) return fallback;
    var english = langOf(lang) === "en"; // the API's own wording is English: other languages get our generic text
    var general = status === 429 ? M.rateLimited : status >= 500 ? M.server : M.generic;
    if (typeof body.detail === "string") return [{ person: null, field: null, message: english ? body.detail : general }];
    if (!Array.isArray(body.detail) && body.detail.error === "name_unreadable") { // by-name matching: {error, who, message}
      var who = body.detail.who === "girl" ? "girl" : body.detail.who === "boy" ? "boy" : null;
      return [{ person: who, field: who ? "name" : null, message: english && body.detail.message ? body.detail.message : M.nameBad }];
    }
    if (!Array.isArray(body.detail) && typeof body.detail.message === "string") {
      return [{ person: null, field: null, message: english ? body.detail.message : general }];
    }
    if (!Array.isArray(body.detail) || !body.detail.length) return fallback;
    return body.detail.map(function (item) {
      var loc = (item.loc || []).map(String), msg = String(item.msg || "").replace(/^Value error,\s*/i, "");
      var person = formType === "pair" ? (loc.indexOf("boy") >= 0 ? "boy" : loc.indexOf("girl") >= 0 ? "girl" : null) : "self";
      var last = loc[loc.length - 1], field = ["date", "time", "city", "name"].indexOf(last) >= 0 ? last : null;
      if (!field && /city|lat/i.test(msg)) field = "city";
      var message = msg;
      if (field === "city") message = M.cityUnknown;
      else if (field === "date") message = M.dateBad;
      else if (field === "time") message = M.timeBad;
      else if (field === "name" && !english) message = M.nameBad;
      else if (!english) message = M.generic;
      if (!person) field = null;
      return { person: field ? person : null, field: field, message: message.charAt(0).toUpperCase() + message.slice(1) };
    });
  }

  /** Cities matching a typed query: name prefix first, then name substring, then state. */
  function filterCities(cities, query, limit) {
    var q = (query || "").trim().toLowerCase(), max = limit || 50;
    if (!q) return cities.slice(0, max);
    var starts = [], contains = [], state = [];
    cities.forEach(function (city) {
      var name = city.name.toLowerCase();
      if (name.indexOf(q) === 0) starts.push(city);
      else if (name.indexOf(q) > 0) contains.push(city);
      else if ((city.state || "").toLowerCase().indexOf(q) === 0) state.push(city);
    });
    return starts.concat(contains, state).slice(0, max);
  }

  root.AstroRender = {
    renderers: { kundali: kundali, matching: matching, mangalDosha: mangalDosha, sadeSati: sadeSati, consultation: consultation },
    chartSvg: chartSvg,
    chartLegend: chartLegend,
    verdict: verdict,
    candidatesHtml: candidatesHtml,
    langOf: langOf,
    messages: messages,
    buildPayload: buildPayload,
    buildNamePayload: buildNamePayload,
    validate: validate,
    validateNames: validateNames,
    parseApiError: parseApiError,
    filterCities: filterCities,
    esc: esc,
    withLang: withLang,
    fmtDate: fmtDate,
    fmtTime: fmtTime,
    dayPartWord: dayPartWord
  };
})(typeof window !== "undefined" ? window : globalThis);
