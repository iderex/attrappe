"""The exclusion is proved by running it rather than by a transcript.

`docs/decisions/0008-headless.md` says the default suite deselects the
hardware-bound marker by configuration, and that the scaffolding milestone owes
a test that fails if a marked test runs in a default invocation. A pasted
terminal session proves the exclusion held on the day somebody ran it and
nothing afterwards, so it is here instead, in the suite, where a change to
`addopts` turns it red.

Each leg runs pytest as a subprocess against a fixture file written into a
temporary directory, using this repository's own `pyproject.toml` as the
configuration. The fixture is outside the tree, so the run under test collects
exactly what it is given and nothing of this suite; the configuration is the
real one, so a leg that passes says something about the settings that ship.
"""

import os
import subprocess
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "pyproject.toml"

# The marked test fails unconditionally, which is what makes the first leg
# meaningful: if the deselection stops working, the run cannot stay green. The
# unmarked test beside it passes, so a run that collected the file is
# distinguishable from a run that collected nothing at all, and the two cases
# are otherwise identical in the counts.
MARKED_AND_UNMARKED = """
import pytest


@pytest.mark.hardware_bound
def test_marked_and_failing():
    raise AssertionError("this fixture exists to be failed")


def test_unmarked_and_passing():
    assert True
"""

# One character away from the registered name. Without --strict-markers this is
# a warning, the test joins the default run, and the typo is invisible in a
# green summary line.
MISSPELLED_MARKER = """
import pytest


@pytest.mark.hardware_bounds
def test_marked_with_a_typo():
    raise AssertionError("this fixture exists to be failed")
"""


def run_pytest(fixture: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run pytest over one fixture file under this repository's configuration.

    `--confcutdir` stops the conftest search at the fixture's own directory.
    Without it the search walks from the fixture up towards the filesystem root,
    which is slow and reaches directories that belong to nobody here.

    `PYTEST_ADDOPTS` is dropped from the child's environment. Pytest reads it in
    addition to `addopts`, so an outer run carrying one would change what the
    inner run selects and the leg would be measuring the caller.
    """
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


def write_fixture(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def test_a_marked_test_is_deselected_and_the_default_invocation_is_green(
    tmp_path: Path,
) -> None:
    """The marked test does not run, the unmarked one beside it does, and the
    run passes."""
    fixture = write_fixture(tmp_path, "test_membership.py", MARKED_AND_UNMARKED)

    result = run_pytest(fixture)

    assert "1 passed" in result.stdout, result.stdout
    assert "1 deselected" in result.stdout, result.stdout
    assert "test_marked_and_failing" not in result.stdout, result.stdout
    assert result.returncode == 0, result.stdout


def test_the_deselection_is_the_only_thing_keeping_the_marked_test_out(
    tmp_path: Path,
) -> None:
    """Asking for the marker runs the same test, and it fails.

    The leg above is satisfied by a run that collected nothing, for any reason
    at all. This is the other direction: the same file, the same configuration,
    and the marked test both selected and failing.
    """
    fixture = write_fixture(tmp_path, "test_membership.py", MARKED_AND_UNMARKED)

    result = run_pytest(fixture, "-m", "hardware_bound")

    assert "test_marked_and_failing" in result.stdout, result.stdout
    assert "1 failed" in result.stdout, result.stdout
    assert "1 deselected" in result.stdout, result.stdout
    assert result.returncode == 1, result.stdout


def test_a_misspelled_marker_is_refused_rather_than_warned_about(tmp_path: Path) -> None:
    """A typo in the marker name stops the run instead of joining it.

    Without this, `hardware_bounds` is an unregistered marker, pytest warns, and
    the test runs in the default suite carrying whatever constraint it was
    written to need. A warning inside a green run is not a refusal.
    """
    fixture = write_fixture(tmp_path, "test_typo.py", MISSPELLED_MARKER)

    result = run_pytest(fixture)

    assert "'hardware_bounds' not found in `markers` configuration option" in result.stdout, (
        result.stdout
    )
    assert result.returncode != 0, result.stdout
