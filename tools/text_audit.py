"""Check the text kinds that are not source: documentation and profile files.

The lint leg already refuses a Python file the formatter would rewrite. This is
the same property over everything else this repository is made of, which is most
of it: `docs/quality-parity.md` states formatting across every text kind as a
target, and a repository that is mostly prose and declarative files with a
formatter over the source alone has the check where the bytes are not.

Run it with no arguments from the repository root:

    python tools/text_audit.py

It exits non-zero when a tracked file breaks a rule, and it prints what it
examined, so a run that covered fewer files than the tree holds cannot be read as
one that covered them all and found nothing.

The proof that the rules bite is executed rather than pasted:

    python tools/text_audit.py --self-test

which runs each rule against a fixture that violates it, the same fixture with
the violation removed, and a nearby legal construct, and requires each fixture to
be refused by exactly the rules it names and no others. Both runs are legs of the
gate.

## The three rules

`documentation-is-formatted` refuses a tracked markdown file whose content
differs from what the formatter would write. It is a check and never a rewrite:
the tool is asked what it would produce and the answer is compared, and nothing
here writes to a tracked file.

`relative-link-resolves` refuses a link or an image in a tracked markdown file
whose target is a path the tree does not hold. A document naming a file that is
not there is cheap to catch and expensive to notice by hand, and this repository
does it constantly - every decision record points at another one, and the README
points at five files.

`profile-matches-the-schema` refuses a tracked profile directory the loader
refuses. The schema is the loader's, in `src/attrappe/profile/loader.py`, rather
than a second declaration of the same rules: a profile validated here against a
copy of the schema would be a profile that passes the gate and fails at load.

## Why the formatter is a dependency and the other two are not

The formatter is `mdformat`, in the `docs` dependency group. A canonical form for
a text kind is not something to write here: the property this leg is for is that
one exists and that a deviation is refused, and implementing a markdown formatter
to get it would be a large tool nobody maintains inside a repository that is not
about markdown. It is pure Python, it configures from its defaults, it needs no
runtime beyond the one already chosen, and its parser is what the link rule reads
too. The reference gate reaches this property with a formatter covering markup
and stylesheets; this tree has neither, so the same property lands over the text
kinds it does have.

The link rule and the schema rule need no dependency. The link rule walks the
parser's token stream, which is why a link written inside a fenced code block is
not a link here - it is an example of one, and a rule matching text rather than
tokens would refuse this file's own documentation. The schema rule imports the
loader.

## What it does not reach, stated so the cover is not read as total

The formatter judges the markdown files. It says nothing about the TOML in a
profile: a profile's declaration is judged by the schema rule and never for its
layout, and the deviation that leaves is written in `docs/quality-parity.md`
rather than here.

The link rule reads relative targets. An absolute URL is not fetched: reaching
one is an outbound network call, which `docs/decisions/0008-headless.md` refuses
in the default suite and which would make the gate depend on somebody else's
uptime. A link to a fragment inside a document is not resolved either, because
nothing here reads a document's own anchors.

The schema rule reads the declarative half. `behaviour.py` beside it is not
imported: loading a profile's code half executes it, which
`docs/decisions/0005-profiles.md` says in as many words, and a gate leg that
executed tracked profile code would be a gate leg running whatever a pull request
put there.

The file list comes from `git ls-files`. An untracked document sitting in a
working copy is not audited and is not counted, because it is not what a merge
would land. An empty list is a finding rather than a pass.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

import mdformat
from markdown_it import MarkdownIt

from attrappe.profile import DECLARATIVE_FILE, ProfileError, load_profile

# The text kinds this audit reads, as pathspecs rather than as a directory walk,
# for the reason the module docstring gives.
MARKDOWN_PATHSPEC = "*.md"
PROFILE_PATHSPECS = (DECLARATIVE_FILE, f"*/{DECLARATIVE_FILE}")

# The name is carried as a string as well as a path, and every finding quotes the
# string. `str(Path(...))` spells a separator the way the host does, so a finding
# about this file would read differently on the machine a contributor runs and on
# the machine the gate runs, and the two transcripts would not compare.
EXPECTATIONS_NAME = "tools/text-audit-expected-refusals.toml"
EXPECTATIONS_PATH = Path(EXPECTATIONS_NAME)

RULES = (
    "documentation-is-formatted",
    "relative-link-resolves",
    "profile-matches-the-schema",
)

# One parser, built once. `commonmark` rather than the default preset, because
# the formatter renders CommonMark and a link the two disagree about would be
# refused here and rewritten there.
PARSER = MarkdownIt("commonmark")


@dataclass(frozen=True)
class Finding:
    """One refusal. `rule` is the name an expectation has to quote to waive it."""

    path: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


@dataclass(frozen=True)
class Expected:
    """One profile that exists in order to be refused, and why it does."""

    profile: str
    reason: str


def tracked(*pathspecs: str) -> list[str]:
    """The files git knows about under these pathspecs, in a stable order."""
    out = subprocess.run(
        ["git", "ls-files", *pathspecs],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(line for line in out.splitlines() if line)


def formatted(text: str) -> str:
    """What the formatter would write for this document.

    The caller reads the file with universal newlines, so `text` carries `\\n`
    whatever the checkout did to the file on disk. That is deliberate: a clone
    configured to write CRLF would otherwise fail every file here for a reason
    that is about git's configuration and not about the document.
    """
    return mdformat.text(text)


def check_formatting(path: str, text: str) -> list[Finding]:
    """Refuse a document the formatter would rewrite, and say where it would.

    The first differing line is quoted rather than the whole diff. A finding
    naming a file and nothing else sends the reader to run the formatter to find
    out what it meant, and the leg exists so that they do not have to.
    """
    wanted = formatted(text)
    if wanted == text:
        return []
    have = text.splitlines()
    want = wanted.splitlines()
    # Not strict: the two lists differ in length whenever the formatter adds or
    # removes a line, which is the case the tail of this function reports.
    for number, (before, after) in enumerate(zip(have, want, strict=False), start=1):
        if before != after:
            return [
                Finding(
                    path,
                    "documentation-is-formatted",
                    f"line {number}: the formatter would write {after!r}, not {before!r}",
                )
            ]
    shorter, longer = (have, want) if len(have) < len(want) else (want, have)
    return [
        Finding(
            path,
            "documentation-is-formatted",
            f"line {len(shorter) + 1}: the formatter would write "
            f"{len(want)} line(s) here, not {len(have)}",
        )
    ]


def targets_in(text: str) -> list[str]:
    """Every link and image target in a document, in the order they appear.

    Read from the parser's tokens rather than from the text, so a link written
    inside a fenced block as an example is not one, and a link split across two
    lines is.
    """
    found: list[str] = []
    for token in PARSER.parse(text):
        for child in token.children or ():
            # `attrGet` is typed as returning any attribute value the parser can
            # hold, which for these two is always a string. `str()` rather than a
            # cast, so a parser that one day answers otherwise is coerced rather
            # than mis-declared.
            if child.type == "link_open":
                found.append(str(child.attrGet("href") or ""))
            elif child.type == "image":
                found.append(str(child.attrGet("src") or ""))
    return found


def check_links(path: str, text: str, resolves: Callable[[str], bool]) -> list[Finding]:
    """Refuse a relative target this tree does not hold.

    `resolves` answers whether a repository-relative path is in the tree, and is
    an argument so that the self-test can supply a tree of its own. A target
    carrying a scheme, or naming only a fragment, is not a path and is not
    judged; the reasons are in the module docstring.
    """
    findings: list[Finding] = []
    directory = Path(path).parent
    for target in targets_in(text):
        split = urlsplit(target)
        if split.scheme or split.netloc:
            continue
        if not split.path:
            continue
        wanted = unquote(split.path)
        resolved = (directory / wanted).as_posix()
        # `Path.as_posix` leaves `..` and `.` in place, and a target that climbs
        # out of a subdirectory is the ordinary case here rather than a strange
        # one, so the segments are collapsed before the tree is asked. A `..`
        # with nothing left to pop has climbed out of the repository, which no
        # tree can hold and which is not the same answer as a missing file.
        parts: list[str] = []
        escaped = False
        for part in resolved.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if parts:
                    parts.pop()
                else:
                    escaped = True
                continue
            parts.append(part)
        candidate = "" if escaped else "/".join(parts)
        if escaped:
            findings.append(
                Finding(
                    path,
                    "relative-link-resolves",
                    f"{target} climbs out of the repository",
                )
            )
            continue
        if not resolves(candidate):
            findings.append(
                Finding(
                    path,
                    "relative-link-resolves",
                    f"{target} resolves to {candidate or '.'}, which the tree does not hold",
                )
            )
    return findings


def resolver(paths: Iterable[str]) -> Callable[[str], bool]:
    """Answer whether a repository-relative path is a tracked file or a directory.

    A directory counts when it holds a tracked file, because a document pointing
    at `docs/decisions/` is pointing at somewhere a reader can go. The set is
    built once so that a document with fifty links does not walk the tree fifty
    times.
    """
    files = set(paths)
    directories = {
        "/".join(parts[:index])
        for path in files
        for parts in (path.split("/"),)
        for index in range(1, len(parts))
    }
    known = files | directories
    return lambda candidate: candidate in known


def check_profile(directory: str) -> list[Finding]:
    """Refuse a profile directory the loader refuses, carrying every problem in it.

    Every problem rather than the first, because that is what the loader
    answers and dropping the rest here would make the gate less useful than
    running the loader by hand.
    """
    try:
        load_profile(Path(directory))
    except ProfileError as refused:
        return [
            Finding(directory, "profile-matches-the-schema", str(problem))
            for problem in refused.problems
        ]
    except OSError as unreadable:
        return [Finding(directory, "profile-matches-the-schema", str(unreadable))]
    return []


def load_expectations(profiles: list[str]) -> tuple[list[Expected], list[Finding]]:
    """Read the register of profiles that exist in order to be refused.

    The loader's own fixtures are the case this is for: a fixture proving that a
    duplicate node is refused has to hold a duplicate node, and a leg refusing
    every bad profile in the tree would refuse the proof that bad profiles are
    refused.

    The register fails closed in both directions. An entry with no reason and an
    entry naming a directory that is not a tracked profile fail here; an entry
    naming a profile that now loads fails in `audit` below as stale.
    """
    if not EXPECTATIONS_PATH.exists():
        return [], []
    data = tomllib.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))
    known = set(profiles)
    expectations: list[Expected] = []
    findings: list[Finding] = []
    for entry in data.get("expected", []):
        profile = str(entry.get("profile", ""))
        reason = str(entry.get("reason", "")).strip()
        where = profile or "<no profile>"
        if not reason:
            findings.append(
                Finding(EXPECTATIONS_NAME, "expectation-carries-a-reason", f"{where} has no reason")
            )
            continue
        if profile not in known:
            findings.append(
                Finding(
                    EXPECTATIONS_NAME,
                    "expectation-names-a-tracked-profile",
                    f"{where} names no tracked profile directory",
                )
            )
            continue
        expectations.append(Expected(profile, reason))
    return expectations, findings


@dataclass(frozen=True)
class Case:
    """One fixture and the exact set of rules it must refuse.

    `refuses` is a set and the comparison is exact, so a fixture that trips a
    second rule fails the case rather than passing it. That is the bound on what
    a case proves: which rules refused the bytes, and never which branch inside
    the rule did the refusing.
    """

    name: str
    document: str
    refuses: frozenset[str]
    # Where the fixture sits, because a relative target is resolved against the
    # directory of the document that carries it and `..` means nothing without
    # one. The default is a document at the root, which is where most of this
    # repository's documents are.
    where: str = "README.md"


# The tree the link fixtures are resolved against. Small and fixed, so a case
# says what it means without the repository underneath it moving the answer.
FIXTURE_TREE = ("README.md", "docs/decisions/0001-implementation-language.md")

# The fixtures. Each rule carries the three legs the gate asks of any guard: the
# violation is refused, the same fixture without the violation is refused by
# nothing, and a nearby legal construct is refused by nothing either. The
# near-misses are the point. They are the one-character mistakes somebody
# actually makes, and a rule that refuses them gets switched off.
CASES = (
    Case("a document the formatter leaves alone", "# Title\n\nA sentence.\n", frozenset()),
    Case(
        "a heading with no blank line under it",
        "# Title\nA sentence.\n",
        frozenset({"documentation-is-formatted"}),
    ),
    Case(
        "trailing whitespace at the end of a line",
        "# Title\n\nA sentence. \n",
        frozenset({"documentation-is-formatted"}),
    ),
    Case(
        "an indented code block, which the formatter fences",
        "# Title\n\n    python -m pytest\n",
        frozenset({"documentation-is-formatted"}),
    ),
    Case(
        "the same block already fenced",
        "# Title\n\n```\npython -m pytest\n```\n",
        frozenset(),
    ),
    Case(
        "a link to a tracked file",
        "# Title\n\nSee [the record](docs/decisions/0001-implementation-language.md).\n",
        frozenset(),
    ),
    Case(
        "a link to a file the tree does not hold",
        "# Title\n\nSee [the record](docs/decisions/0002-transport.md).\n",
        frozenset({"relative-link-resolves"}),
    ),
    Case(
        "a link to a directory that holds a tracked file",
        "# Title\n\nSee [the records](docs/decisions/).\n",
        frozenset(),
    ),
    Case(
        "a link out of two subdirectories and back in",
        "# Title\n\nSee [the readme](../../README.md).\n",
        frozenset(),
        where="docs/decisions/0001-implementation-language.md",
    ),
    Case(
        "the same link one directory short, which lands somewhere else",
        "# Title\n\nSee [the readme](../README.md).\n",
        frozenset({"relative-link-resolves"}),
        where="docs/decisions/0001-implementation-language.md",
    ),
    Case(
        "a link climbing out of the repository",
        "# Title\n\nSee [the readme](../../../README.md).\n",
        frozenset({"relative-link-resolves"}),
        where="docs/decisions/0001-implementation-language.md",
    ),
    Case(
        "an absolute link, which is not fetched",
        "# Title\n\nSee [the tracker](https://github.com/iderex/attrappe/issues).\n",
        frozenset(),
    ),
    Case(
        "a link to a fragment inside this document",
        "# Title\n\nSee [below](#title).\n",
        frozenset(),
    ),
    Case(
        "a tracked file with a fragment after it",
        "# Title\n\nSee [the record](docs/decisions/0001-implementation-language.md#status).\n",
        frozenset(),
    ),
    Case(
        "a link inside a fenced block, which is an example and not a link",
        "# Title\n\n```\n[the record](docs/decisions/0002-transport.md)\n```\n",
        frozenset(),
    ),
    Case(
        "an image whose file is not there",
        "# Title\n\n![a diagram](docs/diagram.png)\n",
        frozenset({"relative-link-resolves"}),
    ),
    Case(
        "a broken link in a document the formatter would also rewrite",
        "# Title\nSee [the record](docs/decisions/0002-transport.md).\n",
        frozenset({"documentation-is-formatted", "relative-link-resolves"}),
    ),
)

# The profile fixtures. These are documents rather than directories, so the case
# is run by writing one into a temporary directory: the loader reads a directory
# and asking it to read anything else would be testing a second code path.
PROFILE_CASES = (
    (
        "a profile the loader accepts",
        """
