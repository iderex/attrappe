"""One client's instrument: its own state, its own seed, its own streams.

    from attrappe.transport import Session

    session = Session(profile, seed=12345)
    session.deliver("*IDN?")

A session is the whole emulator with no socket underneath it. That is the
in-process transport `docs/decisions/0002-transport.md` names as its second
surface: the same object a connected client drives, driven directly by a caller
in the same process, so the parser, the tree and the instrument are exercised
without a listener and without a port.

## One of these per connection, and nothing shared between two

Two clients on one listener get two of these. Each carries its own instrument
state, its own seed, its own streams and its own operation counter, so two test
sessions opened against one process are two independent reproductions rather
than one that depends on how far the other got. `0004-randomness.md` is where
that is required.

## The streams

A stream is derived from the seed and the stream's name by a stable hash of the
two. Not by consuming draws from a shared generator and not by an offset counted
in construction order, because both of those move every existing stream when an
impairment is added, and the failure is quiet: every test still passes against
the new sequence while every recorded reproduction in every bug report has
silently stopped meaning anything.

The hash is `blake2b` rather than the built-in `hash`, whose value for a string
is salted per process, so the same seed and the same name would give a different
stream on every run.

## What is not here yet

The error queue. `refusals` is a list with no depth and no overflow behaviour,
and the depth a profile declares is loaded and unread. #23 is the queue that
gives it both, along with the `SYSTem:ERRor?` family that reads it, and this
list is where it lands.

The clock. Nothing in a session measures time today: an integration that costs
time is #34 and a fault that delays a response is #36, and both arrive with the
clock `0003-time.md` decides. There is no clock in this tree, no issue on this
board builds one, and the fixtures #16 asks for wait on it.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from pathlib import Path

from attrappe.device import Instrument
from attrappe.profile import Profile, load_profile
from attrappe.scpi import Dispatch, Outcome
from attrappe.scpi.dispatch import Error

# How a stream's seed is derived: the session seed and the stream name, hashed
# together. The separator is a byte that cannot appear in a decimal number, so
# no pair of seed and name can collide with another pair by running together.
STREAM_SEPARATOR = b":"
STREAM_DIGEST_SIZE = 8

# The seed a session chooses when nothing hands it one. It is drawn from the
# operating system's entropy rather than from a generator this project seeds,
# because a default seed that is itself derived from something in here would
# make every session that took the default identical.
SEED_BITS = 64


def choose_seed() -> int:
    """A seed for a session nobody gave one to."""
    return int.from_bytes(random.Random().randbytes(SEED_BITS // 8))


def stream_seed(seed: int, name: str) -> int:
    """The seed of one named stream, derived from the session seed and the name."""
    digest = hashlib.blake2b(
        str(seed).encode("utf-8") + STREAM_SEPARATOR + name.encode("utf-8"),
        digest_size=STREAM_DIGEST_SIZE,
    )
    return int.from_bytes(digest.digest())


@dataclass
class Session:
    """One client's emulator: the instrument, the dispatch, the seed, the streams.

    `seed` is what a bug report quotes. It is printed by whatever started the
    session, and a session that was not given one chooses one so that there is
    always something to quote.
    """

    profile: Profile
    seed: int = field(default_factory=choose_seed)
    operations: int = 0
    refusals: list[Error] = field(default_factory=list)
    instrument: Instrument = field(init=False)
    dispatch: Dispatch = field(init=False)
    _streams: dict[str, random.Random] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.instrument = Instrument(self.profile)
        self.dispatch = Dispatch.for_instrument(self.instrument)

    @classmethod
    def from_directory(cls, directory: Path, seed: int | None = None) -> Session:
        """A session on the profile in a directory, refusing a bad profile first."""
        profile = load_profile(directory)
        return cls(profile) if seed is None else cls(profile, seed=seed)

    def stream(self, name: str) -> random.Random:
        """The named stream, the same instance every time it is asked for.

        An impairment holding its own copy would advance a sequence nobody else
        could see, and two impairments sharing a name are one stream on purpose.
        """
        if name not in self._streams:
            self._streams[name] = random.Random(stream_seed(self.seed, name))
        return self._streams[name]

    def deliver(self, message: str) -> Outcome:
        """Run one message, count it, and keep what it refused."""
        self.operations += 1
        outcome = self.dispatch.execute(message)
        self.refusals.extend(outcome.errors)
        return outcome

    def record(self, refusal: Error) -> None:
        """Keep a refusal that never reached the dispatch.

        The framing produces these: a message too long to hold and a byte
        outside the alphabet are both refused before anything has a command to
        run. They belong on the same list as the rest, because a client asking
        the instrument what went wrong asks one question.
        """
        self.refusals.append(refusal)
