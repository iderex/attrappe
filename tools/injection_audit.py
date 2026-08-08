"""Refuse direct clock and randomness use inside the emulator package.

Two decision records say the emulator reaches time and randomness only through
something handed to it. `docs/decisions/0003-time.md` puts the clock behind an
injected interface, and `docs/decisions/0004-randomness.md` puts the generator in
an explicit instance carried by the session. Both records say, in the same words,
that until a check refuses the violation the section is a statement in a document
and nothing more. This is that check.

Run it with no arguments from the repository root:

    python tools/injection_audit.py

It exits non-zero when a tracked package file breaks a rule, and it prints what
it examined, so a run that covered fewer files than the tree holds cannot be read
as one that covered them all and found nothing.

The file list comes from `git ls-files`. An untracked module sitting in a working
copy is not audited and is not counted, because it is not what a merge would
land. An empty list is a finding rather than a pass: a package that moved out
from under this pathspec would otherwise leave every run green with nothing read.

Why an audit over the source and not a lint rule. The rule was asked for in the
lint configuration where the tool can express it, and this repository has no lint
tool configured yet - `pyproject.toml` carries a type-checker table and no other,
and the leg that introduces a linter is a separate issue. So the fallback the
issue names applies: a small dedicated check over the tracked source. It is the
shape `tools/workflow_audit.py` already established here, it adds no dependency,
and it reads the syntax tree rather than matching text, which is what lets it
tell `time.monotonic()` from `self._clock.time()`.

What it does not reach, stated so the cover is not read as total. The clock rule
refuses the import, so it catches every use that needs one; it does not catch a
module reached through `importlib.import_module`, and it says nothing about
wall time arriving by another route - `asyncio.sleep`, `os.times`, a `timeout`
argument passed to a socket or to `threading.Event.wait`. The randomness rule
reads attribute access on the imported module and the names lifted out of it; it
does not follow the module through an assignment (`r = random`), through
`getattr`, or into another library that carries its own generator. Widening
either set is one line in the constants below, and each widening is argued in the
issue that makes it.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

# The package this audit is about. Everything under it is subject; nothing
# outside it is read, so the test suite, the tooling and the documentation are
# free to call whatever they need.
PACKAGE_PATHSPEC = "src/attrappe/*.py"

# The name is carried as a string as well as a path, and every finding quotes the
# string. `str(Path(...))` spells a separator the way the host does, so a finding
# about this file would read differently on the machine a contributor runs and on
# the machine the gate runs, and the two transcripts would not compare.
ALLOWANCES_NAME = "tools/injection-audit-allowances.toml"
ALLOWANCES_PATH = Path(ALLOWANCES_NAME)

RULES = (
    "no-direct-clock-module",
    "no-module-level-random",
)

# Standard-library modules that read the host clock. `time` is the one
# 0003-time.md names. `datetime` is the same violation spelled differently - a
# call to `datetime.now()` reads the same clock and defeats the same test - so it
# is refused under the same rule rather than left as a walk-around.
CLOCK_MODULES = frozenset({"time", "datetime"})

# The `random` module holds one class this project may use and a set of
# module-level functions it may not. The functions draw from a single hidden
# global instance, which is the shared generator 0004-randomness.md refuses,
# reached by a different spelling. `SystemRandom` is not on this list on purpose:
# it cannot be seeded, so it cannot carry the reproducibility the record is for.
ALLOWED_RANDOM_NAMES = frozenset({"Random"})


@dataclass(frozen=True)
class Finding:
    """One refusal. `rule` is the name an allowance has to quote to waive it."""

    path: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


@dataclass(frozen=True)
class Allowance:
    """One waiver. It names one rule on one file and it carries a reason."""

    path: str
    rule: str
    reason: str


def tracked_sources() -> list[str]:
    """The package files git knows about, in a stable order."""
    out = subprocess.run(
        ["git", "ls-files", PACKAGE_PATHSPEC],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(line for line in out.splitlines() if line)


def check_clock(path: str, tree: ast.Module) -> list[Finding]:
    """Refuse an import of a module that reads the host clock.

    Only absolute imports are judged. `from .time import Clock` names a module
    inside this package, and a package module is the thing the record asks for
    rather than the thing it refuses.
    """
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in CLOCK_MODULES:
                    findings.append(
                        Finding(
                            path,
                            "no-direct-clock-module",
                            f"line {node.lineno}: imports {alias.name}; take a clock instead",
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module is not None:
                root = node.module.split(".")[0]
                if root in CLOCK_MODULES:
                    findings.append(
                        Finding(
                            path,
                            "no-direct-clock-module",
                            f"line {node.lineno}: imports from {node.module}; take a clock instead",
                        )
                    )
    return findings


def random_module_names(tree: ast.Module) -> set[str]:
    """The local names bound to the `random` module by an import in this file."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "random":
                    bound.add(alias.asname or alias.name)
    return bound


