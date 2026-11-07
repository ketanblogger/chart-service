"""The public blog: /blog and /blog/<slug>, in English.

THREE ROUTES, AND THEIR ORDER MATTERS. The media route is registered FIRST, so `/blog/media/<id>` can
never be read as a post whose slug is "media" - `paths.RESERVED_SLUGS` closes the same door from the
other side, at the moment a post is created, because two independent guards on a path collision is the
cheap version of this going wrong.

Every post page carries, by construction rather than by the writer remembering:

  * **Article JSON-LD** with the published and modified dates, the publisher, the categories as
    `articleSection`, and the post's own `inLanguage` - asserted against the page's `<html lang>` by
    tests/test_pages_i18n.py for every registry page.
  * **the date, visibly.** A dateline in the structured data and nothing on the page is a date written
    for a crawler and withheld from the reader, which is the wrong way round.
  * **a link to the tool the post is about.** `tool` is a required field precisely so that this link
    cannot be forgotten: a post about kundli matching that does not reach the matching page answered a
    question and then let the reader leave.

A DRAFT IS A 404, not a hidden page with a secret URL. There is no preview token and no `?draft=1`: the
only place a draft can be read is /admin/blog, behind the admin gate. A guessable preview URL is an
unpublished page that is published to anybody who guesses.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from . import images, links, markdown, paths, safety, store

log = logging.getLogger(__name__)
router = APIRouter(include_in_schema=False)

#: The list page's own copy. Held here, the way app/web/dosha_guides.py holds its Hindi copy: this is one
#: English page in one module, and routing it through the three-language content system would mean
#: inventing Hindi and Marathi versions of a page that deliberately does not exist in those trees.
def copy_for(lang: str) -> dict:
    """This page's own words in one tree. Falls back to English for a tree with no copy yet, so adding
    a language to LANGS can never produce a page with blank headings."""
    return TREE_COPY.get(lang) or COPY


COPY = {
    # APPENDED TO EVERY POST AT RENDER TIME, in the post's own language. Not stored on the post and
    # not the writer's to remove: it is a statement about what this whole section of the site is, and
    # a per-post copy would be a per-post chance to leave it out. It matters more now that a post can
    # reach the public without anybody reading it first.
    "disclaimer": ("This article explains traditional Vedic astrology for general information. It is "
                   "not a personal reading or professional advice."),
    "reading_time": "{minutes} min read",
    "read_next": "Read next",
    "key_points": "Key points",
    "contents": "What this post covers",
    "tool_text": "Every figure in this post comes from the same calculation. Run it on your own chart:",
    "filter_label": "Filter by topic", "filter_all": "All", "filter_none": "No posts in that topic yet.",
    "title": "Vedic Astrology, Explained Plainly: The RashiKundli Blog",
    "h1": "Vedic astrology, explained plainly",
    "meta_description": (
        "Longer answers to the questions the calculators cannot fit on one page: what a dosha actually "
        "is, where astrologers disagree, and what the maths behind a kundli is really doing."),
    "intro": (
        "Every tool on this site answers one question and then gets out of the way. Some questions need "
        "more room than that - what a dosha actually is, why two astrologers reading the same chart "
        "disagree, what the ayanamsa is doing to your sign, how much of a published muhurat is "
        "calculation and how much is convention. Those answers live here.",
    ),
    # MOVED OUT OF THE INTRO, NOT DELETED. It is the most important thing on this page and it was the
    # second paragraph somebody had to get past before reaching a single post. At the foot it reads as
    # a standing promise rather than a hurdle, and the index opens on the posts.
    "about_heading": "About this blog",
    "about": (
        "What you will not find is a prediction about you. A post is read by thousands of people and "
        "written about none of them, so nothing here reads your chart, dates your marriage or promises "
        "an outcome; where a question can only be answered from your own birth details, the post sends "
        "you to the free calculator that does it. Nothing here is sold against a fear, either - the "
        "remedies named are the cheap traditional ones, which is what the tradition actually says."),
    "tools_more": "All tools",
    # THE CTA IS AN ACTION, not a page name. "Sidereal birth chart calculator" tells a reader what
    # the page is called; "Find your Vedic sun sign" tells them what they get for tapping it.
    "cta": {
        "kundali": "Draw your free birth chart",
        "kundli": "Draw your free kundli",
        "matching": "Check your match free",
        "mangal-dosha": "Check for mangal dosha",
        "sade-sati": "Check your Sade Sati",
        "sidereal": "Find your Vedic sun sign",
        "panchang": "See today's panchang",
        "consultation": "Ask the AI astrologer",
        "rashifal-hub": "Read today's horoscope",
        "marriage-timing": "See your marriage timing",
        "rashi-by-name": "Find your rashi",
    },
    "cta_fallback": "Open the free tool",
    "byline": "By RashiKundli",
    "byline_source": "Calculated with Swiss Ephemeris (Lahiri)",
    "byline_updated": "Updated {date}",
    "all_posts": "All posts",
    "featured": "Latest",
    "empty": "The first posts are being written. In the meantime, the free tools are all here:",
    "tools_heading": "The tools these posts are about",
    # The rail beside a post, where "the tools these posts are about" is both too long and about
    # the wrong thing - the reader is in ONE post, not in the index.
    "rail_tools_heading": "Other free tools",
    # Named here because the section above links the AI astrologer, and every block on this site that
    # mentions AI says what the calculation rests on. See tests/test_trust_copy.py.
    "tools_note": ("Every chart, date and degree on this site is calculated with the Swiss Ephemeris "
                   "using the Lahiri ayanamsa. The AI astrologer reads that finished chart; it does not "
                   "compute it."),
    "posts_heading": "Posts",
    "read_more": "Read the post",
    "published_label": "Published",
    "updated_label": "Updated",
    "tool_label": "The free tool this post is about",
}


def _article_image(post: dict) -> str:
    from app.web import i18n, share_cards

    hero = post.get("hero_image")
    if hero and images.file_for(hero):
        return i18n.absolute(paths.media_path(hero))
    return i18n.absolute(share_cards.card_path(None, post.get("language") or paths.LANG, {}))


def _article_json_ld(post: dict, url: str) -> dict:
    from app.web import site

    # The publisher and the author both point at the Organization node app/web/seo.py publishes on the
    # home page, by its `@id`, rather than repeating the name and logo here. One organisation, one node.
    base = site.base_url()
    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post["title"][:110],   # Google truncates beyond this; a longer one is silently cut
        "description": post["summary"],
        # THE POST'S OWN LANGUAGE. This said "en" outright, from before the blog had other trees, so
        # every Hindi and Marathi post was telling Google it was written in English - the one claim in
        # this block a search engine acts on directly.
        "inLanguage": post.get("language") or paths.LANG,
        "url": url,
        # The post's hero where it has one, the site card where it does not. Google wants an image on
        # an Article, and the honest one is whatever the post actually shares as.
        "image": _article_image(post),
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "datePublished": store.iso_moment(post.get("published_at")),
        "dateModified": store.iso_moment(post.get("updated_at") or post.get("published_at")),
        # THE PUBLICATION IS THE AUTHOR. No private individual's name goes on a public page here, which
        # is a house rule rather than an SEO choice; the byline a writer may send is shown as the
        # publication's own name or not at all.
        "author": {"@type": "Organization", "name": post.get("author") or site.SITE_NAME,
                   "@id": base + "/#organization"},
        "publisher": {"@id": base + "/#organization"},
        "isAccessibleForFree": True,
    }
    if post["categories"]:
        data["articleSection"] = [safety.CATEGORIES[name] for name in post["categories"]
                                  if name in safety.CATEGORIES]
    if post.get("hero_image") and images.file_for(post["hero_image"]):
        data["image"] = base + paths.media_path(post["hero_image"])
    return data


#: The list page's words per tree. English is the original and the fallback; a tree with no entry here
#: renders in English rather than with blank headings, so adding a language to paths.LANGS is safe
#: before its copy is written.
#:
#: These are SHORT on purpose. The English page argues at length about what a blog post can and cannot
#: say; the Hindi and Marathi pages make the same promise in two sentences, because a wall of
#: translated preamble above three posts reads as padding in any language.
TREE_COPY = {
    "hi": {
        "disclaimer": ("यह लेख पारंपरिक वैदिक ज्योतिष की सामान्य जानकारी देता है। यह किसी की व्यक्तिगत "
                       "कुंडली का विश्लेषण या पेशेवर सलाह नहीं है।"),
        "reading_time": "{minutes} मिनट का पाठ",
        "read_next": "आगे पढ़िए",
        "key_points": "मुख्य बातें",
        "contents": "इस लेख में क्या है",
        "tool_text": "इस लेख का हर आँकड़ा उसी गणना से आता है। अपनी कुंडली पर चलाइए:",
        # MISSING UNTIL NOW, so every Hindi post rendered this card with no heading at all. It
        # showed up the moment the same card went into the rail beside the article.
        "tool_label": "इस लेख का फ़्री साधन",
        # Also absent, and blog_post.html prints it before the date - so every Hindi post showed a
        # bare date with nothing saying what it was the date OF.
        "published_label": "प्रकाशित",
        "filter_label": "विषय से छाँटें", "filter_all": "सभी",
        "filter_none": "इस विषय पर अभी कोई लेख नहीं।",
        "title": "ज्योतिष, सीधी भाषा में: RashiKundli ब्लॉग",
        "h1": "ज्योतिष, सीधी भाषा में",
        "meta_description": "पंचांग, कुंडली और गोचर पर सीधी बातें - गणना कैसे होती है, और कौन सी बात "
                            "परंपरा है। किसी की निजी भविष्यवाणी यहाँ नहीं।",
        "intro": (
            "यहाँ वही सवाल हैं जो लोग पूछते हैं: दो पंचांग अलग तारीख़ क्यों देते हैं, अयनांश आपकी राशि "
            "के साथ क्या करता है, मुहूर्त में गणित कितना है और प्रथा कितनी।",
        ),
        "empty": "पहले लेख लिखे जा रहे हैं। तब तक सभी मुफ़्त साधन यहाँ हैं:",
        "about_heading": "इस ब्लॉग के बारे में",
        "about": "आपके बारे में भविष्यवाणी यहाँ नहीं मिलेगी। एक लेख हज़ारों लोग पढ़ते हैं और वह किसी एक के "
            "लिए नहीं लिखा जाता - जहाँ जवाब आपकी अपनी जन्म-कुंडली से ही निकल सकता है, लेख आपको मुफ़्त "
            "कैलकुलेटर पर भेज देता है।",
        "tools_more": "सभी साधन",
        "cta": {
            "kundali": "अपनी मुफ़्त कुंडली बनाइए",
            "kundli": "अपनी मुफ़्त कुंडली बनाइए",
            "matching": "मुफ़्त कुंडली मिलान कीजिए",
            "mangal-dosha": "मंगल दोष जाँचिए",
            "sade-sati": "अपनी साढ़ेसाती जाँचिए",
            "sidereal": "अपनी वैदिक राशि जानिए",
            "panchang": "आज का पंचांग देखिए",
            "consultation": "AI ज्योतिषी से पूछिए",
            "rashifal-hub": "आज का राशिफल पढ़िए",
            "marriage-timing": "विवाह का समय देखिए",
            "rashi-by-name": "अपनी राशि जानिए",
        },
        "cta_fallback": "ऑनलाइन मुफ़्त टूल खोलिए",
        "byline": "RashiKundli द्वारा",
        "byline_source": "स्विस एफेमेरिस (लाहिरी) से गणना",
        "byline_updated": "{date} को अद्यतन",
        "all_posts": "सभी लेख",
        "featured": "नवीनतम",
        "tools_heading": "इन लेखों से जुड़े साधन",
        "rail_tools_heading": "अन्य फ़्री साधन",
        "tools_note": ("इस साइट की हर कुंडली, तारीख़ और अंश स्विस एफेमेरिस और लाहिड़ी अयनांश से गणना "
                       "किए जाते हैं। AI ज्योतिषी उसी बनी हुई कुंडली को पढ़ता है, उसे बनाता नहीं।"),
    },
    "mr": {
        "disclaimer": ("हा लेख पारंपरिक वैदिक ज्योतिषाची सर्वसाधारण माहिती देतो. ही कोणाच्याही वैयक्तिक "
                       "पत्रिकेची मांडणी किंवा व्यावसायिक सल्ला नाही."),
        "reading_time": "{minutes} मिनिटांचे वाचन",
        "read_next": "पुढे वाचा",
        "key_points": "मुख्य मुद्दे",
        "contents": "या लेखात काय आहे",
        "tool_text": "या लेखातील प्रत्येक आकडा त्याच गणनेतून येतो. तुमच्या पत्रिकेवर चालवा:",
        "tool_label": "या लेखातील मोफत साधन",
        "published_label": "प्रकाशित",
        "filter_label": "विषयानुसार निवडा", "filter_all": "सर्व",
        "filter_none": "या विषयावर अजून लेख नाही.",
        "title": "ज्योतिष, सोप्या भाषेत: RashiKundli ब्लॉग",
        "h1": "ज्योतिष, सोप्या भाषेत",
        "meta_description": "पंचांग, कुंडली आणि गोचराविषयी स्पष्ट लेख - गणित कसे होते, आणि कोणती गोष्ट "
                            "परंपरा आहे. कोणाचेही वैयक्तिक भविष्य इथे नाही.",
        "intro": (
            "लोक जे विचारतात तेच प्रश्न इथे आहेत: दोन पंचांगे वेगळी तारीख का देतात, अयनांश तुमच्या "
            "राशीचे काय करतो, मुहूर्तात गणित किती आणि प्रथा किती.",
        ),
        "empty": "पहिले लेख लिहिले जात आहेत. तोपर्यंत सर्व मोफत साधने इथे आहेत:",
        "about_heading": "या ब्लॉगबद्दल",
        "about": "तुमच्याबद्दलचे भाकीत इथे मिळणार नाही. एक लेख हजारो लोक वाचतात आणि तो कोणा एकासाठी लिहिलेला "
            "नसतो - जिथे उत्तर फक्त तुमच्या पत्रिकेतूनच मिळू शकते, तिथे लेख तुम्हाला मोफत "
            "कॅल्क्युलेटरकडे पाठवतो.",
        "tools_more": "सर्व साधने",
        "cta": {
            "kundali": "तुमची मोफत पत्रिका बनवा",
            "kundli": "तुमची मोफत पत्रिका बनवा",
            "matching": "मोफत पत्रिका जुळवा",
            "mangal-dosha": "मंगळ दोष तपासा",
            "sade-sati": "तुमची साडेसाती तपासा",
            "sidereal": "तुमची वैदिक रास पाहा",
            "panchang": "आजचे पंचांग पाहा",
            "consultation": "AI ज्योतिषाला विचारा",
            "rashifal-hub": "आजचे राशिभविष्य वाचा",
            "marriage-timing": "विवाहाची वेळ पाहा",
            "rashi-by-name": "तुमची रास शोधा",
        },
        "cta_fallback": "मोफत टूल उघडा",
        "byline": "RashiKundli कडून",
        "byline_source": "स्विस एफेमेरिस (लाहिरी) ने गणना",
        "byline_updated": "{date} रोजी अद्यतनित",
        "all_posts": "सर्व लेख",
        "featured": "नवीनतम",
        "tools_heading": "या लेखांशी संबंधित साधने",
        "rail_tools_heading": "इतर मोफत साधने",
        "tools_note": ("या साइटवरील प्रत्येक पत्रिका, तारीख आणि अंश स्विस एफेमेरिस आणि लाहिरी अयनांश "
                       "वापरून काढलेले आहेत. AI ज्योतिषी तयार झालेली पत्रिका वाचतो, ती तयार करत नाही."),
    },
}


def _category_labels(post: dict) -> list[dict]:
    return [{"key": name, "label": safety.CATEGORIES[name]}
            for name in post["categories"] if name in safety.CATEGORIES]


def _dateline(post: dict, lang: str = paths.LANG) -> dict:
    """What the reader sees: the published date always, the modified date only when it differs.

    "Updated 22 October 2026" under "Published 22 October 2026" is noise that teaches a reader to ignore
    both - the same reasoning the chart pages use for their accuracy caveats.

    THE DATE IS IN THE POST'S OWN LANGUAGE. This passed "en" to `format_date` whatever tree it was
    rendering, so every Hindi and Marathi post carried an English month name - "24 October 2026" under
    a Devanagari headline, on the post page, in the index and in the sidebar. The month names for all
    three trees already existed in app/rashifal/i18n.py; only the call site was hardcoded.
    """
    from app.rashifal.i18n import format_date

    published = post.get("published_on") or post.get("created_on")
    updated = post.get("updated_on")
    return {"published": format_date(published, lang) if published else "",
            "updated": format_date(updated, lang) if updated and updated != published else ""}


def _card(post: dict, lang: str = paths.LANG) -> dict:
    """One post as the INDEX reads it - the title, the summary, the date and the categories.

    Deliberately does not render the body. The index shows the summary, so rendering every published
    post's Markdown to build a list of links would make /blog slower with every post ever written
    rather than with what it actually shows - the shape of defect app/admin/routes.py describes in its
    own docstring about per-day queries.
    """
    # The post's path is in ITS OWN tree, which is the tree it was written in - not the tree of the
    # page that happens to be listing it.
    language = post.get("language") or paths.LANG
    # THE DATE IS IN THE LANGUAGE OF THE PAGE SHOWING IT, not of the post. A Hindi index listing an
    # English post is a Hindi page, and its dates should read as Hindi; the post's own `language`
    # decides its PATH, which is a different question.
    return {**post, "categories_view": _category_labels(post), "dates": _dateline(post, lang),
            "path": paths.post_path(post["slug"], language),
            "reading_minutes": reading_minutes(post.get("body_md") or "", language),
            # EVERY CARD HAS A PICTURE, so a list of posts does not come out half-illustrated - and
            # the stand-in is the same size as a real hero, so swapping one in later moves nothing.
            "hero_url": (paths.media_path(post["hero_image"])
                         if post.get("hero_image") and images.file_for(post["hero_image"])
                         else PLACEHOLDER),
            "has_hero": bool(post.get("hero_image") and images.file_for(post["hero_image"]))}


#: The stand-in hero. Wordless by design - see the file itself for why it carries no text.
PLACEHOLDER = "/static/img/blog-placeholder.svg"

#: The six tools shown as cards on the index, in the order a newcomer needs them: the chart first,
#: because everything else here is read off one, then the questions people actually arrive with.
FEATURED_TOOLS = ("kundali", "matching", "rashifal-hub", "mangal-dosha", "sade-sati", "consultation")

#: Which mark each featured tool wears, by the symbol ids in _tool_icons.html.
TOOL_ICONS = {"kundali": "ti-chart", "matching": "ti-match", "rashifal-hub": "ti-sun",
              "mangal-dosha": "ti-mars", "sade-sati": "ti-saturn", "consultation": "ti-chat"}

#: Words a minute, per tree. English is the usual figure for ordinary prose; Devanagari is slower for
#: the same word count - the script is denser, conjuncts carry more information per glyph, and a word
#: is longer. These are estimates and the page says "min read", not a promise.
READING_SPEED = {"en": 200, "hi": 150, "mr": 150}


def reading_minutes(body_md: str, language: str) -> int:
    """Minutes, rounded up, never less than one.

    Zero minutes reads as an error and "less than a minute" is more words than the number saves. The
    count is of what a reader SEES - markdown.plain_text strips the markup first, so a post full of
    links does not read as longer than it is.
    """
    words = markdown.word_count(body_md)
    speed = READING_SPEED.get(language, READING_SPEED["en"])
    return max(1, round(words / speed + 0.49))


def _share_for(path: str, lang: str, title: str) -> dict | None:
    from app.web import sharing

    return sharing.share(path, "blog", lang, title=title)


def _all_tools_path(lang: str) -> str:
    """Where "All tools" goes.

    THE HOME PAGE, WITH THE ANCHOR THAT ACTUALLY EXISTS. The first version pointed at "#tools", which
    is not an id on that page - a fragment that resolves to nothing leaves the reader at the top
    wondering what they were supposed to see, and nothing would ever have reported it.
    """
    from app.web import i18n

    return i18n.url_for("home", lang) + "#more-from-us"


def _filters(posts: list[dict]) -> list[dict]:
    """The categories actually present on this tree's posts, in the order the catalogue lists them."""
    present = {name for post in posts for name in (post.get("categories") or ())}
    return [{"key": key, "label": label} for key, label in safety.CATEGORIES.items() if key in present]


