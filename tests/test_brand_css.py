"""The two brand colour rules that are easiest to lose in a later edit, enforced mechanically.

1. **Never light text on a gold background.** Gold `#E0A526` + white is 2.19:1 and fails WCAG AA; gold + Ink is
   7.65:1. The guidelines call a gold-background component with white text a bug to flag in review - so this file
   flags it instead, by measuring the contrast of every declared pair rather than by looking for the literal `#fff`.
2. **Caution is `--color-warning` `#A13D2B` - never Saffron, never a plain red.** It carries active mangal dosha,
   active sade sati and the caution windows (the accuracy caveats under a chart). Checked in the stylesheet AND in
   what static/js/render.js actually renders for an active dosha.

The parser here is deliberately small: it only needs selectors, declarations and `var()` resolution, which is all
site.css uses. A rule the parser cannot understand shows up as an unparsed colour, not as a silent pass.
"""

import json
import re

import pytest

from app.web import STATIC_DIR

CSS_PATH = STATIC_DIR / "css" / "site.css"
CSS = CSS_PATH.read_text(encoding="utf-8")

AA = 4.5  # WCAG AA for normal-size text
GOLD_TOKENS = ("--color-accent", "--color-accent-dark", "--color-accent-soft")
BACKGROUND_PROPS = ("background", "background-color")

# The surfaces that state "this is a caution": Brand §5. `.accuracy` is the near-cusp / non-standard-clock
# caveat block rendered by render.js `accuracyHtml`, which the guidelines count as a caution indicator.
CAUTION_RULES = (".banner--warn", ".badge--warn", ".accuracy", ".accuracy h3",
                 "tr.is-flagged th, tr.is-flagged td", ".form-status--error",
                 ".pay-status--delayed, .pay-status--unpaid")
# Colours a caution surface is allowed to use: the Warning family plus Ink. Anything else - Saffron, a plain
# red, last year's amber - is the failure this test exists for.
CAUTION_PALETTE = {"#a13d2b", "#fbede9", "#e8c6bd", "#1e1b2e", "#fdf6f4"}

# `.swatch--*` are the rashifal "lucky colour" chips: each one paints the literal colour it names, so a red
# swatch is the word "red" drawn, not a status. Nothing else in the sheet may be a plain red.
SWATCH = re.compile(r"^\.swatch--")


# ---------------------------------------------------------------- tiny CSS reader


def _declarations(body: str) -> dict[str, str]:
    decls = {}
    for part in body.split(";"):
        if ":" not in part:
            continue
        name, _, value = part.partition(":")
        decls[name.strip().lower()] = value.strip()
    return decls


