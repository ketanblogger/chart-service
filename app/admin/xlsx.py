"""A workbook writer: enough OOXML to produce a real .xlsx, in the standard library and nothing else.

WHY NOT openpyxl. The accounting export is three sheets of strings and numbers with one number format and
one bold row. `requirements.txt` is installed by hand on the production box (README: `uv pip install -r
requirements.txt`), and a dependency added for this would have to be installed there before the page could
be opened - on a deadline, for a file format whose write path is a ZIP of five XML parts. The same
reasoning produced app/admin/charts.py, which draws the dashboard's charts as inline SVG rather than
adding a charting library. If a future sheet needs formulas, pivot tables or styling, that is the moment
to take the dependency; nothing here is a reason to avoid it then.

WHAT THIS DELIBERATELY DOES NOT DO: formulas, merged cells, images, charts, more than one font, dates as
dates. **Dates are written as text**, in `YYYY-MM-DD HH:MM` IST, and that is a decision rather than a
limitation: an Excel serial date carries no timezone, so a reader in any other locale would see an IST
timestamp relabelled as their own, and the whole file is a tax record whose dates decide which return a
figure belongs to. Text cannot be silently reinterpreted.

MONEY IS NEVER A FLOAT ON THE WAY IN. `Rupees` holds integer PAISE and the cell's decimal string is built
from the integer, so nothing in this file can round a figure that arrived exact - see `Rupees.text`.
"""

from __future__ import annotations

import datetime as dt
import re
import zipfile
from dataclasses import dataclass, field

# Excel's own limits on a sheet name: 31 characters, and none of these. Enforced rather than trusted,
# because a workbook with an invalid sheet name opens as "we found a problem with some content" and
# repairs itself by throwing the sheet away - a silently missing sheet in an accounting file.
MAX_SHEET_NAME = 31
_BAD_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
# XML 1.0 forbids most control characters outright; they cannot be escaped, only removed. A tab, newline
# and carriage return are legal and are kept.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

MONEY_FORMAT_ID = 164   # the first id available for a custom format; 0-163 are Excel's built-ins
STYLE_PLAIN, STYLE_BOLD, STYLE_MONEY = 0, 1, 2

# A fixed timestamp on every member, so the same month exports to byte-identical bytes. Two downloads of
# a closed month that differ are two files somebody has to compare; 1980-01-01 is the earliest a ZIP can
# express. (The real "generated at" is a cell inside the Summary sheet, where it is readable.)
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class Rupees:
    """A money cell, carried as integer PAISE and written as an exact decimal.

    The whole point of this class is that `257.00` and `256.995` can never happen to the same figure. The
    cell text is built by integer division - `f"{paise / 100:.2f}"` would be correct for every amount this
    business will ever see, but it makes exactness a property of binary floating point rather than of the
    code, and app/payments/gst.py went to some trouble to keep money in integers all the way through. This
    is the last step of that path, so it keeps the discipline.

    `None` is an EMPTY CELL, never a zero. The rest of this codebase is emphatic that NULL is "not
    recorded" (see `register_columns` in app/db.py), and a spreadsheet is exactly where a zero that means
    "unknown" gets summed into a total nobody can explain.
    """

    __slots__ = ("paise",)

    def __init__(self, paise: int | None):
        if paise is not None and not isinstance(paise, int):
            raise TypeError(f"Rupees takes whole paise or None, got {paise!r}")
        self.paise = paise

    @property
    def text(self) -> str:
        whole, fraction = divmod(abs(self.paise), 100)
        return f"{'-' if self.paise < 0 else ''}{whole}.{fraction:02d}"

    def __repr__(self) -> str:
        return f"Rupees({self.paise!r})"


class Bold:
    """A string cell in the bold style - a header, or a heading inside the Summary sheet."""

    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value


@dataclass
class Sheet:
    """One worksheet: a name, rows of cells, and optional column widths.

    `freeze_header` freezes the first row, which is what makes a 20-column tax sheet readable at all once
    you have scrolled past the first screen of invoices.
    """

    name: str
    rows: list[list] = field(default_factory=list)
    widths: tuple[int, ...] = ()
    freeze_header: bool = True

    def __post_init__(self):
        cleaned = _BAD_SHEET_CHARS.sub(" ", str(self.name)).strip() or "Sheet"
        if len(cleaned) > MAX_SHEET_NAME:
            raise ValueError(f"sheet name {self.name!r} is longer than the {MAX_SHEET_NAME} characters Excel allows")
        self.name = cleaned