def guides_for_tool(tool_key: str, lang: str, limit: int = 3) -> list[dict]:
    """Posts about one tool, for a "Related guides" block ON that tool's page - the reverse link.

    Every post names the tool it is about, so this is that field read backwards. Posts for THIS tool
    first, then the rest of the tree by recency, because a tool page with an empty block looks like a
    section that failed to load rather than one with nothing to say yet - and a general guide beside
    the kundli form is still worth reading.

    Returns [] when the blog is empty, and the template renders nothing at all for that. A heading
    with no list under it is worse than no heading.
    """
    posts = store.published(language=lang)
    if not posts:
        return []
    posts.sort(key=lambda other: (other.get("tool") != tool_key, -(other.get("published_at") or 0)))
    return [_card(other, lang) for other in posts[:limit]]


def _related(post: dict, lang: str, limit: int = 3) -> list[dict]:
    """Posts worth reading next: this tree only, shared categories first, then recency.

    A list that is simply the newest three is a recency list with a different label - which is fine
    until the newest three have nothing to do with what somebody just read.
    """
    mine = set(post.get("categories") or ())
    rest = [other for other in store.published(language=lang) if other["slug"] != post["slug"]]
    rest.sort(key=lambda other: (-len(mine & set(other.get("categories") or ())),
                                 -(other.get("published_at") or 0)))
    return [_card(other, lang) for other in rest[:limit]]


