"""The review sheet: both sources' readings side by side, with a box for the decision.

WHY A PDF AND NOT A PAGE. This is read away from the machine, next to a printed copy, by somebody
checking a text they know. It wants to be printable, paginated and in a font that renders Devanagari
correctly - which is the PDF path this project already has.

THE SHEET IS NOT A DRAFT OF THE PAGE. It shows every pada where the two sources differ, both
readings, and nothing else: no meanings, no translation, no commentary. The decision it collects is
"which reading is the text", and anything else on the sheet is a distraction from that.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from html.parser import HTMLParser

DEVA = re.compile(r"[ऀ-ॿ]")
# THE ASCII PIPE COUNTS AS A DANDA. Devanagari text typed on a Latin keyboard routinely uses | and
# || for । and ॥, and one of these sources does it throughout - Lingashtakam extracted to ZERO padas
# when the filter recognised only the real characters, which is a silent way to lose a whole text.
DANDA = re.compile(r"[।॥|]")

#: Above the longest genuine pada seen (Shiv Tandav, 84) and below the shortest prose intrusion
#: seen (94). See the comment in `padas`.
MAX_PADA = 90


def padas(lines, *, require_danda: bool = False) -> list[str]:
    """Verse padas from a source's lines.

    A DANDA IS THE DISCRIMINATOR. Devotional sites wrap the text in navigation, headings and
    promotional strips that are all in Devanagari, so "is it Devanagari" does not separate the
    recitation from the furniture - "प्रेरक कहानियाँ" is a menu item. What every pada of a chalisa
    has and no menu item has is a danda ending it.
    """
    out = []
    for line in lines:
        if len(DEVA.findall(line)) < 10:
            continue
        # REQUIRING A DANDA DROPS REAL VERSE, and it took three catches to accept that. It was the
        # only thing separating text from navigation when whole PAGES were read; once the text is
        # taken from its container and anchor text is skipped, it filters almost nothing - a
        # devotional page's own prose carries dandas too, because Hindi prose ends sentences with
        # one - and it quietly removes any line punctuated some other way:
        #
        #   * the Gayatri Mantra's first two padas carry no danda, so the mantra came out halved;
        #   * Sankat Mochan Hanuman Ashtak punctuates with COMMAS - बाल समय रवि भक्षी लियो तब, -
        #     so 28 of its 55 padas vanished, the opening line among them;
        #   * the Hanuman Chalisa's OPENING DOHAS end in commas too. श्रीगुरु चरन सरोज रज is the
        #     single most recited line in the batch and it was being dropped, which is how "86
        #     padas, exactly right" turned out to be 86 padas with six of the most famous missing.
        #     The real count is 92: two opening dohas at four padas each, forty chaupais at two,
        #     and a closing doha.
        #
        # The parameter stays so a caller with a known-noisy source can ask for it, and nothing in
        # this repository does.
        if require_danda and not DANDA.search(line):
            continue
        line = re.sub(r"&#?\w+;", " ", line)
        for chunk in DANDA.split(line):
            chunk = re.sub(r"[०-९0-9]+", " ", chunk)
            chunk = unicodedata.normalize("NFC", " ".join(chunk.split()))
            # AND NOT PROSE. Hindi prose uses the danda as a FULL STOP, so a devotional page's
            # own introduction - "भक्त अपने जीवन में पैदा हुई कठिनाइयों और बाधाओं को दूर करने के
            # लिए..." - passes the danda test and lands in the middle of the scripture. It did,
            # for several texts, before anyone looked at a rendered sheet.
            #
            # Length separates them. A pada is a half-line: median 23 characters across these
            # twenty-one texts, and the longest genuine one is Shiv Tandav's at 84 - that metre is
            # famously long. The prose intrusions run 100 to 193. The cap sits above the real
            # maximum and below the shortest intrusion, and it is a heuristic rather than a rule,
            # which is one more reason every text goes past a reader before it goes live.
            if len(DEVA.findall(chunk)) >= 10 and len(chunk) <= MAX_PADA:
                out.append(chunk)
    return _without_prose(out)


LATIN = re.compile(r"[A-Za-z]{3,}")


def _without_prose(candidates: list[str]) -> list[str]:
    """Drop what is not recitation, using the text's own shape rather than a fixed number.

    TWO THINGS SURVIVE THE DANDA AND THE CAP. A sidebar link - "Ram Stuti Lyrics in Hindi and
    English - श्री रामचन्द्र..." - appeared inside five different texts, and a site's own
    promotional paragraph - "भगवान गणेश की कृपा पाने और सुख-समृद्धि के लिए नियमित..." - inside
    three. Both are under the cap.

    Latin letters settle the first: these texts are Devanagari throughout, and a run of three or
    more Latin letters is a link or a heading from the page around them.

    The second is settled by the text's OWN median. A fixed cap cannot do it: Shiv Tandav's padas
    run to 84 characters because that metre is long, while a 78-character line in Shiv Chalisa -
    median 23 - is three times everything around it and is prose. Measuring each text against
    itself is the only version of this that works for both.
    """
    if not candidates:
        return []
    lengths = sorted(len(c) for c in candidates)
    median = lengths[len(lengths) // 2]
    limit = max(60, int(median * 2.5))
    return [c for c in candidates if len(c) <= limit and not LATIN.search(c)]


def fold(pada: str) -> str:
    """What two sources must agree on: the syllables, not how they were typeset.

    Final anusvara against final म्, compounding and spacing are folded; a different VOWEL or a
    different consonant is not, because that is a different word in a text people say aloud.
    """
    flat = "".join(DEVA.findall(pada)).replace("ऽ", "")
    flat = re.sub(r"ं$|म्$", "", flat)
    return flat.replace("ं", "म्")


def compare(a: list[str], b: list[str]) -> list[dict]:
    """One row per pada of source A: agreed, or differing with B's nearest reading."""
    index = {fold(x): x for x in b}
    rows = []
    for pada in a:
        folded = fold(pada)
        if folded in index:
            rows.append({"state": "agree", "a": pada, "b": index[folded]})
            continue
        near = difflib.get_close_matches(folded, list(index), n=1, cutoff=0.6)
        rows.append({"state": "differ", "a": pada, "b": index[near[0]] if near else ""})
    return rows


