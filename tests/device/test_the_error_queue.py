"""The error queue: its order, its depth, its overflow, and what reaches it.

Three groups, and they prove different things.

The first drives the queue object directly, because order, depth and overflow
are properties of the queue and a message in front of them would only make the
assertions longer. The second drives it through the wire, because
`SYSTem:ERRor?` reading the queue and `*CLS` emptying it are properties of the
commands rather than of the queue.

The third is the one the issue this file closes exists for. It asserts that
every refusal either stage can produce ends up in the queue, and it is driven
from the two refusal tables rather than from a list of numbers written here: the
messages below are keyed by the id of the row each one provokes, and a test
asserts those keys are exactly the two tables' ids. So a refusal added to either
table with nothing that provokes it turns this file red, which is what stops the
queue from being the place half the errors are recorded.

The numbers the queue produces itself, the no-error entry and the overflow
entry, are read out of `docs/decisions/0006-conformance-surface.md` rather than
transcribed here a second time.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from attrappe.device import (
    NO_ERROR,
    QUEUE_OVERFLOW,
    Entry,
    ErrorQueue,
    Instrument,
)
from attrappe.profile import Profile, load_profile
from attrappe.scpi import Dispatch, Outcome, queue_entry
from attrappe.scpi.dispatch import REFUSALS as EXECUTION_REFUSALS
from attrappe.scpi.parser import REFUSALS as MESSAGE_REFUSALS

INSTRUMENT_PROFILE = Path(__file__).parents[1] / "scpi" / "fixtures" / "instrument"
QUEUE_PROFILE = Path(__file__).parent / "fixtures" / "queue"
RECORD = Path(__file__).parents[2] / "docs" / "decisions" / "0006-conformance-surface.md"

# The depth the shallow fixture declares. Read off the loaded profile in the
# tests rather than compared against this, which is here so a reader knows why
# three messages are enough to overflow it.
SHALLOW_DEPTH = 2

# A line of the record's error table: the number and the standard message.
ERROR_LINE = re.compile(r"^(-?\d+)\s\s+(\S.*)$")

# One message per refusal row, keyed by the row's id, read against the
# instrument fixture. Each provokes exactly one refusal, so what lands in the
# queue is unambiguous; the spellings are the ones the parser's and the
# dispatch's own tables use, because a provocation invented here would be a
# third opinion about what those rows mean.
PROVOCATION: dict[str, str] = {
    # The parser's table: a message refused for its form.
    "invalid-character": "SE$NS:VOLT 1",
    "syntax-error": "SENS::VOLT 1",
    "invalid-separator": "ROUT:CHAN 1 2",
    "undefined-header": "TRIG:SOUR IMM",
    "header-suffix-out-of-range": "ROUT:CHAN0",
    "numeric-data-error": "ROUT:CHAN 1.2.3",
    "invalid-suffix": "SENS:VOLT:DC:RANG 10V2",
    # The dispatch's table: a command refused for its fit.
    "parameter-not-allowed": "SENS:VOLT:DC:RANG? 1",
    "missing-parameter": "CONF:VOLT:DC 100",
    "header-is-not-a-command": "SENS",
    "suffix-above-the-instances": "ROUT:CHAN5?",
    "numeric-data-not-allowed": "DISP:TEXT 5",
    "suffix-not-allowed": "SENS:VOLT:DC:NPLC 1 S",
    "suffix-is-not-the-declared-unit": "SENS:VOLT:DC:RANG 100 A",
    "character-data-not-allowed": "DISP:TEXT HELLO",
    "string-data-not-allowed": 'SENS:VOLT:DC "ON"',
    "data-out-of-range": "SENS:VOLT:DC:RANG 2000",
    "illegal-parameter-value": "SENS:FUNC POWER",
}

REFUSALS_BY_ID = {row.id: row for row in (*MESSAGE_REFUSALS, *EXECUTION_REFUSALS)}


@pytest.fixture
def dispatch() -> Dispatch:
    """The dispatch fixture's instrument, whose queue is sixteen deep."""
    return Dispatch.for_instrument(Instrument(load_profile(INSTRUMENT_PROFILE)))


@pytest.fixture
def shallow() -> Profile:
    """A profile declaring a queue two entries deep, for the overflow."""
    return load_profile(QUEUE_PROFILE)


def entry(number: int) -> Entry:
    """One entry, distinguishable from its neighbours by its detail."""
    return Entry(number, "Undefined header", f"entry {number}")


