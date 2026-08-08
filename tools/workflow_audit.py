"""Audit the workflow files against the rules this repository holds them to.

Six rules, one function each, every refusal going through `Finding`. Run it with
no arguments from the repository root:

    python tools/workflow_audit.py

It exits non-zero when a workflow breaks a rule, and it prints what it examined
so a run that covered fewer files than the tree holds cannot be read as one that
covered them all and found nothing.

The file list comes from `git ls-files`. An untracked workflow sitting in a
working copy is not audited and is not counted, because it is not what a merge
would land.

The workflow-security audit already in this repository overlaps three of these
rules. It flags an unpinned action, an over-broad permission and a checkout that
persists credentials, under its own names and its own severity threshold. The
overlap is stated rather than removed: that audit is a third-party tool with its
own release cadence and its own idea of what is actionable, and this file is the
repository saying which of those findings it will not merge past. Rules 5 and 6,
the job timeout and the concurrency group, are outside what it gates on at the
persona this repository runs it at.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# A pinned reference is a full-length lowercase hex object name. Forty
# characters, because a shorter prefix is ambiguous and a tag or a branch is
# mutable by whoever owns the action.
PINNED = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")

# The version comment that has to follow the pin on the same line. Without it a
# reader has forty characters and no way to tell what they point at, so nobody
# updates the pin and it rots.
VERSION_COMMENT = re.compile(r"@[0-9a-f]{40}\s+#\s*\S")

EXCEPTIONS_PATH = Path("tools/workflow-audit-exceptions.toml")

RULES = (
    "pinned-to-a-hash",
    "pin-carries-a-version-comment",
    "no-workflow-level-write",
    "checkout-does-not-persist-credentials",
    "every-job-has-a-timeout",
    "workflow-has-a-concurrency-group",
)


@dataclass(frozen=True)
class Finding:
    """One refusal. `rule` is the name an exception has to quote to waive it."""

    path: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


@dataclass(frozen=True)
class Waiver:
    """A waiver. It names one rule on one workflow and it carries a reason."""

    path: str
    rule: str
    reason: str


def tracked_workflows() -> list[str]:
    """The workflow files git knows about, in a stable order."""
    out = subprocess.run(
        ["git", "ls-files", ".github/workflows/*.yml", ".github/workflows/*.yaml"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(line for line in out.splitlines() if line)


def triggers(document: dict[Any, Any]) -> Any:
    """The `on:` block.

    YAML 1.1 reads a bare `on` as the boolean true, so the key is `True` and not
    the string. Reading only the string is how a checker silently sees no
    triggers at all.
    """
    return document.get(True, document.get("on"))


def uses_lines(path: str) -> list[tuple[int, str, str]]:
    """Every `uses:` in the file as (line number, whole line, reference).

    Read from the text rather than from the parsed document, because the version
    comment is a comment and the parser has already dropped it.
    """
    found: list[tuple[int, str, str]] = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        match = re.match(r"^\s*(?:-\s*)?uses:\s*(\S+)", line)
        if match:
            found.append((number, line, match.group(1)))
    return found


def check_pins(path: str) -> list[Finding]:
    findings: list[Finding] = []
    for number, line, reference in uses_lines(path):
        if reference.startswith((".", "/")):
            # A local action or a reusable workflow in this repository. There is
            # no third party to pin against.
            continue
        if not PINNED.match(reference):
            findings.append(
                Finding(
                    path,
                    "pinned-to-a-hash",
                    f"line {number}: {reference} is not a 40-character hash",
                )
            )
        elif not VERSION_COMMENT.search(line):
            findings.append(
                Finding(
                    path,
                    "pin-carries-a-version-comment",
                    f"line {number}: {reference} has no trailing version comment",
                )
            )
    return findings


def check_workflow_permissions(path: str, document: dict[Any, Any]) -> list[Finding]:
    permissions = document.get("permissions")
    if permissions is None:
        return [
            Finding(
                path,
                "no-workflow-level-write",
                "no workflow-level permissions block, so the job inherits the token's defaults",
            )
        ]
    if isinstance(permissions, str):
        # `permissions: write-all` and `permissions: read-all` are the two
        # scalar forms. Only one of them is a write.
        return (
            []
            if permissions == "read-all"
            else [
                Finding(
                    path, "no-workflow-level-write", f"workflow-level permissions: {permissions}"
                )
            ]
        )
    written = sorted(scope for scope, level in permissions.items() if level == "write")
    if written:
        return [
            Finding(
                path,
                "no-workflow-level-write",
                f"workflow-level write on {', '.join(written)}; grant it on the job instead",
            )
        ]
    return []


def check_checkout_credentials(path: str, document: dict[Any, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for name, job in (document.get("jobs") or {}).items():
        for index, step in enumerate(job.get("steps") or []):
            if "actions/checkout" not in str(step.get("uses", "")):
                continue
            with_block = step.get("with") or {}
            if with_block.get("persist-credentials") is not False:
                findings.append(
                    Finding(
                        path,
                        "checkout-does-not-persist-credentials",
                        f"job {name}, step {index}: persist-credentials is "
                        f"{with_block.get('persist-credentials')!r}, expected false",
                    )
                )
    return findings


def check_job_timeouts(path: str, document: dict[Any, Any]) -> list[Finding]:
    """A job runs until its timeout or forever, so every job declares one.

    A job that calls a reusable workflow is the one shape that cannot. It has no
    `runs-on` and no steps, `timeout-minutes` is not a key it accepts, and the
    timeout that binds is the one on the job inside the workflow it calls, which
    this same check reads when it reaches that file. Exempting it here is what
    keeps the rule about the job that actually runs rather than about the line
    that names it.
    """
    return [
        Finding(path, "every-job-has-a-timeout", f"job {name} has no timeout-minutes")
        for name, job in (document.get("jobs") or {}).items()
        if job.get("timeout-minutes") is None and not job.get("uses")
    ]


def check_concurrency(path: str, document: dict[Any, Any]) -> list[Finding]:
    concurrency = document.get("concurrency")
    if not concurrency:
        return [Finding(path, "workflow-has-a-concurrency-group", "no concurrency block")]
    group = concurrency if isinstance(concurrency, str) else concurrency.get("group")
    if not group:
        return [
            Finding(path, "workflow-has-a-concurrency-group", "concurrency block names no group")
        ]
    return []


def load_exceptions() -> tuple[list[Waiver], list[Finding]]:
    """Read the waiver file.

    A waiver is a debt that carries what retires it, not a dispensation, so the
    file is refused rather than trusted when it is malformed. An entry with no
    reason, an entry naming a rule that does not exist, or an entry naming a
    workflow that is not tracked, each fail here.
    """
    if not EXCEPTIONS_PATH.exists():
        return [], []
    data = tomllib.loads(EXCEPTIONS_PATH.read_text(encoding="utf-8"))
    tracked = set(tracked_workflows())
    exceptions: list[Waiver] = []
    findings: list[Finding] = []
    for entry in data.get("exception", []):
        path = str(entry.get("workflow", ""))
        rule = str(entry.get("rule", ""))
        reason = str(entry.get("reason", "")).strip()
        where = f"{path or '<no workflow>'} / {rule or '<no rule>'}"
        if not reason:
            findings.append(
                Finding(
                    str(EXCEPTIONS_PATH), "exception-carries-a-reason", f"{where} has no reason"
                )
            )
            continue
        if rule not in RULES:
            findings.append(
                Finding(
                    str(EXCEPTIONS_PATH),
                    "exception-names-a-real-rule",
                    f"{where} names no rule this audit has",
                )
            )
            continue
        if path not in tracked:
            findings.append(
                Finding(
                    str(EXCEPTIONS_PATH),
                    "exception-names-a-tracked-workflow",
                    f"{where} names no tracked file",
                )
            )
            continue
        exceptions.append(Waiver(path, rule, reason))
    return exceptions, findings


def audit() -> int:
    paths = tracked_workflows()
    exceptions, findings = load_exceptions()
    waived = {(e.path, e.rule) for e in exceptions}
    used: set[tuple[str, str]] = set()

    for path in paths:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if triggers(document) is None:
            findings.append(
                Finding(path, "pinned-to-a-hash", "file has no triggers and may not be a workflow")
            )
        for finding in (
            *check_pins(path),
            *check_workflow_permissions(path, document),
            *check_checkout_credentials(path, document),
            *check_job_timeouts(path, document),
            *check_concurrency(path, document),
        ):
            if (finding.path, finding.rule) in waived:
                used.add((finding.path, finding.rule))
                continue
            findings.append(finding)

    # A waiver that no longer waives anything is stale. Leaving it green would
    # let the register fill with entries nobody can tell apart from live ones.
    for exception in exceptions:
        if (exception.path, exception.rule) not in used:
            findings.append(
                Finding(
                    str(EXCEPTIONS_PATH),
                    "exception-is-still-needed",
                    f"{exception.path} / {exception.rule} waives nothing; remove it",
                )
            )

    print(f"audited {len(paths)} tracked workflow file(s) against {len(RULES)} rule(s)")
    for path in paths:
        print(f"  {path}")
    print(f"waivers in force: {len(exceptions)}")

    if findings:
        print(f"\n{len(findings)} finding(s):", file=sys.stderr)
        for finding in sorted(findings, key=str):
            print(f"  {finding}", file=sys.stderr)
        return 1
    print("\nno findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(audit())
