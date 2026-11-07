"""The sample pages on /kundli-pdf: real pages of the real document, from a birth that never happened.

THE PAGE PROMISED A SAMPLE AND DID NOT HAVE ONE. The URL registry's comment for /kundli-pdf has said
"with a sample of each" since the page was written; what it carried was two bullet lists and a price.
Somebody deciding whether to pay Rs 299 for a document wants to see a page of it.

TWO THINGS THESE TESTS GUARD, and they pull in opposite directions:

The images must be the REAL DOCUMENT - rendered by scripts/sample_preview.py through the same endpoint
that serves a reader their own PDF, not a mock-up drawn for the page, and not cropped to look denser
than the document is.

And the birth must be INVENTED, and said to be invented on the page. No real birth detail and no real
person's name goes into this repository; an image published here is cached and indexed by people we will
never hear from.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import kundli_pdf_page

client = TestClient(app)

PATHS = {"en": "/kundli-pdf", "hi": "/hi/kundli-pdf", "mr": "/mr/kundali-pdf"}


@pytest.mark.parametrize("lang, path", PATHS.items())
def test_the_sample_section_renders_with_real_images(lang, path):
    html = client.get(path).text
    assert 'id="sample"' in html, f"{path} has no sample section"
    sources = re.findall(r'<img src="(/static/img/sample/[^"]+)"', html)
    assert sources, f"{path} shows no sample pages"
    for src in sources:
        assert Path("app" + src).exists(), f"{src} is referenced and not checked in"
        assert client.get(src).status_code == 200


@pytest.mark.parametrize("lang, path", PATHS.items())
def test_every_sample_image_reserves_its_own_space(lang, path):
    """THE SHIFT THIS AVOIDS. This block sits above the fold on a phone; without width and height the
    page reflows when the first picture decodes. Measured: the section adds 0.0000 CLS, because the
    dimensions are read from the files rather than guessed - a guessed height reserves the wrong box and
    causes the very shift it is meant to prevent."""
    html = client.get(path).text
    section = html[html.index('id="sample"'):]
    section = section[:section.index("</section>")]
    tags = re.findall(r"<img [^>]+>", section)
    assert tags
    for tag in tags:
        assert re.search(r'width="\d+"', tag), f"no width: {tag[:80]}"
        assert re.search(r'height="\d+"', tag), f"no height: {tag[:80]}"


@pytest.mark.parametrize("lang", list(PATHS))
def test_the_declared_dimensions_are_the_files_real_dimensions(lang):
    """Cross-checked against Pillow, which the APPLICATION no longer uses - that is the point of the
    check. The page reads the WebP header itself; this proves the header read agrees with a real image
    library, without the page needing one."""
    from PIL import Image

    for page in kundli_pdf_page.sample_pages(lang):
        with Image.open(Path("app" + page["src"])) as image:
            assert (image.width, image.height) == (page["width"], page["height"])


def test_the_sample_pages_need_no_image_library_at_request_time(monkeypatch):
    """THE BUG THIS FILE DID NOT CATCH, and the production 500 it caused.

    `sample_pages()` imported Pillow inside the function. Pillow is in the developer's environment
    because something else pulls it in, and it is NOT in requirements.txt - so every test passed, the
    page rendered locally, and in production the import raised at REQUEST time. /kundli-pdf,
    /hi/kundli-pdf and /mr/kundali-pdf returned 500 while the rest of the site was fine.

    An import inside a function is deferred, not optional. This test makes the application prove it can
    render these pages with no image library installed at all."""
    import builtins

    real_import = builtins.__import__

    def without_pil(name, *args, **kwargs):
        if name == "PIL" or name.startswith("PIL."):
            raise ImportError("No module named 'PIL'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_pil)
    for name in [module for module in list(sys.modules) if module.startswith("PIL")]:
        monkeypatch.delitem(sys.modules, name, raising=False)

    for lang, path in PATHS.items():
        response = client.get(path)
        assert response.status_code == 200, f"{path} needs an image library to render"
        assert 'id="sample"' in response.text, f"{path} dropped the sample without Pillow"
        assert kundli_pdf_page.sample_pages(lang), f"{lang} found no sample pages without Pillow"


@pytest.mark.parametrize("lang, path", PATHS.items())
def test_the_page_says_the_birth_is_invented(lang, path):
    """A sample that does not say it is a sample is a document about a person who does not exist,
    presented as one who does."""
    html = client.get(path).text
    note = kundli_pdf_page.COPY[lang]["sample_note"]
    assert note in html
    invented = {"en": "does not exist", "hi": "नहीं है", "mr": "अस्तित्वात नाही"}[lang]
    assert invented in note, f"the {lang} note does not say the person is invented"


def test_no_real_birth_detail_is_committed_with_the_sample():
    """The standing rule, checked where it would be easiest to break: a sample needs a birth, and the
    convenient birth to use is a real one."""
    script = Path("scripts/sample_preview.py").read_text(encoding="utf-8")
    assert "Asha Kulkarni" in script
    for banned in ("1889-11-14", "Nehru", "nehru"):
        assert banned not in script, f"{banned} appears in the sample generator"


@pytest.mark.parametrize("lang", list(PATHS))
def test_the_sample_pdf_is_offered_whole(lang):
    """Two pages are a preview. The reader can have the whole free document without giving anything -
    which is the claim the rest of this page makes, so the page had better honour it."""
    response = client.get(f"/static/img/sample/{lang}-free-sample.pdf")
    assert response.status_code == 200
    assert response.content[:4] == b"%PDF"


def test_a_missing_sample_image_does_not_break_the_page():
    """The page is useful without the sample and must not 500 because an asset was not regenerated -
    rendering one needs Chromium, which a web server must never depend on."""
    assert kundli_pdf_page.sample_pages("xx") == []


def test_the_application_never_imports_a_test_only_library():
    """THE GENERAL SHAPE OF THE BUG. requirements.txt has a runtime section and a test/tools section;
    anything the app imports must come from the first. Pillow sat in the second (and before that, in
    nobody's list at all) and was imported from app/web/kundli_pdf_page.py - which works on any machine
    where a test run has installed it, and 500s on the server where it is not.

    Checked by reading the source rather than by importing, so it fails on the developer's machine too,
    where every one of these libraries is present."""
    offenders = []
    for path in Path("app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for module in ("PIL", "pypdfium2", "fontTools", "py_mini_racer", "pytest"):
            if re.search(rf"^\s*(from {module}[. ]|import {module}\b)", text, flags=re.M):
                offenders.append(f"{path}: {module}")
    assert not offenders, f"the application imports a test/tools-only library: {offenders}"
