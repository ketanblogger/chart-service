"""The month-end GST records: /admin/accounting, the spreadsheet, the ZIP and the 1st-of-the-month e-mail.

Four claims, in the order of what they would cost if they broke:

1. **THE TOTALS EQUAL THE LINE ITEMS TO THE PAISA.** Read back out of the workbook that was actually
   written - not out of the Python objects that built it - because a figure that is right in memory and
   wrong in the file is the only kind of wrong that reaches a return. Run at a rate whose half is a
   fraction of a paisa (12.5%, so CGST is 6.25%), which is where a rounding that drifts actually shows up;
   at 18% of whole rupees nothing rounds at all and a broken split would pass.
2. **AN INTERNAL ORDER IS IN THE SHEET, FLAGGED, AND IN THE TOTALS.** An invoice number comes out of one
   gap-free consecutive series, so a document dropped because the dashboard does not count the sale as
   revenue leaves a hole somebody has to explain to an assessing officer. The flag is a column; it is
   never a filter. Asserted together with the fact that the dashboard's own reader DOES leave it out, so
   the test states the difference rather than one half of it.
3. **A refunded month lists the invoice and its credit note**, each in the month its own document was
   issued in - which is frequently not the same month.
4. **A zero-sale month produces a valid, openable, empty file** rather than an exception.

Every buyer, address and name here is invented; `tests/` is published.

THE FIXTURES ARE BUILT THROUGH THE PRODUCTION CODE PATH - `store.insert_order`, `invoice.assign`,
`store.record_refund`, `credit_note.issue` - and not one line of DDL is written here. A fixture with its own
hand-written schema is a second schema that passes happily while production raises `no such table: users`,
which has already happened in this repository once.
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import db
from app.admin import accounting, xlsx
from app.main import app
from app.payments import credit_note, gst, internal, invoice, states, store
from app.web import site

# Imported for the SIDE EFFECT of their schema registrations, which is exactly how production gets them -
# NOT for anything named below. `app/db.py` applies the DDL that modules registered at import time, so a
# module nothing imports is a table that does not exist, and a fixture that wrote its own `CREATE TABLE`
# instead would be a second schema passing happily while production raised `no such table`. That has
# happened here. `app.admin.alerts` owns `admin_alerts_sent`, where the monthly e-mail is deduplicated;
# `app.payments.store` owns `orders` and `webhook_refunds`; `app.analytics` owns the event tables the admin
# pages read.
from app import analytics  # noqa: F401,E402  (schema side effect)
from app.admin import alerts  # noqa: F401,E402  (schema side effect)

PASSWORD = "an-accounting-password-long-enough-to-be-real"
OWNER = "owner@rashikundli.invalid"          # invented: the "internal because it is ours" address
BUYER = "asha@example.invalid"               # invented
BUYER_NAME = "Asha Invented"                 # invented
SELLER_STATE = states.seller_code()          # intra-state: CGST + SGST
OTHER_STATE = "29" if SELLER_STATE != "29" else "24"   # inter-state: IGST
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


# ---- environment ------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def admin_env(monkeypatch):
    """The password door, no alert delivery, and a known admin set for the internal classification.

    `internal.admin_emails` is patched rather than `ADMIN_EMAILS`, for the two reasons
    tests/test_internal_orders.py gives: `site.ADMIN_EMAILS` is read once when that module is imported, so
    the environment variable reaches nothing after the app has loaded; and setting it would switch the
    /admin door to the allowlist and shut the password route these tests come in through.
    """
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("SESSION_SECRET", "test-accounting-session-secret")
    monkeypatch.setenv("BASE_URL", "https://admin.test")
    monkeypatch.setenv("ADMIN_ALERTS_ON_VIEW", "0")
    monkeypatch.setenv("REPORT_EMAIL_ENABLED", "")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setattr(site, "ADMIN_EMAILS", ())
    monkeypatch.setattr(internal, "admin_emails", lambda: frozenset({OWNER}))


@pytest.fixture
def client():
    """Over https, because the admin session cookie is Secure - see tests/test_admin_web.py."""
    return TestClient(app, base_url="https://admin.test")


def header() -> dict:
    return {"Authorization": "Basic " + base64.b64encode(f"admin:{PASSWORD}".encode()).decode()}


def ist(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> float:
    return dt.datetime(year, month, day, hour, minute, tzinfo=accounting.IST).timestamp()


# ---- fixtures built the way production builds them ---------------------------------------------------


def invoiced(order_id: str, *, at: float, price_paise: int = 29900, state: str | None = SELLER_STATE,
             product: str = "kundali-report", email: str = BUYER, name: str = BUYER_NAME,
             live: int = 1, marked: str | None = None) -> dict:
    """One paid order with an invoice number, through the real path: insert, mark paid, allocate.

    `live` and `created_at` are set explicitly because `insert_order` reads the Razorpay keys to decide the
    mode and the tests have none, so every order would otherwise be a test-mode (and therefore internal)
    row - which is the very distinction half of this file is about.

    `marked` writes the STORED classification (`internal` / `internal_reason`), the way
    scripts/mark_internal_orders.py does on the live database. That matters: an order that is internal only
    by evidence and one that has been marked are two different rows, and a filter written against the
    column would drop the second while leaving the first - so both are exercised below.
    """
    tax = gst.split(price_paise, states.tax_settings(state))
    store.insert_order(order_id=order_id, product=product, kind="report", amount_paise=tax.total_paise,
                       currency="INR", razorpay_order_id=f"order_{order_id}", user_id=f"user-{order_id}",
                       report_id=order_id[:32], language="en", names={"self": name}, email=email,
                       base_paise=tax.base_paise, gst_paise=tax.gst_paise, gst_rate_bp=tax.rate_bp,
                       place_of_supply=state)
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET status='paid', paid_via='verify', payment_id=?, fulfilment='ready', "
                     "paid_at=?, created_at=?, updated_at=?, live=?, internal=?, internal_reason=? "
                     "WHERE id=?",
                     (f"pay_{order_id}", at, at, at, live, None if marked is None else 1, marked,
                      order_id))
    number = invoice.assign(store.get_order(order_id))
    assert number, f"{order_id} was not given an invoice number"
    return store.get_order(order_id)


def refunded(order_id: str, *, refund_id: str, paise: int, at: float) -> str:
    """One processed refund and its credit note, through the real path."""
    store.record_refund(order_id, refund_id=refund_id, amount_paise=paise, at=at)
    number = credit_note.issue(store.get_order(order_id), refund_id)
    assert number, f"{refund_id} was not given a credit note"
    return number


# ---- reading the workbook back -----------------------------------------------------------------------


def read_workbook(data: bytes) -> dict[str, list[list[str]]]:
    """{sheet name: rows of cell text}, parsed out of the .xlsx that was actually written.

    Deliberately NOT a check of `accounting`'s own view objects. The claim being defended is about the
    FILE: the sheet is what a CA opens and what a figure is read off, and a total that is right in Python
    and wrong in the file is wrong. Empty cells are omitted from the XML entirely, so each cell is placed
    by its own `r` reference rather than by its position in the element list - reading them in order is how
    a sheet with one blank cell silently shifts every column after it.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        book = ET.fromstring(archive.read("xl/workbook.xml"))
        names = [sheet.get("name") for sheet in book.iter(f"{NS}sheet")]
        sheets = {}
        for index, name in enumerate(names, start=1):
            rows = []
            for row in ET.fromstring(archive.read(f"xl/worksheets/sheet{index}.xml")).iter(f"{NS}row"):
                cells: dict[int, str] = {}
                for cell in row.iter(f"{NS}c"):
                    letters = re.match(r"([A-Z]+)", cell.get("r") or "A")
                    column = 0
                    for character in (letters.group(1) if letters else "A"):
                        column = column * 26 + (ord(character) - ord("A") + 1)
                    inline = cell.find(f"{NS}is/{NS}t")
                    value = cell.find(f"{NS}v")
                    cells[column - 1] = (inline.text if inline is not None and inline.text else
                                         (value.text or "") if value is not None else "")
                rows.append([cells.get(n, "") for n in range(max(cells) + 1 if cells else 0)])
            sheets[name] = rows
    return sheets


