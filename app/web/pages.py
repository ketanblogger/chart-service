"""The page-config system: ONE structure for every public page in every language.

    copy = pages.get("matching", "hi")        # PageCopy, fully formatted (prices, URLs filled in)
    spec = pages.TOOLS["matching"]            # language-independent wiring: form, API route, renderer, product

Where things live:
  * app/web/i18n.py            - URLs (page key x language -> path). Nothing else spells a path.
  * app/web/content/{en,hi,mr}.py - the words. Each exports `PAGES: dict[page_key, PageCopy]` and `UI: dict[str, str]`
    (template strings: nav, form labels, footer ...). Every language is WRITTEN to its own keyword
    (each tree uses its own search vocabulary: EN "birth chart / horoscope", HI "kundali / rashifal",
    MR "patrika / rashi bhavishya") -
    never a mechanical translation of another language. tests/test_pages_i18n.py checks the three stay in step.
  * this module                - the dataclasses, the wiring (TOOLS) and `get()`, which fills the placeholders.

To add a page: a path in i18n.PAGES, a PageCopy in each content module, and (for a calculator) a TOOLS entry plus a
renderer of the same name in static/js/render.js. No new template, no new route.

Placeholders usable in ANY copy string (so copy can never drift from the charge or from the URL registry):
  {price}            this page's own product price in rupees (tool pages; the pack price on the consultation page)
  {price_kundali_simple} {price_kundali} {price_matching} {price_mangal_dosha} {price_sade_sati}
  {price_pack} {price_premium}          - the two Kundali tiers and the two consultation tiers
  {pack_messages} {free_messages} {site_name}
  {url_home} {url_kundali} {url_matching} {url_mangal_dosha} {url_sade_sati} {url_consultation}
  {url_rashifal_hub} {url_rashifal_weekly}      - paths in the SAME language as the copy
  + whatever the caller passes to get() (the rashifal pages pass {rashi}, {sign}, {latin}, {lord} ...).
Prices come from app.payments.catalogue at call time. A string with an <a> must be a markupsafe.Markup.

Copy rules: constructive framing, no fear, never predict death or serious illness.
"""

import importlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass, replace

from markupsafe import Markup, escape

from app.web import i18n, site


@dataclass(frozen=True)
class Product:
    """Copy of the paid upsell under a free result. Product key and price are not copy: see TOOLS / the catalogue.

    `button` is the label of a page that sells ONE thing. A page that offers tiers (PURCHASE_OPTIONS) labels each of
    its buttons in `extra` instead - `buy_<key>` and its one-line promise `gets_<key>` - and leaves `button` empty."""

    heading: str
    text: str
    button: str = ""
    points: tuple[str, ...] = ()


@dataclass(frozen=True)
class Section:
    """A block of long-form SEO content: an H2 and its body. A str is a paragraph, a list is bullets."""

    heading: str
    blocks: tuple[str | list[str], ...]
    anchor: str | None = None  # id="" of the <section>, for deep links (#by-name)


@dataclass(frozen=True)
class PageCopy:
    """Everything a page says, in one language."""

    nav_label: str
    title: str  # <title> without the site name; unique site-wide
    meta_description: str
    h1: str
    intro: str
    sections: tuple[Section, ...] = ()
    faqs: tuple[tuple[str, str], ...] = ()
    # tool pages + consultation
    form_heading: str = ""
    submit_label: str = ""
    result_heading: str = ""
    card_blurb: str = ""  # this page's card on the home page and in "more tools" lists
    product: Product | None = None
    extra: Mapping[str, str] = field(default_factory=dict)  # page-specific strings (by-name mode, chat UI, hub labels)


@dataclass(frozen=True)
class RashiBody:
    """The part of a rashi hub page that is genuinely about THAT rashi.

    The rest of `RASHIFAL_RASHI` is one PageCopy per language rendered twelve times with {rashi} / {latin} /
    {deva} / {lord} swapped in, which is right for a title and an intro and quite wrong for a thousand words of
    body: twelve pages of the same essay with one noun changed is duplicate content, and a search engine is
    entitled to read it as doorway pages. So the body lives here instead, keyed by rashi, written once per rashi
    per language out of material that really does differ - the sign lord and where it is strong or weak, the
    element and quality, the nakshatras the sign spans, which houses Saturn has to reach for sade sati, what the
    sign tends to do under its own mahadasha.

    `intro` replaces the shared one; `sections` and `faqs` are the page body. Placeholders still work here."""

    intro: str
    sections: tuple[Section, ...]
    faqs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ToolSpec:
    """Language-independent wiring of a calculator page."""

    form: str  # "single" (one person) or "pair" (boy + girl)
    endpoint: str  # JSON API route the form posts to
    renderer: str  # key of the result renderer in static/js/render.js
    product: str  # catalogue product key of the paid upsell (data-product, `product:purchase` detail)


