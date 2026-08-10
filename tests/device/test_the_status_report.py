"""Status reporting: which event raises which bit, and what the status byte is.

`tests/device/test_the_instrument_state.py` holds the arithmetic over registers
somebody set by hand. What is here is the other half: that the bits are raised by
the events that cause them, driven through the wire, and that the status byte
reads an output queue rather than a constant.

Through a session rather than through an `Instrument`, wherever an event is what
is being proved. A bit raised by a call this file makes is a bit this file set,
and the property is that a message a client sends sets it.

## The query error bit has no event in this tree

Four of the five bits are raised by something a client can do. The query error
bit is not, because nothing in this tree produces an error in its block: those
errors are message-exchange conditions of a bus that addresses a device to talk,
and `docs/decisions/0002-transport.md` takes a stream socket and no other
surface. `test_no_refusal_in_this_tree_is_a_query_error` is that statement as a
check rather than as a sentence, so the first refusal added in the block turns
this file red instead of raising no bit in silence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from attrappe.device import (
    COMMAND_ERROR_BIT,
    DEVICE_ERROR_BIT,
    ERROR_CLASSES,
    EVENT_SUMMARY_BIT,
    EXECUTION_ERROR_BIT,
    FIRST_DEVICE_SPECIFIC_NUMBER,
    MASTER_SUMMARY_BIT,
    MESSAGE_AVAILABLE_BIT,
    OPERATION_COMPLETE_BIT,
    QUERY_ERROR_BIT,
    QUEUE_OVERFLOW_NUMBER,
    Entry,
    Instrument,
    event_bit,
)
from attrappe.profile import Profile, load_profile
from attrappe.scpi import Refused
from attrappe.scpi.dispatch import REFUSALS as EXECUTION_REFUSALS
from attrappe.scpi.parser import MESSAGE_SEPARATOR
from attrappe.scpi.parser import REFUSALS as MESSAGE_REFUSALS
from attrappe.transport import Session
from attrappe.transport.server import REFUSALS as FRAMING_REFUSALS

QUEUE_PROFILE = Path(__file__).parent / "fixtures" / "queue"

# One message per bit, and the message is the event rather than a stand-in for
# it. The spellings are the ones `tests/device/test_the_error_queue.py` provokes
# the same rows with, so a message here and a message there mean the same thing.
CAUSES: tuple[tuple[str, int], ...] = (
    ("TRIG:SOUR IMM", COMMAND_ERROR_BIT),
    ("SENS:VOLT:DC:RANG 2000", EXECUTION_ERROR_BIT),
    ("*OPC", OPERATION_COMPLETE_BIT),
)

# The masks the status byte tests arm. Written as the bit rather than as the
# number a client sends, because what `*ESE 32` means is the command error bit
# and a reader should not have to convert.
COMMAND_ERROR_MASK = COMMAND_ERROR_BIT
EVENT_SUMMARY_MASK = EVENT_SUMMARY_BIT
MESSAGE_AVAILABLE_MASK = MESSAGE_AVAILABLE_BIT


@pytest.fixture
def shallow() -> Profile:
    """A profile declaring a queue two entries deep, for the overflow."""
    return load_profile(QUEUE_PROFILE)


def answers(session: Session, message: str) -> list[str]:
    """What a message answered, split back into one answer per query."""
    outcome = session.deliver(message)
    assert outcome.response is not None, message
    return outcome.response.split(MESSAGE_SEPARATOR)


def status_byte(session: Session) -> int:
    """The status byte as a client reads it, which is over the wire."""
    (byte,) = answers(session, "*STB?")
    return int(byte)


@pytest.mark.parametrize(("message", "bit"), CAUSES, ids=[message for message, _ in CAUSES])
def test_one_message_raises_exactly_the_bit_its_event_owns(
    session: Session, message: str, bit: int
) -> None:
    """Exactly, so a bit raised by everything would fail here rather than pass.

    Reading the register is what a client does, and it is also what clears it,
    so the second read is the assertion that nothing else was left standing.
    """
    session.deliver(message)

    assert session.instrument.read_event_status() == bit
    assert session.instrument.read_event_status() == 0


def test_reading_the_event_status_register_clears_what_a_message_raised(
    session: Session,
) -> None:
    """Over the wire, because the order dependence is what a polling loop meets.

    Two clients polling the same instrument is not the case here, since each
    connection has its own. The case is one client whose first `*ESR?` is the
    reason its second one says nothing went wrong.
    """
    session.deliver("TRIG:SOUR IMM")

    assert answers(session, "*ESR?") == [str(COMMAND_ERROR_BIT)]
    assert answers(session, "*ESR?") == ["0"]


def test_a_refusal_that_never_reached_the_dispatch_raises_its_bit_too(
    session: Session,
) -> None:
    """The framing's refusals, which arrive before there is a command to run.

    `Session.record` is the door they come through, and a client polling the
    register for the mistake it made on the wire should be told about it there
    as well as in the queue.
    """
    row = next(item for item in FRAMING_REFUSALS if item.id == "input-buffer-overrun")

    session.record(Refused(row, "a terminator inside the bound; got neither", ""))

    assert session.instrument.read_event_status() == DEVICE_ERROR_BIT


def test_a_queue_with_no_room_still_raises_the_bit_for_the_error_it_dropped(
    shallow: Profile,
) -> None:
    """The register and the queue are independent, and this is where it shows.

    The queue is two deep and three command errors arrive. The third is dropped
    and becomes the overflow entry, so the queue can no longer say a third
    command error happened. The register still says one did, and it says the
    queue overflowed as well, which is a device-dependent error in its own
    right.
    """
    session = Session(shallow, seed=1)

    for _ in range(3):
        session.deliver("TRIG:SOUR IMM")

    assert session.instrument.read_event_status() == COMMAND_ERROR_BIT | DEVICE_ERROR_BIT
    assert session.instrument.errors.entries[-1].number == QUEUE_OVERFLOW_NUMBER


def test_the_status_byte_moves_as_the_masks_move_over_one_event(session: Session) -> None:
    """Leg two of the issue: the same event, three masks, three status bytes.

    Nothing between the reads changes the event status register, and the enable
    masks are the only thing that moves, so a status byte that was stored rather
    than computed would answer the same number three times.
    """
    session.deliver("TRIG:SOUR IMM")

    assert status_byte(session) == 0

    session.deliver(f"*ESE {COMMAND_ERROR_MASK}")
    assert status_byte(session) == EVENT_SUMMARY_BIT

    session.deliver(f"*SRE {EVENT_SUMMARY_MASK}")
    assert status_byte(session) == EVENT_SUMMARY_BIT | MASTER_SUMMARY_BIT


def test_the_message_available_bit_is_set_by_a_query_and_gone_once_it_is_read(
    session: Session,
) -> None:
    """Leg four: the answer of an earlier query in the same message is waiting.

    Three status bytes over one connection. The first has nothing in front of
    it. The second runs after `*IDN?` in the same message, so the
    identification is in the output queue when it is computed. The third runs in
    a message of its own, after the client has been given both answers.
    """
    assert status_byte(session) == 0

    identification, byte = answers(session, "*IDN?;*STB?")
    assert identification == session.instrument.profile.identification
    assert int(byte) == MESSAGE_AVAILABLE_BIT

    assert status_byte(session) == 0


def test_the_master_summary_bit_is_computed_from_the_message_available_bit_too(
    session: Session,
) -> None:
    """Not only from the event summary bit, which is the ordering that is easy to
    get wrong: the master summary is every other summary bit through the service
    request mask, so it has to be computed after the bit an answer sets and not
    before it."""
    session.deliver(f"*SRE {MESSAGE_AVAILABLE_MASK}")

    _, byte = answers(session, "*IDN?;*STB?")

    assert int(byte) == MESSAGE_AVAILABLE_BIT | MASTER_SUMMARY_BIT


def test_clearing_the_status_does_not_throw_away_an_answer_already_produced(
    session: Session,
) -> None:
    """`*CLS` is about status data, and an answer is not status data.

    A client that sent this and got one answer back instead of two would be
    waiting for bytes the instrument had discarded, which is the failure that
    looks exactly like a hang.
    """
    identification, byte = answers(session, "*IDN?;*CLS;*STB?")

    assert identification == session.instrument.profile.identification
    assert int(byte) == MESSAGE_AVAILABLE_BIT


def test_the_output_queue_is_empty_once_the_message_that_filled_it_has_answered(
    session: Session,
) -> None:
    """What `take_output` promises, asserted where the status byte cannot see it."""
    session.deliver("*IDN?;*ESR?")

    assert session.instrument.output == []
    assert session.instrument.status_byte() == 0


def test_no_refusal_in_this_tree_is_a_query_error() -> None:
    """The disclosure in this file's docstring, as a check rather than a sentence.

    When this reddens, a refusal in the query error block has been added and the
    bit it raises now has an event. That is the good day rather than the bad
    one: raise the bit through it, prove it beside the other four, and take both
    this test and the paragraph above out together.
    """
    first, last, _ = next(row for row in ERROR_CLASSES if row[2] == QUERY_ERROR_BIT)
    produced = (*MESSAGE_REFUSALS, *EXECUTION_REFUSALS, *FRAMING_REFUSALS)

    assert [row.id for row in produced if first <= row.number <= last] == []


@pytest.mark.parametrize(("number", "bit"), [(first, bit) for first, _, bit in ERROR_CLASSES])
def test_the_first_number_of_each_class_raises_that_class_bit(number: int, bit: int) -> None:
    assert event_bit(number) == bit


@pytest.mark.parametrize(("number", "bit"), [(last, bit) for _, last, bit in ERROR_CLASSES])
def test_the_last_number_of_each_class_raises_that_class_bit(number: int, bit: int) -> None:
    """The other end of each block, because an off-by-one at this end is the
    mistake that makes `-199` a command error and `-200` one as well."""
    assert event_bit(number) == bit


def test_a_device_specific_number_is_a_device_dependent_error() -> None:
    """The positive numbers `0006` leaves to a profile, which is where #38's
    quirks will produce theirs."""
    assert event_bit(FIRST_DEVICE_SPECIFIC_NUMBER) == DEVICE_ERROR_BIT


def test_a_number_in_no_class_raises_no_bit() -> None:
    """The no-error entry is the only number in this tree that is in no class,
    and nothing records it, so this is asserted here rather than through an
    event."""
    assert event_bit(0) == 0


def test_recording_an_entry_puts_it_in_both_places(shallow: Profile) -> None:
    """`Instrument.record` is the one door, asserted on the object itself.

    The entry the caller handed over is in the queue and the bit its number
    names is in the register, from one call. Two calls at every site would be
    two chances to make one of them.
    """
    instrument = Instrument(shallow)

    instrument.record(Entry(-222, "Data out of range", "a value from 0.1 to 1000"))

    assert instrument.event_status == EXECUTION_ERROR_BIT
    assert instrument.errors.take().number == -222