def _with_heading_ids(html):
    """Give every `<h2>` an id, so the contents box can link to it.

    RETURNS Markup, NOT str. markdown.render() hands back Markup - already escaped, safe to print -
    and `re.sub` on it returns a plain string, which Jinja then escapes again. The post body rendered
    as visible `<p>` tags on the page: every tag shown as text. It is the kind of defect no unit test
    of this function would catch, because the string is correct; only the template's treatment of it
    changes.
    """
    import re

    from markupsafe import Markup

    def tag(match: "re.Match[str]") -> str:
        text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        return f'<h2 id="{_heading_id(text)}">{match.group(1)}</h2>' if text else match.group(0)

    return Markup(re.sub(r"<h2>(.*?)</h2>", tag, str(html), flags=re.S))


def contents_of(html: str) -> list[dict]:
    """The post's own `##` headings, for the contents box.

    NOT "KEY POINTS", and the template labels it as what it is. A heading says what a section is
    about; a takeaway says what to conclude from it. Deriving the second from the first would be the
    site writing claims nobody wrote, which is the one thing a post must never do. Where an author
    sends real takeaways they go in `key_points` and are shown above this.

    Read from the RENDERED html rather than the markdown, because that is what the ids are built from
    and a contents list whose links do not land is worse than none.
    """
    import re

    found = []
    for match in re.finditer(r"<h2[^>]*>(.*?)</h2>", html, re.S):
        text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        if text:
            found.append({"text": text, "id": _heading_id(text)})
    return found


