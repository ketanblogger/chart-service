"""HTML -> PDF with headless Chromium (Playwright).

Environment (all optional; see docs/API.md "Report PDFs"):

| Env var | Default | Meaning |
|---|---|---|
| `PDF_CHROMIUM_EXECUTABLE` | Playwright's bundled chromium-headless-shell | Path to a Chromium / Chrome binary, e.g. `/usr/bin/chromium` on a VPS that uses the distro package |
| `PDF_CHROMIUM_LD_LIBRARY_PATH` | `~/.local/share/astro-chromium/root/usr/lib/x86_64-linux-gnu` if that directory exists, else nothing | Extra shared-library directories for the browser process only (boxes without root where libnss3 etc. were unpacked from .debs). `:`-separated |
| `PDF_CHROMIUM_ARGS` | - | Extra command-line flags, space-separated (e.g. `--disable-gpu`) |
| `PDF_TIMEOUT_SECONDS` | `120` | Per-PDF timeout for every browser step (a 30-60 page book renders twice) |
| `PDF_MAX_CONCURRENT` | `1` | Browsers allowed at once **on the whole machine** (a file lock in `var/`, so several uvicorn workers share the limit). A paid book waits its turn; the free chart sheet waits only `PDF_FREE_WAIT_SECONDS` and then gets a 503 (see `_slots`) |
| `PDF_RENDER_LOCK` | `var/pdf-render.lock` | Where that lock lives. The directory must be writable and on a real filesystem |

A book is rendered TWICE in that one browser (`render_book`): the first pass lays the contents page out with
placeholder page numbers, we read the page number of every heading out of the PDF's own outline - Chromium builds
it from h1-h6 in document order, which is exactly the order of the heading ids in our HTML - and the second pass
prints the real numbers into the fixed-width column, which cannot reflow anything. The passes are compared: if the
second one paginates differently the numbers would be wrong, so it is redone, and if it still will not settle the
contents page is printed without numbers. Better no number than a wrong one.

Design: one short-lived browser per PDF, behind a semaphore. A launch costs well under a second here and
PDFs are generated once per purchase and then served from disk (app/pdf/service.py), so a warm browser
would save little and would add a second long-lived process to supervise (Playwright's sync API is also
bound to the thread that started it, so sharing one needs a dedicated worker thread). If volume ever
justifies it, that worker thread is the upgrade path; nothing outside this module would change.

The page is fully offline: the document and the bundled fonts are served from memory / app/pdf/fonts
through request interception on a made-up origin, and every other request is aborted. After layout, all
four bundled font faces must report `loaded` - otherwise we raise instead of printing a PDF that
silently fell back to some system font (or to tofu boxes) for Devanagari.
"""

import contextlib
import logging
import os
import shlex
import threading
import time
from pathlib import Path

from .render import FONTS_DIR

log = logging.getLogger(__name__)

ORIGIN = "http://report.pdf.internal"
DEFAULT_UNPACKED_LIBS = Path.home() / ".local/share/astro-chromium/root/usr/lib/x86_64-linux-gnu"

_FONT_CHECK_JS = """async () => {
  const faces = [...document.fonts];
  await Promise.allSettled(faces.map(face => face.load()));
  await document.fonts.ready;
  return faces.map(face => ({family: face.family, weight: face.weight, status: face.status}));
}"""


_OVERFLOW_JS = """(limit) => {
  const by = Math.round(document.documentElement.scrollWidth - limit);
  if (by <= 1) return null;
  let worst = null, right = 0;
  for (const el of document.querySelectorAll('body *')) {
    const edge = el.getBoundingClientRect().right;
    if (edge > right) { right = edge; worst = el; }
  }
  const where = worst ? worst.tagName.toLowerCase() + (worst.className ? '.' + worst.className : '') +
                        ' "' + (worst.textContent || '').trim().slice(0, 40) + '"' : '?';
  return {by, what: where};
}"""


class PdfError(RuntimeError):
    """The PDF could not be produced (browser missing, crashed, timed out, or fonts failed to load)."""


class PdfBusy(PdfError):
    """Every render slot on this machine is taken, and this caller's patience for one ran out."""


_semaphore: threading.BoundedSemaphore | None = None
_semaphore_lock = threading.Lock()


def max_concurrent() -> int:
    try:
        return max(1, int(os.getenv("PDF_MAX_CONCURRENT", "1")))
    except ValueError:
        return 1


