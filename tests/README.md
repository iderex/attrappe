# The suite

Two harnesses, one runner, one configuration. The settings that decide what runs
are in `[tool.pytest.ini_options]` in `pyproject.toml` and nowhere else.

## The default suite

    python -m pytest

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

    python -m pytest tests/hardware_bound -m hardware_bound

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

## What the suite does not have yet

`tests/conftest.py` carries the `--device` option and no fixtures. The harness
was asked for shared fixtures for the manual clock, a seeded session and an
in-process transport, so that no test reaches for the real clock or a real
socket by accident. None of the three can be written yet: there is no clock, no
session and no transport in `src/attrappe`, which holds docstrings and a version
literal. #16 stays open on that half and names what each fixture waits for.
