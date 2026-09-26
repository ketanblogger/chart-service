"""The four pre-push privacy greps from the launch checklist, run by machine on every commit.

Why this file exists. The repository is public, and a set of internal documents plus the operator's
personal details were deliberately filtered out of its history before the first push. The runbook records
four greps to run before pushing again. They are correct, they are written down, and on 2026-09-23 they
caught nothing - because a pre-push check runs once, by hand, at the end, and the code it has to defend was
written a hundred commits earlier. Twice now the operator's name has gone back into shippable code
(341a86b reworded one occurrence; 486a2cc removed four more), and an absolute home-directory path survived
both sweeps because neither grep looked for it.

A test runs on every commit, by machine, against the same rules. That is the whole idea here.

Scope. Only files that would actually be PUBLISHED are checked: every tracked file except the paths
`git filter-repo --invert-paths` strips, which this module reads out of the runbook rather than repeating,
so the two cannot drift. Adding a document to the runbook's exclusion list therefore also excludes it here.

Self-reference. This module is a published file, so it is checked by its own rules - there is no exemption
for the checker, because that is the one exemption that would let a violation hide here. A test that greps
for a string therefore cannot contain that string, and every needle below is assembled from fragments,
including the excluded documents' names and the home-directory prefix. Do not "tidy" them into literals:
the file fails on itself, and it fails only once it is TRACKED, so an untracked first run looks green.
That is how this file shipped broken in 1086c7f.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Every needle is assembled from fragments, because this module is itself a published file and is checked by
# its own rules - see the module docstring. None of these may become a literal.
OPERATOR_LATIN = "K" + "etan"
OPERATOR_DEVA = "".join(map(chr, (0x0915, 0x0947, 0x0924, 0x0928)))   # the same name in Devanagari
OPERATOR_EMAIL = "k" + "etan@"
HOME = "/" + "home/"
HOME_PATH = re.compile(HOME + r"(?!astro\b)[A-Za-z0-9._-]+")          # /home/astro is the VPS service account
RUNBOOK_PATH = "docs/" + "LAUNCH_" + "CHECKLIST.md"

RUNBOOK = ROOT / RUNBOOK_PATH

# These checks read the exclusion list out of the launch checklist, and that document is ITSELF excluded from
# the published tree - so on a public clone it is absent and every test here errors on import. That is not a
# hypothetical: the file shipped in that state, and anyone who cloned the source and ran the suite got five
# errors and a failure before anything of theirs ran. So the module skips where the list cannot be read, with
# the reason said out loud. The checks still run wherever they can do their job, which is the private working
# copy the publication is made from.
if not RUNBOOK.exists():                                            # pragma: no cover - the published tree
    pytest.skip(f"{RUNBOOK_PATH} is not in this tree, so the exclusion list these checks enforce cannot be "
                "read. That is expected in a published clone: the checklist is one of the documents the "
                "publication filter removes. Run these from the private working copy.",
                allow_module_level=True)

# The name is printed by law on the policy pages, so these two are the legitimate places for it.
LEGAL_NAME_FILES = {"app/web/site.py", "deploy/env.production.example"}

# The public repository's URL contains the account name, and that URL is the AGPL source offer - it is
# published on the site on purpose and has to appear wherever the source is discussed. Removed from the text
# before scanning rather than exempting whole files, so the name is still caught everywhere else in them.
PUBLIC_REPO = "github.com/" + OPERATOR_LATIN.lower() + "blogger"   # built from the needle, not spelled

TEXT_SUFFIXES = {".py", ".md", ".js", ".html", ".css", ".json", ".txt", ".service", ".conf",
                 ".example", ".sh", ".yml", ".yaml", ".toml", ".cfg"}


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [p for p in out.stdout.split("\0") if p]


def operator_dob() -> str:
    """The date is read out of the runbook's scrub expressions, never written here.

    It used to be a constant in this file, split into fragments so the file would not trip its own grep.
    That defeated the scanner and nothing else: this module is PUBLISHED, the fragments still spell the
    date, and the constant was named after what it held. A reader needed no tooling at all.

    The runbook is excluded from the published tree, so on a public clone this module has already skipped
    before anything calls this. In the private working copy it is the single place the date lives, which is
    also where the scrub that removes it from history is defined - one source, not two."""
    text = RUNBOOK.read_text(encoding="utf-8")
    found = re.findall(r"literal:(\d{4}-\d{2}-\d{2})==>", text)
    assert found, "the runbook no longer declares the date to scrub, so this check has nothing to enforce"
    return found[0]


def excluded_paths() -> set[str]:
    """The `--path` arguments in the runbook's filter-repo command: the single source of truth."""
    text = RUNBOOK.read_text(encoding="utf-8")
    block = text.split("git filter-repo --invert-paths", 1)
    assert len(block) == 2, "the runbook no longer contains the filter-repo command this test reads"
    # the command continues across backslash-continued lines, up to --mailmap
    command = block[1].split("--mailmap", 1)[0]
    paths = set(re.findall(r"--path\s+(\S+)", command))
    assert len(paths) >= 6, f"expected the runbook's exclusion list, parsed only {paths}"
    return paths


