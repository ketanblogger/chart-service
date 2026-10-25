"""The header's collapsed state is decided by CSS, not by a script that runs a second later.

THE LARGEST LAYOUT SHIFT ON THE SITE, and it was on every page. nav.js added `is-collapsed` and
revealed the disclosure button after it ran, so on a phone the header painted as a wrapped list 347px
tall and snapped to 122px when the deferred script executed - about a second in on a throttled
connection - taking every page's content up 128px with it. 0.1442 CLS on the English home page.

IT WAS NOT THE STYLESHEET. The first diagnosis blamed a 95.7 KB render-blocking site.css arriving after
first paint. Inlining the ENTIRE stylesheet into the document changed the number not at all - it stayed
0.1442 to four decimal places - which is what sent the search back to the scripts.

THE NO-JAVASCRIPT GUARANTEE IS UNCHANGED and is the reason the old design existed: without the script,
the full list is visible and there is no button that cannot open. It is expressed in a <noscript> block
now instead of by a script, which is the one state CSS cannot detect for itself.
"""
from __future__ import annotations

import re
from pathlib import Path

CSS = Path("app/static/css/site.css").read_text(encoding="utf-8")
NAV_JS = Path("app/static/js/nav.js").read_text(encoding="utf-8")
BASE = Path("app/web/templates/base.html").read_text(encoding="utf-8")


def test_the_script_no_longer_decides_the_header_layout():
    """It may open and close. It may not collapse, reveal, or hide - those happen after it runs, which
    is a second too late and is the whole defect."""
    assert "is-collapsed" not in _code(NAV_JS), "nav.js still sets the collapsed class"
    assert "toggle.hidden" not in _code(NAV_JS), "nav.js still reveals or hides the button"
    assert "is-open" in NAV_JS, "nav.js no longer opens the menu at all"


def test_the_button_does_not_ship_hidden():
    """`hidden` on the button is what made a script necessary to reveal it."""
    button = re.search(r"<button[^>]*site-nav__toggle[^>]*>", BASE)
    assert button, "the disclosure button is gone"
    assert " hidden" not in button.group(0), "the button still ships hidden"


def test_the_collapse_is_a_media_query():
    assert re.search(r"@media \(max-width: 899px\) \{[^}]*\.site-nav > ul \{ display: none", CSS, re.S), \
        "the collapsed state is not the CSS default below the breakpoint"


def test_nothing_is_keyed_on_a_class_no_longer_set():
    """A rule waiting for `is-collapsed` is a rule that never applies - and one of them left the account
    list open at every width below 760px, 44px of header that had not been there before. A screenshot
    comparison found it by SIZE; nothing else would have."""
    rules = re.sub(r"/\*.*?\*/", " ", CSS, flags=re.S)
    assert "is-collapsed" not in rules, "a stylesheet rule still waits for a class nothing sets"


def test_the_account_list_follows_the_menu():
    """Stated in the stylesheet's own comment: the account follows the menu rather than having a second
    behaviour. Both are collapsed by default and both open together."""
    rules = re.sub(r"/\*.*?\*/", " ", CSS, flags=re.S)
    block = rules[rules.index("@media (max-width: 760px)"):]
    block = block[:block.index("\n}")]
    assert ".site-nav > ul.site-nav__accountlist { display: none; }" in block
    assert ".site-nav.is-open > ul.site-nav__accountlist { display: flex" in block


def test_without_scripting_the_full_list_is_restored():
    """THE GUARANTEE. A disclosure control that cannot open is worse than no control."""
    assert "<noscript>" in BASE
    block = BASE[BASE.index("<noscript>"):BASE.index("</noscript>")]
    assert ".site-nav > ul { display: flex !important; }" in block, "the list is not restored"
    assert ".site-nav__toggle { display: none !important; }" in block, "the dead button is not hidden"
    assert BASE.index("<noscript>") < BASE.index('<nav class="site-nav"'), \
        "the fallback must be parsed before the nav it corrects"


def _code(source: str) -> str:
    """The source with comments stripped - so prose describing the old behaviour does not read as it."""
    return re.sub(r"/\*.*?\*/|//[^\n]*", " ", source, flags=re.S)
