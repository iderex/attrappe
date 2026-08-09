# Quality parity

The target this board is closing the distance to, written as properties, with
where the repository stands against each one and what closes it.

The target is taken from a mature gate that runs elsewhere and is not published,
so this list is the target rather than a link to one. Reproducing the properties
is what matters. The gate they came from is not the deliverable and is not
described here.

Every property below is either closed by a named issue or carries a written
deviation. A property with neither is a defect in this document.

## How to read the standing

A standing is a fact about the tree on the day it was measured, and a fact about
the tree written into a document goes stale silently. So each standing carries
the command that produced it, run against the tracked tree, and a reader who
doubts a line runs the command rather than trusting the sentence. The properties
themselves do not drift, because they are the target and not an observation.

Measured at `d2c2af3d6162fa5ca9bc56c5ff7b9c9bc852aea8`, which is the commit the
change carrying this measurement is based on rather than the commit it produces.
That is sound here and would not be in general: every command below reads
`.github/workflows/`, `pyproject.toml` or `tests/`, and none of them reads
`docs/`, so a change confined to this file cannot move any of the answers. A
change touching any of those three paths has to re-run them and quote the result
from its own tree.

Property 6 carries its own measured-at line, and it is the only one this change
re-ran. Every standing beside it is still the reading taken at `d2c2af3`, and
several of them are older than the tree: the gate has gained legs since, so the
job lists, the counts and the line numbers quoted below have moved and the
sentences saying "not met" have not. Re-reading the whole document is a change of
its own and this is not it. What each line is worth is what its own command
answers today.

The standings were first written at `4c9b12a5a7f27a901a740d4b0545a5fbdf16bb86`
and four of them had gone stale by the time they were re-run, which is the
failure the paragraph above describes happening to this document. Properties 1,
2, 7 and 10 moved. The document said nothing was wrong, because nothing here
refuses a stale standing, and the section at the end that says so is the only
warning a reader had.

The same four moved again at `d2c2af3`, and this time the change that moved them
is the one re-measuring them. The gate gained a third leg, which refuses direct
clock and randomness use inside the package: `.github/workflows/gate.yml` grew a
job, so the job list in properties 1 and 10 grew, the pinned-reference count in
property 7 grew by two, and the line number quoted in property 2 moved down six
lines. None of the ten properties moved. That is the distinction this section is
about: the standing is an observation and it went stale within one change of
being written, while the target did not move at all.

## The properties

### 1. Build and test run on every pull request to the mainline and on every push to it

Partly met. One workflow runs on both events and it carries three legs, the type
check, the workflow audit and the injection audit. None of them builds a
distribution and none of them runs a test, so the count of legs went up twice now
and this property has not moved either time.

```
$ python -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/gate.yml')); print(list(d[True].keys())); print(list(d['jobs']))"
['pull_request', 'push']
['types', 'workflows', 'injection']
$ git grep -nEi 'coverage|pytest|--cov|python -m build|hatch build' -- .github/workflows/; echo "exit=$?"
exit=1
```

This property has two halves and no single issue closes it. The test half is
#19, which completes the gate workflow with the remaining legs, and #19 is in
the scaffolding milestone rather than in this one. The build half is #52, which
is in this milestone and which produces the thing there would be to build.

That is a discrepancy with #47's own done-condition, which asks that every
property be closed by an issue in this milestone or carry a written deviation.
This property is closed by two issues across two milestones and it is not a
deferral, so neither branch of that sentence fits it. It is recorded here rather
than filed under a deviation it is not, and #47 stays open on it.

### 2. The build refuses on any tool warning

Not met. There is no build step, so there is nothing to refuse a warning. The
one tool that does run is the type checker, and it fails the job on any error:

```
$ git grep -n 'python -m mypy' -- .github/workflows/gate.yml
.github/workflows/gate.yml:81:        run: python -m mypy
```

A non-zero exit fails the step, and mypy exits non-zero on any error. That is one
tool, not the property.

The two audits in the same workflow also exit non-zero on a finding, and neither
is a compiler warning. A warning is what a tool emits while still succeeding, and
nothing in this repository emits one yet, so the property has nothing to bite on
rather than being satisfied by three tools that fail loudly.

Closed by #50.

### 3. Dependencies audited against a vulnerability database on every run

Partly met, and the partial cover is the part worth naming. The dependency review
runs on pull requests only, and it judges the dependencies a pull request adds or
changes rather than the whole dependency set:

```
$ python -c "import yaml; d=yaml.safe_load(open('.github/workflows/dependency-review.yml')); print(list(d[True].keys()))"
['pull_request']
```

So a dependency that was clean when it landed and acquires an advisory afterwards
is not caught by anything here, and a push to the mainline is not audited at all.

Closed by #48.

### 4. Tests run with coverage collected in a standard interchange format

Not met. There is no test suite and no coverage tool:

```
$ git ls-files 'tests/*' | wc -l
0
$ git grep -nEi 'coverage|--cov' -- pyproject.toml .github/workflows/; echo "exit=$?"
exit=1
```

Closed by #49, which depends on the test harness in #16.