def refused_as_queued(outcome: Outcome) -> str:
    """What the queue will answer for the one refusal a message produced.

    Built from the refusal itself rather than pasted as a string, because the
    property is that the queue answers the refusal that happened, and a literal
    here would be a second opinion about how a refusal reads.
    """
    (refusal,) = outcome.errors
    return str(queue_entry(refusal))


def read_the_error_table() -> dict[int, str]:
    """The record's error table, as the standard message per number."""
    table: dict[int, str] = {}
    for line in RECORD.read_text(encoding="utf-8").splitlines():
        match = ERROR_LINE.match(line.strip())
        if match is not None:
            table[int(match.group(1))] = match.group(2).strip()
    return table


def test_the_two_entries_the_queue_produces_are_the_record_s() -> None:
    """Read out of the record rather than agreeing with the module a second time.

    `0006` fixes both numbers and both messages. A queue answering `0,"OK"` on
    an empty read would satisfy every other test in this file and would be a
    string no driver matches.
    """
    table = read_the_error_table()

    assert table, "no error table was found in the record"
    assert table[NO_ERROR.number] == NO_ERROR.message
    assert table[QUEUE_OVERFLOW.number] == QUEUE_OVERFLOW.message


def test_reading_an_empty_queue_answers_the_no_error_entry() -> None:
    queue = ErrorQueue(depth=4)

    assert queue.count == 0
    assert queue.take() == NO_ERROR


def test_entries_come_back_in_the_order_they_happened() -> None:
    queue = ErrorQueue(depth=4)

    for number in (-101, -102, -103):
        queue.push(entry(number))

    assert queue.count == 3
    assert [queue.take().number for _ in range(3)] == [-101, -102, -103]
    assert queue.take() == NO_ERROR


def test_a_full_queue_replaces_its_last_entry_with_the_overflow_entry() -> None:
    """The oldest entries survive and the newest is the statement that they stopped.

    Dropping the oldest instead would be the other reasonable-looking choice and
    it is the wrong one: the first mistake is the one that caused the rest, and
    it is the entry a client most needs.
    """
    queue = ErrorQueue(depth=SHALLOW_DEPTH)

    for number in (-101, -102, -103, -104):
        queue.push(entry(number))

    assert queue.count == SHALLOW_DEPTH
    assert queue.entries[0] == entry(-101)
    assert queue.entries[-1] == QUEUE_OVERFLOW


def test_a_queue_that_overflowed_does_not_grow_past_its_depth() -> None:
    """Five hundred errors after the queue filled leave the same two entries."""
    queue = ErrorQueue(depth=SHALLOW_DEPTH)

    for number in range(-500, 0):
        queue.push(entry(number))

    assert queue.count == SHALLOW_DEPTH


def test_clearing_empties_the_queue() -> None:
    queue = ErrorQueue(depth=4)
    queue.push(entry(-101))

    queue.clear()

    assert queue.count == 0
    assert queue.take() == NO_ERROR


def test_a_queue_holding_no_entries_at_all_is_refused() -> None:
    """A depth of zero is not a shallow queue, it is an absent one.

    The loader refuses a profile declaring it, and this is the same bound for a
    queue a caller built without going through a profile. Without it the first
    push onto such a queue would fail on an empty list, which is a crash rather
    than an answer.
    """
    with pytest.raises(ValueError, match="at least"):
        ErrorQueue(depth=0)


def test_an_entry_renders_with_its_detail_and_without_one() -> None:
    """The form a client reads, which is the form the two refusal types render in."""
    assert str(NO_ERROR) == '0,"No error"'
    assert str(Entry(-113, "Undefined header", "MEAS")) == '-113,"Undefined header; MEAS"'


def test_the_error_query_answers_the_no_error_entry_on_a_fresh_instrument(
    dispatch: Dispatch,
) -> None:
    assert dispatch.execute("SYST:ERR?").response == str(NO_ERROR)


def test_the_two_spellings_of_the_error_query_are_one_command(dispatch: Dispatch) -> None:
    """`SYSTem:ERRor?` and `SYSTem:ERRor:NEXT?` are the record's `[:NEXT]`.

    Asserted by the second spelling draining what the first left, rather than by
    both answering the same string, which they would also do if one of them
    quietly answered from nothing.
    """
    undefined = refused_as_queued(dispatch.execute("TRIG:SOUR IMM"))
    illegal = refused_as_queued(dispatch.execute("SENS:FUNC POWER"))

    assert dispatch.execute("SYSTEM:ERROR:NEXT?").response == undefined
    assert dispatch.execute("SYST:ERR?").response == illegal
    assert dispatch.execute("SYST:ERR:NEXT?").response == str(NO_ERROR)