def _heading_id(text: str) -> str:
    """A stable anchor for a heading, in any script.

    Latin letters and digits become a hyphenated slug; a Devanagari heading has none of those, so it
    falls back to a short hash of the text - an id that is opaque but STABLE, which is what an anchor
    has to be. An id that changed between renders would break every link to it.
    """
    import hashlib
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "s-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _view(post: dict, lang: str = paths.LANG) -> dict:
    """One post as its own PAGE reads it: the card, plus the rendered body and the hero image."""
    html, problems = markdown.render(post["body_md"])
    if problems:
        # A published post should never reach here with a render problem - the checks refuse one - so
        # this is worth a log line rather than silence. The page still renders: the problems are about
        # a link or an image, and the rest of the prose is fine.
        log.warning("blog: published post %s still has %d render problem(s): %s",
                    post["slug"], len(problems), problems[0])
    # THE SAME FUNCTION GIVES THE HEADING ITS ID AND THE CONTENTS BOX ITS LINK. Two implementations
    # would agree until somebody changed one, and the symptom would be a contents list whose links
    # land nowhere - which looks like a broken page rather than a broken slug.
    html = _with_heading_ids(html)
    # TERM LINKS, ADDED HERE AND NOT STORED. The body in the database stays the Markdown its writer
    # sent; the links are put on as the page is built, so the whole archive follows app/blog/links.py
    # every time it is rendered rather than freezing whatever the map said on the day it was saved.
    # AFTER the heading ids, because that pass rewrites every <h2> and this one must see the finished
    # headings in order to skip inside them.
    from markupsafe import Markup

    # THE TOOL CTA COUNTS AS A LINK THE POST ALREADY HAS. It is in the template rather than in the
    # body, so add_links cannot see it - and the first version happily linked "sidereal zodiac" to
    # the same page the button underneath it already went to. Twice to one place in one post is the
    # same recommendation twice, which is the thing the skip rule exists to prevent.
    tool = paths.tool_link(post["tool"], lang)
    linked, added = links.add_links(
        str(html), lang=lang,
        self_path=paths.post_path(post["slug"], post.get("language") or paths.LANG),
        also_linked=(tool["path"],) if tool else ())
    html = Markup(linked)
    hero = post.get("hero_image")
    if tool:
        words = copy_for(lang)
        tool = {**tool, "cta": words["cta"].get(tool["key"]) or words["cta_fallback"]}
    return {**_card(post, lang), "html": html, "tool": tool, "links_added": added,
            "contents": contents_of(html),
            "hero_url": paths.media_path(hero) if hero and images.file_for(hero) else None}