[identity]
manufacturer = "Attrappe"
model = "Fixture"
serial = "0"
firmware = "0.0"

[error_queue]
depth = 8

[[node]]
path = "SYSTEM"
short = "SYST"
""",
        False,
    ),
    (
        "a queue depth below one",
        """
[identity]
manufacturer = "Attrappe"
model = "Fixture"
serial = "0"
firmware = "0.0"

[error_queue]
depth = 0

[[node]]
path = "SYSTEM"
short = "SYST"
""",
        True,
    ),
    (
        "a short form that is not a prefix of its long form",
        """
[identity]
manufacturer = "Attrappe"
model = "Fixture"
serial = "0"
firmware = "0.0"

[error_queue]
depth = 8

[node.root]
path = "SYSTem"
short = "SYS"
""",
        True,
    ),
    (
        "a key the schema does not have",
        """
[identity]
manufacturer = "Attrappe"
model = "Fixture"
serial = "0"
firmware = "0.0"

[error_queue]
depth = 8
overflow = -350

[[node]]
path = "SYSTEM"
short = "SYST"
""",
        True,
    ),
)


def self_test() -> int:
    """Run the fixtures and report whether each rule refused exactly its own.

    Run it with

        python tools/text_audit.py --self-test

    This is the executed proof rather than a transcript somebody pasted once. It
    reads no tree, so it says nothing about the state of this repository on the
    day it runs; it says the rules refuse what they claim to refuse. The
    expectation register is not reachable from here, because a register keyed to
    tracked directories needs a tree, and its legs are shown against the tree
    instead.
    """
    import tempfile

    failures = 0
    resolves = resolver(FIXTURE_TREE)
    for case in CASES:
        got = frozenset(
            finding.rule
            for finding in (
                *check_formatting(case.where, case.document),
                *check_links(case.where, case.document, resolves),
            )
        )
        if got == case.refuses:
            print(f"  ok      {case.name} -> {sorted(got) or 'nothing'}")
        else:
            failures += 1
            print(
                f"  FAILED  {case.name}: refused {sorted(got) or 'nothing'}, "
                f"expected {sorted(case.refuses) or 'nothing'}",
                file=sys.stderr,
            )

    with tempfile.TemporaryDirectory() as scratch:
        for name, document, refused in PROFILE_CASES:
            directory = Path(scratch) / name.replace(" ", "-")
            directory.mkdir()
            (directory / DECLARATIVE_FILE).write_text(document, encoding="utf-8")
            findings = check_profile(str(directory))
            if bool(findings) == refused:
                print(f"  ok      {name} -> {'refused' if findings else 'nothing'}")
            else:
                failures += 1
                print(
                    f"  FAILED  {name}: {'refused' if findings else 'refused nothing'}, "
                    f"expected {'a refusal' if refused else 'nothing'}",
                    file=sys.stderr,
                )

    total = len(CASES) + len(PROFILE_CASES)
    print(f"\n{total} fixture(s) against {len(RULES)} rule(s), {failures} failure(s)")
    return 1 if failures else 0


def audit() -> int:
    documents = tracked(MARKDOWN_PATHSPEC)
    declarations = tracked(*PROFILE_PATHSPECS)
    profiles = sorted(str(Path(path).parent.as_posix()) for path in declarations)
    everything = tracked()

    expectations, findings = load_expectations(profiles)
    waived = {expected.profile for expected in expectations}
    used: set[str] = set()

    if not documents:
        findings.append(
            Finding(
                MARKDOWN_PATHSPEC,
                "documentation-is-formatted",
                "no tracked file matches the markdown pathspec, so nothing was read",
            )
        )

    resolves = resolver(everything)
    for path in documents:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as unreadable:
            # git tracks it and this run could not read it: deleted from the
            # working tree, or not text. Either way the audit has nothing to
            # judge, and a run that skipped a file in silence is the fail-open
            # this whole file exists to avoid.
            findings.append(Finding(path, "documentation-is-formatted", str(unreadable)))
            continue
        findings.extend(check_formatting(path, text))
        findings.extend(check_links(path, text, resolves))

    for directory in profiles:
        refusals = check_profile(directory)
        if directory in waived:
            if refusals:
                used.add(directory)
            continue
        findings.extend(refusals)

    # An expectation that no longer waives anything is stale. Leaving it green
    # would let the register fill with entries nobody can tell from live ones.
    for expected in expectations:
        if expected.profile not in used:
            findings.append(
                Finding(
                    EXPECTATIONS_NAME,
                    "expectation-is-still-needed",
                    f"{expected.profile} loads cleanly and waives nothing; remove it",
                )
            )

    print(
        f"audited {len(documents)} tracked document(s) and {len(profiles)} tracked "
        f"profile(s) against {len(RULES)} rule(s)"
    )
    for path in documents:
        print(f"  {path}")
    for directory in profiles:
        mark = " (expected to be refused)" if directory in waived else ""
        print(f"  {directory}{mark}")
    print(f"expected refusals in force: {len(expectations)}")

    if findings:
        print(f"\n{len(findings)} finding(s):", file=sys.stderr)
        for finding in sorted(findings, key=str):
            print(f"  {finding}", file=sys.stderr)
        return 1
    print("\nno findings")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        return audit()
    if argv == ["--self-test"]:
        return self_test()
    print(f"usage: {Path(__file__).name} [--self-test]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
