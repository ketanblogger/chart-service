"""The fixed wording of the mantra pages: labels, titles, meta, and the E-E-A-T block.

EVERY STRING HERE IS WRITTEN, NOT GENERATED. The model writes the explainer; the furniture around
it - what the download button says, how the sources are credited, what the byline claims - is ours
and is the same on every page, which is the only way a reader can learn to trust it.

THE PRIMARY KEYWORD IS THE TEXT'S OWN NAME, and the brief requires it in the title, the H1, the
slug, the first hundred words, at least one H2 and the meta description. The templates place it;
tests/test_mantra_pages.py checks every page for all six.
"""
from __future__ import annotations

#: The one-line claim about who stands behind the page. NEVER A CREDENTIAL WE DO NOT HAVE: no
#: "reviewed by a Sanskrit scholar", no named pandit, no degree. What is true is that the text was
#: taken from a named source, checked against a second, and read by the person who runs the site.
BYLINE = {
    "en": "Written and reviewed by the RashiKundli Editorial Team",
    # The brand stays in Latin in the Hindi tree, as it does everywhere else on the site - the first
    # draft of this line had it half-transliterated, "रashiकुंडली", which is not a word in either
    # script.
    "hi": "RashiKundli संपादकीय टीम द्वारा लिखित और समीक्षित",
}

WORDS = {
    "en": {
        "download": "Download free PDF",
        "download_note": "No sign-up. Printable, with the full text.",
        "text_heading": "{name}: full text",
        "translit_heading": "{name} in English letters",
        "meaning_heading": "What {name} means, verse by verse",
        "recitation_heading": "How and when {name} is recited",
        "tradition_heading": "What the tradition says",
        "faq_heading": "Questions people ask about {name}",
        "related_heading": "Related texts",
        "sources_heading": "Where this text comes from",
        "source_label": "Source",
        "checked_label": "Checked against",
        "author_label": "Author and period",
        "updated_label": "Last updated",
        "verses_label": "{count} verses",
        "about": "About RashiKundli",
        "disclaimer": "Disclaimer",
        "hub_h1": "Mantras, chalisas, aartis and stotras",
        "hub_title": "Mantra, Chalisa and Aarti Lyrics in Hindi with Free PDF",
        "hub_lede": ("The full text of each one in Devanagari, a free printable PDF, the verse in "
                     "English letters, and what each part is saying. Nothing here is "
                     "machine-translated scripture: every text is taken from a named source and "
                     "checked against a second."),
        "hub_meta": ("Full text of Hanuman Chalisa, Shiv Chalisa, Durga Chalisa, Gayatri Mantra "
                     "and more in Hindi, with free PDF downloads and verse-by-verse meaning."),
        "transliteration_note": ("Written to be read aloud rather than to mark vowel length, so "
                                 "there are no dots or dashes over the letters."),
        "kinds": {"chalisa": "Chalisa", "stotra": "Stotra", "aarti": "Aarti",
                  "mantra": "Mantra", "sahasranamam": "Sahasranamam"},
    },
    "hi": {
        "download": "मुफ़्त PDF डाउनलोड करें",
        "download_note": "कोई साइन-अप नहीं। पूरा पाठ, प्रिंट करने योग्य।",
        "text_heading": "{name} - पूरा पाठ",
        "translit_heading": "{name} रोमन अक्षरों में",
        "meaning_heading": "{name} का अर्थ, चौपाई दर चौपाई",
        "recitation_heading": "{name} का पाठ कब और कैसे किया जाता है",
        "tradition_heading": "परंपरा क्या कहती है",
        "faq_heading": "{name} के बारे में पूछे जाने वाले प्रश्न",
        "related_heading": "संबंधित पाठ",
        "sources_heading": "यह पाठ कहाँ से लिया गया है",
        "source_label": "स्रोत",
        "checked_label": "मिलान किया गया",
        "author_label": "रचनाकार और काल",
        "updated_label": "अंतिम अद्यतन",
        "verses_label": "{count} पंक्तियाँ",
        "about": "हमारे बारे में",
        "disclaimer": "अस्वीकरण",
        "hub_h1": "मंत्र, चालीसा, आरती और स्तोत्र",
        "hub_title": "मंत्र, चालीसा और आरती - Lyrics और मुफ़्त PDF",
        "hub_lede": ("हर पाठ देवनागरी में पूरा, मुफ़्त प्रिंट करने योग्य PDF, रोमन अक्षरों में "
                     "पाठ, और हर भाग का अर्थ। यहाँ कोई पाठ मशीन से अनूदित नहीं है: हर पाठ एक "
                     "नामित स्रोत से लिया गया है और दूसरे स्रोत से मिलाया गया है।"),
        "hub_meta": ("हनुमान चालीसा, शिव चालीसा, दुर्गा चालीसा, गायत्री मंत्र और अन्य पाठ हिंदी "
                     "में पूरे, मुफ़्त PDF और अर्थ सहित।"),
        "transliteration_note": ("यह रोमन लिप्यंतरण पढ़कर बोलने के लिए है, स्वर की लंबाई दिखाने "
                                 "के लिए नहीं, इसलिए अक्षरों पर कोई चिह्न नहीं लगाए गए हैं।"),
        "kinds": {"chalisa": "चालीसा", "stotra": "स्तोत्र", "aarti": "आरती",
                  "mantra": "मंत्र", "sahasranamam": "सहस्रनाम"},
    },
}

