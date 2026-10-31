"""The Markdown subset the blog accepts, rendered to HTML THIS MODULE BUILT ITSELF.

MARKDOWN, NOT HTML, AND THE REASON IS NOT TASTE. A post body arrives over an HTTP API from a writer
outside this codebase; it is untrusted input in exactly the way a form field is. There are two honest
ways to put untrusted prose on a page: accept HTML and sanitise it, or accept something that is not
HTML and construct the HTML here. Sanitising is the harder of the two to get right - it is a blocklist
in disguise, it needs a library we do not have and would have to keep current, and every mistake in it
is a cross-site scripting hole on a commercial site. So:

  * the body is **escaped first**, in full, before a single construct is recognised. Every `<`, `>`,
    `&` and `"` in the writer's text is already harmless by the time the first regular expression runs;
  * only the constructs listed in `render` below produce a tag, and every tag is a literal in this file.
    There is no path by which a character from the body becomes part of a tag name or an attribute name;
  * raw HTML is not sanitised, stripped or "mostly" handled. `safety.py` REFUSES a body that contains
    anything tag-shaped, so a writer who pastes HTML is told so instead of seeing their markup appear as
    visible text on the live site, which is what silent escaping would have given them.

LINKS AND IMAGES ARE WHERE THE REAL HOLES ARE, so they are allowlisted rather than cleaned:

  * a link may be a site-relative path, an `http(s)` URL or a `#` anchor. `javascript:`, `data:`,
    `mailto:` and anything else is refused, loudly, and rendered as plain text. (`mailto:` is refused on
    a house rule, not a security one: no real person's address goes on a public page here.)
  * an image may ONLY be one we are hosting, under the blog's own media prefix. That is not caution for
    its own sake: `app/hardening.py` sets `img-src 'self' data: ...`, so a remote image in a post would
    be blocked by the site's own Content-Security-Policy and render as a broken box. Refusing it when
    the post arrives tells the writer; allowing it would show the reader a hole in the page.

What is deliberately NOT supported: tables, fenced code blocks, footnotes, inline HTML, reference-style
links, nested lists. Each is a construct nobody has needed yet, and the subset is the security boundary -
it grows when there is a post that needs it, with its own test, not in advance.
"""

from __future__ import annotations

import html
import re

from markupsafe import Markup

from . import paths

#: Control characters, stripped before anything else. A NUL would collide with the sentinel below, and
#: nothing in prose needs one.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_H2 = re.compile(r"^##\s+(?P<text>\S.*)$")
_H3 = re.compile(r"^###\s+(?P<text>\S.*)$")
_H1 = re.compile(r"^#\s+\S")
_BULLET = re.compile(r"^[-*]\s+(?P<text>\S.*)$")
_NUMBER = re.compile(r"^\d{1,2}[.)]\s+(?P<text>\S.*)$")
_QUOTE = re.compile(r"^>\s*(?P<text>.*)$")
_RULE = re.compile(r"^(?:-{3,}|\*{3,})$")

_CODE = re.compile(r"`([^`\n]+)`")
_IMAGE = re.compile(r"!\[(?P<alt>[^\]\n]*)\]\((?P<src>[^()\s]+)\)")
_LINK = re.compile(r"\[(?P<text>[^\]\n]+)\]\((?P<href>[^()\s]+)\)")
_BOLD = re.compile(r"\*\*(?P<text>[^*\n]+)\*\*")
_ITALIC = re.compile(r"(?<![*\w])[*_](?P<text>[^*_\n]+)[*_](?![*\w])")

_SENTINEL = "\x00%d\x00"
_SENTINEL_BACK = re.compile(r"\x00(\d+)\x00")


def media_prefix() -> str:
    """The one prefix an image in a post may come from: `/blog/media/`."""
    return paths.media_template().split("{image_id}")[0]


_LONE_IMAGE = re.compile(r'^<img src="[^"]*" alt="(?P<alt>[^"]*)"[^>]*>$')


