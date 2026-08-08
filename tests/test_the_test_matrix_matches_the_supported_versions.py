"""The versions the gate tests on are the versions the package says it supports.

Two lists of supported interpreters with nothing between them is how a project
ships a classifier for a version nothing ever ran on, and how a version added to
the matrix never reaches the packaging metadata anybody installing reads.

This is in the suite rather than in the workflow audit because it is about this
repository's own claim rather than about workflow security, and because a suite
is where a reader looks for what the project asserts about itself.

The versions are read out of both files. Neither list is written here: a third
copy would be the drift this exists to refuse.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

ROOT   =  Path(__file__).resolve().parents[1]
GATE = ROOT / ".github" / "workflows" / "gate.yml"
PACKAGING = ROOT / "pyproject.toml"

CLASSIFIER = re.compile(r"^Programming Language :: Python :: ([0-9]+\.[0-9]+)$")
# The matrix line as it is written in the workflow. Read with a pattern rather
# than a YAML parser so that this test needs no dependency group beyond the
# runner: the tests job installs `tests` and nothing else, and a test that
# needed the YAML parser would either widen that install or be skipped there,
# which is the same as not having it.
MATRIX = re.compile(r"^\s*python-version:\s*\[(?P<versions>[^\]]*)\]\s*$", re.MULTILINE)


def declared_versions() -> list[str]:
    packaging: dict[str, Any] = tomllib.loads(PACKAGING.read_text(encoding="utf-8"))
    found = [
        match.group(1)
        for classifier in packaging["project"]["classifiers"]
        if (match := CLASSIFIER.match(classifier))
    ]
    return sorted(found, key=lambda version: tuple(int(part) for part in version.split(".")))


def matrix_versions() -> list[str]:
    match = MATRIX.search(GATE.read_text(encoding="utf-8"))
    assert match is not None, "no python-version matrix in the gate workflow"
    return [entry.strip().strip('"').strip("'") for entry in match.group("versions").split(",")]


def test_the_matrix_and_the_classifiers_name_the_same_versions() -> None:
    assert matrix_versions() == declared_versions()


def test_the_floor_is_the_one_the_packaging_metadata_requires() -> None:
    """The lowest version tested is the lowest version the package will install on.

    A floor in `requires-python` below the lowest tested version is a promise
    nothing stands behind, and one above it is a matrix job running an
    interpreter the package refuses to install on.
    """
    packaging: dict[str, Any] = tomllib.loads(PACKAGING.read_text(encoding="utf-8"))

    assert packaging["project"]["requires-python"] == f">={declared_versions()[0]}"