def test_the_count_query_answers_the_depth_without_removing_anything(
    dispatch: Dispatch,
) -> None:
    dispatch.execute("TRIG:SOUR IMM")
    dispatch.execute("SENS:FUNC POWER")

    assert dispatch.execute("SYST:ERR:COUN?").response == "2"
    assert dispatch.execute("SYST:ERR:COUN?").response == "2"


def test_clear_status_empties_the_queue_and_reset_does_not(dispatch: Dispatch) -> None:
    """`*CLS` is about status data and the errors are status data. `*RST` is not.

    An instrument that emptied the queue on a reset would lose the errors a
    driver made while configuring it, which is exactly when it made them.
    """
    dispatch.execute("TRIG:SOUR IMM")

    assert dispatch.execute("*RST;SYST:ERR:COUN?").response == "1"
    assert dispatch.execute("*CLS;SYST:ERR:COUN?").response == "0"


def test_a_refusal_earlier_in_a_message_is_readable_later_in_the_same_message(
    dispatch: Dispatch,
) -> None:
    """The order a real instrument answers in: units run in the order they arrive.

    A dispatch that queued everything after the message finished would answer
    the no-error entry here, and a driver appending `SYST:ERR?` to every command
    it sends, which is the ordinary way of using an error queue, would be told
    every message was clean.
    """
    outcome = dispatch.execute("TRIG:SOUR IMM;SYST:ERR?")

    assert outcome.response == refused_as_queued(outcome)
    assert dispatch.instrument.errors.count == 0


def test_the_queue_takes_its_depth_from_the_profile(shallow: Profile) -> None:
    """Two profiles, two depths, and the overflow arrives where each one declares.

    Asserted through the wire rather than on the queue object, because the depth
    being loaded and the depth being used are two different facts and the loader
    already proves the first.
    """
    instrument = Instrument(shallow)

    assert instrument.errors.depth == shallow.error_queue_depth == SHALLOW_DEPTH

    dispatch = Dispatch.for_instrument(instrument)
    refused = [dispatch.execute("TRIG:SOUR IMM") for _ in range(SHALLOW_DEPTH + 1)]

    assert dispatch.execute("SYST:ERR:COUN?").response == str(SHALLOW_DEPTH)
    assert dispatch.execute("SYST:ERR?").response == refused_as_queued(refused[0])
    assert dispatch.execute("SYST:ERR?").response == str(QUEUE_OVERFLOW)


def test_a_profile_declaring_its_own_system_subsystem_keeps_it(shallow: Profile) -> None:
    """The core's subsystem and the profile's coexist under one `SYSTem` root.

    The fixture declares `SYSTem:BEEPer` on purpose. A vocabulary that put the
    profile's roots and the core's side by side instead of merging them would
    hold two `SYSTem` nodes, and the walk takes the first, so one of these two
    assertions would fail with an undefined header on a command the instrument
    declares.
    """
    dispatch = Dispatch.for_instrument(Instrument(shallow))

    assert dispatch.execute("SYST:BEEP 1;:SYST:BEEP?").response == "1"
    assert dispatch.execute("SYST:ERR:COUN?").response == "0"


def test_every_refusal_either_stage_produces_has_a_message_that_provokes_it() -> None:
    """The keys are the two tables, so a new row with no provocation is red.

    This is what makes the test below a statement about the tables rather than
    about the eighteen messages somebody happened to write.
    """
    assert set(PROVOCATION) == set(REFUSALS_BY_ID)


@pytest.mark.parametrize("identifier", sorted(PROVOCATION), ids=lambda name: name)
def test_every_refusal_either_stage_produces_reaches_the_queue(
    identifier: str, dispatch: Dispatch
) -> None:
    """One refusal in, one entry out, with the number the table declares.

    Both stages are covered by one parametrisation because the queue does not
    distinguish them, and a client reading it cannot either: a queue holding the
    dispatch's refusals and not the parser's is a queue that reads as a clean
    run to every driver that made a syntax error.
    """
    row = REFUSALS_BY_ID[identifier]
    outcome = dispatch.execute(PROVOCATION[identifier])

    assert [error.refusal.id for error in outcome.errors] == [identifier]
    assert [held.number for held in dispatch.instrument.errors.entries] == [row.number]
    assert dispatch.instrument.errors.take() == Entry(
        row.number, row.message, outcome.errors[0].detail
    )
