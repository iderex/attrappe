"""Refuse a dependency with a known advisory against it.

    python tools/dependency_audit.py

It audits the installed environment, because that is the set the gate actually
runs on: this project's runtime dependency list is empty and everything the gate
executes arrives through a dependency group. Auditing the declared runtime list
instead would be a check that examines nothing and reports no findings, which is
the worst shape a security check can take.

It fails closed. An audit that could not reach its database, could not collect a
dependency, or answered with something this file cannot read is a refusal rather
than a pass with a warning. A silent pass on a security check is the failure this
exists to prevent, so the unreadable cases are refusals with their reason
printed.

The coverage check is done here rather than with the auditor's own strict flag.
That flag refuses an editable install, and this project is installed editable in
every environment its own contributing document describes, so it would refuse
every run for a reason that is not about a dependency. Instead every dependency
the auditor says it skipped is a refusal, with the one exception of an editable
install, which is named in the output rather than passed over in silence.

The register of accepted findings is `tools/dependency-audit-acceptances.toml`.
It fails closed in both directions: an entry with no reason or no retirement
condition is refused, an entry naming a finding that is no longer reported is
refused as stale, and a finding no entry names is refused. An empty register is
the normal state.

The unreachable-database case can be produced by hand, because no database is
unreachable on demand:

    python tools/dependency_audit.py --osv-url http://127.0.0.1:9/v1/query

"""

import argparse
import json
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCES = ROOT / "tools" / "dependency-audit-acceptances.toml"

# The Open Source Vulnerabilities database rather than the PyPI advisory feed.
# It carries the PyPI advisories and the ones that reach a Python package through
# another ecosystem's identifier, and it is the one this file can point somewhere
# unreachable to prove the fail-closed path.
DEFAULT_OSV_URL = "https://api.osv.dev/v1/query"

# The one reason a dependency may go unaudited without the run being refused.
EDITABLE = "distribution marked as editable"


@dataclass(frozen=True)
class Finding:
    package: str
    version: str
    advisory: str
    fixed_in: str


@dataclass(frozen=True)
class Acceptance:
    advisory: str
    package: str
    reason: str
    retired_when: str


def audit(osv_url: str, timeout: int) -> tuple[list[Finding], list[str]]:
    """Run the auditor and read its answer. Problems are refusals, not warnings."""
    command = [
        sys.executable,
        "-m",
        "pip_audit",
        # The environment this interpreter runs in, which is the set the gate
        # executes.
        "--local",
        # An editable install has no released version to ask a database about.
        # The coverage check below is what refuses a dependency that went
        # unaudited for any other reason.
        "--skip-editable",
        "--vulnerability-service",
        "osv",
        "--osv-url",
        osv_url,
        "--timeout",
        str(timeout),
        "--progress-spinner",
        "off",
        "--format",
        "json",
    ]
    print(f"  $ {' '.join(['python' if word == sys.executable else word for word in command])}")
    result = subprocess.run(command, capture_output=True, text=True, check=False, cwd=ROOT)

    try:
        answer = json.loads(result.stdout)
    except json.JSONDecodeError:
        tail = (result.stderr or result.stdout).strip().splitlines()[-4:]
        return [], [
            "the auditor did not answer with a result this file can read, "
            f"exit code {result.returncode}: " + " / ".join(tail)
        ]

    # Deduplicated. The database answers a query about one package with one entry
    # per record it holds, and it holds several records per advisory, so the same
    # advisory against the same version comes back more than once. Reporting it
    # twice would make the refusal read as two problems where there is one.
    seen: dict[tuple[str, str, str], Finding] = {}
    for dependency in answer.get("dependencies", []):
        for vulnerability in dependency.get("vulns", []):
            finding = Finding(
                package=str(dependency.get("name", "")),
                version=str(dependency.get("version", "")),
                advisory=str(vulnerability.get("id", "")),
                fixed_in=", ".join(str(v) for v in vulnerability.get("fix_versions", []))
                or "nothing",
            )
            seen.setdefault((finding.package, finding.version, finding.advisory), finding)

    # Coverage. The auditor reports a dependency it could not audit with the
    # reason it gave up, and a run that quietly examined less than the
    # environment is the failure this leg exists to prevent. The one reason that
    # is not a refusal is an editable install: it has no released version to ask
    # a database about, this project is installed that way in every environment
    # CONTRIBUTING.md describes, and it is named rather than passed over.
    skipped = [
        (str(d.get("name", "")), str(d.get("skip_reason", "")))
        for d in answer.get("dependencies", [])
        if d.get("skip_reason")
    ]
    audited = len(answer.get("dependencies", [])) - len(skipped)
    print(f"  {audited} distribution(s) audited, {len(skipped)} not")
    problems = []
    for name, reason in sorted(skipped):
        if reason == EDITABLE:
            print(f"    not audited, installed from a directory: {name}")
            continue
        problems.append(f"{name} was not audited: {reason}, so this run covers less than the set")

    return sorted(seen.values(), key=lambda f: (f.package, f.advisory)), problems


def acceptances() -> tuple[list[Acceptance], list[str]]:
    """The register, and what is wrong with it."""
    if not ACCEPTANCES.exists():
        return [], [f"{ACCEPTANCES.name} is missing; an empty register is a file, not an absence"]

    entries = tomllib.loads(ACCEPTANCES.read_text(encoding="utf-8")).get("acceptance", [])
    accepted: list[Acceptance] = []
    problems: list[str] = []
    for index, entry in enumerate(entries):
        where = f"{ACCEPTANCES.name} entry {index + 1}"
        advisory = str(entry.get("advisory", ""))
        if not advisory:
            problems.append(f"{where} names no advisory")
            continue
        if not str(entry.get("reason", "")).strip():
            problems.append(f"{where}, {advisory}, has no reason")
        if not str(entry.get("retired_when", "")).strip():
            problems.append(f"{where}, {advisory}, does not say what would retire it")
        accepted.append(
            Acceptance(
                advisory=advisory,
                package=str(entry.get("package", "")),
                reason=str(entry.get("reason", "")),
                retired_when=str(entry.get("retired_when", "")),
            )
        )
    return accepted, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refuse a dependency with a known advisory.")
    parser.add_argument(
        "--osv-url",
        default=DEFAULT_OSV_URL,
        help="where the advisory database is; point it somewhere unreachable to see the run fail",
    )
    parser.add_argument("--timeout", type=int, default=30, help="seconds to wait on the database")
    arguments = parser.parse_args(argv)

    findings, problems = audit(arguments.osv_url, arguments.timeout)
    accepted, register_problems = acceptances()
    problems.extend(register_problems)

    by_advisory = {acceptance.advisory: acceptance for acceptance in accepted}
    for finding in findings:
        acceptance = by_advisory.get(finding.advisory)
        if acceptance is None:
            problems.append(
                f"{finding.package} {finding.version}: {finding.advisory}, "
                f"fixed in {finding.fixed_in}"
            )
        else:
            print(f"  accepted: {finding.advisory} on {finding.package}: {acceptance.reason}")

    reported = {finding.advisory for finding in findings}
    for acceptance in accepted:
        if acceptance.advisory not in reported:
            problems.append(
                f"{ACCEPTANCES.name}: {acceptance.advisory} is accepted and is no longer "
                "reported, so the entry waives nothing and is stale"
            )

    print(f"  audited {len(findings)} finding(s), acceptances in force: {len(accepted)}")
    if problems:
        print("\n  refused:")
        for problem in problems:
            print(f"    {problem}")
        return 1
    print("  no findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
