"""PDF cache: one file per (report id, template version, page size, cover names) under var/pdfs.

`var/pdfs/<id>-v<N>-a5-plain.pdf` is the PDF without a name; one personalised with a name on the cover is
`var/pdfs/<id>-v<N>-a5-<hash of names>.pdf`. A report never changes once generated (its id is a hash of its
inputs), so a cached PDF stays valid until the template changes: bump TEMPLATE_VERSION in render.py and
new files are rendered on the next download (old ones can simply be deleted).

The FREE chart PDF has no report id (it is not a report - it is one engine chart, and nothing about it
is stored), so it is cached under `var/pdfs/basic/` by the SHA-256 of its own rendered HTML. That is the
exact right key: two requests share a file if and only if every printed character matches, so a template
change, a language, a name, a page size or a different birth minute each get their own file without
anybody having to remember to bump a version. Rendering the HTML to hash it costs a millisecond and no
browser. The directory is capped (`PDF_BASIC_CACHE_MAX`, default 400 files, oldest evicted): it is a free
endpoint, so its cache has to have a ceiling that does not depend on anyone behaving.

Env: `PDFS_DIR` (default `var/pdfs`). `PDF_MAX_VARIANTS` (default 5) caps how many differently-named
copies of one report may exist, so the `name` query parameter cannot be used to fill the disk.
`PDF_BASIC_CACHE_MAX` (default 400) caps the free chart cache. `PDF_FREE_WAIT_SECONDS` (default 2) is
how long a free download waits for the machine-wide render slot before giving up with a 503.
"""

import contextlib
import hashlib
import json
import logging
import os
import re
import threading
from pathlib import Path

from app.ai.config import ROOT

from .basic import render_basic_html
from .browser import PdfBusy, fallback_fonts, html_to_pdf, render_book
from .render import TEMPLATE_VERSION, clean_name, page_size_name, render_report_html

log = logging.getLogger(__name__)

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class TooManyVariants(RuntimeError):
    """This report already has PDF_MAX_VARIANTS differently-named PDFs."""


def pdfs_dir() -> Path:
    path = Path(os.getenv("PDFS_DIR", "var/pdfs"))
    return path if path.is_absolute() else ROOT / path


