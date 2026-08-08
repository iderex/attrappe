"""The gate. One list of legs, one order, and one place both routes read it from.

    python tools/gate.py

The legs run in order and the run stops at the first failure. What ran, what
failed, what was not reached and what was not asked for is printed at the end,
so a run that covered part of the set cannot be read as one that covered the set
and found nothing.

The jobs in `.github/workflows/gate.yml` invoke this command with `--only`
instead of restating the tools, so the legs are declared here and selected
there. The `wiring` leg refuses a selector naming a leg this file does not have,
which is what keeps the two in step once somebody edits one of them.

`PROSE, NOT ENFORCEMENT` for the other direction. Nothing refuses a leg that no
job selects, and one is in that state today: `tests` has no job, because the
check-run name and the version matrix for it are #19's to fix and neither is
settled. The run below prints which legs no job selects, so the gap is visible
rather than only absent.
"""

import argparse
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "gate.yml"

# A run of one leg answered. `detail` is empty unless the outcome needs a reason.
PASSED = "passed"
FAILED = "FAILED"
NOT_REACHED = "not reached"
NOT_ASKED_FOR = "not asked for"


@dataclass(frozen=True)
class Leg:
    """One leg. `cost` is what running it needs, printed when it was not run.

    A leg is either a list of commands or a function. The function form exists
    for `wiring`, which reads this file's own leg list and has nothing to shell
    out to.
    """

    id: str
    refuses: str
    cost: str
    commands: tuple[tuple[str, ...], ...] = ()
    check: Callable[[], bool] | None = None


@dataclass
class Outcome:
    leg: Leg
    state: str
    detail: str = ""


@dataclass
class Wiring:
    """What `.github/workflows/gate.yml` selects, and what went wrong reading it."""

    selected: set[str] = field(default_factory=set)
    problems: list[str] = field(default_factory=list)


def read_wiring() -> Wiring:
    """Every `--only` argument in the gate workflow, and how the read went.

    Fails closed. A workflow file that cannot be parsed, or a parser that is not
    installed, is a `wiring` leg that refuses rather than one that finds nothing
    to complain about.
    """
    wiring = Wiring()
    try:
        import yaml
    except ImportError:
        wiring.problems.append(
            "no YAML parser: install the `workflows` dependency group, "
            "`python -m pip install --group workflows`"
        )
        return wiring

    try:
        document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as problem:
        wiring.problems.append(f"{WORKFLOW.name} could not be read: {problem}")
        return wiring

    jobs = (document or {}).get("jobs") or {}
    for name, body in jobs.items():
        for step in (body or {}).get("steps") or []:
            command = str((step or {}).get("run") or "")
            for selector in selectors_in(command):
                wiring.selected.update(split_ids(selector))
                if "tools/gate.py" not in command:
                    wiring.problems.append(
                        f"job {name}: `--only {selector}` outside a run of tools/gate.py"
                    )
    return wiring


def selectors_in(command: str) -> list[str]:
    """The value after each `--only` in a shell command, in either spelling."""
    found: list[str] = []
    words = command.replace("\n", " ").split()
    for index, word in enumerate(words):
        if word.startswith("--only="):
            found.append(word[len("--only=") :])
        elif word == "--only" and index + 1 < len(words):
            found.append(words[index + 1])
    return found


def split_ids(value: str) -> list[str]:
    return [part for part in value.split(",") if part]


def check_wiring() -> bool:
    """Refuse a workflow selector that names a leg this file does not have.

    The failure this prevents is a job that passes because it ran nothing. A
    typo in `--only` would otherwise select an empty set of legs, the command
    would find nothing to do, and the check run would be green.
    """
    known = {leg.id for leg in LEGS}
    wiring = read_wiring()
    problems = list(wiring.problems)
    for selected in sorted(wiring.selected):
        if selected not in known:
            problems.append(f"`--only {selected}` names no leg this command has")

    where = WORKFLOW.relative_to(ROOT).as_posix()
    print(f"  {where} selects: {', '.join(sorted(wiring.selected))}")
    unselected = sorted(known - wiring.selected)
    if unselected:
        print(f"  legs no job selects, which nothing here refuses: {', '.join(unselected)}")
    for problem in problems:
        print(f"  refused: {problem}")
    return not problems


