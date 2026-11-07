"""The biodata as an editable Word document, written with the standard library and nothing else.

A .docx IS A ZIP OF XML. There is no need for a library to produce one, and not taking a dependency
here is worth something concrete: "marriage biodata format in word" is one of the biggest terms this
page is built for, so this file is on the hot path of the feature, and it has no third-party code in
it to pin, audit, credit or install on the server.

WHAT WORD NEEDS AND WHAT IT MERELY TOLERATES. The parts below are the minimum a conforming reader
requires: the content-type map, the package relationships, the document part and the relationships
of the document part. Styles are included because without them Word applies its own defaults and a
heading stops looking like a heading when somebody opens this to edit it, which is the entire point
of offering a .docx rather than only a PDF.

DEVANAGARI IS A COMPLEX SCRIPT TO WORD, and that is not a detail. Text in Devanagari takes its font
from `w:cs` (complex script) and its SIZE from `w:szCs`, not from `w:ascii` and `w:sz`. Set only the
Latin ones - which is what you get by copying a minimal example off the internet - and Hindi and
Marathi render at the wrong size in a font Word picked for itself, or as boxes. Every run written
here carries both.

The font named for complex script is Nirmala UI, which ships with Windows and is what Word itself
uses for Devanagari. A document can only ASK for a font; if a machine does not have it Word
substitutes, which is why the text is also legible at this size in whatever it substitutes.
"""
from __future__ import annotations

import datetime as dt
import io
import zipfile
from xml.sax.saxutils import escape

from . import core, designs, model

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
LATIN_FONT = "Calibri"
SCRIPT_FONT = "Nirmala UI"          # ships with Windows; Word's own choice for Devanagari

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _styles(accent: str) -> str:
    """Normal, a heading and a label style. `docDefaults` is where the complex-script font has to be
    set as well, or every run that does not repeat it falls back to Word's own pick."""
    bare = accent.lstrip("#").upper()
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W}">
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="{LATIN_FONT}" w:hAnsi="{LATIN_FONT}" w:cs="{SCRIPT_FONT}"/>
<w:sz w:val="21"/><w:szCs w:val="21"/>
</w:rPr></w:rPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:styleId="Normal" w:default="1"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="BdTitle"><w:name w:val="Biodata Title"/>
<w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/><w:spacing w:after="120"/></w:pPr>
<w:rPr><w:b/><w:bCs/><w:sz w:val="44"/><w:szCs w:val="44"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="BdInvocation"><w:name w:val="Biodata Invocation"/>
<w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/><w:spacing w:after="60"/></w:pPr>
<w:rPr><w:color w:val="{bare}"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="BdHeading"><w:name w:val="Biodata Heading"/>
<w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="240" w:after="100"/></w:pPr>
<w:rPr><w:b/><w:bCs/><w:color w:val="{bare}"/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="BdFoot"><w:name w:val="Biodata Foot"/>
<w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/><w:spacing w:before="360"/></w:pPr>
<w:rPr><w:color w:val="808080"/><w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr></w:style>
</w:styles>"""


def _core_properties(title: str, now: dt.datetime) -> str:
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>{escape(title)}</dc:title>
<dcterms:created xsi:type="dcterms:W3CDTF">{stamp}</dcterms:created>
<dcterms:modified xsi:type="dcterms:W3CDTF">{stamp}</dcterms:modified>
</cp:coreProperties>"""


def _run(text: str, *, bold: bool = False, colour: str | None = None, italic: bool = False) -> str:
    """One run. BOTH font slots and BOTH size slots, every time - see the module docstring."""
    props = [f'<w:rFonts w:ascii="{LATIN_FONT}" w:hAnsi="{LATIN_FONT}" w:cs="{SCRIPT_FONT}"/>']
    if bold:
        props.append("<w:b/><w:bCs/>")
    if italic:
        props.append("<w:i/><w:iCs/>")
    if colour:
        props.append(f'<w:color w:val="{colour.lstrip("#").upper()}"/>')
    # xml:space, or Word eats a trailing space and "Yes, with parihar " becomes a different string.
    return (f"<w:r><w:rPr>{''.join(props)}</w:rPr>"
            f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r>')


def _paragraph(text: str, *, style: str | None = None, **run) -> str:
    properties = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{properties}{_run(text, **run) if text else ''}</w:p>"


def _row(label: str, value: str, accent: str, *, italic: bool = False) -> str:
    """A two-cell table row. A TABLE, not a tab stop: this file exists to be EDITED, and a value
    typed into a tabbed layout pushes the whole line out of alignment the moment it is longer than
    the one it replaced."""
    lines = value.split("\n") or [""]
    cells = "".join(_paragraph(line, italic=italic) for line in lines)
    return (
        "<w:tr>"
        f'<w:tc><w:tcPr><w:tcW w:w="3200" w:type="dxa"/></w:tcPr>'
        f"{_paragraph(label, colour=accent)}</w:tc>"
        f'<w:tc><w:tcPr><w:tcW w:w="5800" w:type="dxa"/></w:tcPr>{cells}</w:tc>'
        "</w:tr>")


def _table(rows: list[str]) -> str:
    return ("<w:tbl><w:tblPr>"
            '<w:tblW w:w="9000" w:type="dxa"/>'
            '<w:tblBorders><w:insideH w:val="single" w:sz="2" w:color="DDDDDD"/></w:tblBorders>'
            '<w:tblLayout w:type="fixed"/>'
            "</w:tblPr>"
            '<w:tblGrid><w:gridCol w:w="3200"/><w:gridCol w:w="5800"/></w:tblGrid>'
            + "".join(rows) + "</w:tbl>")


def build(fields: dict, *, language: str = "en", design_key: str | None = None,
          paid: bool = False, kundli: dict | None = None,
          now: dt.datetime | None = None) -> bytes:
    """The .docx bytes. Same fields, same order and same wording as the PDF sheet."""
    if language not in model.SECTION_TITLES["kundli"]:
        language = "en"
    design = designs.design(design_key, paid=paid)
    accent = design["tokens"]["accent"]
    title = fields.get("full_name") or _heading(language)

    body = [_paragraph(design["invocation"], style="BdInvocation") if design["invocation"] else "",
            _paragraph(title, style="BdTitle")]

    if kundli:
        body.append(_paragraph(model.SECTION_TITLES["kundli"][language], style="BdHeading"))
        rows = [_row(kundli["labels"][key], kundli["rows"][key]["text"], accent,
                     italic=not kundli["rows"][key]["known"])
                for key in core.ROWS]
        rows += [_row(kundli["labels"][key], fields[key], accent)
                 for key, _ in model.LINEAGE if fields.get(key)]
        body.append(_table(rows))

    for section in model.filled_sections(fields, language=language):
        body.append(_paragraph(section["title"], style="BdHeading"))
        body.append(_table([_row(row["label"], row["value"], accent) for row in section["rows"]]))

    if not paid:
        body.append(_paragraph(designs.MADE_ON[language], style="BdFoot"))

    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                f'<w:document xmlns:w="{W}"><w:body>{"".join(body)}'
                '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
                "</w:sectPr></w:body></w:document>")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", ROOT_RELS)
        zf.writestr("docProps/core.xml", _core_properties(title, now or dt.datetime(2027, 1, 1)))
        zf.writestr("word/_rels/document.xml.rels", DOC_RELS)
        zf.writestr("word/styles.xml", _styles(accent))
        zf.writestr("word/document.xml", document)
    return buffer.getvalue()


def _heading(language: str) -> str:
    from .sheet import HEADINGS

    return HEADINGS[language]
