"""Warnings are errors, and the list of exceptions to that is argued.

Two properties, and each one is run rather than described.

The first is that a warning raised inside a test fails the run. It is checked by
driving pytest over a fixture that raises one, under this repository's own
configuration, the same way `test_the_hardware_bound_exclusion.py` drives the
marker.

The second is about the exception list in `pyproject.toml`. Every entry beyond
the bare `error` has to carry a comment saying where the warning comes from and
why it cannot be fixed here, and has to name a message rather than a whole
category. The list is empty today, so a check that read only the real file would
pass without judging anything. It reads fixtures as well, and the fixtures are
what prove it refuses.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "pyproject.toml"

RAISES_A_DEPRECATION = """
import warnings


def test_that_deprecates_something():
    warnings.warn("the fixture deprecates itself", DeprecationWarning, stacklevel=2)
"""

# A filter entry that is a category and no message. It silences every warning of
# that kind from every source, including the one this project is waiting for.
CATEGORY_ONLY = re.compile(r"^ignore::\w+$")


def run_pytest(fixture: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run pytest over one fixture file under this repository's configuration."""
    environment = dict(os.environ)
    environment.pop("PYTEST_ADDOPTS", None)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(CONFIG),
            "--confcutdir",
            str(fixture.parent),
            "-p",
            "no:cacheprovider",
            *arguments,
            str(fixture),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def test_a_test_that_raises_a_warning_fails(tmp_path: Path) -> None:
    """A deprecation warning inside a test is a failure, not a line in a summary."""
    fixture = tmp_path / "test_deprecating.py"
    fixture.write_text(RAISES_A_DEPRECATION, encoding="utf-8")

    result = run_pytest(fixture)

    assert "1 failed" in result.stdout, result.stdout
    assert "DeprecationWarning: the fixture deprecates itself" in result.stdout, result.stdout
    assert result.returncode == 1, result.stdout


def test_a_specific_matcher_lets_that_same_test_pass(tmp_path: Path) -> None:
    """The shape an entry in the exception list takes, and what it buys.

    `-W` on the command line is where an ini entry would go, in the same
    spelling, so this is the entry being tried before it is written down. The
    matcher names the message, so it silences that warning and nothing else.
    """
    fixture = tmp_path / "test_deprecating.py"
    fixture.write_text(RAISES_A_DEPRECATION, encoding="utf-8")

    result = run_pytest(fixture, "-W", "ignore:the fixture deprecates itself:DeprecationWarning")

    assert "1 passed" in result.stdout, result.stdout
    assert result.returncode == 0, result.stdout


def filter_entries(text: str) -> list[tuple[str, str]]:
    """Every entry in the `filterwarnings` array, with the comment above it.

    Read from the text rather than from a parsed document, because the reason an
    entry exists is a TOML comment and a parser has already dropped it. This is
    the same reason `tools/workflow_audit.py` reads its version comments from the
    file.
    """
    lines = text.splitlines()
    try:
        start = lines.index("filterwarnings = [")
    except ValueError:
        return []

    entries: list[tuple[str, str]] = []
    comment: list[str] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped == "]":
            break
        if stripped.startswith("#"):
            comment.append(stripped.lstrip("# ").strip())
            continue
        if stripped.startswith('"'):
            entries.append((stripped.strip(",").strip('"'), " ".join(c for c in comment if c)))
            comment = []
    return entries


def problems_in(text: str) -> list[str]:
    """What the exception list gets refused for.

    `error` needs no argument: it is the property itself rather than an exception
    to it. Everything else is an exception and owes both a reason and a message.
    """
    problems: list[str] = []
    for entry, comment in filter_entries(text):
        if entry == "error":
            continue
        if not comment:
            problems.append(f"{entry!r} has no comment above it saying where it comes from and why")
        if CATEGORY_ONLY.match(entry):
            problems.append(f"{entry!r} silences a whole category rather than a message")
    return problems


ARGUED = """filterwarnings = [
  "error",
  # setuptools, from a dependency this project does not choose. Retired when
  # that dependency stops importing it.
  "ignore:pkg_resources is deprecated:DeprecationWarning:something",
]
"""

NO_REASON = """filterwarnings = [
  "error",
  "ignore:pkg_resources is deprecated:DeprecationWarning:something",
]
"""

WHOLE_CATEGORY = """filterwarnings = [
  "error",
  # setuptools, from a dependency this project does not choose.
  "ignore::DeprecationWarning",
]
"""


def test_an_entry_with_a_reason_and_a_message_is_accepted() -> None:
    assert problems_in(ARGUED) == []


def test_an_entry_with_no_reason_is_refused() -> None:
    problems = problems_in(NO_REASON)
    assert len(problems) == 1, problems
    assert "no comment above it" in problems[0], problems


def test_an_entry_silencing_a_whole_category_is_refused() -> None:
    problems = problems_in(WHOLE_CATEGORY)
    assert len(problems) == 1, problems
    assert "whole category" in problems[0], problems


def test_the_bare_error_entry_needs_no_argument() -> None:
    """It is the property, not an exception to it, so it owes no reason."""
    assert problems_in('filterwarnings = [\n  "error",\n]\n') == []


def test_the_list_this_repository_ships_is_argued() -> None:
    """The same check against the real file. Empty today, and that is the point:
    a run of this alone would prove nothing, which is what the fixtures above are
    for."""
    text = CONFIG.read_text(encoding="utf-8")
    assert problems_in(text) == []