def _text(value) -> str:
    """XML-escaped cell text with the characters XML cannot carry removed."""
    escaped = (_CONTROL_CHARS.sub("", str(value))
               .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return escaped


def _column(index: int) -> str:
    """0 -> "A", 25 -> "Z", 26 -> "AA"."""
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _cell(reference: str, value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, Rupees):
        return "" if value.paise is None else f'<c r="{reference}" s="{STYLE_MONEY}"><v>{value.text}</v></c>'
    if isinstance(value, Bold):
        return f'<c r="{reference}" s="{STYLE_BOLD}" t="inlineStr"><is><t xml:space="preserve">' \
               f'{_text(value.value)}</t></is></c>'
    if isinstance(value, bool):
        # Before the int check: a bool IS an int in Python, and TRUE/FALSE in a tax sheet is a worse
        # answer than the word the column header asks for ("yes"/"no"), so callers pass strings. This
        # branch exists so a stray bool is visible rather than appearing as 1.
        return f'<c r="{reference}" t="inlineStr"><is><t>{"yes" if value else "no"}</t></is></c>'
    if isinstance(value, int):
        return f'<c r="{reference}"><v>{value:d}</v></c>'
    if isinstance(value, float):
        return f'<c r="{reference}"><v>{value!r}</v></c>'
    return f'<c r="{reference}" t="inlineStr"><is><t xml:space="preserve">{_text(value)}</t></is></c>'


def _sheet_xml(sheet: Sheet) -> str:
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
    if sheet.freeze_header and sheet.rows:
        parts.append('<sheetViews><sheetView workbookViewId="0">'
                     '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                     '</sheetView></sheetViews>')
    if sheet.widths:
        cols = "".join(f'<col min="{n + 1}" max="{n + 1}" width="{width}" customWidth="1"/>'
                       for n, width in enumerate(sheet.widths))
        parts.append(f"<cols>{cols}</cols>")
    parts.append("<sheetData>")
    for number, row in enumerate(sheet.rows, start=1):
        cells = "".join(_cell(f"{_column(index)}{number}", value) for index, value in enumerate(row))
        parts.append(f'<row r="{number}">{cells}</row>' if cells else f'<row r="{number}"/>')
    parts.append("</sheetData></worksheet>")
    return "".join(parts)


_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
{sheets}
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

# Two fonts (regular, bold), one custom number format, three cellXfs. Nothing else is referenced anywhere,
# and Excel refuses a styles part that is missing the fills/borders/cellStyleXfs it expects to index into.
_STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="{MONEY_FORMAT_ID}" formatCode="0.00"/></numFmts>
<fonts count="2">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font>
</fonts>
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="{MONEY_FORMAT_ID}" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def workbook(sheets: list[Sheet]) -> bytes:
    """The sheets as one .xlsx file.

    At least one sheet, always: a workbook with none is not a file Excel will open, and the empty month
    this export has to survive is an empty SHEET SET, not an absent one (app/admin/accounting.py builds
    all three headers whatever the month holds).
    """
    if not sheets:
        raise ValueError("a workbook needs at least one sheet")
    overrides = "\n".join(
        f'<Override PartName="/xl/worksheets/sheet{n}.xml" '
        f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for n in range(1, len(sheets) + 1))
    entries = {
        "[Content_Types].xml": _CONTENT_TYPES.format(sheets=overrides),
        "_rels/.rels": _ROOT_RELS,
        "xl/styles.xml": _STYLES,
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                           '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                           "<sheets>"
                           + "".join(f'<sheet name="{_text(sheet.name)}" sheetId="{n}" r:id="rId{n}"/>'
                                     for n, sheet in enumerate(sheets, start=1))
                           + "</sheets></workbook>",
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                                      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      + "".join(
                                          f'<Relationship Id="rId{n}" Type="http://schemas.openxmlformats.org/'
                                          f'officeDocument/2006/relationships/worksheet" '
                                          f'Target="worksheets/sheet{n}.xml"/>'
                                          for n in range(1, len(sheets) + 1))
                                      + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.'
                                        f'openxmlformats.org/officeDocument/2006/relationships/styles" '
                                        f'Target="styles.xml"/></Relationships>',
    }
    for n, sheet in enumerate(sheets, start=1):
        entries[f"xl/worksheets/sheet{n}.xml"] = _sheet_xml(sheet)

    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in entries.items():
            info = zipfile.ZipInfo(name, date_time=_FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, body.encode("utf-8"))
    return buffer.getvalue()


def when(stamp: float | None, tz: dt.timezone) -> str:
    """A timestamp as the text this workbook writes dates as - see the module docstring on why it is text."""
    if stamp is None:
        return ""
    return dt.datetime.fromtimestamp(float(stamp), tz).strftime("%Y-%m-%d %H:%M")