# ---- the routes --------------------------------------------------------------------------------------


def _media(image_id: str) -> Response:
    found = images.response(image_id)
    if found is None:
        raise HTTPException(status_code=404, detail="no such image")
    return found


def _list(request: Request, lang: str = paths.LANG) -> HTMLResponse:
    from app.web import i18n, seo
    from app.web.routes import _json_ld, page_context, respond

    words = copy_for(lang)
    path = paths.list_path(lang)
    # ONLY THIS TREE'S POSTS. A Hindi list page showing English posts would be a list of pages the
    # reader cannot read, and the sitemap already says they are not alternates of each other.
    posts = [_card(post, lang) for post in store.published(language=lang)]
    context = page_context(paths.LIST_KEY, lang, path=path)
    crumbs = [(context["ui"]["home"], i18n.url_for("home", lang)), (words["h1"], path)]
    blog_ld = {
        "@context": "https://schema.org", "@type": "Blog", "@id": i18n.absolute(path) + "#blog",
        "name": words["h1"], "description": words["meta_description"], "inLanguage": lang,
        "url": i18n.absolute(path), "publisher": {"@id": i18n.absolute("/") + "#organization"},
        "blogPost": [{"@type": "Article", "headline": post["title"][:110],
                      "url": i18n.absolute(post["path"]),
                      "datePublished": store.iso_moment(post.get("published_at"))} for post in posts],
    }
    context.update(
        words=words, posts=posts, title=words["title"], meta_description=words["meta_description"],
        tools=[paths.tool_link(key, lang) for key in paths.tool_keys()],
        # Where "All tools" goes: the home page's own tools section, which is the real directory.
        tools_path=_all_tools_path(lang),
        # ONLY CATEGORIES THAT HAVE A POST IN THIS TREE. A chip that filters to nothing is a chip that
        # looks broken, and the reader has no way to know it was always empty.
        filters=_filters(posts),
        # THE LATEST POST, LARGER, AND THEN THE REST. An index where every card is the same size asks
        # the reader to choose; this one answers the question they actually arrived with, which is
        # "what is new". The featured post is NOT repeated in the grid below it.
        featured=(posts[0] if posts else None), rest=posts[1:],
        # Six tool cards, then a link to the others. Fourteen links in a column is a directory, not a
        # recommendation, and nobody reads to the end of one.
        tool_cards=[{**paths.tool_link(key, lang), "icon": TOOL_ICONS[key]}
                    for key in FEATURED_TOOLS if paths.tool_link(key, lang)],
        crumbs=crumbs,
        json_ld=[_json_ld(blog_ld), _json_ld(seo.breadcrumbs(crumbs))])
    return respond(request, "blog_list.html", context)