def published_files() -> list[str]:
    """Every tracked text file that would survive the filter, i.e. every file a stranger can read."""
    excluded = excluded_paths()

    def is_excluded(path: str) -> bool:
        return any(path == e or path.startswith(e.rstrip("/") + "/") for e in excluded)

    return [p for p in tracked_files()
            if not is_excluded(p) and Path(p).suffix in TEXT_SUFFIXES]


def read(path: str) -> str:
    try:
        return (ROOT / path).read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return ""


def normalise(text: str) -> str:
    """Fold the separators that let a literal search walk past a match it should have found.

    The rendered date strings in this codebase join their parts with U+00A0, a non-breaking space. It is
    indistinguishable from a space in any terminal, so a grep for the spelled-month form of a date returned
    zero while exactly that text sat in the repository - and the zero was believed, and reported as clean.
    Anything that scans for a human-readable form has to normalise first.

    The example is deliberately NOT written out here. This file is published, and quoting the real date to
    explain why the real date must not be published put it in the one file whose job is keeping it out - it
    was the only occurrence left in the public tree, found by a proof run that expected zero. A docstring is
    shipped text like any other."""
    return text.replace("\u00a0", " ").replace("\u202f", " ").replace("\u2009", " ")


@pytest.fixture(scope="module")
def published() -> dict[str, str]:
    files = published_files()
    assert len(files) > 80, f"only {len(files)} published files found - is the exclusion parse too greedy?"
    return {path: normalise(read(path)) for path in files}


def test_the_runbooks_exclusion_list_is_the_one_this_test_enforces():
    """If the runbook's list changes, this test follows it rather than disagreeing with it silently."""
    paths = excluded_paths()
    assert RUNBOOK.relative_to(ROOT).as_posix() in paths, (
        "the launch checklist must exclude itself - it quotes the details it exists to keep out")
    for path in paths:
        # Deliberately NOT asserting that the path matches something today. An exclusion path does three
        # different jobs and only two of them leave a trace: it strips a document out of history, it keeps a
        # present-but-unwanted file out of the publication, and it stands guard so a future commit cannot add
        # one. The third leaves nothing to find, and several of these documents are untracked by design -
        # they live only in the proprietor's working copy, so a fresh clone of even the PRIVATE repo has
        # neither the file nor any history of it. Asserting presence here failed for exactly that reason and
        # would fail for anyone else who cloned this repository.
        assert path and not any(c in path for c in "*?["), (
            f"the exclusion list contains {path!r}, which is not a plain path - filter-repo takes literal "
            f"paths, so a glob here silently excludes nothing")


