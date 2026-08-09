# The suite

Two harnesses, one runner, one configuration. The settings that decide what runs
are in `[tool.pytest.ini_options]` in `pyproject.toml` and nowhere else.

## The default suite

```
python -m pytest
```

Everything under this directory except the hardware-bound marker, which
`addopts` deselects. This is the suite the gate runs and the suite a contributor
runs locally, selected the same way in both places rather than by two settings
that happen to agree. `docs/decisions/0008-headless.md` is where that is
required and why.

The directories mirror the package. A test of `attrappe.scpi` belongs in
`tests/scpi`, and so on for `device`, `transport`, `impairment` and `profile`.
Most of them hold a README and no test yet, and each says which issue brings the
first one.

## The hardware-bound harness

```
python -m pytest tests/hardware_bound -m hardware_bound
```

`-m hardware_bound` on the command line replaces the deselection in `addopts`,
and the path restricts the run to this harness, so the command runs the
hardware-bound tests and nothing else.

Add `--device NAME` to say what it ran against. The run states the name, or
states that no device was present when the option is not given. Nothing probes
for hardware: a probe is a device node, a driver call or a permission prompt
depending on the operating system, and all three are refused here, so the device
is a claim by the person running the harness and the output says so.

This harness never gates a merge and its result covers nothing the default suite
covers.

It holds no test yet, so the command above collects nothing and exits 5, which
is pytest's code for a run in which no test ran. The first member it is owed is
the soak run in #46.

## The shared fixtures

`tests/conftest.py` carries the `--device` option and three fixtures, so that no
test has a reason to build its own session, pick its own seed or reach for a
real socket by accident.

`instrument_profile` is the dispatch's profile fixture, loaded fresh for each
test that asks for it.

`session` is a seeded session on that profile. It is the in-process transport as
well as the seeded session, rather than one of two things:
`docs/decisions/0002-transport.md` defines that transport as the same session
object a connected client drives, driven directly by a caller in the same
process, so a second fixture would hand out one class under two names.

`new_session` is the factory, for a test that needs two sessions, another seed
or another profile.

The seed is one constant in the conftest rather than a number per file, so a
failure anywhere in the suite is reproduced from one seed and one profile.
`tests/test_the_shared_fixtures.py` asserts each of those promises, because a
fixture nothing checks fails quietly: the tests that took it keep passing while
asserting against a state nobody set.

## What the suite does not have yet

There is no manual clock fixture, because there is no clock:

```
$ git grep -nE '^(def|class) .*[Cc]lock' -- src/attrappe ; echo "exit=$?"
exit=1
```

`docs/decisions/0003-time.md` decides a clock interface with a real and a manual
implementation. A fixture here cannot be the first one, because it would put an
interface the package itself has to import in a place the package cannot import
from, and would guarantee a second implementation on the day the real one lands.
#16 stays open on that fixture.