def post_context(request: Request, post: dict, lang: str) -> dict:
    """Everything blog_post.html needs, for a published post OR a draft being previewed.

    ONE BUILDER, TWO CALLERS. The admin preview used to render its own template, so "it looked right in
    preview" and "it looks right published" were two different renderings of the same post - which is
    the bug that makes a preview worth less than no preview. The admin route renders THIS context
    through THIS template, so the only difference between what an editor sees and what a reader gets is
    the chrome around it.
    """
    from app.web import i18n, seo
    from app.web.routes import _json_ld, page_context

    slug = post["slug"]
    words = copy_for(lang)
    view = _view(post, lang)
    path = paths.post_path(slug, lang)
    context = page_context(paths.POST_KEY, lang, path=path, slug=slug)
    crumbs = [(context["ui"]["home"], i18n.url_for("home", lang)),
              (words["h1"], paths.list_path(lang)), (post["title"], path)]
    context.update(
        words=words, post=view, title=post["title"], meta_description=post["summary"],
        blog_path=paths.list_path(lang), crumbs=crumbs,
        # THE TRANSLATIONS OF THIS POST, as hreflang alternates. Two posts are alternates when they
        # share a translation group, never merely because they sit in different trees.
        translations=store.translations_of(post),
        # HREFLANG FROM THE TRANSLATION GROUP, not from the registry. Every other page family on this
        # site exists in all three trees, so page_context() can build alternates from the key alone; a
        # blog post exists in ONE tree and has an alternate only where somebody wrote one. Alternates
        # built from the key would point at URLs that 404.
        alternates=_alternates(post, path, lang),
        # A POST WITH A HERO SHARES THE HERO. The site-wide card says what RashiKundli is; a post's
        # own picture says what the post is, which is the more useful thing to arrive with. A post
        # without one keeps the site card rather than sharing as a bare link.
        **({"og_image": i18n_absolute(view["hero_url"]),
            "og_image_alt": post["title"]} if view.get("hero_url") else {}),
        # THE SWITCHER, BUILT FROM THE SAME TRANSLATION GROUP. The generic one rebuilds the current
        # path in each tree, which for a post means offering /hi/blog/<slug> whether or not anybody
        # wrote a Hindi version - a switcher full of 404s. A tree without a translation gets that
        # tree's blog index instead, which is the nearest thing that exists and is still about the
        # blog. Caught by the site-wide internal-link test, but only once a post existed to catch it
        # on: the guard had been passing against an empty table.
        switcher=_switcher(post, path, lang),
        # THE RAIL, SHOWN ONLY AT 1200px AND WIDER. Not new material: it is the contents and the tool
        # this page already carries, moved into the space a wide screen has going spare, plus three
        # tools. Below the breakpoint the rail is not rendered at all and the inline versions stay
        # where they were, which is why there is no duplicate for a phone reader to scroll past.
        # Three, not six: a column of links beside an article is a suggestion, and six is a menu.
        rail_tools=[card for card in
                    ({**paths.tool_link(key, lang), "icon": TOOL_ICONS[key]}
                     for key in FEATURED_TOOLS if paths.tool_link(key, lang))
                    if not (view.get("tool") and card.get("path") == view["tool"]["path"])][:3],
        # The share: the post's own link and title, never anything about a reader.
        share=_share_for(path, lang, post["title"]),
        # THREE RELATED POSTS, AS CARDS. Same tree, same category first, then the rest by recency -
        # a "related" list that is simply the newest three is a recency list wearing another name.
        others=_related(post, lang, limit=3),
        json_ld=[_json_ld(_article_json_ld(post, i18n.absolute(path))),
                 _json_ld(seo.breadcrumbs(crumbs))])
    return context