def paise(text: str) -> int:
    """A money cell as whole paise. `Decimal`, not `float`: this is the assertion, so it may not round."""
    return 0 if not text else int(Decimal(text) * 100)


def column(header: tuple[str, ...], name: str) -> int:
    return header.index(name)


def labelled(rows: list[list[str]], first_cell: str) -> list[str]:
    """The one row whose first cell is exactly this. Asserts it is ONE - a summary block that appeared
    twice would make every figure below ambiguous and the test would quietly check the wrong one."""
    found = [row for row in rows if row and row[0] == first_cell]
    assert len(found) == 1, f"expected exactly one {first_cell!r} row, found {len(found)}"
    return found[0]


def block(rows: list[list[str]], after_header: str) -> list[list[str]]:
    """The rows of one Summary table: everything between its header row and the next blank row."""
    start = next(n for n, row in enumerate(rows) if row and row[0] == after_header)
    out = []
    for row in rows[start + 1:]:
        if not row or not row[0]:
            break
        out.append(row)
    return out


# ---- 1. the one that matters: the totals reconcile to the paisa --------------------------------------


@pytest.mark.parametrize("rate", ["18", "12.5"])
def test_the_totals_equal_the_sum_of_the_line_items_to_the_paisa(monkeypatch, rate):
    """Every column of the Summary is the sum of the rows above it, exactly, read out of the file.

    12.5% is the case that matters: half of it is 6.25%, so CGST is a fraction of a paisa and `gst.heads`
    has to put the odd paisa somewhere. At 18% of whole-rupee prices nothing rounds - the split is exact by
    arithmetic - so a test run only at 18% would pass with the rounding broken. The prices below are
    deliberately not all round for the same reason.

    FOUR THINGS ARE ASSERTED, and the fourth is the one a drift escapes through: each row's own parts add
    up to its total; the Invoices total is the sum of the invoice rows; the Credit notes total is the sum of
    the credit-note rows; and the by-state and by-product breakdowns each add back to the same figure. A
    paisa lost in a grouping key would pass the first three.
    """
    monkeypatch.setenv("GST_RATE_PERCENT", rate)
    month = dt.date(2026, 11, 1)
    prices = (4900, 5900, 9999, 11900, 24900, 29900, 34901)
    # Spread over the seller's own state, another state, an export and a sale with no recorded state, so
    # every tax head and the "not classified" column all carry something.
    places = [SELLER_STATE, OTHER_STATE, SELLER_STATE, None, OTHER_STATE, SELLER_STATE, OTHER_STATE]
    for n, (price, place) in enumerate(zip(prices, places)):
        invoiced(f"ord_paisa{n:02d}", at=ist(2026, 11, 3 + n, 10, n), price_paise=price, state=place)
    # Two partial refunds on one order and a full one on another: the partials are credited against the
    # RUNNING total (app/payments/credit_note.py), which is the other place a paisa can go missing.
    refunded("ord_paisa05", refund_id="rfnd_paisa05a", paise=10000, at=ist(2026, 11, 20, 9))
    refunded("ord_paisa05", refund_id="rfnd_paisa05b", paise=5000, at=ist(2026, 11, 21, 9))
    refunded("ord_paisa01", refund_id="rfnd_paisa01", paise=5900, at=ist(2026, 11, 22, 9))

    view = accounting.month_view(month)
    sheets = read_workbook(accounting.month_workbook(view))
    heads = ("Taxable value", "CGST", "SGST", "IGST", "Tax not classified", "Total")

    # The two sheets name the same six figures slightly differently - a credit note CREDITS a taxable
    # value - so each one's column titles are listed rather than guessed from the other's.
    for sheet_name, head, total_row, titles in (
            (accounting.INVOICES_SHEET, accounting.INVOICE_HEADER, "Invoices", heads),
            (accounting.CREDIT_NOTES_SHEET, accounting.CREDIT_NOTE_HEADER, "Credit notes",
             ("Taxable value credited", "CGST", "SGST", "IGST", "Tax not classified", "Total credited"))):
        rows = sheets[sheet_name][1:]
        assert rows, f"{sheet_name} is empty, so this test would assert nothing"
        money = {name: column(head, title) for name, title in zip(heads, titles)}
        # (a) every row adds up on its own.
        for row in rows:
            parts = sum(paise(row[money[name]]) for name in heads[:-1])
            assert parts == paise(row[money["Total"]]), f"{sheet_name} row {row[0]} does not add up"
        # (b) the Summary's figures are the sums of those rows, column by column.
        summary = labelled(sheets[accounting.SUMMARY_SHEET], total_row)
        for offset, name in enumerate(heads, start=1):
            expected = sum(paise(row[money[name]]) for row in rows)
            assert paise(summary[offset]) == expected, f"{total_row} / {name}"

    # (c) the net line is the difference of the two, to the paisa.
    issued = labelled(sheets[accounting.SUMMARY_SHEET], "Invoices")
    credited = labelled(sheets[accounting.SUMMARY_SHEET], "Credit notes")
    net = labelled(sheets[accounting.SUMMARY_SHEET], "Net")
    for offset in range(1, len(heads) + 1):
        assert paise(net[offset]) == paise(issued[offset]) - paise(credited[offset])

    # (d) both breakdowns add back to the same totals. Columns: taxable, tax, total on each side.
    for header_cell in ("Code", "Product"):
        rows = block(sheets[accounting.SUMMARY_SHEET], header_cell)
        assert rows, f"the {header_cell} breakdown is empty"
        for side, taxable_at, total_at, against in ((("invoices"), 3, 5, issued),
                                                    (("credit notes"), 7, 9, credited)):
            assert sum(paise(row[taxable_at]) for row in rows) == paise(against[1]), f"{header_cell}/{side}"
            assert sum(paise(row[total_at]) for row in rows) == paise(against[6]), f"{header_cell}/{side}"


