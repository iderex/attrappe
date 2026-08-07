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

Measured at `4c9b12a5a7f27a901a740d4b0545a5fbdf16bb86`.

## The properties

### 1. Build and test run on every pull request to the mainline and on every push to it

Partly met. One workflow runs on both events and it carries one leg, the type
check. Nothing builds a distribution and nothing runs a test.

```
$ python -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/gate.yml')); print(list(d[True].keys())); print(list(d['jobs']))"
['pull_request', 'push']
['types']
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
.github/workflows/gate.yml:73:        run: python -m mypy
```

A non-zero exit fails the step, and mypy exits non-zero on any error. That is one
tool, not the property.

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

Not met. No formatter is configured and none runs:

```
$ git grep -nEi 'ruff format|black|prettier|fmt --check' -- .github/workflows/ pyproject.toml; echo "exit=$?"
exit=1
```

Closed by #51.

### 7. Every action reference is pinned to a full commit hash with the version in a trailing comment

Met. Thirteen references across six workflow files, and none of them fails the
shape:

```
$ git grep -hE '^\s*(- )?uses:' -- .github/workflows/ | wc -l
13
$ git grep -hE '^\s*(- )?uses:' -- .github/workflows/ | grep -vE '@[0-9a-f]{40} # v'; echo "exit=$?"
exit=1
```

Met is not the same as guarded. Nothing in this repository refuses a fourteenth
reference written as a tag except the workflow-security audit, which flags an
unpinned action under its own rule. #53 is the issue that makes the property
refusable in its own right, and it says where it overlaps the audit rather than
duplicating it silently.

Closed by #53.

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

As with property 7, met is not guarded. Closed by #53.

## Deviations from the gate this list came from

The reference gate audits a package ecosystem this board does not use, so the
audit tool changes while the property does not. Property 3 is the property; which
advisory database and which tool serves it is #48's to choose.

The reference gate's formatting job covers markup and stylesheets, which this
board has almost none of. Property 6 therefore covers the source, the profile
files and the documentation instead. The property is unchanged: every text kind
in the repository, not only the primary language.

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