TOOLS: dict[str, ToolSpec] = {
    "kundali": ToolSpec("single", "/api/chart", "kundali", "kundali-report"),
    "matching": ToolSpec("pair", "/api/matching", "matching", "matching-report"),
    "mangal-dosha": ToolSpec("single", "/api/mangal-dosha", "mangalDosha", "mangal-dosha-remedy"),
    "sade-sati": ToolSpec("single", "/api/sade-sati", "sadeSati", "sade-sati-guide"),
    # Same form, same endpoint, same renderer and same upsell as "kundali" - deliberately, because it IS the
    # birth chart. Only the copy differs, for a reader who searched "sidereal" rather than "birth chart".
    "sidereal": ToolSpec("single", "/api/chart", "kundali", "kundali-report"),
}
assert tuple(TOOLS) == i18n.TOOL_KEYS + i18n.EN_ONLY_TOOL_KEYS

CONSULTATION_ENDPOINT = "/api/consultation/start"
CONSULTATION_PRODUCT = "consultation-basic"  # the entry tier, and the price {price} means on the consultation page

# Pages that sell the same thing at two depths, cheapest first. Every other page sells the single product of its
# TOOLS entry and keeps its one button. Ids are the catalogue's; a tier the catalogue retires stops being offered
# here by itself (`catalogue.sellable`), which is how `consultation-pack` disappeared without a line of page code.
PURCHASE_OPTIONS = {"kundali": ("kundali-report-simple", "kundali-report"),
                    "sidereal": ("kundali-report-simple", "kundali-report"),  # same chart, so the same two tiers
                    "consultation": (CONSULTATION_PRODUCT, "consultation-premium")}
OPTION_KEYS = {"kundali-report-simple": "simple", "kundali-report": "detailed",
               CONSULTATION_PRODUCT: "basic", "consultation-premium": "premium"}

COPY_KEYS = ("home", *i18n.TOOL_KEYS, "consultation", "rashifal-hub", "rashifal-weekly", "rashifal-rashi",
             "rashifal-reading")  # every content module must define exactly these

_PRICE_NAMES = {"kundali-report": "price_kundali", "kundali-report-simple": "price_kundali_simple",
                "matching-report": "price_matching", "mangal-dosha-remedy": "price_mangal_dosha",
                "sade-sati-guide": "price_sade_sati",
                CONSULTATION_PRODUCT: "price_pack", "consultation-premium": "price_premium"}


def content(lang: str):
    """The content module of a language (app/web/content/<lang>.py)."""
    if lang not in i18n.LANGS:
        raise KeyError(f"unknown language {lang!r}")
    return importlib.import_module(f"app.web.content.{lang}")


def ui(lang: str) -> dict[str, str]:
    """Template strings of a language, placeholders filled."""
    values = common_values(lang)
    return {key: _fill(text, values) for key, text in content(lang).UI.items()}


def prices() -> dict[str, int]:
    from app.payments import catalogue

    return catalogue.prices_inr()


def chat_offer() -> dict[str, int]:
    """{"price_inr", "pack_messages", "free_messages"} of the consultation - from the chat settings, like the 402."""
    from app.ai.config import get_chat_settings
    from app.payments import catalogue

    settings = get_chat_settings()
    pack = catalogue.item(CONSULTATION_PRODUCT)
    return {"price_inr": pack.price_inr, "pack_messages": pack.messages, "free_messages": settings.free_messages}


def product_price(page_key: str) -> int | None:
    if page_key in TOOLS:
        return prices()[TOOLS[page_key].product]
    if page_key == "consultation":
        return chat_offer()["price_inr"]
    return None


def purchase_options(page_key: str) -> list[dict]:
    """[{product, price_inr, key}] - what this page offers, in the order it shows them, priced by the catalogue at
    request time. `key` is None on a page that sells a single product (its label is the Product's own `button`)."""
    from app.payments import catalogue

    products = PURCHASE_OPTIONS.get(page_key)
    if products is None:
        products = (TOOLS[page_key].product,) if page_key in TOOLS else ()
    offered = []
    for product in products:
        entry = catalogue.sellable(product)
        if entry:
            offered.append({"product": product, "price_inr": entry.price_inr, "key": OPTION_KEYS.get(product)})
    return offered


