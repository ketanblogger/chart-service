"""The .docx package: valid zip, conforming parts, and Devanagari that Word will actually set.

WHAT THESE TESTS CANNOT DO is open the file in Word. There is no word processor on the machine that
builds this, so every check here is structural - the package rules a conforming reader enforces, and
the specific run properties Word needs for a complex script. That is a real limit and it is written
down rather than papered over: a file that satisfies every assertion below can still look wrong in
Word, and the first person to open one should be a human being.

The people are invented.
"""
import datetime as dt
import io
import re
import zipfile
from xml.dom import minidom

import pytest

from app.biodata import core, designs, docx, model

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
BORN = dt.date(1991, 4, 3)
FIELDS = model.fields_from({"full_name": "Keshav Pardeshi", "qualification": "B.E. Mechanical",
                            "father_name": "Anil Pardeshi", "devak": "Umbar",
                            "siblings": "One brother\nOne sister"})


def built(**kw):
    kw.setdefault("kundli", core.from_birth(BORN, birth_time=dt.time(14, 25), lat=18.52, lon=73.86,
                                            language=kw.get("language", "mr")))
    return zipfile.ZipFile(io.BytesIO(docx.build(FIELDS, **kw)))


def test_the_package_is_a_valid_zip_with_the_parts_a_reader_requires():
    z = built()
    assert z.testzip() is None
    required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml",
                "word/_rels/document.xml.rels", "docProps/core.xml"}
    assert required <= set(z.namelist())


def test_every_part_is_well_formed_xml():
    z = built()
    for name in z.namelist():
        minidom.parseString(z.read(name))      # raises if not


def test_every_relationship_points_at_a_part_that_exists():
    """A dangling relationship is the classic way a hand-built .docx opens as 'unreadable content'."""
    z = built()
    names = set(z.namelist())
    for part, base in (("_rels/.rels", ""), ("word/_rels/document.xml.rels", "word/")):
        for target in re.findall(r'Target="([^"]+)"', z.read(part).decode()):
            assert (base + target).lstrip("/") in names, f"{part} -> {target}"


def test_every_part_has_a_declared_content_type():
    """Word refuses a package whose parts are not typed, and the Default/Override split is where a
    hand-written content-type map usually goes wrong."""
    z = built()
    types = z.read("[Content_Types].xml").decode()
    defaults = set(re.findall(r'Default Extension="([^"]+)"', types))
    overrides = set(re.findall(r'Override PartName="([^"]+)"', types))
    for name in z.namelist():
        extension = name.rsplit(".", 1)[-1]
        assert extension in defaults or "/" + name in overrides, name


def test_every_run_names_a_complex_script_font():
    """DEVANAGARI TAKES ITS FONT FROM w:cs, NOT w:ascii. A run with only the Latin slots set renders
    Hindi and Marathi in whatever Word picks, at whatever size it picks. The minimal example anybody
    would copy off the internet sets only the Latin ones."""
    z = built()
    document = z.read("word/document.xml").decode()
    fonts = re.findall(r"<w:rFonts [^/]*/>", document)
    assert fonts, "no run properties at all - is the document empty?"
    for declaration in fonts:
        assert f'w:cs="{docx.SCRIPT_FONT}"' in declaration, declaration
    styles = z.read("word/styles.xml").decode()
    # ...and the sizes, which are a separate slot again.
    assert f'w:cs="{docx.SCRIPT_FONT}"' in styles
    for size in re.findall(r'<w:sz w:val="(\d+)"/><w:szCs w:val="(\d+)"/>', styles):
        assert size[0] == size[1], f"Latin and complex-script sizes differ: {size}"
    assert styles.count("<w:sz ") == styles.count("<w:szCs ")


def test_the_devanagari_is_in_the_document_as_text():
    z = built(language="mr", design_key="traditional")
    document = z.read("word/document.xml").decode()
    assert designs.INVOCATIONS["ganesh"] in document
    assert core.LABELS["mr"]["rashi"] in document and "अनुराधा" in document
    assert model.SECTION_TITLES["kundli"]["mr"] in document


def test_a_value_with_xml_characters_in_it_survives():
    """A biodata is typed by hand and pasted from WhatsApp. An unescaped ampersand in a surname is a
    corrupt file, not a cosmetic bug."""
    awkward = model.fields_from({"full_name": 'Keshav & Sons <"Pardeshi">',
                                 "occupation": "Research & development"})
    blob = docx.build(awkward, language="en")
    z = zipfile.ZipFile(io.BytesIO(blob))
    minidom.parseString(z.read("word/document.xml"))
    document = z.read("word/document.xml").decode()
    assert "&amp;" in document and "&lt;" in document
    assert "Keshav & Sons" not in document        # the raw form must not be there
    text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", document))
    import html as html_module
    assert 'Keshav & Sons <"Pardeshi">' in html_module.unescape(text)


def test_a_multi_line_value_becomes_several_paragraphs_in_one_cell():
    z = built()
    document = z.read("word/document.xml").decode()
    assert "One brother" in document and "One sister" in document
    cell = document.split("One brother")[1].split("</w:tc>")[0]
    assert "One sister" in cell       # same cell, not a new row


def test_rows_are_a_table_rather_than_tab_stops():
    """This file exists to be EDITED. A value typed into a tabbed layout pushes the line out of
    alignment the moment it is longer than the one it replaced."""
    z = built()
    document = z.read("word/document.xml").decode()
    assert "<w:tbl>" in document and "<w:tab" not in document
    assert document.count("<w:gridCol") >= 2


def test_an_unsettled_row_is_italic_here_too():
    """The PDF marks them; a .docx that silently dropped the mark would be a different document."""
    z = built(kundli=core.from_birth(BORN, language="mr"))
    document = z.read("word/document.xml").decode()
    assert "<w:i/><w:iCs/>" in document
    assert core.NEEDS_TIME["mr"] in document


def test_the_credit_line_follows_the_same_rule_as_the_pdf():
    free = built(language="mr", design_key="classic").read("word/document.xml").decode()
    paid = built(language="mr", design_key="ganesh-gold", paid=True).read("word/document.xml").decode()
    assert designs.MADE_ON["mr"] in free
    assert designs.MADE_ON["mr"] not in paid


@pytest.mark.parametrize("language", ["en", "hi", "mr"])
def test_it_builds_in_every_language(language):
    z = built(language=language)
    document = z.read("word/document.xml").decode()
    assert model.SECTION_TITLES["kundli"][language] in document
    assert f'<w:document xmlns:w="{W}">' in document


def test_the_document_is_deterministic():
    """Same input, same bytes - so a person who downloads twice gets the same file, and a test that
    compares output is comparing the document rather than a timestamp."""
    now = dt.datetime(2027, 3, 1, 9, 30)
    a = docx.build(FIELDS, language="mr", now=now)
    b = docx.build(FIELDS, language="mr", now=now)
    assert a == b