def summary(rows: list[dict]) -> dict:
    agree = sum(1 for r in rows if r["state"] == "agree")
    differ = [r for r in rows if r["state"] == "differ"]
    return {"padas": len(rows), "agree": agree, "differ": len(differ),
            "unmatched": sum(1 for r in differ if not r["b"])}


def build_html(*, title: str, slug: str, source_a: str, source_b: str,
               rows: list[dict], css: str) -> str:
    """The sheet. Plain tables, because it is printed and ticked with a pen."""
    from markupsafe import escape

    counts = summary(rows)
    differences = []
    for number, row in enumerate((r for r in rows if r["state"] == "differ"), start=1):
        b = escape(row["b"]) if row["b"] else "<em>no comparable reading in source B</em>"
        differences.append(
            f'<tr><td class="rv-n">{number}</td>'
            f'<td class="rv-read"><span class="rv-src">A</span> {escape(row["a"])}<br>'
            f'<span class="rv-src">B</span> {b}</td>'
            f'<td class="rv-box">A &#9744;<br>B &#9744;</td></tr>')
    full = "".join(
        f'<li class="{r["state"]}">{escape(r["a"])}</li>' for r in rows)
    return f"""<!doctype html>
<html lang="hi"><head><meta charset="utf-8"><title>{escape(title)} — review</title>
<style>{css}</style></head>
<body class="rv">
<h1>{escape(title)}</h1>
<p class="rv-meta">Review sheet · {slug}</p>
<table class="rv-sources">
  <tr><th>Source A</th><td>{escape(source_a)}</td></tr>
  <tr><th>Source B</th><td>{escape(source_b)}</td></tr>
  <tr><th>Padas</th><td>{counts['padas']} — {counts['agree']} agree,
      {counts['differ']} differ ({counts['unmatched']} with no comparable reading)</td></tr>
</table>
<p class="rv-note">Tick the reading that is the text. Where neither is right, write the correct
one beside it. Only the verse text is in question here — meanings and notes are not taken from
either source.</p>
<h2>Differences</h2>
<table class="rv-diff">
  <thead><tr><th>#</th><th>Reading</th><th>Choose</th></tr></thead>
  <tbody>{''.join(differences) or '<tr><td colspan="3">The two sources agree throughout.</td></tr>'}</tbody>
</table>
<h2>Full text as source A has it</h2>
<ol class="rv-full">{full}</ol>
</body></html>"""