def test_a_tax_head_split_that_drifts_is_caught(monkeypatch):
    """Proof that the guard above can actually fail: break the split and watch a row stop adding up.

    `_heads` is forced to lose a paisa off SGST. Nothing else changes - the figures still look entirely
    plausible - and `Document` refuses to be built, which is what stops a drift reaching a file at all.
    """
    honest = accounting._heads      # noqa: SLF001 - captured BEFORE the patch, or `lossy` calls itself

    def lossy(amounts, code):
        cgst, sgst, igst, unclassified = honest(amounts, code)
        return cgst, max(0, sgst - 1), igst, unclassified

    invoiced("ord_drift", at=ist(2026, 11, 4), state=SELLER_STATE)
    monkeypatch.setattr(accounting, "_heads", lossy)
    with pytest.raises(ValueError, match="add up to"):
        accounting.month_view(dt.date(2026, 11, 1))


# ---- 2. an internal order is in the sheet, flagged, and in the totals --------------------------------


def test_an_internal_order_is_in_the_sheet_flagged_and_never_dropped():
    """The brief's own assertion. An issued invoice is a GST record whatever the dashboard makes of it.

    The customer's order and the proprietor's own are identical but for the address. Both get an invoice
    number out of the same consecutive series, so dropping one would leave a hole in the series - and the
    thing that keeps the revenue figures honest is the COLUMN, not an absence. The dashboard's own reader
    is asserted to leave it out in the same breath, so this test states the difference between the two
    rather than half of it.
    """
    month = dt.date(2026, 10, 1)
    customer = invoiced("ord_acc_customer", at=ist(2026, 10, 6), price_paise=29900, email=BUYER)
    # MARKED, the way the live database's own rows are: `internal = 1` with a reason. A filter written
    # against that column is the obvious way this feature gets broken, and it would not touch the row
    # below, which is internal only by evidence - so both are here.
    mine = invoiced("ord_acc_mine", at=ist(2026, 10, 7), price_paise=5900, email=OWNER, name="Proprietor",
                    marked=internal.ADMIN)
    by_evidence = invoiced("ord_acc_evidence", at=ist(2026, 10, 8), price_paise=4900, email=OWNER,
                           name="Proprietor")

    view = accounting.month_view(month)
    numbers = {document.number: document for document in view["invoices"]}
    assert set(numbers) == {customer["invoice_no"], mine["invoice_no"], by_evidence["invoice_no"]}
    assert numbers[mine["invoice_no"]].internal is True
    assert numbers[mine["invoice_no"]].internal_reason == internal.ADMIN
    assert numbers[by_evidence["invoice_no"]].internal is True
    assert numbers[by_evidence["invoice_no"]].internal_reason == internal.ADMIN
    assert numbers[customer["invoice_no"]].internal is False
    # IN the totals, not beside them: a return is filed on all three documents.
    assert view["totals"]["invoices"]["count"] == 3
    assert view["totals"]["invoices"]["total_paise"] == 29900 + 5900 + 4900
    assert view["internal_invoices"] == 2

    # And they are in the FILE, with "yes" in the Internal column.
    sheets = read_workbook(accounting.month_workbook(view))
    rows = {row[0]: row for row in sheets[accounting.INVOICES_SHEET][1:]}
    flag = column(accounting.INVOICE_HEADER, "Internal")
    assert rows[mine["invoice_no"]][flag] == "yes"
    assert rows[by_evidence["invoice_no"]][flag] == "yes"
    assert rows[customer["invoice_no"]][flag] == "no"

    # THE OTHER HALF OF THE CLAIM: the dashboard's reader is right to leave them out, and does.
    from app.admin import orders as admin_orders

    start, end = accounting.month_bounds(month)
    business, ours = internal.split(admin_orders.paid_between(start, end))
    assert sorted(order["id"] for order in ours) == ["ord_acc_evidence", "ord_acc_mine"]
    assert [order["id"] for order in business] == ["ord_acc_customer"]


