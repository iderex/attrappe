"""The session: its own instrument, its own seed, its own streams.

No socket in this file. `docs/decisions/0002-transport.md` names the in-process
transport as the same session object driven directly by a caller, and driving it
directly is what most of this project's tests should do, because most of what
will be wrong is in the parser and the physics rather than in the socket.

The profile is the dispatch's fixture. A third profile declaring almost the same
instrument would drift against the two that exist.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from attrappe.profile import ProfileError, load_profile
from attrappe.transport import Session, stream_seed

PROFILE = Path(__file__).parents[1] / "scpi" / "fixtures" / "instrument"
BROKEN = Path(__file__).parents[1] / "profile" / "fixtures" / "broken-duplicate-node"

DRAWS = 5


def draws(session: Session, name: str, how_many: int = DRAWS) -> list[float]:
    stream = session.stream(name)
    return [stream.random() for _ in range(how_many)]


def test_a_session_chooses_a_seed_when_nobody_gives_it_one() -> None:
    """There is always something for a bug report to quote."""
    profile = load_profile(PROFILE)

    first = Session(profile)
    second = Session(profile)

    assert first.seed != second.seed


def test_the_same_seed_and_name_give_the_same_sequence() -> None:
    profile = load_profile(PROFILE)

    assert draws(Session(profile, seed=7), "noise") == draws(Session(profile, seed=7), "noise")


def test_a_different_seed_gives_a_different_sequence() -> None:
    profile = load_profile(PROFILE)

    assert draws(Session(profile, seed=7), "noise") != draws(Session(profile, seed=8), "noise")


def test_two_names_under_one_seed_are_two_streams() -> None:
    session = Session(load_profile(PROFILE), seed=7)

    assert draws(session, "noise") != draws(session, "drift")


def test_adding_a_stream_does_not_move_an_existing_one() -> None:
    """The property the derivation exists for, and the reason it is not an offset.

    With one shared generator, or with an offset counted in construction order,
    adding a draw anywhere shifts every later draw. Nothing in a suite catches
    that, because every test still passes against the new sequence, and every
    recorded reproduction in every bug report stops meaning anything at the same
    moment.
    """
    alone = Session(load_profile(PROFILE), seed=7)
    expected = draws(alone, "noise")

    crowded = Session(load_profile(PROFILE), seed=7)
    for name in ("drift", "warmup", "quantisation"):
        draws(crowded, name)

    assert draws(crowded, "noise") == expected


def test_one_name_is_one_stream_and_not_a_copy_of_it() -> None:
    """Two callers asking for a name get the generator, not two of them.

    Two impairments each holding their own copy would each advance a sequence
    the other could not see, and the seed would stop describing the run.
    """
    session = Session(load_profile(PROFILE), seed=7)

    assert session.stream("noise") is session.stream("noise")


def test_the_stream_seed_is_stable_across_processes() -> None:
    """Hashed rather than built on the interpreter's own string hash.

    The built-in hash of a string is salted per process, so a derivation using
    it would give a different stream on every run from the same seed, which is
    the whole of what the seed is for. The number below was produced by
    `stream_seed(7, "noise")` and it is here to be compared with, not to be
    read.
    """
    assert stream_seed(7, "noise") == 4941175376626430674


def test_two_sessions_on_one_profile_do_not_share_instrument_state() -> None:
    profile = load_profile(PROFILE)
    first, second = Session(profile), Session(profile)

    first.deliver("SENS:VOLT:DC:RANG 100")

    assert first.deliver("SENS:VOLT:DC:RANG?").response == "100.0"
    assert second.deliver("SENS:VOLT:DC:RANG?").response == "10.0"


def test_a_session_counts_what_it_was_asked_and_queues_what_it_refused() -> None:
    """Both messages are counted, and only the refused one leaves an entry.

    Read off the instrument's queue rather than off a list of the session's
    own, which is where a refusal goes now that there is a queue with a depth
    to put it in.
    """
    session = Session(load_profile(PROFILE), seed=7)

    session.deliver("*IDN?")
    session.deliver("SENS:VOLT:DC:RANG 2000")

    assert session.operations == 2
    assert [entry.number for entry in session.instrument.errors.entries] == [-222]


def test_a_session_on_a_directory_refuses_a_bad_profile_before_it_exists() -> None:
    """The half of #25 that says the emulator does not start on a bad profile.

    It is asserted here at the session rather than at the listener, because this
    is the object a listener would have to build first and the refusal is the
    same one either way.
    """
    with pytest.raises(ProfileError):
        Session.from_directory(BROKEN)


def test_a_session_on_a_directory_takes_the_seed_it_is_given() -> None:
    assert Session.from_directory(PROFILE, seed=11).seed == 11
    assert Session.from_directory(PROFILE).seed != 11