def _block_or_figure(inner: str) -> str:
    """A paragraph, or - when the paragraph is nothing but an image - a captioned figure.

    A FIGURE IS NOT PHRASING CONTENT AND CANNOT LIVE IN A <p>. A browser meeting one closes the
    paragraph itself, leaving a stray </p> and a figure with no block parent, which is part of why
    body images sat outside the reading column. So the figure is only made where the image IS the
    block; an image inside a sentence stays an ordinary inline <img>.

    The alt becomes the caption as well. It stays on the img for the readers who never see the page,
    and `aria-hidden` on the caption stops a screen reader reading the same sentence twice. The alt
    is already HTML-escaped - this whole module works over a body escaped in full before any
    construct is recognised - so escaping it again would print "a chart &amp; its houses".
    """
    match = _LONE_IMAGE.match(inner.strip())
    if not match:
        return f"<p>{inner}</p>"
    alt = match.group("alt")
    if not alt.strip():
        return f'<figure class="post__figure">{inner.strip()}</figure>'
    return (f'<figure class="post__figure">{inner.strip()}'
            f'<figcaption aria-hidden="true">{alt}</figcaption></figure>')


def _inline(escaped: str, problems: list[str]) -> str:
    """Inline constructs, applied to text that is ALREADY HTML-escaped. Returns HTML."""
    spans: list[str] = []

    def park(markup: str) -> str:
        """Hold a finished fragment out of the way so later rules cannot reach inside it."""
        spans.append(markup)
        return _SENTINEL % (len(spans) - 1)

    def code(match: re.Match) -> str:
        return park(f"<code>{match.group(1)}</code>")

    def image(match: re.Match) -> str:
        src, alt = match.group("src"), match.group("alt")
        if src.startswith("//") or not src.startswith(media_prefix()):
            problems.append(
                f"the image {src!r} is not hosted here. Upload it with POST /api/blog/images and use the "
                f"`url` that comes back ({media_prefix()}...): the site's Content-Security-Policy allows "
                "images from its own origin only, so a remote image renders as a broken box")
            return park(f"<em>{alt}</em>" if alt else "")
        if not alt.strip():
            problems.append(f"the image {src!r} has no alt text; describe it in the square brackets")
        # loading="lazy" and the explicit alt are the whole of what we add here. Whether this
        # becomes a captioned <figure> is decided in close_paragraph(), which is the only place that
        # knows whether the image is the whole block or a word inside a sentence.
        return park(f'<img src="{src}" alt="{alt}" loading="lazy" decoding="async">')

    def link(match: re.Match) -> str:
        href, text = match.group("href"), match.group("text")
        if href.startswith("//"):
            # A PROTOCOL-RELATIVE URL IS NOT A PATH. "//evil.invalid/x" starts with a slash and navigates
            # off this site entirely, so the "starts with /" test below used to let it straight through.
            # Checked first, and separately, because the two look identical at a glance.
            problems.append(
                f"the link target {href!r} starts with // , which is another site and not a path on "
                "this one. Write the full https:// URL if that is what was meant")
            return park(text)
        if href.startswith("/"):
            return park(f'<a href="{href}">{text}</a>')
        if href.startswith("#"):
            return park(f'<a href="{href}">{text}</a>')
        if href.lower().startswith(("https://", "http://")):
            # A writer-supplied outbound link carries no endorsement and must not open in our tab with a
            # handle on our window: `noopener` is what closes that, `nofollow ugc` is what says the link
            # was not an editorial choice of ours.
            return park(f'<a href="{href}" rel="nofollow ugc noopener" target="_blank">{text}</a>')
        problems.append(
            f"the link target {href!r} is not allowed. A link may be a path on this site (\"/birth-chart\"), "
            "an https:// URL or a \"#\" anchor on the same page. javascript:, data: and mailto: are refused - "
            "the first two because they execute, mailto: because no real address goes on a public page here")
        return park(text)

    out = _CODE.sub(code, escaped)
    out = _IMAGE.sub(image, out)
    out = _LINK.sub(link, out)
    out = _BOLD.sub(lambda m: f"<strong>{m.group('text')}</strong>", out)
    out = _ITALIC.sub(lambda m: f"<em>{m.group('text')}</em>", out)
    return _SENTINEL_BACK.sub(lambda m: spans[int(m.group(1))], out)