def test_a_test_mode_order_with_an_invoice_number_is_in_the_sheet_too():
    """`live = 0` - a rehearsal, a browser check - keeps its invoice if it was ever given one.

    This is the case `orders.paid_between` filters out by design (`COALESCE(live, 1) = 1`), which is why
    this module does not use it: that number came out of the series and a return reconciled against a
    series with an unexplained hole in it is a return somebody has to explain.
    """
    rehearsal = invoiced("ord_acc_rehearsal", at=ist(2026, 10, 9), price_paise=4900, live=0)
    view = accounting.month_view(dt.date(2026, 10, 1))
    document = next(d for d in view["invoices"] if d.number == rehearsal["invoice_no"])
    assert document.internal is True and document.internal_reason == internal.TEST_MODE
    assert view["totals"]["invoices"]["total_paise"] == 4900

    from app.admin import orders as admin_orders

    start, end = accounting.month_bounds(dt.date(2026, 10, 1))
    assert admin_orders.paid_between(start, end) == []     # the dashboard does not count it, correctly


# ---- 3. a month with a refund and its credit note ----------------------------------------------------


def test_a_month_with_a_refund_carries_the_invoice_and_its_credit_note():
    month = dt.date(2026, 10, 1)
    order = invoiced("ord_acc_refund", at=ist(2026, 10, 12), price_paise=5900, state=SELLER_STATE)
    number = refunded("ord_acc_refund", refund_id="rfnd_acc_1", paise=5760, at=ist(2026, 10, 18, 11))

    view = accounting.month_view(month)
    assert [d.number for d in view["invoices"]] == [order["invoice_no"]]
    assert [d.number for d in view["credit_notes"]] == [number]
    note = view["credit_notes"][0]
    assert note.reference == order["invoice_no"]        # the note names the invoice it reduces
    assert note.total_paise == 5760
    # The invoice row names the note, which is what stops an invoice asserting by omission that the money
    # was kept (app/payments/invoice.py makes the same point about the document itself).
    assert view["invoices"][0].reference == number
    assert view["invoices"][0].status == "paid, refunded in part"
    # Net is the invoice less the note, and the taxable value nets off the same way.
    assert view["totals"]["net"]["total_paise"] == 5900 - 5760
    assert view["totals"]["net"]["base_paise"] == view["invoices"][0].base_paise - note.base_paise

    sheets = read_workbook(accounting.month_workbook(view))
    assert [row[0] for row in sheets[accounting.CREDIT_NOTES_SHEET][1:]] == [number]
    refund_column = column(accounting.CREDIT_NOTE_HEADER, "Razorpay refund id")
    assert sheets[accounting.CREDIT_NOTES_SHEET][1][refund_column] == "rfnd_acc_1"


def test_a_credit_note_is_filed_in_the_month_it_was_issued_not_the_invoice_s():
    """October's invoice, November's credit note: two months, two returns, one document each.

    Filing the note under the invoice's month is the mistake worth a test, because it is invisible - both
    figures look reasonable and only the month's total is wrong.
    """
    order = invoiced("ord_acc_across", at=ist(2026, 10, 28), price_paise=9900)
    number = refunded("ord_acc_across", refund_id="rfnd_acc_across", paise=9900, at=ist(2026, 11, 4, 10))

    october = accounting.month_view(dt.date(2026, 10, 1))
    november = accounting.month_view(dt.date(2026, 11, 1))
    assert [d.number for d in october["invoices"]] == [order["invoice_no"]]
    assert october["credit_notes"] == []
    assert november["invoices"] == []
    assert [d.number for d in november["credit_notes"]] == [number]
    assert november["totals"]["net"]["total_paise"] == -9900     # a month of pure reversal reads negative