def _post(request: Request, slug: str, lang: str = paths.LANG) -> HTMLResponse:
    from app.web.routes import respond

    post = store.get(slug)
    # A DRAFT IS A 404. Not a 403, and not a page behind a query string: see the module docstring.
    if post is None or not post["is_published"]:
        raise HTTPException(status_code=404, detail="not found")
    # AND SO IS THE WRONG TREE. A Hindi post served at /blog/<slug> would be a Hindi page with an
    # English canonical, which is the one thing hreflang cannot survive.
    if (post.get("language") or paths.LANG) != lang:
        raise HTTPException(status_code=404, detail="not found")
    return respond(request, "blog_post.html", post_context(request, post, lang))


# THE MEDIA ROUTE FIRST. FastAPI matches in registration order, so this one is reached before the post
# route's `{slug}` could swallow it.
router.add_api_route(paths.media_template(), _media, methods=["GET"], name="blog-media")
def sitemap_alternates(params: dict) -> dict[str, str]:
    """{hreflang: absolute url} for one post, for the sitemap - THE SAME SET THE PAGE DECLARES.

    Built from `_alternates`, deliberately, rather than from a second reading of the translation
    group: the sitemap and the page disagreeing is exactly the defect this exists to stop, and two
    implementations of one rule is how they would drift apart again.
    """
    from app.web import i18n

    post = store.get(params.get("slug") or "")
    if post is None or not post["is_published"]:
        return {}
    lang = post.get("language") or paths.LANG
    links = _alternates(post, paths.post_path(post["slug"], lang), lang)
    return {item["hreflang"]: item["href"] for item in links}