def _thread_slots() -> threading.BoundedSemaphore:
    global _semaphore
    with _semaphore_lock:
        if _semaphore is None:
            _semaphore = threading.BoundedSemaphore(max_concurrent())
        return _semaphore


def lock_path() -> Path:
    from app.ai.config import ROOT

    path = Path(os.getenv("PDF_RENDER_LOCK", "var/pdf-render.lock"))
    return path if path.is_absolute() else ROOT / path


POLL_SECONDS = 0.05  # how often a bounded waiter re-tries the lock; a render is seconds, so this is free


def _acquire_thread_slot(deadline: float | None) -> bool:
    """The in-process half of the limit, honouring the same deadline as the file locks below."""
    semaphore = _thread_slots()
    if deadline is None:
        semaphore.acquire()
        return True
    remaining = deadline - time.monotonic()
    return semaphore.acquire(timeout=remaining) if remaining > 0 else semaphore.acquire(blocking=False)


@contextlib.contextmanager
def _slots(wait: bool | float = True):
    """At most `PDF_MAX_CONCURRENT` renders **on this machine**.

    A Chromium printing a 60-page book peaks around 400 MB, and uvicorn runs several workers, so a
    per-process semaphore would let `--workers 2` put two of those in flight on a 2 GB box. The limit is
    therefore a set of file locks (one file per slot) that every worker shares: a thread semaphore first,
    so waiting inside a process is cheap, then `flock` across processes. If the lock file cannot be used
    at all (a filesystem without locking), the render still happens - one report matters more than the
    guard - and says so once in the log.

    `wait` is how long to queue for a slot: True (forever), False (not at all), or a number of seconds.
    Anything but True raises PdfBusy when the deadline passes - the bound must never fall through into a
    render, because the bound is the whole point.

    The reason a bound exists at all is THREADPOOL STARVATION, not politeness to paying customers. Both
    PDF routes are sync, so they run in FastAPI's threadpool; a caller that queues here holds one of its
    ~40 threads for as long as it waits, and enough of them starve EVERY route on the site, not just the
    PDF ones. So the limit that matters is on WAITERS, and it applies hardest to the ungated route, which
    an anonymous visitor can fire at will. Note what does NOT justify relaxing it: a render is only a few
    seconds (measured below), so the paid path would tolerate unbounded queueing perfectly well - that is
    an argument about render time, not about how many threads may be parked here.

    The free chart sheet therefore waits a bounded `PDF_FREE_WAIT_SECONDS` (app/pdf/service.py) and then
    gives up; a paid book waits indefinitely, and `render_book` has no `wait` parameter so it cannot be
    made to do otherwise. The asymmetry is deliberate.

    Measured, pinned to two cores with `taskset -c 0,1` to model the 2-vCPU production box: the 64-page
    book is 2.4-2.5 s and the free sheet 0.71 s, so a bounded waiter of ~2 s clears almost every
    collision - and the free sheet's main source of contention is OTHER FREE SHEETS, not books (at 1000
    free downloads and 100 book sales a day that is 710 s/day of free renders against 240 s/day of
    books). It smooths the funnel against its own volume."""
    import fcntl

    deadline = None if wait is True else time.monotonic() + (0.0 if wait is False else float(wait))
    if not _acquire_thread_slot(deadline):
        raise PdfBusy("every render slot on this machine is busy")
    try:
        handles = []
        try:
            for slot in range(max_concurrent()):
                try:
                    path = lock_path().with_suffix(f".{slot}")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    handles.append(path.open("a+b"))
                except OSError as exc:
                    log.warning("PDF render lock %s cannot be opened (%s): rendering without the "
                                "machine-wide concurrency limit", lock_path(), exc)
                    yield
                    return
            while True:
                for handle in handles:
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except OSError:
                        continue  # another process holds this slot; try the next one
                    except (AttributeError, NotImplementedError):  # pragma: no cover - no flock on this box
                        yield
                        return
                    else:
                        try:
                            yield
                        finally:
                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                        return
                # every slot is busy in another process
                if deadline is None:
                    fcntl.flock(handles[0].fileno(), fcntl.LOCK_EX)   # wait for the first one
                    try:
                        yield
                    finally:
                        fcntl.flock(handles[0].fileno(), fcntl.LOCK_UN)
                    return
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PdfBusy("every render slot on this machine is busy")
                time.sleep(min(POLL_SECONDS, remaining))
        finally:
            for handle in handles:
                with contextlib.suppress(OSError):
                    handle.close()
    finally:
        _thread_slots().release()