### 5. The coverage number is published to the run summary, and the full report uploaded as an artefact

Not met, for the same reason as property 4: there is no number to publish.

Closed by #49.

### 6. Formatting is checked across every text kind, and it checks rather than rewrites

Met for three of the four text kinds this tree holds, and the fourth is the
deviation written below rather than an omission. Measured at
`0a301c9200a2fa0367d6515765280046a5fc5bec`, which is the commit that added the
second leg rather than the commit carrying this paragraph; the change carrying it
touches this file alone, so none of the answers below moves.

The kinds, by count:

```
$ for kind in py md toml yml; do printf "%s\t%s\n" "$kind" "$(git ls-files "*.$kind" | wc -l)"; done
py      25
md      24
toml    13
yml     8
```

Two legs carry the property. The source is the `format` leg, which asks the
formatter what it would write and never lets it write:

```
$ git grep -n -- "--check" tools/gate.py
tools/gate.py:169:        commands=((sys.executable, "-m", "ruff", "format", "--check", "--diff"),),
tools/gate.py:208:        commands=((sys.executable, "tools/required_checks.py", "--check"),),
```

The documentation and the profile files are the `text` leg, which does the same
for markdown and validates each profile against the loader's schema. Its rules
are proved against fixtures on every run, and the run over the tree says how much
it read:

```
$ python tools/text_audit.py --self-test | tail -1
21 fixture(s) against 3 rule(s), 0 failure(s)
$ python tools/text_audit.py | head -1
audited 24 tracked document(s) and 8 tracked profile(s) against 3 rule(s)
```

Closed by #51 for those three. The fourth kind is the layout of the declarative
files, which nothing formats, and the deviation section below is where that is
argued.

### 7. Every action reference is pinned to a full commit hash with the version in a trailing comment

Met, and guarded since #53 landed. Seventeen references across six workflow files,
and none of them fails the shape:

```
$ git grep -hE '^\s*(- )?uses:' -- .github/workflows/ | wc -l
17
$ git grep -hE '^\s*(- )?uses:' -- .github/workflows/ | grep -vE '@[0-9a-f]{40} # v'; echo "exit=$?"
exit=1
```

The count moved from thirteen to fifteen when the gate gained a second job, and
from fifteen to seventeen when it gained a third. The shape held across both
additions, which is what the second command says and what the first one on its
own would not.

The guarded half is what changed. When this standing was first written, nothing
in the repository refused a sixteenth reference written as a tag except the
workflow-security audit, under its own rule and its own severity threshold. #53
has since landed a first-party audit that refuses it by name, and that audit is
a job in the gate rather than a script somebody remembers to run:

```
$ python tools/workflow_audit.py; echo "exit=$?"
audited 6 tracked workflow file(s) against 6 rule(s)
  .github/workflows/dco.yml
  .github/workflows/dependency-review.yml
  .github/workflows/gate.yml
  .github/workflows/scorecard.yml
  .github/workflows/unicode-guard.yml
  .github/workflows/zizmor.yml
waivers in force: 0

no findings
exit=0
```

The rule bites, shown by writing the violation rather than by reading the source
that would refuse it. A pin replaced with a tag in one tracked workflow, the
audit re-run, and the file restored:

```
$ python - <<'EOF'
import pathlib
p = pathlib.Path(".github/workflows/unicode-guard.yml")
p.write_text(p.read_text(encoding="utf-8").replace(
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
    "actions/checkout@v7", 1), encoding="utf-8")
EOF
$ python tools/workflow_audit.py; echo "exit=$?"

1 finding(s):
  .github/workflows/unicode-guard.yml: pinned-to-a-hash: line 28: actions/checkout@v7 is not a 40-character hash
audited 6 tracked workflow file(s) against 6 rule(s)
  .github/workflows/dco.yml
  .github/workflows/dependency-review.yml
  .github/workflows/gate.yml
  .github/workflows/scorecard.yml
  .github/workflows/unicode-guard.yml
  .github/workflows/zizmor.yml
waivers in force: 0
exit=1
$ git checkout -- .github/workflows/unicode-guard.yml
$ python tools/workflow_audit.py >/dev/null; echo "exit=$?"
exit=0
```

Closed by #53, which is closed.

### 8. The build is a reusable job that the release path calls

Not met. There is no build job and no release path.

Closed by #52.

### 9. The upload step fails when it finds no files

Not met, and it applies to an upload that exists today. The one artefact upload
in the tree does not set the option, so it defaults to warning rather than
failing:

```
$ git grep -n -A4 'upload-artifact' -- .github/workflows/scorecard.yml
.github/workflows/scorecard.yml:84:        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
.github/workflows/scorecard.yml-85-        with:
.github/workflows/scorecard.yml-86-          name: SARIF file
.github/workflows/scorecard.yml-87-          path: results.sarif
.github/workflows/scorecard.yml-88-          retention-days: 5
$ git grep -n 'if-no-files-found' -- .github/workflows/; echo "exit=$?"
exit=1
```