def test_no_published_file_names_the_operator(published):
    """341a86b and 486a2cc both fixed this. It is attribution in a comment, not a functional bug, which is
    why it keeps coming back: it reads as courtesy. The name belongs in LEGAL_ENTITY and nowhere else."""
    offenders = []
    for path, text in published.items():
        if path in LEGAL_NAME_FILES:
            continue
        text = text.replace(PUBLIC_REPO, "github.com/<account>")
        for needle in (OPERATOR_LATIN, OPERATOR_DEVA, OPERATOR_EMAIL):
            # Case-insensitively: the near-miss that prompted this was a generator script carrying a
            # /Users/<name>/Downloads path, where the name is lower-case and a case-sensitive needle walks
            # straight past it. A file path is exactly where a name arrives without its capital.
            for match in re.finditer(re.escape(needle), text, re.IGNORECASE):
                line = text.count("\n", 0, match.start()) + 1
                excerpt = text.splitlines()[line - 1].strip()[:110]
                offenders.append(f"{path}:{line}  {excerpt}")
    assert not offenders, (
        "the operator's name is in published code. Attribute the decision, not the person "
        "('the product rule', 'the brief'):\n    " + "\n    ".join(offenders))


def test_no_published_file_carries_the_operators_real_birth_details(published):
    """The fixtures were rewritten to documented public-figure charts precisely so this stays true."""
    offenders = [f"{path}:{text.count(chr(10), 0, text.index(operator_dob())) + 1}"
                 for path, text in published.items() if operator_dob() in text]
    assert not offenders, f"the operator's real date of birth is in published files: {offenders}"


def test_no_published_file_leaks_a_home_directory(published):
    """The class neither runbook grep looked for: an absolute path naming a local user. Harmless on its own
    - the name is public by law on the policy pages - but it is the same norm, and it reveals a machine."""
    offenders = []
    for path, text in published.items():
        for match in HOME_PATH.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path}:{line}  {match.group(0)}")
    assert not offenders, (
        "published files name a local home directory; use a relative path or ~:\n    "
        + "\n    ".join(offenders))


def test_no_published_file_points_at_an_excluded_document(published):
    """Runbook grep 1. A pointer to a document a stranger cannot open is worse than no pointer: it tells
    them something is being withheld and gives them nothing."""
    names = set()
    for path in excluded_paths():
        stem = Path(path).stem
        names |= {Path(path).name, stem}
        # ...and every underscore-boundary PREFIX that is itself filename-shaped, because a shortened form is
        # still a direct reference: published code cited one of these documents by its first two words for
        # weeks, and the full stem does not match that. The prefix must contain an underscore of its own -
        # a single leading word is prose (the product's own name is the first word of one of these files and
        # belongs in published code everywhere).
        parts = stem.split("_")
        for cut in range(2, len(parts)):
            names.add("_".join(parts[:cut]))
    offenders = []
    for path, text in published.items():
        for name in names:
            if len(name) < 6:                     # too short to be a distinctive filename
                continue
            if name in text:
                line = text.count("\n", 0, text.index(name)) + 1
                offenders.append(f"{path}:{line}  -> {name}")
    assert not offenders, (
        "published files reference documents that are filtered out of the public repository:\n    "
        + "\n    ".join(offenders))


def test_the_rules_are_actually_being_exercised(published):
    """Guard on the guards: if the needles stopped matching anything anywhere - including in the files that
    are SUPPOSED to contain them - the patterns have rotted and every test above is vacuously green."""
    checklist = read(RUNBOOK.relative_to(ROOT).as_posix())
    assert OPERATOR_LATIN in checklist and operator_dob() in checklist, (
        "the needles no longer match the runbook that documents them - the patterns have drifted")
    assert any(OPERATOR_LATIN in read(path) for path in LEGAL_NAME_FILES), (
        "LEGAL_ENTITY no longer names the proprietor, so this file's exemption is now meaningless")
    assert HOME_PATH.search(HOME + "someone/x") and not HOME_PATH.search(HOME + "astro/x")