#: The page title and meta description per text, built from its own name. THE BRIEF SAYS TITLES
#: TARGET THE KEYWORD DATA, and the data for every one of these is dominated by "lyrics" and "pdf"
#: rather than "meaning" - so the title promises the text and the download, in that order.
#: THE HINDI TITLE CARRIES THE ROMAN NAME, for two reasons that happen to agree. The site requires
#: a Devanagari title to hold a Roman phrase of at least four letters, so a reader skimming a list
#: of results can tell what the page is; and "hanuman chalisa lyrics" in Latin letters is a larger
#: query than the Devanagari spelling, so the English name belongs there anyway. "PDF" alone does
#: not satisfy the rule - three letters - which is how this was caught.
#: LONGEST FORM THAT FITS, because the names vary from "गायत्री मंत्र" to "Sankat Mochan Hanuman
#: Ashtak" and one template cannot serve both inside sixty characters. Written as a list rather
#: than as string arithmetic so each variant can be read and judged as a title in its own right;
#: `title()` below takes the first that fits, and every form carries a Roman phrase of four or more
#: letters so the Devanagari titles satisfy the site-wide rule by construction.
TITLE_FORMS = {
    "en": (
        "{name} Lyrics in English and Hindi with Free PDF",
        "{name} Lyrics with Free PDF Download",
        "{name} Lyrics and Free PDF",
        "{name} Lyrics PDF",
    ),
    "hi": (
        "{name} - पूरा पाठ, {english} Lyrics PDF",
        "{name} - पूरा पाठ और {english} PDF",
        "{name} - {english} Lyrics PDF",
        "{name} - {english} PDF",
        "{english} - {name}",
    ),
}
TITLE_LIMIT = 60


def title(name: str, english: str, lang: str) -> str:
    """The longest title form that fits the limit. The last form is short enough for every name in
    the registry, and tests/test_mantra_pages.py asserts that for all of them rather than trusting
    it - a name long enough to overflow even the shortest form would otherwise ship silently."""
    forms = TITLE_FORMS[lang]
    for form in forms:
        candidate = form.format(name=name, english=english)
        if len(candidate) <= TITLE_LIMIT:
            return candidate
    return forms[-1].format(name=name, english=english)
META = {
    "en": ("{name} full text in Hindi with English transliteration, a free printable PDF, and "
           "what each verse means. Taken from a named source and checked against a second."),
    "hi": ("{name} का पूरा पाठ हिंदी में, रोमन लिप्यंतरण, मुफ़्त PDF और हर पंक्ति का अर्थ। "
           "नामित स्रोत से लिया गया और दूसरे स्रोत से मिलाया गया।"),
}
