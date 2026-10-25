"""IndexNow: telling Bing and Yandex a URL changed, without breaking anything that already worked.

GOOGLE IS DELIBERATELY ABSENT. Its Indexing API is restricted to job postings and livestreams, so using
it for ordinary pages breaks its terms and achieves nothing. Bing and Yandex accept IndexNow, and whether
that becomes traffic is answerable rather than assumed: the source tracking names Bing arrivals.

THE KEY IS PUBLIC. It is served at the site root for the engines to fetch, and it proves control of the
domain rather than identity - there is nothing in it to leak.
"""
from __future__ import annotations

import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n, indexnow

client = TestClient(app, raise_server_exceptions=False)


def test_the_key_file_is_served_at_the_site_root():
    response = client.get(indexnow.key_path())
    assert response.status_code == 200
    assert response.text.strip() == indexnow.KEY
    assert response.headers["content-type"].startswith("text/plain")


def test_the_key_route_does_not_shadow_the_other_files_at_the_root():
    """THE REGRESSION THIS CAUGHT. The key route was first written as "/{key}.txt" with the check inside,
    and that pattern matched EVERY .txt at the site root - so /robots.txt reached the IndexNow handler,
    failed the key comparison and returned 404. robots.txt is the last file on the site that should
    quietly disappear, and nothing else would have noticed: the sitemap still worked, every page still
    answered, and only a crawler would have found out."""
    assert client.get("/robots.txt").status_code == 200
    assert "Sitemap:" in client.get("/robots.txt").text
    assert client.get("/sitemap.xml").status_code == 200


def test_an_unknown_key_is_not_served():
    assert client.get("/0000000000000000000000000000ffff.txt").status_code == 404


def test_the_key_is_a_key_and_not_a_secret():
    """A 32-character hex key. It is in the repository on purpose: an engine must be able to fetch it,
    so hiding it would break the only thing it does."""
    assert re.fullmatch(r"[0-9a-f]{32}", indexnow.KEY), indexnow.KEY


def test_nothing_is_submitted_without_a_key(monkeypatch):
    monkeypatch.setattr(indexnow, "KEY", "")
    result = indexnow.submit(["/"])
    assert result["sent"] == 0 and "no INDEXNOW_KEY" in result["detail"]


def test_a_submission_names_this_site_and_its_own_key_file(monkeypatch):
    # Submission is production-only now: a developer's laptop was sending 39 URLs to Bing and Yandex on
    # every local refresh and getting rate-limited for it. These tests are about what a submission looks
    # like when it DOES happen, so they say where they are.
    monkeypatch.setenv("APP_ENV", "production")
    sent = {}

    def fake_urlopen(request, timeout=None):
        import json

        sent["body"] = json.loads(request.data)
        sent["url"] = request.full_url

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        return Response()

    monkeypatch.setattr(indexnow.urllib.request, "urlopen", fake_urlopen)
    result = indexnow.submit(["/horoscope/libra/weekly"], reason="a test")
    assert result["sent"] == 1 and result["status"] == 200
    assert sent["url"] == indexnow.ENDPOINT
    assert sent["body"]["key"] == indexnow.KEY
    assert sent["body"]["keyLocation"].endswith(indexnow.key_path())
    assert sent["body"]["urlList"] == [
        indexnow.site.base_url().rstrip("/") + "/horoscope/libra/weekly"]
    assert "://" not in sent["body"]["host"], "host is a hostname, not a URL"


def test_a_failed_submission_never_raises(monkeypatch):
    # Submission is production-only now: a developer's laptop was sending 39 URLs to Bing and Yandex on
    # every local refresh and getting rate-limited for it. These tests are about what a submission looks
    # like when it DOES happen, so they say where they are.
    monkeypatch.setenv("APP_ENV", "production")
    """A refresh or a publish must not fail because Bing is unreachable. Measurement is never a reason
    for the site to misbehave."""
    def boom(*_args, **_kwargs):
        raise OSError("no route to host")

    monkeypatch.setattr(indexnow.urllib.request, "urlopen", boom)
    result = indexnow.submit(["/"])
    assert result["sent"] == 0 and "no route to host" in result["detail"]


def test_a_window_turnover_submits_that_period_in_all_three_trees():
    paths = []

    def record(urls, reason=""):
        paths.extend(urls)
        return {"sent": len(urls), "status": 200, "detail": ""}

    real = indexnow.submit
    try:
        indexnow.submit = record
        indexnow.submit_rashifal_window("weekly")
    finally:
        indexnow.submit = real
    assert len(paths) == 12 * 3 + 3, len(paths)      # 36 readings plus the three weekly hubs
    for lang in i18n.LANGS:
        assert i18n.url_for("rashifal-weekly", lang) in paths


def test_a_full_submission_covers_the_whole_sitemap():
    captured = {}

    def record(urls, reason=""):
        captured["urls"] = urls
        return {"sent": len(urls), "status": 200, "detail": ""}

    real = indexnow.submit
    try:
        indexnow.submit = record
        indexnow.submit_everything()
    finally:
        indexnow.submit = real
    assert len(captured["urls"]) == len(list(i18n.all_paths()))


def test_the_refresh_pings_but_cannot_be_broken_by_it():
    """The generator calls IndexNow after a run and swallows anything that goes wrong. Read as source,
    because the alternative is a refresh that fails on a network blip."""
    source = pathlib.Path("app/rashifal/generate.py").read_text(encoding="utf-8")
    assert "_tell_the_search_engines(summary)" in source
    body = source.split("def _tell_the_search_engines")[1]
    assert "except Exception" in body, "a failed submission must not fail the refresh"


def test_the_submit_script_is_a_dry_run_by_default():
    source = pathlib.Path("scripts/indexnow_submit.py").read_text(encoding="utf-8")
    body = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    guard = body.index("if not args.send:")
    assert body.index("indexnow.submit(paths") > guard, "the real submission must sit after the guard"


def test_google_is_not_submitted_to():
    """Not an oversight. Its Indexing API refuses ordinary pages, and asking anyway would be a terms
    breach for no benefit."""
    for path in ("app/web/indexnow.py", "scripts/indexnow_submit.py"):
        source = pathlib.Path(path).read_text(encoding="utf-8")
        code = "\n".join(line for line in source.splitlines()
                         if not line.lstrip().startswith("#") and '"""' not in line)
        assert "indexing.googleapis.com" not in code, path
