# attrappe

Nothing described in the next five sections is built yet. This board holds
decision records, packaging metadata, workflow guards and one leg of a gate. The
section after them says what the tree actually contains, with the commands that
answer it.

## What this is meant to be

An instrument emulator that answers a measurement driver over a socket the way a
bench instrument answers it, including the parts that are inconvenient. It is
meant to speak the same command language and the same message-level standard a
real instrument speaks, and to return values that drift, settle, quantise,
saturate, and occasionally do not arrive.

It is meant to sit where the instrument is not yet: in the test suite of the
measurement software, in continuous integration, before the hardware is on the
bench.

## What already exists

Rudimentary dummy instruments already ship in the established instrument-control
frameworks. PyMeasure and QCoDeS both provide them, they are documented, and they
are widely used. That sentence is a statement about other projects, read from
their documentation, and nothing in this tree measures it.

What those dummies do is answer. A query gets a well-formed, clean, immediate
value, which is enough to check that the calling code runs, that the command
string was built correctly, and that the parsing on the way back works. That is a
real job and those tools do it.

## The difference this project claims

An existing dummy returns a clean value to every query. Measurement software does
not break on clean values.

It breaks on a reading that drifts a little further from the setpoint every
minute the box warms up. On an autorange that overshoots and returns the overload
sentinel, which is a specific large number and not an error, so the arithmetic
downstream keeps going with it. On a value quantised to the digit setting
somebody changed three commands ago. On one read in four hundred that takes
longer than the client's timeout. On a response that comes back malformed, or
truncated, or one reply out of step after a state change, so that every
subsequent answer is the previous question's.

Those are the failure modes measurement software actually breaks on, and nothing
tests them systematically. That is the gap this board is aimed at.

## What that would buy

A driver that attaches unmodified and cannot tell the difference, so the test is
a test of the driver rather than of a mock somebody wrote to match the driver.

A deliberately fragile measurement program that fails the way it would fail
against the instrument, at a desk, rather than in a laboratory at two in the
morning during a run that cannot be repeated.

A seed and a schedule, so a failure somebody hit once can be handed to somebody
else and hit again.

## What this is not

It is not a simulator of any manufacturer's firmware. It is meant to reproduce
behaviour described in published documentation and behaviour measured on a bench,
and it is not a reimplementation of anybody's product.

It is not certified against any standard. No conformance test has been run
against it and none is planned for the first release.

It does not replace testing against a real instrument before results are trusted.
An emulator is a model, the gap between a model and a device is where the
interesting faults live, and this project's own parity report is where that gap
is meant to be written down rather than hidden.

## Where the board stands today

The package is layout only. It declares five subpackages and a version, and it
holds no function and no class:

```
$ git ls-files src/attrappe
src/attrappe/__init__.py
src/attrappe/device/__init__.py
src/attrappe/impairment/__init__.py
src/attrappe/profile/__init__.py
src/attrappe/scpi/__init__.py
src/attrappe/transport/__init__.py
$ git grep -nE '^(def|class) ' -- src/attrappe; echo "exit=$?"
exit=1
```

There is no test suite:

```
$ git ls-files 'tests/*' | wc -l
0
```

So there is no parser, no listener, no profile and no impairment. Every
capability sentence above is a goal, which is what the first paragraph and the
two section headings that say "meant to be" and "would buy" are for.

## Where the reasons are

Planning happens on the issue tracker first. Every decision that shapes the
architecture is written down in [docs/decisions](docs/decisions/) with its
options, its reasons and the costs it accepted, before the code that depends on
it exists. [docs/decisions/README.md](docs/decisions/README.md) is the index, and
a record is superseded rather than edited, so the history of what was believed
stays readable.

[docs/quality-parity.md](docs/quality-parity.md) states the quality target this
board is closing the distance to, property by property, with where the tree
stands against each one and the command that measured it.

See [NOTICE.md](NOTICE.md) for the intended-use notice and
[SECURITY.md](SECURITY.md) for how to report a vulnerability.