def purchase_offers(page_key: str, copy: PageCopy) -> list[dict]:
    """purchase_options() with the words each button shows: `buy_<key>` / `gets_<key>` from this language's copy for a
    tier, the Product's single `button` for a page that sells one thing. The copy is already price-filled."""
    offers = []
    for option in purchase_options(page_key):
        key = option["key"]
        label = copy.extra[f"buy_{key}"] if key else (copy.product.button if copy.product else "")
        offers.append({**option, "label": label, "blurb": copy.extra.get(f"gets_{key}", "") if key else ""})
    return offers


def common_values(lang: str, page_key: str | None = None) -> dict:
    offer = chat_offer()
    values = {name: amount for product, amount in prices().items() if (name := _PRICE_NAMES.get(product))}
    values.update(pack_messages=offer["pack_messages"], free_messages=offer["free_messages"], site_name=site.SITE_NAME)
    # Only for languages that actually have the page: EN_ONLY_TOOL_KEYS exist in one tree, and url_for would
    # raise for the others. An unfilled {url_...} is caught by tests/test_pages_i18n.py rather than shipped.
    for key in ("home", *i18n.TOOL_KEYS, *i18n.EN_ONLY_TOOL_KEYS, "consultation", "rashifal-hub", "rashifal-weekly"):
        if lang in i18n.page_langs(key):
            values["url_" + key.replace("-", "_")] = i18n.url_for(key, lang)
    own = product_price(page_key) if page_key else None
    if own is not None:
        values["price"] = own
    return values


_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")


def _fill(value, values: dict):
    """Recursively fill {placeholders} in every string of a copy structure. Markup stays Markup (values are escaped).
    An unknown placeholder is left as it is, so a caller can fill per-item values later (hub pages fill {rashi} once
    per rashi); tests/test_pages_i18n.py checks that nothing is left unfilled on a rendered page."""
    if isinstance(value, str):
        if "{" not in value:
            return value
        markup = isinstance(value, Markup)

        def substitute(match):
            if match.group(1) not in values:
                return match.group(0)
            found = values[match.group(1)]
            return str(escape(found)) if markup else str(found)

        text = _PLACEHOLDER.sub(substitute, str(value))
        return Markup(text) if markup else text
    if isinstance(value, tuple):
        return tuple(_fill(item, values) for item in value)
    if isinstance(value, list):
        return [_fill(item, values) for item in value]
    if isinstance(value, Mapping):
        return {key: _fill(item, values) for key, item in value.items()}
    if is_dataclass(value):
        return replace(value, **{f.name: _fill(getattr(value, f.name), values) for f in fields(value)})
    return value


def fill(text: str, **values) -> str:
    """Fill placeholders of one already-fetched string (per-rashi labels on the hub pages)."""
    return _fill(text, values)


def rashi_bodies(lang: str) -> dict[str, RashiBody]:
    """{rashi key: RashiBody} of a language - the twelve per-rashi hub bodies."""
    return content(lang).RASHI_BODIES


def raw(page_key: str, lang: str, rashi: str | None = None) -> PageCopy:
    """The copy as written, placeholders intact (tests use this to check no price is hard-coded).

    `rashi` (an i18n.RASHI_KEYS key) folds that rashi's own body into the shared hub copy."""
    module = content(lang)
    # A page the registry gives this tree and not the others keeps its copy in LOCAL_PAGES, because PAGES must
    # equal COPY_KEYS in every module - that equality is what keeps the three trees in step, and a page that
    # exists in one language is not a page whose translation is missing.
    copy = module.PAGES[page_key] if page_key in module.PAGES else getattr(module, "LOCAL_PAGES", {})[page_key]
    if page_key == "rashifal-rashi" and rashi:
        body = rashi_bodies(lang)[i18n.rashi_key(rashi)]
        copy = replace(copy, intro=body.intro, sections=body.sections, faqs=body.faqs)
    return copy


def get(page_key: str, lang: str, **values) -> PageCopy:
    """The copy of a page in a language with every placeholder filled. Extra keyword values win over the common ones.

    A rashi hub is called with the rashi's names (i18n.rashi_names), whose `key` selects that rashi's own body."""
    return _fill(raw(page_key, lang, values.get("key") if page_key == "rashifal-rashi" else None),
                 {**common_values(lang, page_key), **values})
