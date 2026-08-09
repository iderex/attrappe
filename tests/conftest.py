"""Configuration and fixtures shared by both harnesses.

`--device` is declared here rather than in `tests/hardware_bound/conftest.py`
because pytest reads command-line options only from an initial conftest, and a
subdirectory conftest is not one. The option is read there, where it is
reported.

## Why the fixtures are here rather than in each test

A test that builds its own session picks its own seed, and a suite with a seed
per file has no single number a bug report can quote. The fixtures below hand
out one seed and one profile, so a failure anywhere in the suite is reproduced
by the same two facts.

## The seeded session and the in-process transport are one fixture

`docs/decisions/0002-transport.md` defines the in-process transport as the same
session object a connected client drives, driven directly by a caller in the
same process. Two fixtures would hand out that one class under two names and
invite a reader to look for a second thing. `session` is both, and a test that
wants a port asks the operating system for one the way
`tests/transport/test_the_listener.py` does.

## There is no manual clock fixture

`docs/decisions/0003-time.md` decides a clock interface with a real and a manual
implementation, and neither exists in the package:

    $ git grep -nE '^(def|class) .*[Cc]lock' -- src/attrappe ; echo "exit=$?"
    exit=1

A fixture here cannot be the first one. It would put an interface the emulator
itself has to import in a place the emulator cannot import from, and it would
guarantee a second implementation on the day the real one lands. So the tests
that need a clock most, which are the impairment stages, still have nothing to
take one from, and that half of #16 waits on a clock in `src/attrappe`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pytest

from attrappe.profile import Profile, load_profile
from attrappe.transport import Session

# The instrument the suite is driven against. The dispatch's fixture rather than
# a third one: `tests/transport/README.md` says why a profile declaring almost
# the same instrument is worse than a shared one, and the reason holds harder
# for a profile every harness would see.
INSTRUMENT_PROFILE = Path(__file__).parent / "scpi" / "fixtures" / "instrument"

# The seed every fixture session takes unless a test asks for another. The value
# is arbitrary and it is fixed, which is the whole property: a sequence a test
# asserts against is the same sequence on the next run and on somebody else's
# machine. `attrappe.transport.choose_seed` is what a session takes when nobody
# hands it one, and a suite on that would assert against a different sequence
# every run.
FIXTURE_SEED = 7


class SessionFactory(Protocol):
    """What `new_session` hands back: a session on a seed, or on another profile."""

    def __call__(self, seed: int = ..., profile: Profile | None = ...) -> Session: ...


@pytest.fixture
def instrument_profile() -> Profile:
    """The loaded profile the session fixtures are built on.

    Loaded per test rather than once for the run. A `Profile` is frozen the
    whole way down and sharing one would be safe, but a test that reaches into
    the profile and finds it altered by an earlier test is a failure nobody
    reads correctly, and a TOML file this size costs nothing to read again.
    """
    return load_profile(INSTRUMENT_PROFILE)


@pytest.fixture
def session(instrument_profile: Profile) -> Session:
    """A seeded session on that profile, with no socket underneath it."""
    return Session(instrument_profile, seed=FIXTURE_SEED)


@pytest.fixture
def new_session(instrument_profile: Profile) -> SessionFactory:
    """A second session, or one on a different seed, or one on another profile.

    A test that compares two sessions needs both to be built the same way, and a
    test about a seed needs to choose one. Both would otherwise reach past the
    `session` fixture to the constructor and take the profile path with them.
    """

    def make(seed: int = FIXTURE_SEED, profile: Profile | None = None) -> Session:
        return Session(instrument_profile if profile is None else profile, seed=seed)

    return make


def pytest_addoption(parser: pytest.Parser) -> None:
    """Name the device the hardware-bound harness ran against.

    Nothing probes for hardware. A probe is a device node, a driver call or a
    permission prompt depending on the operating system, and the headless
    record refuses all three in this repository. So the device is stated by
    whoever runs the harness and the harness repeats what it was told, which is
    a claim by a person rather than a measurement, and reads as one.
    """
    parser.addoption(
        "--device",
        action="store",
        default="",
        metavar="NAME",
        help=(
            "the instrument the hardware-bound harness is running against; "
            "left unset, that harness reports that no device was present"
        ),
    )