def _variant(names: dict[str, str]) -> str:
    payload = json.dumps({"v": TEMPLATE_VERSION, "names": names}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def pdf_path(report_id: str, names: dict[str, str] | None = None, page_size: str | None = None) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", report_id):
        raise ValueError("bad report id")
    names = {key: value for key, value in (names or {}).items() if value}
    size = page_size_name(page_size)
    return pdfs_dir() / f"{report_id}-v{TEMPLATE_VERSION}-{size}-{_variant(names) if names else 'plain'}.pdf"


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def ensure_pdf(report: dict, names: dict[str, str | None] | None = None, page_size: str | None = None) -> Path:
    """Path of the PDF for this report, generating it on first use. Blocking: a few seconds on a miss
    (a book is rendered twice, so that its contents page carries true page numbers).

    Raises PdfError if Chromium cannot produce it, TooManyVariants if the name quota is used up."""
    cleaned = {key: clean_name(value) for key, value in (names or {}).items()}
    cleaned = {key: value for key, value in cleaned.items() if value}
    size = page_size_name(page_size)
    path = pdf_path(report["id"], cleaned, size)
    if path.is_file():
        return path
    with _lock_for(path.name):  # two simultaneous downloads of a new report render it once
        if path.is_file():
            return path
        if cleaned:
            limit = int(os.getenv("PDF_MAX_VARIANTS", "5"))
            existing = [p for p in path.parent.glob(f"{report['id']}-v{TEMPLATE_VERSION}-{size}-*.pdf") if "plain" not in p.name]
            if len(existing) >= limit:
                raise TooManyVariants(report["id"])
        pdf = render_book(lambda toc_pages: render_report_html(report, names=cleaned, page_size=size,
                                                               toc_pages=toc_pages))
        try:
            strays = fallback_fonts(pdf)
        except Exception:  # inspection is a courtesy; never lose a good PDF over it
            strays = set()
        if strays:
            log.warning("report %s: PDF uses non-bundled fonts %s - some character is missing from app/pdf/fonts",
                        report["id"], sorted(strays))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_bytes(pdf)
        tmp.replace(path)  # atomic: a crash never leaves a half-written PDF to be served
        return path


def download_name(report: dict) -> str:
    """ASCII file name for Content-Disposition, e.g. `kundali-report-1931-10-15-mr.pdf`."""
    data = report.get("data") or {}
    dates = [(data.get(key) or {}).get("input", {}).get("date") for key in ("chart", "boy_chart", "girl_chart")]
    parts = [report.get("product", "report"), *[d for d in dates if d], report.get("language", "")]
    return re.sub(r"[^A-Za-z0-9._-]+", "-", "-".join(p for p in parts if p)).strip("-") + ".pdf"


# ---- the free Basic Chart PDF -------------------------------------------------------------------

BASIC_DIR = "basic"
DEFAULT_BASIC_CACHE_MAX = 400

# How long a free chart download queues for the machine-wide render slot before giving up (503 pdf_busy).
#
# Not zero, and not unbounded. A queued request holds a FastAPI threadpool thread for as long as it waits,
# and this is the ungated route, so unbounded queueing is how an anonymous visitor starves every route on
# the site. But refusing instantly throws away the easy wins: measured on two pinned cores (`taskset -c
# 0,1`, modelling the 2-vCPU production box) the 64-page book is 2.4-2.5 s and this sheet is 0.71 s, and
# the free sheet's main source of contention is OTHER FREE SHEETS - at 1000 free downloads and 100 book
# sales a day that is 710 s/day of free renders against 240 s/day of books. Two seconds therefore clears
# every free-on-free collision and most free-on-book ones, and caps the thread cost of doing so.
DEFAULT_FREE_WAIT_SECONDS = 2.0


def basic_dir() -> Path:
    return pdfs_dir() / BASIC_DIR


def free_wait_seconds() -> float:
    """Seconds a free chart download may queue for a render slot. 0 refuses instantly; read per call."""
    try:
        return max(0.0, float(os.getenv("PDF_FREE_WAIT_SECONDS", str(DEFAULT_FREE_WAIT_SECONDS))))
    except ValueError:
        return DEFAULT_FREE_WAIT_SECONDS


def _basic_cache_max() -> int:
    try:
        return max(1, int(os.getenv("PDF_BASIC_CACHE_MAX", str(DEFAULT_BASIC_CACHE_MAX))))
    except ValueError:
        return DEFAULT_BASIC_CACHE_MAX


def _prune_basic(keep: Path) -> None:
    """Hold the free cache to its ceiling, oldest first. `keep` is the file just written, which is never
    evicted. Best effort: a cache that cannot be pruned is a disk-space problem, not a reason to fail a
    download that has already been produced."""
    try:
        files = sorted(basic_dir().glob("*.pdf"), key=lambda path: path.stat().st_mtime)
    except OSError:
        return
    for path in files[:max(0, len(files) - _basic_cache_max())]:
        if path != keep:
            with contextlib.suppress(OSError):
                path.unlink()


def ensure_basic_pdf(chart: dict, *, language: str = "en", name: str | None = None,
                     chart_script: str | None = None, page_size: str | None = None,
                     approximate_time: bool = False, before_render=None) -> Path:
    """Path of the FREE chart PDF for this engine chart, rendering it on first use.

    **No AI call happens anywhere under this function.** It renders app/pdf/basic.py's document and prints
    it; there is no report, no entitlement and no model client on the path. One pass, not two - the free
    sheet has no contents page to number.

    `before_render` is called once, only when a browser is actually about to run, and may raise to refuse.
    That is where the route's rate limit lives, so that a CACHE HIT COSTS NOTHING: somebody downloading the
    same sheet again - or a whole CGNAT pool downloading a chart one of them has already generated - is not
    charged for a render that does not happen. The limit then counts what it is there to ration, which is
    Chromium, not HTTP requests.

    Raises PdfError if Chromium cannot produce it, PdfBusy if every render slot on the machine is taken."""
    html = render_basic_html(chart, language=language, name=name, chart_script=chart_script,
                             page_size=page_size, approximate_time=approximate_time)
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()[:32]
    path = basic_dir() / f"chart-{digest}.pdf"
    if path.is_file():
        return path
    with _lock_for(path.name):
        if path.is_file():
            return path
        if before_render is not None:
            before_render()
        # A BOUNDED wait, never an unbounded one: see DEFAULT_FREE_WAIT_SECONDS above and `_slots` in
        # app/pdf/browser.py. When it runs out this raises PdfBusy, which the route turns into a 503 -
        # it must never fall through into a render, because the bound is the whole point.
        pdf = html_to_pdf(html, wait=free_wait_seconds())
        try:
            strays = fallback_fonts(pdf)
        except Exception:  # inspection is a courtesy; never lose a good PDF over it
            strays = set()
        if strays:
            log.warning("free chart PDF uses non-bundled fonts %s - some character is missing from "
                        "app/pdf/fonts", sorted(strays))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_bytes(pdf)
        tmp.replace(path)  # atomic: a crash never leaves a half-written PDF to be served
        _prune_basic(path)
        return path


def basic_download_name(chart: dict, language: str) -> str:
    """ASCII file name for Content-Disposition, e.g. `basic-chart-1931-10-15-mr.pdf`."""
    date = (chart.get("input") or {}).get("date") or ""
    parts = ["basic-chart", str(date), language]
    return re.sub(r"[^A-Za-z0-9._-]+", "-", "-".join(part for part in parts if part)).strip("-") + ".pdf"
