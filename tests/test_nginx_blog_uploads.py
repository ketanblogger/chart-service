"""The one place the site-wide request-body limit is lifted, and why it has to be.

WHAT HAPPENED: Blogauto's image uploads got HTTP 413 in production. nginx caps request bodies at 256k
site-wide, and `POST /api/blog/images` sends the file AS the body - so every real hero image was
refused by the proxy before the application was reached, and the caller got nginx's HTML error page
rather than the API's JSON.

It was fixed by hand on the server first. These tests exist so the repository cannot drift back from
it: a deployed config that only lives on one machine is a config nobody can review, and the next
rebuild loses it silently.

The number is 3m rather than something generous because app/blog/config.py enforces BLOG_MAX_IMAGE_KB
(2 MiB by default) and counts the body as it reads it. nginx refusing at 3m and the app refusing at
2 MiB means a file in between gets the APPLICATION's message, which says what the limit is.
"""
from __future__ import annotations

import re
from pathlib import Path

CONF = Path("deploy/nginx/astrology.conf").read_text(encoding="utf-8")


def block(name: str) -> str:
    """One location block's body, by its exact header line."""
    start = CONF.index(name)
    depth, index = 0, CONF.index("{", start)
    for position in range(index, len(CONF)):
        if CONF[position] == "{":
            depth += 1
        elif CONF[position] == "}":
            depth -= 1
            if depth == 0:
                return CONF[index:position]
    raise AssertionError(f"{name} is not closed")


def test_the_upload_route_lifts_the_body_limit():
    assert "location = /api/blog/images" in CONF
    assert "client_max_body_size 3m;" in block("location = /api/blog/images")


def test_the_site_wide_limit_is_untouched():
    """The exception is written at the location that needs it. Raising the global ceiling would let
    every other route accept a 3 MB body, including the ones that only ever receive a few hundred."""
    assert re.search(r"^\s*client_max_body_size 256k;", CONF, re.M)
    assert CONF.count("client_max_body_size") == 2, "a third body limit appeared"


def test_it_is_an_exact_match_and_comes_before_the_api_prefix():
    """nginx prefers an exact location over a prefix one wherever they sit, but keeping it first means
    the file reads in the order it is evaluated."""
    assert CONF.index("location = /api/blog/images") < CONF.index("location /api/ {")


def test_it_keeps_the_same_rate_limit_as_the_rest_of_the_api():
    """A route that lifts the body limit and drops the rate limit is a route somebody can fill the
    disk through."""
    upload, api = block("location = /api/blog/images"), block("location /api/ {")
    limit = re.search(r"limit_req zone=\S+ burst=\d+ nodelay;", api).group(0)
    assert limit in upload, f"the upload route does not carry {limit!r}"


def test_it_proxies_the_same_way():
    upload = block("location = /api/blog/images")
    for line in ("proxy_pass http://astrology_app;", "include /etc/nginx/proxy_params;",
                 "proxy_http_version 1.1;", 'proxy_set_header Connection "";'):
        assert line in upload, line


def test_the_timeout_is_a_minute_not_the_api_default():
    """330s on /api/ is for report generation. An upload that has not finished in a minute is a
    stalled connection, and holding a worker for five and a half minutes on one is how a handful of
    them take the site down."""
    assert "proxy_read_timeout 60s;" in block("location = /api/blog/images")


def test_the_smoke_check_tests_for_it():
    """The check sends a 1.5 MB body with NO token: the right answer is 401 (or 404 where no token is
    configured), and a 413 means the proxy refused it. Nothing is uploaded either way, which is what
    makes it safe to run against production."""
    smoke = Path("scripts/smoke_check.py").read_text(encoding="utf-8")
    assert "/api/blog/images" in smoke
    section = smoke[smoke.index("blog image uploads") - 2000:]
    assert "1_500_000" in smoke or "1500000" in smoke
    assert "413" in section and "(401, 404)" in section


def test_the_api_doc_tells_the_two_413s_apart():
    """Ours is JSON and respects BLOG_MAX_IMAGE_KB; the proxy's is HTML and arrives whatever the token
    says. A caller that cannot tell them apart will go looking in the wrong codebase."""
    doc = Path("docs/BLOG_API.md").read_text(encoding="utf-8")
    assert "413 WITH AN HTML BODY IS THE PROXY" in doc
    assert "client_max_body_size" in doc or "3m" in doc
