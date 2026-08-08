"""Put the coverage numbers where a reviewer sees them without downloading anything.

    python tools/coverage_summary.py --label 3.11

Reads `coverage.xml`, the interchange format the test leg writes, and appends a
short block to the file named by `GITHUB_STEP_SUMMARY`. With that variable
unset it writes the same block to standard output, so running it locally shows
what the server would show rather than doing nothing.

A number nobody reads is a number that drifts. The full report is an artefact,
and an artefact is something somebody downloads, unzips and opens, which is a
thing that happens once and then stops happening. The two percentages in the
run summary are what actually gets read, so they are what this produces.

It refuses a missing or unreadable report rather than writing an empty block. A
summary saying nothing looks the same as a summary saying everything passed, and
the case it would be hiding is the one where the report was never written.
"""

from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ElementTree
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "coverage.xml"


def rates(report: Path) -> tuple[float, float]:
    """The line and branch rates from the report, as percentages.

    The two attributes are on the root element of the interchange format, so
    this reads what the report states rather than recomputing it from the
    per-file counts and risking a second answer.
    """
    root = ElementTree.parse(report).getroot()
    line = root.get("line-rate")
    branch = root.get("branch-rate")
    if line is None or branch is None:
        raise SystemExit(
            f"{report.name} carries no line-rate or branch-rate on its root element. "
            "Was it written by `coverage xml` with branch coverage on?"
        )
    return float(line) * 100, float(branch) * 100


def block(label: str, line: float, branch: float) -> str:
    heading = f"### Coverage on {label}" if label else "### Coverage"
    return "\n".join(
        [
            heading,
            "",
            "| Measure | Covered |",
            "| --- | --- |",
            f"| Lines | {line:.2f}% |",
            f"| Branches | {branch:.2f}% |",
            "",
            "The floor the test leg refuses below is `fail_under` in `pyproject.toml`.",
            "The full report is the artefact this run uploaded.",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Append the coverage percentages to the run summary."
    )
    parser.add_argument(
        "--label",
        default="",
        help="what the run was of, for example the interpreter version",
    )
    arguments = parser.parse_args(argv)

    if not REPORT.is_file():
        print(
            f"no {REPORT.name}: the test leg writes it and this step reads it, "
            "so this step running before the leg means the leg did not run",
            file=sys.stderr,
        )
        return 1

    line, branch = rates(REPORT)
    written = block(arguments.label, line, branch)

    destination = os.environ.get("GITHUB_STEP_SUMMARY")
    if destination:
        with open(destination, "a", encoding="utf-8") as summary:
            summary.write(written)
    else:
        print(written, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
