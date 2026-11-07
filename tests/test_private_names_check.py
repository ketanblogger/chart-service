"""The publication check that blocks a private name, in both directions.

A guard that only ever passes is indistinguishable from no guard, and this one exists because a real
reader's given name and rashi were published in two code comments and stayed there for weeks. So every
test here either proves it FIRES on something it must catch, or proves it stays quiet on something it
must not - and one proves that a missing list refuses rather than waves the publish through.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_private_names.py"


def run(tree: Path, listing: Path | None, *extra: str):
    args = [sys.executable, str(SCRIPT), str(tree)]
    if listing is not None:
        args += ["--list", str(listing)]
    args += list(extra)
    return subprocess.run(args, capture_output=True, text=True)


@pytest.fixture
def tree(tmp_path):
    """The tree to scan. The names list is written OUTSIDE it, which is where it lives in production -
    a list of names that must not be published cannot sit in the tree being published."""
    root = tmp_path / "tree"
    (root / "app").mkdir(parents=True)
    (root / "app" / "clean.py").write_text("# a comment about Meera, who is invented\n")
    return root


def test_it_fires_on_a_listed_name(tree, tmp_path):
    listing = tmp_path / "names.txt"
    listing.write_text("Meera\n")
    result = run(tree, listing)
    assert result.returncode == 1, result.stdout
    assert "REFUSING TO PUBLISH" in result.stdout
    assert "app/clean.py:1" in result.stdout


def test_it_is_quiet_when_no_listed_name_appears(tree, tmp_path):
    listing = tmp_path / "names.txt"
    listing.write_text("Someone Else\n")
    result = run(tree, listing)
    assert result.returncode == 0, result.stdout
    assert "PASS" in result.stdout


@pytest.mark.parametrize("written, listed", [
    ("meera", "Meera"), ("MEERA", "Meera"), ("Meera", "meera"),
])
def test_case_does_not_let_a_name_through(tmp_path, written, listed):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "f.py").write_text(f"# about {written}\n")
    listing = tmp_path / "names.txt"
    listing.write_text(listed + "\n")
    assert run(tree, listing).returncode == 1, f"{written!r} slipped past {listed!r}"


def test_devanagari_is_matched_however_it_is_composed(tmp_path):
    """The same Devanagari word can be encoded two ways, and a check that only catches one is the kind
    that reports zero and is believed - which is exactly how the birth record shipped twice."""
    import unicodedata

    tree = tmp_path / "tree"
    tree.mkdir()
    name = "दिलीप"
    (tree / "f.py").write_text("# " + unicodedata.normalize("NFD", name) + "\n", encoding="utf-8")
    listing = tmp_path / "names.txt"
    listing.write_text(unicodedata.normalize("NFC", name) + "\n", encoding="utf-8")
    assert run(tree, listing).returncode == 1, "a differently-composed Devanagari name slipped past"


def test_a_missing_list_refuses_rather_than_passing(tree, tmp_path):
    """THE FAILURE MODE THAT MATTERS. A safety check that waves everything through when it is
    misconfigured is worse than no check, because it is believed."""
    result = run(tree, tmp_path / "does-not-exist.txt")
    assert result.returncode == 1
    assert "REFUSING" in result.stdout and "not an empty one" in result.stdout


def test_the_absence_of_a_list_can_be_stated_explicitly(tree, tmp_path):
    result = run(tree, tmp_path / "does-not-exist.txt", "--no-private-list")
    assert result.returncode == 0
    assert "nothing checked" in result.stdout


def test_comments_and_blank_lines_in_the_list_are_ignored(tree, tmp_path):
    listing = tmp_path / "names.txt"
    listing.write_text("# who must never be named\n\nMeera\n")
    assert run(tree, listing).returncode == 1


def test_binary_and_vendored_paths_are_skipped(tmp_path):
    """A name cannot meaningfully hide in a font, and walking var/ or .git would make this unusable."""
    tree = tmp_path / "tree"
    (tree / "var").mkdir(parents=True)
    (tree / "var" / "scratch.txt").write_text("Meera\n")
    (tree / "ok.py").write_text("# nothing here\n")
    listing = tmp_path / "names.txt"
    listing.write_text("Meera\n")
    assert run(tree, listing).returncode == 0, "var/ is scratch and is never published"


def test_publish_sh_actually_calls_it():
    """The check is worth nothing if the publish path does not run it."""
    publish = (Path(__file__).resolve().parents[1] / "scripts" / "publish.sh").read_text()
    assert "check_private_names.py" in publish
    before_push = publish.split("git push", 1)[0]
    assert "check_private_names.py" in before_push, "the check must run BEFORE the push, not after"