# ---- 4. a month with nothing in it -------------------------------------------------------------------


def test_a_zero_sale_month_is_a_valid_empty_workbook_and_zip():
    """An empty month is a real answer and it has to be a real file.

    A workbook that was not written, or one sheet short, reads as a failed export rather than as a quiet
    month - and somebody then spends an evening working out which it was.
    """
    view = accounting.month_view(dt.date(2026, 7, 1))
    assert view["invoices"] == [] and view["credit_notes"] == []
    assert view["totals"]["invoices"]["total_paise"] == 0
    assert view["totals"]["net"]["count"] == 0

    sheets = read_workbook(accounting.month_workbook(view))
    assert set(sheets) == {accounting.INVOICES_SHEET, accounting.CREDIT_NOTES_SHEET,
                           accounting.SUMMARY_SHEET}
    # The headers are there with no rows under them, so the columns are readable and the emptiness is
    # legible as emptiness rather than as a truncated file.
    assert sheets[accounting.INVOICES_SHEET] == [list(accounting.INVOICE_HEADER)]
    assert sheets[accounting.CREDIT_NOTES_SHEET] == [list(accounting.CREDIT_NOTE_HEADER)]
    assert labelled(sheets[accounting.SUMMARY_SHEET], "Invoices")[1] == "0.00"

    body, notes = accounting.month_zip(view, render_pdf=lambda html: b"%PDF-1.4 never called")
    assert notes["written"] == []
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert archive.testzip() is None
        assert sorted(archive.namelist()) == ["README.txt", "accounts-2026-07.xlsx"]
        assert b"0 tax invoice(s)" in archive.read("README.txt")


# ---- the ZIP ----------------------------------------------------------------------------------------


def test_the_zip_holds_every_document_of_the_month_plus_the_spreadsheet():
    order = invoiced("ord_acc_zip", at=ist(2026, 10, 14), price_paise=11900)
    number = refunded("ord_acc_zip", refund_id="rfnd_acc_zip", paise=5000, at=ist(2026, 10, 15, 9))
    view = accounting.month_view(dt.date(2026, 10, 1))

    printed = []

    def fake_pdf(html: str) -> bytes:
        printed.append(html)
        return b"%PDF-1.4 fake"

    body, notes = accounting.month_zip(view, render_pdf=fake_pdf)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = sorted(archive.namelist())
    assert names == sorted([
        "README.txt", "accounts-2026-10.xlsx",
        f"invoices/invoice-{order['invoice_no'].replace('/', '-')}.pdf",
        f"credit-notes/credit-note-{number.replace('/', '-')}.pdf"])
    assert notes["html_instead_of_pdf"] == [] and notes["not_rendered"] == []
    # The documents handed to the renderer are the real ones, print-ready: the number is on the page and so
    # are the bundled font faces, without which headless Chromium has no Devanagari face to print with.
    assert order["invoice_no"] in printed[0] and "@font-face" in printed[0]
    assert number in printed[1]


def test_a_document_whose_pdf_cannot_be_printed_goes_in_as_html_and_is_named():
    """Chromium can be absent, busy or broken; none of those may lose a month a record.

    The HTML is the source the PDF is printed from and the thing the customer was linked to, so it is the
    honest substitute - and README.txt names every one that fell back, because a silent substitution is a
    folder somebody files without noticing it is not what they asked for.
    """
    order = invoiced("ord_acc_nopdf", at=ist(2026, 10, 16), price_paise=4900)

    def broken(html: str) -> bytes:
        from app.pdf.browser import PdfBusy

        raise PdfBusy("every render slot on this machine is taken")

    view = accounting.month_view(dt.date(2026, 10, 1))
    body, notes = accounting.month_zip(view, render_pdf=broken)
    stem = f"invoice-{order['invoice_no'].replace('/', '-')}"
    assert notes["html_instead_of_pdf"] == [f"{stem}.pdf"]
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert f"invoices/{stem}.html" in archive.namelist()
        assert order["invoice_no"].encode() in archive.read(f"invoices/{stem}.html")
        readme = archive.read("README.txt").decode()
    assert "NO PDF FOR THESE" in readme and stem in readme


# ---- the page ---------------------------------------------------------------------------------------


def test_the_page_shows_the_month_and_offers_the_download(client):
    order = invoiced("ord_acc_page", at=ist(2026, 10, 20), price_paise=29900)
    response = client.get("/admin/accounting?month=2026-10", headers=header())
    assert response.status_code == 200, response.text
    assert order["invoice_no"] in response.text
    assert "/admin/accounting/download" in response.text
    assert 'value="2026-10"' in response.text
    assert response.headers["x-robots-tag"] == "noindex, nofollow"


def test_the_page_carries_no_customer_name_and_no_full_address_but_the_sheet_does(client):
    """The privacy boundary, which is `accounting.month_page` and not the template.

    A tax invoice is issued to a named buyer, so the SPREADSHEET must carry the name and the address - a
    GST record with the buyer blanked is not a record. A browser page does not need either, and app/admin's
    rule is that the only page showing a full address is the single-order page, which is audited before it
    renders. So the figures are on the page, the records are in the download, and taking the download is
    what gets written to the audit log.
    """
    invoiced("ord_acc_privacy", at=ist(2026, 10, 21), price_paise=5900)
    page = client.get("/admin/accounting?month=2026-10", headers=header()).text
    assert BUYER_NAME not in page
    assert BUYER not in page

    view = accounting.month_view(dt.date(2026, 10, 1))
    sheets = read_workbook(accounting.month_workbook(view))
    row = sheets[accounting.INVOICES_SHEET][1]
    assert row[column(accounting.INVOICE_HEADER, "Customer name")] == BUYER_NAME
    assert row[column(accounting.INVOICE_HEADER, "Customer e-mail")] == BUYER