def _rules(css: str) -> list[tuple[str, dict[str, str]]]:
    """[(selector list, declarations)] in source order; @media / @supports blocks are flattened into it."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found: list[tuple[str, dict[str, str]]] = []

    def walk(text: str) -> None:
        index = 0
        while (open_brace := text.find("{", index)) != -1:
            selector = text[index:open_brace].strip()
            depth, cursor = 1, open_brace + 1
            while cursor < len(text) and depth:
                depth += (text[cursor] == "{") - (text[cursor] == "}")
                cursor += 1
            body = text[open_brace + 1:cursor - 1]
            if selector.startswith("@"):
                if selector.split()[0] in ("@media", "@supports"):
                    walk(body)
            elif selector:
                found.append((selector, _declarations(body)))
            index = cursor

    walk(css)
    return found


RULES = _rules(CSS)
ROOT_TOKENS = {name: value for selector, decls in RULES if selector == ":root"
               for name, value in decls.items() if name.startswith("--")}


def _resolve(value: str, depth: int = 0) -> str:
    """Substitute var(--token) from :root, repeatedly (the sheet nests them at most two deep)."""
    while "var(" in value and depth < 6:
        value = re.sub(r"var\((--[a-z0-9-]+)(?:\s*,[^)]*)?\)",
                       lambda m: ROOT_TOKENS.get(m.group(1), m.group(0)), value)
        depth += 1
    return value.strip()


def _rgb(value: str) -> tuple[int, int, int] | None:
    """The colour a declaration paints, or None when it paints none (transparent, a gradient, a keyword)."""
    value = _resolve(value).lower()
    if match := re.search(r"#([0-9a-f]{6})\b", value):
        digits = match.group(1)
        return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))
    if match := re.search(r"#([0-9a-f]{3})\b", value):
        return tuple(int(c * 2, 16) for c in match.group(1))
    if match := re.search(r"rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)\s*(?:[,/]\s*([\d.]+))?", value):
        # A translucent wash is not a fill: `rgba(224, 165, 38, .22)` over the indigo CTA panel is a dark
        # tint, not gold, so it is not what "a gold background" means. Only near-opaque values count.
        if match.group(4) is not None and float(match.group(4)) < 0.9:
            return None
        return tuple(int(part) for part in match.groups()[:3])
    if re.search(r"\bwhite\b", value):
        return (255, 255, 255)
    if re.search(r"\bblack\b", value):
        return (0, 0, 0)
    return None


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def _luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for raw in rgb:
        part = raw / 255
        channels.append(part / 12.92 if part <= 0.03928 else ((part + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(one: tuple[int, int, int], other: tuple[int, int, int]) -> float:
    high, low = sorted((_luminance(one), _luminance(other)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _compound(selector: str) -> str:
    """The rightmost compound of a selector, without pseudo-classes: ".cta .btn--cta:hover" -> ".btn--cta"."""
    last = re.split(r"[\s>+~]+", selector.strip())[-1]
    return re.split(r"::?(?![-\w]*\()", last)[0] or last


def _selectors(selector_list: str) -> list[str]:
    return [part.strip() for part in selector_list.split(",") if part.strip()]


def _background(decls: dict[str, str]) -> str | None:
    for prop in BACKGROUND_PROPS:
        if prop in decls:
            return decls[prop]
    return None


GOLDS = {_hex(_rgb(ROOT_TOKENS[token])) for token in GOLD_TOKENS}


def _is_gold(value: str | None) -> bool:
    rgb = _rgb(value) if value else None
    return rgb is not None and _hex(rgb) in GOLDS


# ---------------------------------------------------------------- rule 1: nothing light on gold


def test_the_three_gold_tokens_are_the_brand_gold():
    assert ROOT_TOKENS["--color-accent"].strip().lower() == "#e0a526"
    for token in GOLD_TOKENS:
        gold, ink = _rgb(ROOT_TOKENS[token]), _rgb(ROOT_TOKENS["--color-ink"])
        assert contrast(gold, ink) >= AA, f"{token} is no longer legible under Ink"
        assert contrast(gold, (255, 255, 255)) < AA, f"{token} is not a gold any more - re-check Brand §2"


def test_no_css_rule_puts_light_text_on_a_gold_background():
    """Rule 1. Two halves, because a light colour can arrive from either side:

    a) a rule that paints gold must say what colour its text is, and that pair must clear 4.5:1;
    b) a rule that sets text too light for gold must not target an element that is ever gold - unless it
       repaints the background itself (that is how the outlined `.cta__option--lite` button stays white).
    """
    gold_compounds = {_compound(selector) for selector_list, decls in RULES
                      if _is_gold(_background(decls)) for selector in _selectors(selector_list)}
    assert gold_compounds, "no gold background found at all - has the palette moved?"

    failures = []
    for selector_list, decls in RULES:
        background, colour = _background(decls), decls.get("color")
        if _is_gold(background):
            if colour is None:
                failures.append(f"{selector_list}: paints gold but never says what colour its text is")
                continue
            text, gold = _rgb(colour), _rgb(background)
            if text is None or contrast(text, gold) < AA:
                failures.append(f"{selector_list}: color {colour} on gold {background} "
                                f"is {contrast(text, gold):.2f}:1" if text else
                                f"{selector_list}: unreadable color value {colour!r} on gold")
            continue
        if colour is None or (text := _rgb(colour)) is None:
            continue
        if background is not None:  # the rule repaints the surface, so it is not on gold
            continue
        if min(contrast(text, _rgb(gold)) for gold in GOLDS) >= AA:
            continue
        for selector in _selectors(selector_list):
            if _compound(selector) in gold_compounds:
                failures.append(f"{selector_list}: color {colour} would land on the gold "
                                f"{_compound(selector)} and fails AA there")
    assert not failures, "gold with light text (Brand §2 - never ship this):\n  " + "\n  ".join(failures)


# ---------------------------------------------------------------- rule 2: caution is Warning, nothing else


def test_warning_is_the_brand_maroon_and_is_readable_both_ways():
    assert ROOT_TOKENS["--color-warning"].strip().lower() == "#a13d2b"
    warning = _rgb(ROOT_TOKENS["--color-warning"])
    assert contrast(warning, (255, 255, 255)) >= AA          # white text on a Warning fill
    assert contrast(warning, _rgb(ROOT_TOKENS["--color-bg"])) >= AA        # Warning as text on cream
    assert contrast(warning, _rgb(ROOT_TOKENS["--color-warning-bg"])) >= AA  # and on its own tint


@pytest.mark.parametrize("selector", CAUTION_RULES)
def test_every_caution_surface_uses_the_warning_palette_and_nothing_else(selector):
    """Rule 2. Active mangal dosha, active sade sati and the caution windows are Warning - not Saffron, not a
    plain red, not whatever amber the sheet happened to have before."""
    matched = [decls for selector_list, decls in RULES if selector_list == selector]
    assert matched, f"{selector} has disappeared from site.css - caution has to live somewhere"
    saffron = _hex(_rgb(ROOT_TOKENS["--color-saffron"]))
    for decls in matched:
        for prop, value in decls.items():
            if prop == "color" or prop.startswith("background") or "border" in prop:
                rgb = _rgb(value)
                if rgb is None:
                    continue
                assert _hex(rgb) != saffron, f"{selector} {prop}: Saffron is not the caution colour (Brand §5)"
                assert _hex(rgb) in CAUTION_PALETTE, (
                    f"{selector} {prop}: {_hex(rgb)} is outside the Warning palette {sorted(CAUTION_PALETTE)}")


def test_no_plain_red_survives_anywhere_in_the_stylesheet():
    """"Not plain red" is the other half of rule 2: a later edit must not reach for #c00 for a dosha."""
    allowed = {_rgb(ROOT_TOKENS[token]) for token in ("--color-warning", "--color-saffron")}
    strays = []
    for selector_list, decls in RULES:
        if selector_list == ":root":
            continue  # the palette declares Saffron and Warning; where they may be USED is the test above
        if any(SWATCH.match(selector) for selector in _selectors(selector_list)):
            continue  # a lucky-colour chip paints the colour it names
        for prop, value in decls.items():
            rgb = _rgb(value)
            if rgb is None or rgb in allowed:
                continue
            red, green, blue = rgb
            if red >= 140 and red >= 1.8 * green and red >= 1.8 * blue:
                strays.append(f"{selector_list} {{ {prop}: {value} }} -> {_hex(rgb)}")
    assert not strays, "plain red found; caution is --color-warning (Brand §5):\n  " + "\n  ".join(strays)


