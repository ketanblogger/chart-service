"""PDFs. Two documents, built by two separate render paths that share only the fonts and the stylesheet.

THE PAID REPORT is a printed BOOK - cover, contents page with real page numbers, each part starting on a
new page, ready to print and bind.

report JSON -> parts and chapters (book.py) -> blocks (blocks.py) + cover ornaments (cover.py)
            -> print HTML (render.py, templates/report.html + print.css)
            -> headless Chromium, rendered twice so the contents page carries true page numbers (browser.py)
            -> cached file per report, template version and page size (service.py).

THE FREE BASIC CHART PDF (basic.py, templates/basic.html) is a few A5 sheets of pure engine output: both
charts, the graha table, the doshas and the running dasha. It makes NO AI call - that is its whole point -
and it is a separate document rather than the book with its paid parts switched off, because a switch is
one careless edit away from being flipped. Its template can draw only engine blocks and our own labels.

Every PDF, paid or free, carries the "How this report was made" box on its first page
(a trust requirement: the reader is told the dates were computed, not invented) and the engine's
accuracy caveats when the chart flags them.

Fonts in app/pdf/fonts are Noto Sans 2.015 and Noto Sans Devanagari 2.007 (Regular + Bold, hinted TTF) from
https://github.com/notofonts/notofonts.github.io, under the SIL Open Font License 1.1 (fonts/OFL.txt).
"""

from .basic import render_basic_html
from .browser import (PdfError, chromium_available, embedded_fonts, fallback_fonts, html_to_pdf, outline_pages,
                      render_book)
from .render import heading_ids, render_report_html

__all__ = ["PdfError", "chromium_available", "embedded_fonts", "fallback_fonts", "heading_ids", "html_to_pdf",
           "outline_pages", "render_basic_html", "render_book", "render_report_html"]