LEGS: tuple[Leg, ...] = (
    Leg(
        id="format",
        refuses="a file the formatter would rewrite",
        cost="the `lint` dependency group",
        commands=((sys.executable, "-m", "ruff", "format", "--check", "--diff"),),
    ),
    Leg(
        id="lint",
        refuses="an unused name, a bare except, a mutable default, a bad comparison",
        cost="the `lint` dependency group",
        commands=((sys.executable, "-m", "ruff", "check", "--no-fix"),),
    ),
    Leg(
        id="types",
        refuses="a type error in the package, the tooling or the suite",
        cost="the package installed, and the `types`, `workflows` and `tests` groups",
        commands=((sys.executable, "-m", "mypy"),),
    ),
    Leg(
        id="wiring",
        refuses="a workflow selector naming a leg this command does not have",
        cost="the `workflows` dependency group, for the YAML parser",
        check=check_wiring,
    ),
    Leg(
        id="required-checks",
        refuses="a required-checks document that no longer matches the workflow files",
        cost="the `workflows` dependency group, for the YAML parser",
        commands=((sys.executable, "tools/required_checks.py", "--check"),),
    ),
    Leg(
        id="workflows",
        refuses="an unpinned action, a workflow-level write, a job without a timeout",
        cost="the `workflows` dependency group, for the YAML parser",
        commands=((sys.executable, "tools/workflow_audit.py"),),
    ),
    Leg(
        id="injection",
        refuses="a direct clock read or a module-level draw inside the package",
        cost="nothing beyond the interpreter",
        commands=(
            (sys.executable, "tools/injection_audit.py", "--self-test"),
            (sys.executable, "tools/injection_audit.py"),
        ),
    ),
    Leg(
        id="tests",
        refuses="a failing test in the default suite",
        cost="the package installed and the `tests` dependency group",
        commands=((sys.executable, "-m", "pytest"),),
    ),
)


def run_commands(leg: Leg) -> bool:
    for command in leg.commands:
        spoken = ("python" if word == sys.executable else word for word in command)
        printable = " ".join(spoken)
        print(f"  $ {printable}")
        if subprocess.run(command, cwd=ROOT, check=False).returncode != 0:
            return False
    return True


def run(selected: Sequence[str]) -> int:
    chosen = [leg for leg in LEGS if leg.id in selected]

    print(f"about to run {len(chosen)} of {len(LEGS)} leg(s), in this order:")
    for leg in LEGS:
        mark = "run " if leg.id in selected else "skip"
        print(f"  {mark} {leg.id:<16} {leg.refuses}")
    print()

    outcomes: list[Outcome] = []
    stopped_at = ""
    for leg in LEGS:
        if leg.id not in selected:
            outcomes.append(Outcome(leg, NOT_ASKED_FOR, f"running it needs {leg.cost}"))
            continue
        if stopped_at:
            outcomes.append(Outcome(leg, NOT_REACHED, f"the run stopped at {stopped_at}"))
            continue
        print(f"{leg.id}: {leg.refuses}")
        passed = leg.check() if leg.check is not None else run_commands(leg)
        print()
        outcomes.append(Outcome(leg, PASSED if passed else FAILED))
        if not passed:
            stopped_at = leg.id

    print("what this run examined:")
    for outcome in outcomes:
        detail = f"  ({outcome.detail})" if outcome.detail else ""
        print(f"  {outcome.leg.id:<16} {outcome.state}{detail}")

    failed = [outcome for outcome in outcomes if outcome.state == FAILED]
    if failed:
        print(f"\nthe gate refused at {failed[0].leg.id}")
        return 1
    if len(chosen) < len(LEGS):
        print("\nno leg refused what it was asked to examine, and it was not the whole set")
    else:
        print("\nno leg refused anything, over the whole set")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the gate legs in order and stop at the first failure."
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="ID[,ID...]",
        help="run these legs and report the rest as not asked for; repeatable",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print the legs in order and exit",
    )
    arguments = parser.parse_args(argv)

    if arguments.list:
        for leg in LEGS:
            print(f"{leg.id:<16} {leg.refuses}\n{'':<16} needs {leg.cost}")
        return 0

    known = {leg.id for leg in LEGS}
    asked: list[str] = []
    for value in arguments.only:
        asked.extend(split_ids(value))
    unknown = sorted(set(asked) - known)
    if unknown:
        print(f"no such leg: {', '.join(unknown)}", file=sys.stderr)
        print(f"the legs are: {', '.join(sorted(known))}", file=sys.stderr)
        return 2

    return run(asked or sorted(known, key=[leg.id for leg in LEGS].index))


if __name__ == "__main__":
    raise SystemExit(main())