def check_random(path: str, tree: ast.Module) -> list[Finding]:
    """Refuse a module-level random function, by either spelling.

    `import random` itself is legal, because `random.Random` is how the explicit
    generator gets constructed. What is refused is reaching past that one name:
    an attribute on the imported module, or a name lifted out of it by a
    from-import.
    """
    findings: list[Finding] = []
    bound = random_module_names(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module == "random":
                for alias in node.names:
                    if alias.name not in ALLOWED_RANDOM_NAMES:
                        findings.append(
                            Finding(
                                path,
                                "no-module-level-random",
                                f"line {node.lineno}: imports random.{alias.name}; "
                                "draw from the session generator instead",
                            )
                        )
        elif isinstance(node, ast.Attribute):
            value = node.value
            if isinstance(value, ast.Name) and value.id in bound:
                if node.attr not in ALLOWED_RANDOM_NAMES:
                    findings.append(
                        Finding(
                            path,
                            "no-module-level-random",
                            f"line {node.lineno}: {value.id}.{node.attr} is a module-level draw; "
                            "draw from the session generator instead",
                        )
                    )
    return findings


def load_allowances(tracked: list[str]) -> tuple[list[Allowance], list[Finding]]:
    """Read the allowance file.

    The two modules that implement the real clock and construct the generator are
    the ones that have to touch what everything else is forbidden. Their
    exemption is written here, per file, where a reader sees it.

    The register fails closed in both directions. An entry with no reason, an
    entry naming a rule this audit does not have, and an entry naming a file git
    does not track in the package each fail here; an entry that suppresses
    nothing fails in `audit` below as stale.
    """
    if not ALLOWANCES_PATH.exists():
        return [], []
    data = tomllib.loads(ALLOWANCES_PATH.read_text(encoding="utf-8"))
    known = set(tracked)
    allowances: list[Allowance] = []
    findings: list[Finding] = []
    for entry in data.get("allowance", []):
        path = str(entry.get("file", ""))
        rule = str(entry.get("rule", ""))
        reason = str(entry.get("reason", "")).strip()
        where = f"{path or '<no file>'} / {rule or '<no rule>'}"
        if not reason:
            findings.append(
                Finding(ALLOWANCES_NAME, "allowance-carries-a-reason", f"{where} has no reason")
            )
            continue
        if rule not in RULES:
            findings.append(
                Finding(
                    ALLOWANCES_NAME,
                    "allowance-names-a-real-rule",
                    f"{where} names no rule this audit has",
                )
            )
            continue
        if path not in known:
            findings.append(
                Finding(
                    ALLOWANCES_NAME,
                    "allowance-names-a-tracked-package-file",
                    f"{where} names no tracked file in the package",
                )
            )
            continue
        allowances.append(Allowance(path, rule, reason))
    return allowances, findings


def audit() -> int:
    paths = tracked_sources()
    allowances, findings = load_allowances(paths)
    waived = {(a.path, a.rule) for a in allowances}
    used: set[tuple[str, str]] = set()

    if not paths:
        findings.append(
            Finding(
                PACKAGE_PATHSPEC,
                "package-has-tracked-source",
                "no tracked file matches the package pathspec, so nothing was read",
            )
        )

    for path in paths:
        try:
            source = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as unreadable:
            # git tracks it and this run could not read it: deleted from the
            # working tree, or not text. Either way the audit has nothing to
            # judge, and a run that skipped a file in silence is the fail-open
            # this whole file exists to avoid.
            findings.append(Finding(path, "source-is-readable", str(unreadable)))
            continue
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as broken:
            # An unparsable file is not a pass. The audit cannot say what it
            # contains, and saying nothing is what a fail-open looks like.
            findings.append(
                Finding(path, "source-parses", f"line {broken.lineno}: {broken.msg}")
            )
            continue
        for finding in (*check_clock(path, tree), *check_random(path, tree)):
            if (finding.path, finding.rule) in waived:
                used.add((finding.path, finding.rule))
                continue
            findings.append(finding)

    # An allowance that no longer allows anything is stale. Leaving it green
    # would let the register fill with entries nobody can tell from live ones.
    for allowance in allowances:
        if (allowance.path, allowance.rule) not in used:
            findings.append(
                Finding(
                    ALLOWANCES_NAME,
                    "allowance-is-still-needed",
                    f"{allowance.path} / {allowance.rule} allows nothing; remove it",
                )
            )

    print(f"audited {len(paths)} tracked package file(s) against {len(RULES)} rule(s)")
    for path in paths:
        print(f"  {path}")
    print(f"allowances in force: {len(allowances)}")

    if findings:
        print(f"\n{len(findings)} finding(s):", file=sys.stderr)
        for finding in sorted(findings, key=str):
            print(f"  {finding}", file=sys.stderr)
        return 1
    print("\nno findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(audit())