def test_saffron_is_never_a_text_colour():
    """Brand §2: every badge and tag this product ships is far below WCAG's "large text", so Saffron's
    3.63:1 has no exemption to hide behind. It is a fill colour only."""
    saffron = _rgb(ROOT_TOKENS["--color-saffron"])
    used_as_text = [selector_list for selector_list, decls in RULES
                    if "color" in decls and _rgb(decls["color"]) == saffron]
    assert not used_as_text, f"Saffron used as text in: {used_as_text}"


# ---------------------------------------------------------------- rule 2, as the page actually renders it


MANGLIK_BIRTH = {"date": "1984-02-19", "time": "09:05", "city": "Pune"}  # manglik, no classical cancellation


@pytest.fixture(scope="module")
def js():
    """static/js/render.js in an embedded V8, as tests/test_web.py runs it."""
    mini_racer = pytest.importorskip("py_mini_racer")
    context = mini_racer.MiniRacer()
    context.eval((STATIC_DIR / "js" / "render.js").read_text(encoding="utf-8"))

    def call(expression: str, **variables):
        names = ", ".join(variables)
        args = ", ".join(json.dumps(value, ensure_ascii=False) for value in variables.values())
        return json.loads(context.eval(f"JSON.stringify((function({names}) {{ return {expression}; }})({args}))"))

    return call


def test_an_active_mangal_dosha_renders_with_the_warning_tone(js):
    from tests.test_web import client  # the same TestClient the rendering tests use

    response = client.post("/api/mangal-dosha", json=MANGLIK_BIRTH)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["mangal_dosha"]["present"] and not data["mangal_dosha"]["cancellation_applies"], \
        "this birth is no longer an uncancelled mangal dosha - pick another one"
    html = js("AstroRender.renderers.mangalDosha(data, ctx)", data=data, ctx={"lang": "en"})
    assert "banner banner--warn" in html, "an active mangal dosha must carry the caution tone"
    assert "badge badge--warn" in html


def test_an_active_sade_sati_renders_with_the_warning_tone(js):
    """`active` depends on where Saturn is today, so the flag is set on a real response rather than waited for:
    the branch under test is the renderer's, and this pins which tone it picks."""
    from tests.test_web import client

    response = client.post("/api/sade-sati", json=MANGLIK_BIRTH)
    assert response.status_code == 200, response.text
    data = json.loads(response.text)
    data["sade_sati"]["active"], data["sade_sati"]["phase"] = True, "peak"
    html = js("AstroRender.renderers.sadeSati(data, ctx)", data=data, ctx={"lang": "en"})
    assert "banner banner--warn" in html, "an active sade sati must carry the caution tone, not the info tone"

    data["sade_sati"]["active"] = False
    quiet = js("AstroRender.renderers.sadeSati(data, ctx)", data=data, ctx={"lang": "en"})
    assert "banner--warn" not in quiet, "only an ACTIVE sade sati is a caution (Brand §5: don't decorate everything)"


