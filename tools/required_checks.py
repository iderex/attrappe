"""Generate docs/required-checks.md from the workflow files.

    python tools/required_checks.py            # write the document
    python tools/required_checks.py --check    # refuse if it is out of date

The list of check-run names is derived from the tracked workflow files, so a job
renamed without regenerating the document turns the gate red rather than leaving
a required-checks list that names a check nobody produces any more. The prose for
each name lives in `NOTES` below, next to the generator, and a name with no entry
is refused rather than written out with an empty description.

What a name is: a check run carries the job's `name` if the job has one, and the
job's key otherwise. The workflow's own name is not a prefix. That was measured
on this repository and the measurement is quoted in `.github/workflows/gate.yml`.
"""

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs" / "required-checks.md"


@dataclass(frozen=True)
class Note:
    """The prose for one check-run name. `refuses` is what a red run means."""

    refuses: str
    candidate: str


# One entry per check-run name a job in this tree produces. A name with no entry
# here fails the generator, which is the case that matters: adding a job is how a
# name arrives, and a job added without a sentence saying what its check refuses
# would otherwise appear in this document as a row nobody can act on.
NOTES: dict[str, Note] = {
    "Gate / lint": Note(
        refuses=(
            "a file the formatter would rewrite, and a violation of the lint groups "
            "selected in pyproject.toml"
        ),
        candidate="yes",
    ),
    "Gate / types": Note(
        refuses="a type error in the package, the repository tooling or the suite",
        candidate="yes",
    ),
    "Gate / workflows": Note(
        refuses=(
            "an unpinned action, a workflow-level write, a job without a timeout, "
            "a workflow without a concurrency group, a checkout that keeps the token, "
            "and a leg selector in gate.yml naming a leg the gate command does not have"
        ),
        candidate="yes",
    ),
    "Gate / injection": Note(
        refuses="a direct clock read or a module-level random draw inside the package",
        candidate="yes",
    ),
    "Gate / dependencies": Note(
        refuses=(
            "a dependency in the installed set with a known advisory against it, and an "
            "acceptance register entry with no reason, no retirement condition, or naming a "
            "finding that is no longer reported"
        ),
        candidate=(
            "yes, and it is the one whose red run can arrive without a commit. Its workflow "
            "also runs on a timer, so the mainline turns red when an advisory is published "
            "against a dependency nobody touched"
        ),
    ),
    "DCO sign-off": Note(
        refuses="a commit with no Signed-off-by trailer matching its author",
        candidate="yes",
    ),
    "Reject Trojan Source Unicode": Note(
        refuses="a bidirectional or invisible Unicode character in tracked text",
        candidate="yes",
    ),
    "dependency-review": Note(
        refuses="a dependency added in the change with a known advisory against it",
        candidate=(
            "yes for what it covers, and read what that is: it judges dependencies the change "
            "adds and says nothing about an advisory published tomorrow against one already "
            "here, which is #48"
        ),
    ),
    "Audit workflows (zizmor)": Note(
        refuses="a workflow-security finding the audit tool reports at or above its threshold",
        candidate=(
            "yes for a pull request from this repository. Its job asks for a write permission "
            "so that it can upload findings, a fork's pull request is not granted one, and the "
            "upload step fails there. Requiring it would make every fork's pull request red for "
            "a reason that is not about the change"
        ),
    ),
    "Scorecard analysis": Note(
        refuses="nothing. It scores the repository and uploads the result",
        candidate=(
            "no. It publishes rather than refuses, it does not run on a pull request at all, "
            "and its score moves with a service outside this tree"
        ),
    ),
}

# Check runs that appear on this repository and that no job in the tree produces.
# Typed rather than derived, because nothing in the tree names them; the command
# that observed them and the commits it was run against are printed with them, so
# a reader can repeat the observation rather than trust the list.
OBSERVED_ELSEWHERE: tuple[tuple[str, str], ...] = (
    (
        "zizmor",
        "the code-scanning check the workflow audit's upload creates. It publishes findings "
        "rather than refusing a change, and it is produced by a service rather than by a job "
        "here, so requiring it would make the gate depend on that service",
    ),
)

OBSERVED_ON = (
    "ab980631426e35029e3d6967bac50a76908fd9ef",
    "b59c7be47b87352d5a3df6a2e1164f8713739db8",
)


@dataclass(frozen=True)
class Check:
    name: str
    workflow: str
    job: str
    on_pull_request: bool
    asks_for_write: bool