def launch_options() -> dict:
    """Keyword arguments for `chromium.launch()`, from the environment. Read per call so tests can change it."""
    options: dict = {"headless": True}
    executable = os.getenv("PDF_CHROMIUM_EXECUTABLE", "").strip()
    if executable:
        options["executable_path"] = executable
    args = shlex.split(os.getenv("PDF_CHROMIUM_ARGS", ""))
    if args:
        options["args"] = args
    extra_libs = os.getenv("PDF_CHROMIUM_LD_LIBRARY_PATH")
    if extra_libs is None and DEFAULT_UNPACKED_LIBS.is_dir():
        extra_libs = str(DEFAULT_UNPACKED_LIBS)
    if extra_libs:
        env = dict(os.environ)
        env["LD_LIBRARY_PATH"] = ":".join(part for part in (extra_libs, env.get("LD_LIBRARY_PATH", "")) if part)
        options["env"] = env
    return options


def _timeout_ms() -> float:
    return float(os.getenv("PDF_TIMEOUT_SECONDS", "120")) * 1000


def _serve(document: dict):
    """Request interception: the document currently in `document["html"]`, the bundled fonts, nothing else."""
    fonts_root = FONTS_DIR.resolve()

    def handler(route):
        url = route.request.url.split("?", 1)[0]
        if url == f"{ORIGIN}/report.html":
            return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=document["html"])
        if url.startswith(f"{ORIGIN}/fonts/"):
            path = (fonts_root / url.rsplit("/", 1)[1]).resolve()
            if path.parent == fonts_root and path.suffix == ".ttf" and path.is_file():
                return route.fulfill(status=200, content_type="font/ttf", body=path.read_bytes())
        return route.abort()  # no network, no local files: reports are rendered from what we hand over only

    return handler


MAX_TOC_PASSES = 3  # first pass + at most two attempts to make the page numbers agree with the layout


