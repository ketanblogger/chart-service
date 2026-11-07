"""The favicon, the app icons and the web manifest.

Most of this is plumbing that only breaks in a browser, so the checks are about the two things that are
invisible from the markup: that the files a browser fetches from the ROOT exist at the root (a <link> in the
head does not help a bare /favicon.ico request, which every browser makes before it has parsed anything), and
that the icons are shaped the way the platforms that crop them expect.

The last test is the one worth keeping: the manifest's theme colour is the brand's primary, written in a
second file, with nothing connecting the two. That is the same shape as the Razorpay checkout hex and the two
stylesheets - a value whose correctness lives somewhere else.
"""

import json
import re
import struct
from pathlib import Path

import pytest
from PIL import Image

from tests.test_web import client

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "app/static/icons"
INDIGO = (36, 27, 84)          # --color-primary #241B54


def test_the_files_browsers_fetch_from_the_root_are_at_the_root():
    for path, media in (("/favicon.ico", "image/x-icon"),
                        ("/apple-touch-icon.png", "image/png"),
                        ("/site.webmanifest", "application/manifest+json")):
        response = client.get(path)
        assert response.status_code == 200, f"{path} is not served from the root"
        assert media in response.headers["content-type"], f"{path}: {response.headers['content-type']}"


def test_the_manifest_has_what_an_install_prompt_requires():
    """name, short_name, start_url, display and a 192 plus a 512 icon. Without start_url and display the
    manifest parses and the install prompt never appears, which is the failure that looks like success."""
    manifest = json.loads(client.get("/site.webmanifest").content)
    for key in ("name", "short_name", "start_url", "display", "theme_color", "background_color", "icons"):
        assert manifest.get(key), f"the manifest has no {key}"
    assert manifest["display"] in {"standalone", "fullscreen", "minimal-ui"}, manifest["display"]
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes, sizes


@pytest.mark.parametrize("icon", json.loads((ROOT / "app/static/site.webmanifest").read_text())["icons"])
def test_every_manifest_icon_exists_and_is_the_size_it_claims(icon):
    response = client.get(icon["src"])
    assert response.status_code == 200, icon["src"]
    declared = tuple(int(n) for n in icon["sizes"].split("x"))
    with Image.open(ROOT / icon["src"].lstrip("/").replace("static/", "app/static/", 1)) as image:
        assert image.size == declared, f"{icon['src']} is {image.size}, manifest says {icon['sizes']}"


def test_the_ico_carries_the_sizes_windows_and_old_browsers_ask_for():
    """A .ico with one entry is the easy mistake: Pillow derives its sizes from the source image, so saving
    from an already-16px image silently produces a single 16px entry."""
    data = (ICONS / "favicon.ico").read_bytes()
    count = struct.unpack("<H", data[4:6])[0]
    entries = {(data[6 + i * 16] or 256, data[7 + i * 16] or 256) for i in range(count)}
    assert {(16, 16), (32, 32), (48, 48)} <= entries, entries


def test_the_maskable_icon_bleeds_to_every_edge():
    """A maskable icon is cropped by the OS to a circle or a squircle of its own choosing, so it has to be
    opaque to the corners and keep its content well inside. A source with rounded corners or a light margin
    shows as slivers inside the platform's own mask."""
    with Image.open(ICONS / "maskable-icon-512.png") as image:
        assert image.mode == "RGB", "a maskable icon must not be transparent"
        pixels = image.load()
        for corner in ((0, 0), (511, 0), (0, 511), (511, 511)):
            assert pixels[corner] == INDIGO, f"corner {corner} is {pixels[corner]}, not the brand indigo"
        # the emblem must sit inside the safe zone: the ring of pixels at 90% radius is still background
        assert pixels[256, 30] == INDIGO and pixels[30, 256] == INDIGO, "content reaches the crop zone"


def test_the_apple_icon_is_opaque_and_unrounded():
    """iOS composites onto white and applies its own corner radius. Transparency shows as white patches and
    a baked-in radius shows as a second, smaller rounding inside Apple's."""
    with Image.open(ICONS / "apple-touch-icon-180.png") as image:
        assert image.mode == "RGB", "iOS does not honour alpha here"
        assert image.load()[(0, 0)] == INDIGO, "the corner is not the tile colour, so a radius is baked in"


def test_the_manifest_theme_colour_is_the_brands_primary():
    """The value lives in site.webmanifest and its correctness lives in site.css, with nothing linking them -
    the same shape as the checkout theme hex. This is the link."""
    manifest = json.loads((ROOT / "app/static/site.webmanifest").read_text())
    css = (ROOT / "app/static/css/site.css").read_text(encoding="utf-8")
    primary = re.search(r"--color-primary:\s*(#[0-9A-Fa-f]{6})", css).group(1)
    background = re.search(r"--color-bg:\s*(#[0-9A-Fa-f]{6})", css).group(1)
    assert manifest["theme_color"].lower() == primary.lower(), (
        f"manifest theme_color {manifest['theme_color']} but --color-primary is {primary}")
    assert manifest["background_color"].lower() == background.lower(), (
        f"manifest background_color {manifest['background_color']} but --color-bg is {background}")


@pytest.mark.parametrize("source", ["favicon-source.png", "main-logo.png", "emblem-96.png"])
def test_the_stored_brand_sources_carry_no_colour_under_their_transparency(source):
    """The files as delivered had red and green noise sitting under an alpha of zero - invisible until
    something resized or flattened them without weighting RGB by alpha, and then it bled in as speckle.
    Pillow's resize does exactly that: it averages RGB and alpha separately, so a transparent red pixel
    contributes its red at full weight to a neighbour.

    The copies in this repository are matted: every pixel that is not essentially opaque carries the
    artwork's own gold, so any bleed is gold into gold. This asserts that stays true, because the obvious
    way to undo it is to re-copy the raw file over the top.
    """
    gold = (224, 165, 38)
    with Image.open(ROOT / "app/static/brand" / source) as image:
        image = image.convert("RGBA")
        rgb, alpha = image.convert("RGB").load(), image.getchannel("A").load()
        offenders = [(x, y, rgb[x, y]) for y in range(0, image.height, 2) for x in range(0, image.width, 2)
                     if alpha[x, y] < 200 and rgb[x, y] != gold]
    assert not offenders, (
        f"{source}: {len(offenders)} near-transparent pixels carry colour that is not the matte, e.g. "
        f"{offenders[:3]}. Re-run the icon generator rather than copying the raw source in.")
