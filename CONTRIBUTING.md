# Contributing

## Before anything else

```
python tools/gate.py
```

That is the whole gate. Its legs run in order and the run stops at the first
failure, and it prints what it was about to run and what it ran, so a run that
covered part of the set cannot be read as one that covered the set and found
nothing. If it does not pass, nothing else matters yet.

What the legs are is printed by the command and is not listed here, because a
list in a document drifts against the thing it describes:

```
python tools/gate.py --list
```

A leg can be asked for on its own, and the run then says which legs were not
asked for and what running each one would need:

```
python tools/gate.py --only types
```

The jobs in `.github/workflows/gate.yml` invoke the same command with `--only`
rather than restating the tools, so there is one list of legs and it lives in
`tools/gate.py`. The `wiring` leg refuses a selector in that workflow naming a
leg the command does not have.

Nothing runs the command for you. There is no pre-push hook in this repository
and the workflow is triggered by the push rather than by anything local, so a
run that never happened leaves the same trace as one that was green until the
server says otherwise.

## What to install

The tools are development dependency groups in `pyproject.toml`, one per leg,
and the command tells you which group a leg needs when it reports a leg it did
not run. All of them at once, in a virtual environment:

```
python -m pip install -e . --group lint --group types --group workflows --group tests
```

The runtime dependency list is empty and every addition to it is argued in the
issue that adds it.

## Tests

`tests/README.md` says how the two harnesses are run and what separates them.
The short version is that `python -m pytest` is the default suite, the
hardware-bound harness is deselected from it by configuration, and the
hardware-bound harness never gates a merge.

## Where the rules come from

Every decision that shapes the architecture is written down in
[docs/decisions](docs/decisions/) with its options, its reasons and the costs it
accepted. Read the one a rule comes from before arguing with the rule, because
most disagreements about a rule here are disagreements about a decision, and it
is easier to argue with the decision directly.

Planning happens on the issue tracker first. An issue says what is wrong, what
the evidence is, and what "done" means, and where the evidence is a number it
carries the command that produced it.

## Commits

Commits are signed and carry a `Signed-off-by` trailer matching their author,
which is the Developer Certificate of Origin. A commit without one is refused by
the sign-off check that runs on every pull request.

A commit message states what changed and what failure it prevents. Where a
correction is being made, it says what was wrong and how it was found.