def _alternates(post: dict, path: str, lang: str) -> list[dict]:
    """The hreflang set for one post: itself, its published translations, and x-default.

    BUILT FROM THE TRANSLATION GROUP, not from the registry. Every other page family here exists in all
    three trees, so i18n.alternates() can derive the set from the key alone; a blog post exists in ONE
    tree and has an alternate only where somebody wrote one, so a set derived from the key would point
    at URLs that 404.

    The SET IS THE SAME on every member of the group - that is what makes it reciprocal, and the
    site-wide hreflang test checks exactly that. x-default is the English member when there is one, and
    otherwise the original, because a group with no English version still needs one default and the
    original is the only member guaranteed to exist.
    """
    from app.web import i18n

    members = {lang: path}
    for other in store.translations_of(post):
        if other["language"] in i18n.HTML_LANG:
            members[other["language"]] = other["path"]
    if len(members) < 2:
        return []                            # a post with no translations has no alternates at all
    default = members.get(i18n.DEFAULT_LANG) or members[sorted(members)[0]]
    links = [{"hreflang": i18n.HTML_LANG[language], "href": i18n.absolute(where)}
             for language, where in sorted(members.items())]
    links.append({"hreflang": "x-default", "href": i18n.absolute(default)})
    return links


def i18n_absolute(path: str) -> str:
    from app.web import i18n

    return i18n.absolute(path)


def _switcher(post: dict, path: str, lang: str) -> list[dict]:
    """Language links for one post: the translation where there is one, that tree's index otherwise."""
    from app.web import i18n

    translated = {lang: path}
    for other in store.translations_of(post):
        if other["language"] in i18n.HTML_LANG:
            translated[other["language"]] = other["path"]
    return [{"lang": code, "hreflang": i18n.HTML_LANG[code], "label": i18n.LANGUAGE_NAMES[code],
             "path": translated.get(code) or paths.list_path(code), "current": code == lang}
            for code in i18n.LANGS]


def _bind(language: str):
    """Handlers for one tree, with REAL ANNOTATIONS.

    FastAPI builds each route's signature by inspecting the callable, so a bare `lambda request: ...`
    is read as a handler wanting a query parameter called "request" - every blog page answered 422
    until these were written out. The language is bound per route rather than parsed from the path
    because the tree is decided by which route matched, which is what the rest of the site does.
    """
    def list_page(request: Request) -> HTMLResponse:
        return _list(request, language)

    def post_page(request: Request, slug: str) -> HTMLResponse:
        return _post(request, slug, language)

    return list_page, post_page


for _lang in paths.LANGS:
    _list_page, _post_page = _bind(_lang)
    router.add_api_route(paths.list_template(_lang), _list_page, methods=["GET"],
                         response_class=HTMLResponse, name=f"blog-list-{_lang}")
    router.add_api_route(paths.post_template(_lang), _post_page, methods=["GET"],
                         response_class=HTMLResponse, name=f"blog-post-{_lang}")