def render(body: str) -> tuple[Markup, list[str]]:
    """(html, problems). `problems` is blocking: a post with any of them stays a draft.

    The HTML is `Markup`, so a template prints it as markup - which is safe here for one reason only,
    that every tag in it was written as a literal in this file over text escaped on the way in.
    """
    problems: list[str] = []
    text = _CONTROL.sub("", body or "").replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    #: The list currently open, so consecutive bullets become one <ul> rather than one each.
    open_list: str | None = None
    paragraph: list[str] = []
    quote: list[str] = []

    def close_paragraph() -> None:
        if paragraph:
            inner = _inline(html.escape(" ".join(paragraph)), problems)
            out.append(_block_or_figure(inner))
            paragraph.clear()

    def close_quote() -> None:
        if quote:
            inner = _inline(html.escape(" ".join(quote)), problems)
            out.append(f"<blockquote><p>{inner}</p></blockquote>")
            quote.clear()

    def close_list() -> None:
        nonlocal open_list
        if open_list:
            out.append(f"</{open_list}>")
            open_list = None

    def close_all() -> None:
        close_paragraph()
        close_quote()
        close_list()

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            close_all()
            continue
        if _H1.match(line):
            # The post's H1 is its title, rendered by the template. A second one on the page is a real
            # defect - tests/test_pages_i18n.py asserts exactly one H1 on every indexable page - so this
            # is refused rather than quietly demoted to an H2 the writer did not ask for.
            problems.append("a top-level heading (`# ...`) in the body: the post's one H1 is its title. "
                            "Use `## ` for a section and `### ` under it")
            close_all()
            continue
        if (match := _H3.match(line)):
            close_all()
            out.append(f"<h3>{_inline(html.escape(match.group('text')), problems)}</h3>")
            continue
        if (match := _H2.match(line)):
            close_all()
            out.append(f"<h2>{_inline(html.escape(match.group('text')), problems)}</h2>")
            continue
        if _RULE.match(line):
            close_all()
            out.append("<hr>")
            continue
        if (match := _QUOTE.match(line)):
            close_paragraph()
            close_list()
            quote.append(match.group("text").strip())
            continue
        for pattern, tag in ((_BULLET, "ul"), (_NUMBER, "ol")):
            if (match := pattern.match(line)):
                close_paragraph()
                close_quote()
                if open_list != tag:
                    close_list()
                    out.append(f"<{tag}>")
                    open_list = tag
                out.append(f"<li>{_inline(html.escape(match.group('text')), problems)}</li>")
                break
        else:
            close_quote()
            close_list()
            paragraph.append(line)
    close_all()
    return Markup("\n".join(out)), problems


def plain_text(body: str) -> str:
    """The words a reader actually sees, with the markup taken off.

    The safety screens run on THIS and not on the raw body: `app/ai/safety.py` measures how close a
    commerce word sits to the name of a stone, within one sentence, and a URL sitting between the two
    would push them apart in the raw text while the reader sees them side by side. Screening what is
    read is the only version of that measurement that means anything.
    """
    text = _CONTROL.sub("", body or "").replace("\r\n", "\n")
    text = _IMAGE.sub(lambda m: m.group("alt"), text)
    text = _LINK.sub(lambda m: m.group("text"), text)
    text = _CODE.sub(lambda m: m.group(1), text)
    text = re.sub(r"^#{1,6}\s+|^>\s*|^[-*]\s+|^\d{1,2}[.)]\s+", "", text, flags=re.M)
    text = re.sub(r"\*\*|[*_]", "", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def word_count(body: str) -> int:
    return len(plain_text(body).split())