def build_single_source_html(*, title: str, slug: str, source: str, verses: list[str],
                             css: str) -> str:
    """A sheet for a text with ONE source: the whole thing, large, to be read rather than compared.

    THIS IS A DIFFERENT JOB FROM THE COMPARISON SHEET and looks different on purpose. There is no
    second reading to put beside each pada, so there is nothing to tick line by line; what the
    reader is doing is reading the text they know and marking anything wrong. So the type is large,
    the padas are numbered so a correction can be pointed at, and there is room in the margin.

    A text approved this way becomes verified: the reader IS the second source. That is why the
    sheet says so at the top - somebody signing it should know what their signature means.
    """
    from markupsafe import escape

    lines = "".join(
        f'<li><span class="sv-t">{escape(v)}</span></li>' for v in verses)
    return f"""<!doctype html>
<html lang="hi"><head><meta charset="utf-8"><title>{escape(title)} — review</title>
<style>{css}</style></head>
<body class="rv sv">
<h1>{escape(title)}</h1>
<p class="rv-meta">Single-source review sheet · {slug} · {len(verses)} padas</p>
<table class="rv-sources">
  <tr><th>Source</th><td>{escape(source)}</td></tr>
  <tr><th>Second</th><td>None found. <strong>Your reading is the second check</strong> — a text you
      approve here becomes verified and can be given a release date.</td></tr>
</table>
<p class="rv-note">Read it as you would recite it. Mark anything wrong in the margin; the pada
numbers are there so a correction can be pointed at. Only the verse text is in question — no
meaning or note is taken from the source.</p>
<ol class="sv-list">{lines}</ol>
<p class="sv-sign">Approved as correct &#9744;&nbsp;&nbsp;&nbsp;Corrections marked above
&#9744;&nbsp;&nbsp;&nbsp;Date ______________</p>
</body></html>"""


class _Container(HTMLParser):
    """Collect the text of ONE element, by tag and class, and nothing around it.

    WHY A PARSER AND NOT A REGEX OVER THE PAGE. Reading a whole devotional page gives you the
    sidebar too, and the sidebar on these sites is other texts: the Tulsi aarti turned up inside
    four different aartis, and a Ganesh Chalisa blurb inside the Hanuman Chalisa. Cross-contaminated
    scripture is the worst thing this pipeline could produce - a line that is real, and real
    somewhere else. Depth counting is what keeps the sidebar out, and that needs a parser.
    """

    def __init__(self, tag: str, class_name: str):
        super().__init__(convert_charrefs=True)
        self.tag, self.class_name = tag, class_name
        self.depth = 0
        self.anchors = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class", "") or ""
        if self.depth:
            if tag == self.tag:
                self.depth += 1
            # A LINK IS NOT A VERSE. The content container ends with a list of related texts -
            # "श्री हनुमान आरती", "संकटमोचन अष्टक" - which are short, Devanagari, and survive every
            # filter above because they look exactly like padas. They are also, without exception,
            # hyperlinks; scripture is not.
            if tag == "a":
                self.anchors += 1
            if tag in ("br", "p", "div", "li"):
                self.parts.append("\n")
        elif tag == self.tag and self.class_name in classes.split():
            self.depth = 1

    def handle_endtag(self, tag):
        if self.depth and tag == self.tag:
            self.depth -= 1
        if self.anchors and tag == "a":
            self.anchors -= 1

    def handle_data(self, data):
        if self.depth and not self.anchors:
            self.parts.append(data)

    def lines(self) -> list[str]:
        return [" ".join(l.split()) for l in "".join(self.parts).splitlines()]


def container_lines(html: str, tag: str, class_name: str) -> list[str]:
    """Lines of the named element, or [] when the page does not have one."""
    parser = _Container(tag, class_name)
    parser.feed(html)
    return parser.lines()