def test_the_download_returns_one_zip_and_is_audited(client, monkeypatch):
    from app.admin import audit

    monkeypatch.setattr(accounting, "_default_pdf", lambda html: b"%PDF-1.4 fake")
    invoiced("ord_acc_download", at=ist(2026, 10, 22), price_paise=9900)
    response = client.get("/admin/accounting/download?month=2026-10", headers=header())
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "accounts-2026-10.zip" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        assert "accounts-2026-10.xlsx" in archive.namelist()
    assert any(entry["action"] == audit.EXPORT and entry["subject"] == "accounts-2026-10.zip"
               for entry in audit.recent(20))


def test_a_stranger_cannot_reach_either_route(client):
    for path in ("/admin/accounting?month=2026-10", "/admin/accounting/download?month=2026-10"):
        assert client.get(path).status_code == 401, path


def test_an_unreadable_month_shows_the_current_month_rather_than_failing(client):
    """A bad `?month=` is a typo or a crawler. The month shown is named on the page, so the fallback
    cannot be mistaken for the month that was asked for."""
    response = client.get("/admin/accounting?month=not-a-month", headers=header())
    assert response.status_code == 200
    assert accounting.month_label(accounting.parse_month("")) in response.text


# ---- the 1st-of-the-month e-mail ---------------------------------------------------------------------


def test_the_month_end_message_has_the_subject_the_owner_asked_for_and_links_to_the_page():
    invoiced("ord_acc_mail1", at=ist(2026, 10, 3), price_paise=29900)
    invoiced("ord_acc_mail2", at=ist(2026, 10, 9), price_paise=5900)
    subject, body, figures = accounting.compose(dt.date(2026, 10, 1))
    assert subject == "October 2026 accounts ready: 2 invoices, Rs 358"
    assert figures == {"month": "2026-10", "invoices": 2, "charged_inr": 358.0, "credit_notes": 0,
                       "net_inr": 358.0}
    assert "https://admin.test/admin/accounting?month=2026-10" in body
    # A LINK AND NO ATTACHMENT: the file names every customer of the month, and the page needs a sign-in
    # where an e-mailed file does not.
    assert "attaches nothing" in body or "Nothing is attached" in body
    assert "signed in" in body


def test_the_message_says_internal_orders_are_counted_in_rather_than_hiding_them():
    invoiced("ord_acc_mail_mine", at=ist(2026, 10, 4), price_paise=5900, email=OWNER)
    subject, body, _ = accounting.compose(dt.date(2026, 10, 1))
    assert subject == "October 2026 accounts ready: 1 invoices, Rs 59"
    assert "1 invoice(s) and 0 credit note(s) are ours" in body