def tracked_workflows() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", ".github/workflows/*.yml", ".github/workflows/*.yaml"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout
    return sorted(line for line in out.splitlines() if line)


def triggers(document: dict[Any, Any]) -> Any:
    """The `on:` block. YAML 1.1 reads a bare `on` as the boolean true."""
    return document.get(True, document.get("on"))


def checks() -> list[Check]:
    import yaml

    found: list[Check] = []
    for path in tracked_workflows():
        document = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
        events = triggers(document) or {}
        on_pull_request = "pull_request" in events
        for key, body in (document.get("jobs") or {}).items():
            permissions = (body or {}).get("permissions") or {}
            asks_for_write = isinstance(permissions, dict) and "write" in permissions.values()
            found.append(
                Check(
                    name=str((body or {}).get("name") or key),
                    workflow=path,
                    job=str(key),
                    on_pull_request=on_pull_request,
                    asks_for_write=asks_for_write,
                )
            )
    return sorted(found, key=lambda check: check.name)


def fork_answer(check: Check) -> str:
    if not check.on_pull_request:
        return "no, the workflow has no pull_request trigger"
    if check.asks_for_write:
        return "runs, but the job asks for a write permission a fork's pull request is not granted"
    return "yes"


def render() -> str:
    found = checks()
    missing = sorted({check.name for check in found} - set(NOTES))
    if missing:
        raise SystemExit(
            "no prose for: "
            + ", ".join(missing)
            + "\nAdd an entry to NOTES in tools/required_checks.py saying what the check refuses "
            "and whether it is a candidate. A row with an empty description is worse than a "
            "missing document."
        )

    refusing = [check for check in found if NOTES[check.name].candidate.startswith("yes")]
    publishing = [check for check in found if not NOTES[check.name].candidate.startswith("yes")]

    lines: list[str] = []
    write = lines.append

    write("# Required checks")
    write("")
    write("Generated by `python tools/required_checks.py` from the workflow files this tree")
    write("tracks. Do not edit it. `python tools/gate.py --only required-checks` refuses a")
    write("document that no longer matches the workflows, so a job renamed without")
    write("regenerating this turns the gate red.")
    write("")
    write("**Nothing here has been applied.** No branch protection rule and no ruleset was")
    write("created or changed by the plan that produced this document. Requiring a check is a")
    write("repository setting and setting it is the maintainer's action. This exists so that")
    write("doing it is one sitting rather than an archaeology exercise.")
    write("")
    write("A required check matches the check-run name literally. A job renamed later stops")
    write("being the check that was required, and the setting does not complain: it waits for a")
    write("check that will never arrive, or it silently gates on nothing, depending on how the")
    write("rule was written. That failure is quiet and it has bitten this class of setup before,")
    write("which is why the strings below are exact and why the check above exists.")
    write("")
    write("A check run carries the job's `name` where the job has one and the job's key")
    write("otherwise. The workflow's name is shown beside it in the pull-request interface and")
    write("reads like a prefix, and is not one.")
    write("")

    write("## Candidates")
    write("")
    write("Each of these refuses something. The name is the exact string to enter.")
    write("")
    write("| Check-run name | Produced by | What a red run means | Runs on a fork's pull request |")
    write("| --- | --- | --- | --- |")
    for check in refusing:
        note = NOTES[check.name]
        write(
            f"| `{check.name}` | `{check.workflow}`, job `{check.job}` "
            f"| {note.refuses} | {fork_answer(check)} |"
        )
    write("")
    for check in refusing:
        note = NOTES[check.name]
        if note.candidate != "yes":
            write(f"`{check.name}`: {note.candidate}.")
            write("")

    write("## Not candidates")
    write("")
    write("These publish a result rather than refusing a change. Requiring one makes the merge")
    write("depend on a service outside this tree.")
    write("")
    write("| Check-run name | Produced by | What it does | Why it is not a candidate |")
    write("| --- | --- | --- | --- |")
    for check in publishing:
        note = NOTES[check.name]
        write(
            f"| `{check.name}` | `{check.workflow}`, job `{check.job}` "
            f"| {note.refuses} | {note.candidate} |"
        )
    for name, why in OBSERVED_ELSEWHERE:
        write(f"| `{name}` | no job in this tree | {why} | the same reason |")
    write("")
    write("The last row is not derived from the workflow files, because nothing in them names")
    write("it. It was observed instead, and the observation is repeatable:")
    write("")
    write("```")
    for commit in OBSERVED_ON:
        write(f"gh api repos/iderex/attrappe/commits/{commit}/check-runs \\")
        write("  --jq '[.check_runs[].name] | sort | .[]'")
    write("```")
    write("")
    write("The first is a mainline commit and the second a pull-request head, and the two sets")
    write("differ in both directions: the pull-request-only guards appear on one and the")
    write("push-only scorecard on the other. Compare against the table above before requiring")
    write("anything, because a check that never runs on a pull request cannot be satisfied by")
    write("one.")
    write("")

    write("## What this list does not settle")
    write("")
    write("It says which checks could be required. It does not say which should be, and it does")
    write("not say what happens to a pull request from a fork under a rule that requires a check")
    write("a fork's pull request cannot produce.")
    write("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="refuse if the document on disk is not what this would write",
    )
    arguments = parser.parse_args(argv)

    wanted = render()
    if not arguments.check:
        DOCUMENT.write_text(wanted, encoding="utf-8", newline="\n")
        print(f"wrote {DOCUMENT.relative_to(ROOT).as_posix()}")
        return 0

    found = DOCUMENT.read_text(encoding="utf-8") if DOCUMENT.exists() else ""
    if found == wanted:
        print(f"{DOCUMENT.relative_to(ROOT).as_posix()} matches the workflow files")
        return 0
    print(
        f"{DOCUMENT.relative_to(ROOT).as_posix()} does not match the workflow files.\n"
        "Regenerate it with `python tools/required_checks.py`.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
