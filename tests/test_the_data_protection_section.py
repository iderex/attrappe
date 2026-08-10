"""The data protection section, and the list in it that the code decides.

`docs/data-protection.md` states what this software writes to disk. A list of
that kind typed by hand is a list that is right on the day it is written, so the
one in that document is checked against the package here: the syntax tree is
read for every call that opens or creates a path, and the result has to be
exactly the set of entries the document carries.

It fails closed in both directions. A write added with no entry fails, which is
the case the section exists for. An entry naming a place the package no longer
writes from fails too, because a document describing an artefact that is not
there reads as a disclosure and is a guess.

## What the scan reads, and what it does not

It reads the tracked package sources, the same pathspec `tools/injection_audit.py`
uses, and it reads them as a syntax tree rather than as text, so a name that
happens to spell a filesystem call is told apart from the call itself.

Two shapes count. A whole-file write or a path being created, which is
`write_text`, `write_bytes`, `touch`, `mkdir`, `makedirs` and the copying and
moving functions. And an open whose mode is not a read, judged from the literal
where there is one and counted as a write where there is not, which is the safe
direction: an unrecognised open is refused rather than passed.

`rename` and `replace` are not in the set, and their absence is deliberate
rather than an omission. They move a path rather than produce a file whose
contents this document would have to describe, and the bare method name is also
`dataclasses.replace` and `str.replace`, both of which this package calls and
neither of which touches a disk. A rule matching the name would refuse them, and
a rule refusing them would be a rule nobody could keep green.

## What one entry is, and what that bounds

An entry is a file, a function and the call that wrote, and the comparison is
between sets of those. So the bound is the third element: two writes in one
function through two different calls are two entries, and two writes in one
function through the same call are one. A second `open` added beside the first
inside `destination` is therefore invisible here, and it is measured rather than
supposed - the mutation is in the pull request that landed this.

Widening it further means putting a line number in the key, and a line number in
a document is a document that goes red on every edit above it. The narrower
thing this cannot see is a second file opened the same way in the same function,
which is a shape a reviewer can see and a shape the function's own name would
have to stop describing.

What the scan cannot reach at all is written into the document itself, under the
heading that says so, rather than only here.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECTION = ROOT / "docs" / "data-protection.md"

# The package, as the injection audit spells it. Git reads `*` across
# separators, so this is every module under the package and not only the top
# level.
PACKAGE_PATHSPEC = "src/attrappe/*.py"

# One entry in the document. The heading names the file, the function and the
# call, all three as inline code, which is what makes the entry machine-readable
# without a markdown parser: the `tests` dependency group carries the runner and
# nothing else, and a check that needed the `docs` group would not run in the
# job that runs the suite.
#
# The call is in the key rather than only in the prose because without it two
# writes in one function are one entry, and the second one would arrive silently.
# What is left over is stated in the module docstring above.
ENTRY = re.compile(r"^### `([^`]+)`, in `([^`]+)`, through `([^`]+)`$", re.MULTILINE)

# Calls that produce a file or a directory outright.
CREATES = frozenset(
    {
        "write_text",
        "write_bytes",
        "touch",
        "mkdir",
        "makedirs",
        "copy",
        "copy2",
        "copyfile",
        "copytree",
        "move",
    }
)

# Calls that hand back a handle. Whether one writes is the mode's to say.
OPENS = frozenset({"open"})

# The characters that make a mode a write. `+` is among them because `r+` opens
# an existing file for writing.
WRITING_MODES = frozenset("wxa+")

# The sentences the done-condition of #57 asks the section to state. Each is a
# phrase the document carries rather than a whole paragraph, so that the
# document can be rewritten without the check turning into a copy of it.
REQUIRED_PHRASES = (
    "No outbound connection.",
    "Loopback by default.",
    "Local-only artefacts.",
    "Export by file rather than by transmission.",
    "tests/test_nothing_calls_out.py",
    "no authentication, no authorisation and no transport security",
)

REQUIRED_HEADINGS = (
    "## The four properties",
    "## What the emulator writes to disk",
    "## Federation",
    "## Binding beyond loopback",
    "## A profile can carry code",
)


def tracked_sources() -> list[str]:
    """The package files git knows about, in a stable order.

    Git rather than a directory walk, because an untracked module in a working
    copy is not what a merge would land, and this check is about what the
    document ships beside.
    """
    out = subprocess.run(
        ["git", "ls-files", PACKAGE_PATHSPEC],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout
    return sorted(line for line in out.splitlines() if line)


def called(call: ast.Call) -> str | None:
    """The name at the end of what is being called, however it was reached."""
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def mode_of(call: ast.Call) -> ast.expr | None:
    """The mode argument of an open, wherever it was passed.

    `open(path, mode)` puts it second and `path.open(mode)` puts it first, so
    which position to read follows from how the call was reached.
    """
    for keyword in call.keywords:
        if keyword.arg == "mode":
            return keyword.value
    position = 1 if isinstance(call.func, ast.Name) else 0
    if len(call.args) > position:
        return call.args[position]
    return None


def writes(call: ast.Call) -> bool:
    """Whether this call can put bytes on the host."""
    name = called(call)
    if name is None:
        return False
    if name in CREATES:
        return True
    if name not in OPENS:
        return False
    mode = mode_of(call)
    if mode is None:
        # No mode is the default mode, and the default is a read.
        return False
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return bool(WRITING_MODES & set(mode.value))
    # A mode this cannot read is counted as a write. The refusal is stricter
    # than the property and never looser, which is the direction a check about
    # what leaves a host has to err in.
    return True


def sites_in(path: str, source: str) -> set[tuple[str, str, str]]:
    """Every place in one module that writes, by function and by the call it made."""
    found: set[tuple[str, str, str]] = set()

    def walk(node: ast.AST, enclosing: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                walk(child, child.name)
                continue
            if isinstance(child, ast.Call) and writes(child):
                found.add((path, enclosing, called(child) or ""))
            walk(child, enclosing)

    walk(ast.parse(source), "<module>")
    return found


def sites_in_the_package() -> set[tuple[str, str, str]]:
    """Every write in the tracked package, as the document has to name it."""
    found: set[tuple[str, str, str]] = set()
    for path in tracked_sources():
        found |= sites_in(path, (ROOT / path).read_text(encoding="utf-8"))
    return found


def entries_in_the_section() -> set[tuple[str, str, str]]:
    """Every write the document claims, read off its headings."""
    return set(ENTRY.findall(SECTION.read_text(encoding="utf-8")))


def test_the_scan_read_the_whole_package() -> None:
    """An empty read is a finding rather than a pass.

    A pathspec that stopped matching would leave every assertion below green
    with nothing examined, which is the quietest way for this check to stop
    being one.
    """
    sources = tracked_sources()
    assert len(sources) >= 10
    assert "src/attrappe/cli.py" in sources


def test_every_place_the_package_writes_has_an_entry_in_the_section() -> None:
    """The case the section exists for: a new output path with nothing said about it."""
    assert sites_in_the_package() <= entries_in_the_section()


def test_every_entry_in_the_section_names_a_place_the_package_writes() -> None:
    """The other direction, so the list cannot describe a file that is not produced."""
    assert entries_in_the_section() <= sites_in_the_package()


def test_the_section_lists_the_one_write_this_tree_has() -> None:
    """Named rather than only counted, so the set under test is visible here."""
    assert sites_in_the_package() == {("src/attrappe/cli.py", "destination", "open")}


def test_the_scan_finds_a_write_and_leaves_a_read_alone() -> None:
    """The proof that the rule bites, run rather than asserted.

    Three fixtures for each shape: one that writes, the same one with the write
    taken out, and a nearby construct that spells one of the same names and
    touches no disk.
    """
    writing = (
        "from pathlib import Path\n"
        "def keep(where: Path) -> None:\n"
        "    handle = where.open('w')\n"
        "    handle.close()\n"
    )
    reading = (
        "from pathlib import Path\n"
        "def keep(where: Path) -> None:\n"
        "    handle = where.open()\n"
        "    handle.close()\n"
    )
    neighbour = (
        "import dataclasses\n"
        "def keep(thing: object, name: str) -> object:\n"
        "    return dataclasses.replace(thing, name=name.replace('-', '_'))\n"
    )

    assert sites_in("fixture.py", writing) == {("fixture.py", "keep", "open")}
    assert sites_in("fixture.py", reading) == set()
    assert sites_in("fixture.py", neighbour) == set()


def test_a_whole_file_write_is_found_wherever_it_is() -> None:
    """The second shape, and the module level as well as a function."""
    inside = "from pathlib import Path\ndef keep(p: Path) -> None:\n    p.write_text('x')\n"
    outside = "from pathlib import Path\nPath('x').write_bytes(b'x')\n"

    assert sites_in("fixture.py", inside) == {("fixture.py", "keep", "write_text")}
    assert sites_in("fixture.py", outside) == {("fixture.py", "<module>", "write_bytes")}


def test_an_open_whose_mode_cannot_be_read_counts_as_a_write() -> None:
    """Stricter than the property rather than looser, which is the safe direction."""
    computed = (
        "from pathlib import Path\n"
        "def keep(p: Path, mode: str) -> None:\n"
        "    handle = p.open(mode)\n"
        "    handle.close()\n"
    )
    assert sites_in("fixture.py", computed) == {("fixture.py", "keep", "open")}


def test_the_section_states_the_four_properties_and_cites_its_evidence() -> None:
    """Each phrase the done-condition names, and the test it points at exists."""
    said = SECTION.read_text(encoding="utf-8")
    for phrase in REQUIRED_PHRASES:
        assert phrase in said, phrase
    for heading in REQUIRED_HEADINGS:
        assert heading in said, heading
    assert (ROOT / "tests" / "test_nothing_calls_out.py").is_file()


def test_the_section_names_every_field_of_the_file_it_lists() -> None:
    """The fields are the startup lines, so the two cannot drift apart unnoticed.

    The names come from `attrappe.cli` rather than from a list here, which is
    what makes a line renamed in the code a red run instead of a document that
    quietly describes the old name.
    """
    from attrappe import cli

    said = SECTION.read_text(encoding="utf-8")
    for field in ("profile", "identification", "listening", "seed", "configuration"):
        assert f"- `{field}`," in said, field

    # The same six the command prints, derived from the code that prints them.
    printed = [line.split(":", 1)[0] for line in _startup_lines()]
    assert printed == [
        "profile",
        "identification",
        "listening",
        "seed",
        "fault schedule",
        "configuration",
    ]
    assert cli.PROGRAM == "attrappe"


def _startup_lines() -> list[str]:
    """The lines the command writes, taken from the command rather than retyped."""
    from attrappe import cli
    from attrappe.profile import load_profile
    from attrappe.transport import LOOPBACK, Server

    profile = load_profile(ROOT / "tests" / "scpi" / "fixtures" / "instrument")
    server = Server(profile, port=0, seed=1)
    settings = cli.Settings(
        directory=profile.directory,
        host=LOOPBACK,
        port=0,
        seed=1,
        log=None,
        configuration=None,
    )
    return cli.startup_lines(server, profile, settings)


def test_the_module_under_test_is_on_the_path_this_suite_runs_from() -> None:
    """The scan reads the checkout, so a suite run against an installed copy would lie."""
    from attrappe import cli

    assert Path(cli.__file__).resolve() == (ROOT / "src" / "attrappe" / "cli.py").resolve()
    assert sys.version_info >= (3, 11)
