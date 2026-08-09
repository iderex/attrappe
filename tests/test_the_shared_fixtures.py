"""What the shared fixtures promise, asserted rather than assumed.

`tests/conftest.py` hands out a seeded session on one profile, and a factory for
a second session, another seed or another profile. Those are promises: that the
seed is fixed rather than drawn, that two sessions built the same way draw the
same sequence, that two sessions are two instruments, and that the object handed
out is wired to the whole stack rather than merely constructed.

A fixture whose promise nothing checks is scaffolding that fails quietly. The
failure is the slow kind: every test that took the fixture keeps passing while
asserting against a state nobody set, and the first person to notice is whoever
tries to reproduce a bug report from the seed.

Nothing here imports the conftest. The assertions are about what the fixtures
hand out, and a test comparing a fixture against the constant that fixture was
built from would agree with itself whatever the constant became.

A seed is fixed if it is the same on the next run, and a run cannot see the next
one. What is asserted instead is that two sessions the fixtures built separately
carry one seed, beside the fact that two sessions left to choose their own do
not. The first sentence is what a fixed seed produces and the second is what
makes it worth asserting: without it the test would pass against any pair of
sessions that happened to agree.

No socket appears in this file either. `tests/test_nothing_calls_out.py` is
where a session opening one is refused, and repeating that here would be a
second place claiming the same property with less behind it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from attrappe.profile import Profile, load_profile
from attrappe.transport import Session

# A second profile, for the factory's profile argument. The parser's vocabulary
# rather than a new directory: it is in the tree already, and its identification
# differs from the instrument's, which is what makes the assertion below say
# something.
VOCABULARY_PROFILE = Path(__file__).parent / "scpi" / "fixtures" / "vocabulary"

# How many draws compare two streams. Five is enough that two generators seeded
# differently do not agree by accident, and short enough to read in a failure.
DRAWS = 5


def draws(session: Session, name: str = "noise", how_many: int = DRAWS) -> list[float]:
    """A fixed number of draws from one named stream of one session."""
    stream = session.stream(name)
    return [stream.random() for _ in range(how_many)]


def test_the_session_fixture_is_seeded_rather_than_drawing_a_seed(
    session: Session, new_session: Callable[..., Session], instrument_profile: Profile
) -> None:
    """A session nobody seeds chooses one, and a suite on that reproduces nothing."""
    assert session.seed == new_session().seed
    assert Session(instrument_profile).seed != Session(instrument_profile).seed


def test_two_sessions_built_the_same_way_draw_the_same_sequence(
    session: Session, new_session: Callable[..., Session]
) -> None:
    """The factory's default is the fixture's seed and not a second one."""
    assert draws(session) == draws(new_session())


def test_the_factory_takes_a_seed(session: Session, new_session: Callable[..., Session]) -> None:
    """A test that needs a second reproduction can ask for one."""
    assert draws(session) != draws(new_session(seed=session.seed + 1))


def test_the_factory_takes_another_profile(
    new_session: Callable[..., Session], instrument_profile: Profile
) -> None:
    """A test about a second instrument does not have to reach past the fixture.

    Asserted against the second profile's identification rather than against the
    session's own, which is the same string either way and would agree with a
    factory that dropped the argument.
    """
    vocabulary = load_profile(VOCABULARY_PROFILE)
    other = new_session(profile=vocabulary)

    assert vocabulary.identification != instrument_profile.identification
    assert other.deliver("*IDN?").response == vocabulary.identification


def test_the_fixture_session_reaches_the_instrument(
    session: Session, instrument_profile: Profile
) -> None:
    """Wired through the parser, the tree and the instrument, with no listener."""
    assert session.deliver("*IDN?").response == instrument_profile.identification


def test_the_fixture_session_carries_its_own_settings(session: Session) -> None:
    """A written setting reads back, so the instrument behind the fixture is real."""
    session.deliver("SENS:VOLT:DC:RANG 100")

    assert session.deliver("SENS:VOLT:DC:RANG?").response == "100.0"


def test_two_sessions_from_the_factory_are_two_instruments(
    session: Session, new_session: Callable[..., Session]
) -> None:
    """One test's writes are invisible to another's, which is what per session means."""
    session.deliver("SENS:VOLT:DC:RANG 100")

    assert new_session().deliver("SENS:VOLT:DC:RANG?").response == "10.0"