Closed jointly by #49 and #52, which are the two issues that add an upload step,
and each of which owes the setting on the step it adds. Neither issue names the
existing upload in the supply-chain self-audit, and that one is not closed by
either; it is named here so the gap is visible rather than assumed covered.

### 10. Least privilege at the workflow level, with write scopes granted per job

Met. No workflow grants a write scope at the workflow level, and the two
workflows that need one grant it on the job:

```
$ git ls-files '.github/workflows/*.yml' | python -c "
import sys, yaml
for f in sys.stdin.read().split():
    d = yaml.safe_load(open(f))
    print(f, 'top:', d.get('permissions'))
    for j, job in d['jobs'].items():
        print('   job', j, 'perms:', job.get('permissions'), 'timeout:', job.get('timeout-minutes'))
"
.github/workflows/dco.yml top: {'contents': 'read'}
   job dco perms: None timeout: 5
.github/workflows/dependency-review.yml top: {'contents': 'read'}
   job dependency-review perms: None timeout: 10
.github/workflows/gate.yml top: {'contents': 'read'}
   job types perms: None timeout: 10
   job workflows perms: None timeout: 5
   job injection perms: None timeout: 5
.github/workflows/scorecard.yml top: {'contents': 'read'}
   job analysis perms: {'contents': 'read', 'security-events': 'write', 'id-token': 'write'} timeout: 15
.github/workflows/unicode-guard.yml top: {'contents': 'read'}
   job bidi perms: None timeout: 5
.github/workflows/zizmor.yml top: {}
   job zizmor perms: {'security-events': 'write', 'contents': 'read'} timeout: 10
```

The paths come from `git ls-files` rather than from a directory listing, so an
untracked workflow file sitting in a working copy cannot make this answer look
more complete than the tree is.

Every job also carries a timeout, which is not one of the ten properties and is
recorded because the same command answers it.

As with property 7, the guarded half is what #53 changed, and it has landed. The
audit refuses a workflow-level write under its own rule, and the rule bites:

```
$ python - <<'EOF'
import pathlib
p = pathlib.Path(".github/workflows/unicode-guard.yml")
p.write_text(p.read_text(encoding="utf-8").replace(
    "permissions:\n  contents: read\n",
    "permissions:\n  contents: write\n", 1), encoding="utf-8")
EOF
$ python tools/workflow_audit.py; echo "exit=$?"

1 finding(s):
  .github/workflows/unicode-guard.yml: no-workflow-level-write: workflow-level write on contents; grant it on the job instead
audited 6 tracked workflow file(s) against 6 rule(s)
  .github/workflows/dco.yml
  .github/workflows/dependency-review.yml
  .github/workflows/gate.yml
  .github/workflows/scorecard.yml
  .github/workflows/unicode-guard.yml
  .github/workflows/zizmor.yml
waivers in force: 0
exit=1
$ git checkout -- .github/workflows/unicode-guard.yml
$ python tools/workflow_audit.py >/dev/null; echo "exit=$?"
exit=0
```

That covers the workflow-level half of the property and not the per-job half.
The audit refuses a write granted at the top; nothing in it judges whether a
write granted on a job is the smallest one that job needs, and no reading of
these files could. The two jobs that hold a write scope are read by a person or
not at all.

Closed by #53, which is closed.

## Deviations from the gate this list came from

The reference gate audits a package ecosystem this board does not use, so the
audit tool changes while the property does not. Property 3 is the property; which
advisory database and which tool serves it is #48's to choose.

The reference gate's formatting job covers markup and stylesheets, which this
board has almost none of. Property 6 therefore covers the source, the profile
files and the documentation instead. The property is unchanged: every text kind
in the repository, not only the primary language.

Inside that, the layout of the declarative files is not checked and their content
is. A profile is validated against the loader's schema, which is the half that
decides whether it loads; how its tables are spaced and ordered is judged by
nobody. The formatters for that text kind are a second runtime apiece, which
`docs/decisions/0001-implementation-language.md` is the reason not to take for a
property this narrow, and a first-party one would be a formatter maintained
inside a repository that is not about TOML. The schedule files
`docs/decisions/0007-fault-schedule.md` describes are the same kind and do not
exist yet; they join this leg when they land, under the same two halves.

The reference gate builds a distributable artefact on every run. For a compiled
plugin that is cheap; here it means building a package. The property is kept and
the step is smaller.

The reference gate publishes nightly builds. This board does not need them before
its first release, so that property is deferred rather than adapted, and the
deferral is written here so it is visible rather than absent.

## What this document does not cover

The standings above are a reading of the tracked tree. They say what the
repository contains, and they do not say whether a workflow that exists behaves
the way its file suggests. A green run is evidence of behaviour; a file is not.

Nothing refuses a stale standing. If a property is closed and this document is
not updated, the line above goes on saying "not met" and nothing turns red. The
commands are what a reader has instead, and they are the reason each standing
carries one.

#54 writes down the required-checks list for the maintainer to apply. It closes
none of the ten properties, because a required check makes a property refuse a
merge rather than making it true. It is named here so its absence from the
mapping is deliberate rather than an oversight.