def test_the_accuracy_caveats_are_styled_as_a_caution_window():
    """The near-cusp and non-standard-clock notes are caution indicators, so they wear Warning rather than the
    neutral info tint they used to share with "here is a fact about your chart"."""
    accuracy = {selector_list: decls for selector_list, decls in RULES if selector_list in (".accuracy", ".accuracy h3")}
    assert _hex(_rgb(accuracy[".accuracy"]["background"])) == _hex(_rgb(ROOT_TOKENS["--color-warning-bg"]))
    assert _hex(_rgb(accuracy[".accuracy h3"]["color"])) == _hex(_rgb(ROOT_TOKENS["--color-warning"]))
    body = _rgb(accuracy[".accuracy"]["color"])
    assert contrast(body, _rgb(accuracy[".accuracy"]["background"])) >= AA


# ---------------------------------------------------------------- the chart, in both stylesheets

# app/pdf/chart_svg.py and static/js/render.js emit ONE set of class names for the kundali, and two
# stylesheets paint them: this one for the screen, app/pdf/templates/print.css for the book. The geometry
# cannot drift - tests/test_pdf.py compares the two SVGs label by label and coordinate by coordinate - but
# until this test the COLOURS could, silently, and the signature visual would quietly stop being the same
# object in the report and on the page. Stroke widths and font sizes are free to differ (a 76mm print
# chart and a 390px screen chart want different hairlines); the paint is not.
PRINT_CSS_PATH = CSS_PATH.parents[2] / "pdf" / "templates" / "print.css"
CHART_CLASSES = (".kundali__frame", ".kundali__lines", ".kundali__sign",
                 ".kundali__graha", ".kundali__graha--lagna", ".kundali__retro")
PAINT_PROPS = ("fill", "stroke", "color", "background", "background-color")


def _sheet(path):
    """(rules, :root tokens) of a stylesheet."""
    rules = _rules(path.read_text(encoding="utf-8"))
    tokens = {name: value for selector, decls in rules if selector == ":root"
              for name, value in decls.items() if name.startswith("--")}
    return rules, tokens


def _painted(rules, tokens, monkeypatch) -> dict[str, dict[str, str]]:
    """{class: {paint property: resolved hex}} - resolved against THAT sheet's own tokens."""
    monkeypatch.setattr("tests.test_brand_css.ROOT_TOKENS", tokens)
    painted: dict[str, dict[str, str]] = {name: {} for name in CHART_CLASSES}
    for selector_list, decls in rules:
        for selector in _selectors(selector_list):
            if selector not in painted:
                continue
            for prop in PAINT_PROPS:
                if prop in decls:
                    rgb = _rgb(decls[prop])
                    painted[selector][prop] = _hex(rgb) if rgb else decls[prop].strip().lower()
    return painted


def test_the_kundali_chart_is_painted_identically_in_both_stylesheets(monkeypatch):
    web_rules, web_tokens = _sheet(CSS_PATH)
    print_rules, print_tokens = _sheet(PRINT_CSS_PATH)
    web = _painted(web_rules, web_tokens, monkeypatch)
    book = _painted(print_rules, print_tokens, monkeypatch)
    monkeypatch.setattr("tests.test_brand_css.ROOT_TOKENS", web_tokens)  # leave the module as we found it

    differences = []
    for name in CHART_CLASSES:
        assert web[name], f"{name} is not painted at all by site.css"
        assert book[name], f"{name} is not painted at all by print.css"
        for prop in sorted(set(web[name]) | set(book[name])):
            on_screen, in_book = web[name].get(prop), book[name].get(prop)
            if on_screen != in_book:
                differences.append(f"{name} {{ {prop} }}: site.css {on_screen}, print.css {in_book}")
    assert not differences, ("the kundali is the signature visual and must be one object in the book and on "
                            "the page (Brand §5):\n  " + "\n  ".join(differences))


def test_the_chart_is_legible_on_its_own_indigo_ground(monkeypatch):
    """Whatever the two sheets agree on, it still has to be readable: the grahas are what a reader reads."""
    _, tokens = _sheet(CSS_PATH)
    monkeypatch.setattr("tests.test_brand_css.ROOT_TOKENS", tokens)
    ground = _rgb(tokens["--color-card"])
    for token, floor in (("--color-on-dark", AA), ("--color-meta-dark", AA), ("--color-accent", 3.0)):
        ratio = contrast(_rgb(tokens[token]), ground)
        assert ratio >= floor, f"{token} on --color-card is {ratio:.2f}:1"