def _run(build_html, screenshot_path: str | None, *, two_pass: bool, wait: bool | float = True) -> bytes:
    """Open one browser, render the document (twice when it has a contents page), return the PDF bytes."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - playwright is in requirements.txt
        raise PdfError("playwright is not installed") from exc

    from .render import content_width_px, heading_ids

    timeout = _timeout_ms()
    document = {"html": build_html(None)}
    anchors = heading_ids(document["html"]) if two_pass else []
    width = content_width_px(document["html"])
    with _slots(wait):
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(timeout=timeout, **launch_options())
                try:
                    # the viewport is one page's content box and the media is print, so the layout the
                    # checks below see is the layout that is printed
                    context = browser.new_context(java_script_enabled=True, offline=False, service_workers="block",
                                                  viewport={"width": width, "height": 1000})
                    context.set_default_timeout(timeout)
                    context.route("**/*", _serve(document))
                    page = context.new_page()
                    page.emulate_media(media="print")
                    pass_number = 0

                    def render_current() -> bytes:
                        nonlocal pass_number
                        pass_number += 1
                        page.goto(f"{ORIGIN}/report.html?pass={pass_number}", wait_until="load")
                        if pass_number == 1:
                            # Chromium lays every page out in the first page's content box and silently
                            # shrinks the WHOLE document if anything is wider: that would change every type
                            # size in the book, so say so loudly instead of printing a quietly scaled book.
                            overflow = page.evaluate(_OVERFLOW_JS, width)
                            if overflow:
                                log.warning("the print layout overflows the page width by %spx (%s): Chromium "
                                            "will shrink the whole book to fit", overflow["by"], overflow["what"])
                            faces = page.evaluate(_FONT_CHECK_JS)
                            failed = [face for face in faces if face["status"] != "loaded"]
                            if not faces or failed:
                                raise PdfError(f"bundled fonts did not load: {failed or 'no @font-face rules found'}")
                            if screenshot_path:
                                page.screenshot(path=screenshot_path, full_page=True)
                        return page.pdf(print_background=True, prefer_css_page_size=True,
                                        display_header_footer=False, outline=True, tagged=True)

                    pdf = render_current()
                    if not two_pass:
                        return pdf
                    pages = outline_pages(pdf)
                    if len(pages) != len(anchors):
                        if anchors:
                            log.warning("PDF outline has %s entries for %s headings: the contents page is printed "
                                        "without page numbers", len(pages), len(anchors))
                        document["html"] = build_html({})
                        return render_current()
                    for _ in range(MAX_TOC_PASSES - 1):
                        document["html"] = build_html(dict(zip(anchors, pages)))
                        filled = render_current()
                        settled = outline_pages(filled)
                        if settled == pages:
                            return filled  # the numbers printed are the pages they landed on
                        pages = settled
                    log.warning("the book did not paginate the same way twice; printing it without page numbers")
                    document["html"] = build_html({})
                    return render_current()
                finally:
                    browser.close()
        except PlaywrightError as exc:
            raise PdfError(f"Chromium could not produce the PDF: {exc}") from exc


def html_to_pdf(html: str, *, screenshot_path: str | None = None, wait: bool | float = True) -> bytes:
    """Render one finished HTML document (from app/pdf/render.py) to PDF bytes - single pass, so the
    contents page keeps whatever numbers that document already carries. Blocking; call from a worker thread
    (FastAPI sync routes already are). Raises PdfError, or PdfBusy when every render slot on the machine
    is taken and `wait` (True / False / seconds) runs out."""
    return _run(lambda pages: html, screenshot_path, two_pass=False, wait=wait)


def render_book(build_html, *, screenshot_path: str | None = None) -> bytes:
    """The two-pass render. `build_html(toc_pages)` must return the whole document: called with None for the
    first pass (placeholder page numbers), then with {heading id: page number} for the real one, and with {}
    if the numbers cannot be trusted. Blocking. Raises PdfError."""
    return _run(build_html, screenshot_path, two_pass=True)


def outline_pages(pdf: bytes) -> list[int]:
    """1-based page number of every entry of the PDF's outline, in document order.

    Chromium builds the outline from the h1-h6 elements of the page, depth-first in document order, so this
    list lines up one-to-one with `render.heading_ids()` of the HTML it was printed from. (Chromium sometimes
    repeats a heading's text in the title when a page break splits it, which is why nothing here matches on
    titles.) An outline entry whose destination cannot be resolved stops the walk: a short list means "do not
    trust these numbers", which the caller handles."""
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf))
    numbers: list[int] = []

    def walk(items) -> bool:
        for item in items:
            if isinstance(item, list):
                if not walk(item):
                    return False
            else:
                try:
                    numbers.append(reader.get_destination_page_number(item) + 1)
                except Exception:  # noqa: BLE001 - an unresolvable destination invalidates the whole mapping
                    return False
        return True

    try:
        walk(reader.outline)
    except Exception as exc:  # noqa: BLE001 - a PDF we cannot read the outline of is still a good PDF
        log.warning("could not read the PDF outline: %s: %s", type(exc).__name__, exc)
        return []
    return numbers


def embedded_fonts(pdf: bytes) -> set[str]:
    """Font names embedded in a PDF, without the subset prefix: {"NotoSans-Regular", "NotoSansDevanagari-Bold", ...}."""
    import io

    from pypdf import PdfReader

    names = set()
    for page in PdfReader(io.BytesIO(pdf)).pages:
        fonts = (page.get("/Resources") or {}).get("/Font") or {}
        for font in fonts.values():
            names.add(str(font.get_object().get("/BaseFont", "")).lstrip("/").split("+")[-1])
    return names


def fallback_fonts(pdf: bytes) -> set[str]:
    """Embedded fonts that are not ours. Non-empty means some character was missing from the bundled Noto
    files and Chromium took it from a system font - the text is still readable here, but may be tofu elsewhere."""
    bundled = {path.stem for path in FONTS_DIR.glob("*.ttf")}
    return {name for name in embedded_fonts(pdf) if name and name not in bundled}


def chromium_available() -> tuple[bool, str]:
    """(ok, reason). Used by tests to skip cleanly, and handy for a deploy smoke test."""
    try:
        pdf = html_to_pdf(
            "<!DOCTYPE html><html><head><style>@font-face{font-family:F;src:url('fonts/NotoSans-Regular.ttf')}"
            "body{font-family:F}</style></head><body>ok</body></html>")
    except PdfError as exc:
        return False, str(exc).splitlines()[0][:300]
    return (True, "") if pdf.startswith(b"%PDF") else (False, "Chromium returned something that is not a PDF")