def test_the_month_end_message_is_sent_once_and_only_once():
    """Deduplicated in `admin_alerts_sent`, the table app/admin/alerts.py already owns - so a cron line
    that fires twice, or a retry after a timeout, cannot put two of these in an inbox."""
    invoiced("ord_acc_once", at=ist(2026, 10, 11), price_paise=4900)
    sent: list[str] = []

    def deliver(subject: str, body: str) -> bool:
        sent.append(subject)
        return True

    # EVERY SEND NEEDS A MOMENT AFTER THE MONTH ENDED. These used to pass no `now`, so they sent
    # October's figures while October was still running - which the send now refuses, because mailing a
    # part-month marks it done and the real message on the 1st would never go. The scenario these tests
    # describe only ever happens after the month closes, so that is when they run it.
    after_october = dt.datetime(2026, 11, 1, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
    assert accounting.send_month_email(dt.date(2026, 10, 1), now=after_october, deliver=deliver) is True
    assert accounting.send_month_email(dt.date(2026, 10, 1), now=after_october, deliver=deliver) is False
    assert len(sent) == 1
    # A new month speaks - and December is the first moment November may be sent.
    after_november = dt.datetime(2026, 12, 1, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
    assert accounting.send_month_email(dt.date(2026, 11, 1), now=after_november, deliver=deliver) is True
    assert len(sent) == 2


def test_a_refused_delivery_is_not_recorded_as_sent():
    """The same rule app/admin/alerts.py's `fire_due` follows: the whole value of this message is that the
    first one arrives, so a Resend outage must leave the next run free to try again."""
    invoiced("ord_acc_retry", at=ist(2026, 10, 13), price_paise=4900)
    after_october = dt.datetime(2026, 11, 1, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
    assert accounting.send_month_email(dt.date(2026, 10, 1), now=after_october,
                                       deliver=lambda s, b: False) is False
    assert accounting.send_month_email(dt.date(2026, 10, 1), now=after_october,
                                       deliver=lambda s, b: True) is True


def test_the_message_goes_to_admin_emails_and_nowhere_else(monkeypatch):
    """ADMIN_EMAILS, not ALERT_EMAIL_TO: the allowlist is who may open the page the message links to, so a
    recipient who could not use the link cannot be on the list by construction."""
    from app import mailer

    monkeypatch.setattr(site, "ADMIN_EMAILS", ("one@rashikundli.invalid", "two@rashikundli.invalid"))
    addressed: list[str] = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, text: addressed.append(to) or True)
    assert accounting.email_delivery("subject", "body") is True
    assert addressed == ["one@rashikundli.invalid", "two@rashikundli.invalid"]

    # Empty allowlist: nothing is sent and nothing is invented to send it to.
    addressed.clear()
    monkeypatch.setattr(site, "ADMIN_EMAILS", ())
    assert accounting.email_delivery("subject", "body") is False
    assert addressed == []


def test_the_first_of_the_month_reports_the_month_that_just_ended():
    """The 09:00 IST cron line runs on the 1st, and what is ready then is the month before it. January has
    to reach back into the previous year, which is why this is date arithmetic and not month - 1."""
    assert accounting.due_month(dt.datetime(2026, 11, 1, 9, 0, tzinfo=accounting.IST)) == dt.date(2026, 10, 1)
    assert accounting.due_month(dt.datetime(2027, 1, 1, 9, 0, tzinfo=accounting.IST)) == dt.date(2026, 12, 1)
    assert accounting.due_month(dt.datetime(2026, 11, 20, 9, 0, tzinfo=accounting.IST)) == dt.date(2026, 10, 1)


# ---- the honest holes -------------------------------------------------------------------------------


def test_an_order_with_no_recorded_place_of_supply_is_filed_to_the_supplier_state_and_says_so():
    """THE RULE CHANGED, ON THE OWNER'S INSTRUCTION, AND THE TEST CHANGED WITH IT.

    Checkout has asked for a place of supply since 28 September 2026, so the only orders without one are
    older than that. They used to keep their tax in a "not classified" column, because inventing a state
    for a past sale is a real thing to be uneasy about. The owner's decision - to be confirmed with his
    CA - is to file them to the supplier's own state, Maharashtra, as CGST 9% + SGST 9%.

    What makes that honest rather than a quiet rewrite is the column: every such row says
    "state defaulted: recipient address not on record", because THE CUSTOMER'S ISSUED INVOICE STILL SHOWS
    NO STATE AND A SINGLE COMPOSITE GST LINE. Those documents are not reissued - a tax document that has
    gone to a buyer is not rewritten months later to tidy a spreadsheet - so for these rows the sheet and
    the document deliberately disagree, and the disagreement is on the face of the export.
    """
    invoiced("ord_acc_nostate", at=ist(2026, 10, 24), price_paise=5900, state=None)
    view = accounting.month_view(dt.date(2026, 10, 1))
    document = view["invoices"][0]
    assert document.unclassified_paise == 0, "the tax is attributed now, not held aside"
    assert document.cgst_paise == 450 and document.sgst_paise == 450, "9% + 9%, the supplier's own state"
    assert document.igst_paise == 0
    assert document.cgst_paise + document.sgst_paise == 900, "and it still adds to the tax collected"
    assert document.state_code == states.seller_code()
    assert document.state_note == accounting.DEFAULTED_NOTE, "a defaulted state that does not say so is a"\
                                                             " state somebody will read as the buyer's"


def test_a_recorded_state_is_never_overwritten_by_the_default():
    """The default is for orders with NO state. An order that has one keeps it, including when it is the
    supplier's own - otherwise a real Maharashtra sale would be labelled as a guess."""
    invoiced("ord_acc_realmh", at=ist(2026, 10, 26), price_paise=5900, state=states.seller_code())
    document = [d for d in accounting.month_view(dt.date(2026, 10, 1))["invoices"]
                if d.order_id == "ord_acc_realmh"][0]
    assert document.cgst_paise == 450 and document.sgst_paise == 450
    assert document.state_note == "", "this buyer's state was recorded; nothing was defaulted"


def test_a_two_letter_state_code_is_recognised_and_its_tax_attributed():
    """"MH" IS Maharashtra, and the export used to disagree.

    The checkout API accepts `^[0-9]{2}$`, so a letter code cannot have come through it and a row
    carrying one was written by hand. The first version of this export therefore printed "(not a GST
    state code: MH)" and put the whole tax in the unattributed column - correct about the data and wrong
    in a return, by the amount of the tax. Recognising it is not the same as accepting anything: see the
    test below, which still refuses a code that is not a state.
    """
    invoiced("ord_acc_mh", at=ist(2026, 10, 25), price_paise=5900, state=None)
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET place_of_supply='MH' WHERE id='ord_acc_mh'")
    document = [d for d in accounting.month_view(dt.date(2026, 10, 1))["invoices"]
                if d.order_id == "ord_acc_mh"][0]
    assert document.state_name == "27 - Maharashtra", "the column names the state and its code"
    assert document.state_code == "27", "and the code cell carries the GST code, not the abbreviation"
    assert document.cgst_paise == 450 and document.sgst_paise == 450, "9% + 9%, the supplier's own state"
    assert document.unclassified_paise == 0, "nothing is left unattributed"


def test_a_stored_place_of_supply_that_is_not_a_state_at_all_is_still_named():
    """Recognising "MH" must not turn into accepting any string. A value that is neither a GST code nor a
    known abbreviation is a data repair somebody has to make, and a repair nobody can see is one nobody
    makes - so it is named in the column rather than folded into "not recorded"."""
    invoiced("ord_acc_junkstate", at=ist(2026, 10, 26), price_paise=5900, state=None)
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET place_of_supply='ZZ' WHERE id='ord_acc_junkstate'")
    document = [d for d in accounting.month_view(dt.date(2026, 10, 1))["invoices"]
                if d.order_id == "ord_acc_junkstate"][0]
    assert document.state_name == "(not a GST state code: ZZ)"
    assert document.unclassified_paise == 900, "its tax is held aside, not filed to a guessed state"


def test_the_description_is_readable_and_never_a_bare_slug():
    """A description column saying "kundali-simple" is an internal identifier leaking into a tax document,
    and a reader cannot tell whether it is a product or a typo."""
    invoiced("ord_acc_desc", at=ist(2026, 10, 27), price_paise=5900, state="27")
    document = [d for d in accounting.month_view(dt.date(2026, 10, 1))["invoices"]
                if d.order_id == "ord_acc_desc"][0]
    assert accounting.SERVICE_PHRASE in document.description
    assert "-report-" not in document.description and "_" not in document.description
    assert accounting.description({"product": "made-up-thing"}).startswith("Made up thing (not in the")


def test_an_invoice_number_with_no_recorded_split_is_counted_as_left_out_rather_than_guessed(caplog):
    """Reachable only by a hand-written row - `invoice.assign` refuses an order with no recorded GST. A
    line with a number and no figures would be worse in a return than a loud absence, so it is both."""
    invoiced("ord_acc_broken", at=ist(2026, 10, 26), price_paise=5900)
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET base_paise=NULL, gst_paise=NULL WHERE id='ord_acc_broken'")
    view = accounting.month_view(dt.date(2026, 10, 1))
    assert view["invoices"] == [] and view["unreadable"] == 1
    sheets = read_workbook(accounting.month_workbook(view))
    assert labelled(sheets[accounting.SUMMARY_SHEET],
                    "Invoice numbers with no recorded GST split")[1] == "1"


def test_months_with_documents_lists_only_months_that_hold_one():
    invoiced("ord_acc_sept", at=ist(2026, 10, 2), price_paise=4900)
    refunded("ord_acc_sept", refund_id="rfnd_acc_sept", paise=4900, at=ist(2026, 12, 2, 9))
    assert accounting.months_with_documents() == ["2026-12", "2026-10"]


# ---- the writer itself ------------------------------------------------------------------------------


def test_money_is_written_from_integer_paise_and_never_rounded():
    """`Rupees` is the last step of the integer path app/payments/gst.py starts, so it is where a paisa
    would be lost. The two-decimal text is built by integer division, not by formatting a float."""
    assert xlsx.Rupees(0).text == "0.00"
    assert xlsx.Rupees(25339).text == "253.39"
    assert xlsx.Rupees(-5760).text == "-57.60"
    assert xlsx.Rupees(1).text == "0.01"
    assert xlsx.Rupees(100000000001).text == "1000000000.01"
    with pytest.raises(TypeError):
        xlsx.Rupees(253.39)      # a float can never get in here


def test_a_none_amount_is_an_empty_cell_and_never_a_zero():
    """NULL is "not recorded" everywhere in this codebase, and a spreadsheet is exactly where a zero
    meaning "unknown" gets summed into a total nobody can explain."""
    sheets = read_workbook(xlsx.workbook([xlsx.Sheet("S", [[xlsx.Rupees(None), xlsx.Rupees(0)]])]))
    assert sheets["S"][0] == ["", "0.00"]


def test_the_workbook_is_a_structurally_complete_package():
    """Every relationship and every content-type override points at a part that is actually in the ZIP.

    This is the check that stands in for opening the file in Excel, which no test here can do. A missing or
    mis-targeted part does not produce an error on OUR side at all: Excel reports "we found a problem with
    some content", repairs the workbook by discarding what it cannot resolve, and opens it - so a sheet can
    go missing from an accounting file with nothing anywhere saying so. Every part is also parsed as XML,
    because a malformed one is repaired exactly the same silent way.
    """
    data = xlsx.workbook([xlsx.Sheet("One", [["a", xlsx.Rupees(1)]]), xlsx.Sheet("Two", [["b"]])])
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        for name in names:
            ET.fromstring(archive.read(name))        # raises on a malformed part
        rels = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
        for part, base in (("_rels/.rels", ""), ("xl/_rels/workbook.xml.rels", "xl/")):
            targets = [node.get("Target") for node in ET.fromstring(archive.read(part)).iter(rels)]
            assert targets, f"{part} declares no relationships"
            for target in targets:
                assert base + target in names, f"{part} points at {target}, which is not in the package"
        types = ET.fromstring(archive.read("[Content_Types].xml"))
        declared = {node.get("PartName").lstrip("/") for node in types
                    if node.tag.endswith("Override")}
        assert declared <= names
        # Every .xml part either has an override or is covered by the Default for the extension.
        assert {"xl/workbook.xml", "xl/styles.xml", "xl/worksheets/sheet1.xml",
                "xl/worksheets/sheet2.xml"} <= declared


def test_a_product_name_in_devanagari_survives_the_round_trip():
    """The description column is the product as the BUYER saw it, which on this site is often Devanagari.
    A workbook that mangles it is a workbook whose line items do not match the documents."""
    name = "सविस्तर जन्मकुंडली अहवाल"
    sheets = read_workbook(xlsx.workbook([xlsx.Sheet("S", [[name, "a & b <c>"]])]))
    assert sheets["S"][0] == [name, "a & b <c>"]
