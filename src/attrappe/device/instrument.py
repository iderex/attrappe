"""The instrument a session talks to: its settings, its reset, its registers.

    from attrappe.device import Instrument
    from attrappe.profile import load_profile

    instrument = Instrument(load_profile(Path("profiles/bench-multimeter")))

Everything a message can change lives here, and the message language lives in
`attrappe.scpi`. The split is what keeps the dispatch from being the only place
that knows what a setting is: a reset, a status byte and a self-test are things
the instrument does, and a caller that is not a parsed message can ask for them.

## Settings are stored per instance, and only once written

A node declares how many instances of itself exist, and a numeric suffix selects
among them, so `ROUTe2:CHANnel3` and `ROUTe1:CHANnel3` are two settings and not
one. The store is keyed by the walked path, which carries a suffix per mnemonic,
and a key that was never written reads as the parameter's declared default. That
is why nothing enumerates the instances: a node declaring two hundred channels
would otherwise cost two hundred entries before a client had said anything.

It is also what makes the reset one line. `*RST` drops every entry whose
parameter does not survive a reset, and the next read of that setting comes back
to the default because nothing was written since.

## What the registers hold, and what sets each bit

The event status register, its enable mask and the service request enable mask
are real 8-bit registers here, and the status byte is computed from them at the
moment it is read rather than stored. `*ESR?` answers and clears, which is the
behaviour that makes a polling loop order-dependent.

Four of the bits are raised by errors, and which one an error raises is read off
its number rather than out of a table beside it. The error classes occupy blocks
of numbers, `docs/decisions/0006-conformance-surface.md` lists the numbers in
their blocks, and `event_bit` below is that arithmetic. A table would be a second
place to add a row to, and a refusal added with no row would raise nothing while
still reaching the queue.

`record` is the one door: it pushes the entry into the queue and raises the bit
for the same error, so a refusal that reached a client through `SYSTem:ERRor?`
and a refusal that reached it through `*ESR?` are the same refusal. The queue and
the register are still independent of each other. A queue that has no room drops
the entry and the bit is raised anyway, because the event happened; and the drop
itself is a device-dependent error, so the full queue raises that bit too.

Operation complete is not an error and is not wired from elsewhere: `*OPC` sets
its own bit, which is the whole of what that command does.
`docs/decisions/0006-conformance-surface.md` records that this emulator has no
overlapped commands, so an operation is complete when the command that started it
returns.

## The output queue, and what the message-available bit is about

Answers go into `output` as each query produces one, and the message that carried
them takes the lot at the end. So the bit is set for a query that runs after
another query in the same message and clear once the answers have been handed
over, which is the order dependence worth reproducing: `*IDN?;*STB?` and `*IDN?`
followed by `*STB?` are two different status bytes.

What this does not model is a client that has been sent an answer and has not
read it off its socket yet. The bit says the emulator is holding an answer, not
that the operating system is. A device on a bus holds its answer until the
controller addresses it to talk; this surface is a stream socket, the answer is
written as soon as the message ends, and `docs/decisions/0002-transport.md` takes
that surface and no other.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from attrappe.device.errors import QUEUE_OVERFLOW_NUMBER, Entry, ErrorQueue
from attrappe.profile import Node, Parameter, Profile

# A walked header path: one long-form mnemonic and its numeric suffix per step.
# The same shape `attrappe.scpi.parser` produces, so a dispatched command is the
# key without a conversion in between.
Instance = tuple[tuple[str, int], ...]

# The event status register, by the bit each condition owns. The numbers are the
# message-level standard's and are the same on every instrument that carries the
# register, which is why a driver switches on them.
OPERATION_COMPLETE_BIT = 1 << 0
QUERY_ERROR_BIT = 1 << 2
DEVICE_ERROR_BIT = 1 << 3
EXECUTION_ERROR_BIT = 1 << 4
COMMAND_ERROR_BIT = 1 << 5

# The status byte. The message-available bit reads the output queue below, and
# the two summary bits are computed through the enable masks.
MESSAGE_AVAILABLE_BIT = 1 << 4
EVENT_SUMMARY_BIT = 1 << 5
MASTER_SUMMARY_BIT = 1 << 6

# The blocks of error numbers the four error classes occupy, first and last
# inclusive, in the order `event_bit` asks them. They are the message-level
# standard's blocks and they are what
# `docs/decisions/0006-conformance-surface.md` lists its numbers inside, so a
# refusal added under any number that record already covers raises its bit
# without a line being added here.
ERROR_CLASSES: tuple[tuple[int, int, int], ...] = (
    (-199, -100, COMMAND_ERROR_BIT),
    (-299, -200, EXECUTION_ERROR_BIT),
    (-399, -300, DEVICE_ERROR_BIT),
    (-499, -400, QUERY_ERROR_BIT),
)

# The smallest device-specific error number. `0006` says a profile may add error
# numbers of its own, "which are the positive ones and the ones outside the
# published table", and every one of them is a device-dependent error because
# the standard's own classes are the negative blocks above.
FIRST_DEVICE_SPECIFIC_NUMBER = 1


# Both enable registers are eight bits wide. A wider value is not a register
# this instrument has, and accepting one would leave a driver believing it had
# enabled something.
REGISTER_MINIMUM = 0
REGISTER_MAXIMUM = 255

# What `*TST?` answers. Zero is pass, and every non-zero value is a device's own
# code for what failed. Nothing here fails: there is no hardware to test and no
# self-test model, so a profile that wants a failing self-test gets one as a
# quirk in #38 rather than as a setting the core reads.
SELF_TEST_PASSED = 0


def event_bit(number: int) -> int:
    """The event status bit one error number raises, or zero for no bit at all.

    Zero is the answer for a number in none of the classes, which is the
    no-error entry and nothing else this tree produces. It is a bit rather than
    a refusal because the caller is recording an error, and a crash there would
    lose the entry as well as the bit.
    """
    for first, last, bit in ERROR_CLASSES:
        if first <= number <= last:
            return bit
    if number >= FIRST_DEVICE_SPECIFIC_NUMBER:
        return DEVICE_ERROR_BIT
    return 0


@dataclass
class Instrument:
    """One instrument's state: its profile, its settings and its registers.

    One of these per session. Two clients on one listener get two of them, which
    is what `docs/decisions/0002-transport.md` means by a session owning its own
    instrument state, and it is why nothing in this class is a class attribute.
    """

    profile: Profile
    settings: dict[tuple[Instance, str], object] = field(default_factory=dict)
    event_status: int = 0
    event_status_enable: int = 0
    service_request_enable: int = 0
    output: list[str] = field(default_factory=list)
    errors: ErrorQueue = field(init=False)
    _nodes: dict[tuple[str, ...], Node] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._nodes = {node.path: node for node in self.profile.nodes()}
        self.errors = ErrorQueue(self.profile.error_queue_depth)

    def node_at(self, path: tuple[str, ...]) -> Node | None:
        """The node a header resolved to, or None when the tree has no such path."""
        return self._nodes.get(path)

    def value(self, instance: Instance, parameter: Parameter) -> object:
        """What a setting reads as: what was written, or the declared default."""
        return self.settings.get((instance, parameter.name), parameter.default)

    def write(self, instance: Instance, parameter: Parameter, value: object) -> None:
        """Write one setting on one instance of its node."""
        self.settings[(instance, parameter.name)] = value

    def reset(self) -> None:
        """`*RST`: back to the declared defaults, except the declared survivors.

        Dropping the entry rather than writing the default back is what keeps
        the two paths to a default identical. Writing it back would leave a
        setting that was reset distinguishable from one that was never touched,
        and the distinction has no meaning to anything reading it.

        The registers are untouched. `*RST` is about the device's settings and
        `*CLS` is about its status data, and an instrument that cleared the
        service request enable mask on a reset would silence a driver that
        armed it before configuring anything.
        """
        survivors = {
            (node.path, parameter.name)
            for node in self._nodes.values()
            for parameter in node.parameters
            if parameter.survives_reset
        }
        self.settings = {
            (instance, name): value
            for (instance, name), value in self.settings.items()
            if (tuple(mnemonic for mnemonic, _ in instance), name) in survivors
        }

    def clear_status(self) -> None:
        """`*CLS`: clear the event status register and empty the error queue.

        The enable masks are not cleared, because clearing them is what `*ESE 0`
        and `*SRE 0` are for and a driver that armed them expects them to stay
        armed. The queue is cleared here and not by `*RST`: a reset is about the
        device's settings and this command is about its status data, and the
        errors are status data.

        The output queue is left alone, which is the same distinction one step
        further: an answer already produced is not status data, and discarding
        it would leave a client that sent `*IDN?;*CLS` waiting for a response
        the instrument had thrown away.
        """
        self.event_status = 0
        self.errors.clear()

    def record(self, entry: Entry) -> None:
        """Record one error: into the queue, and into the event status register.

        The one door for both, so a refusal cannot reach a client through
        `SYSTem:ERRor?` and be absent from `*ESR?`. Which bit it raises is read
        off the number by `event_bit` rather than chosen by the caller, because
        the caller that produced a refusal knows its number and should not also
        have to know its class.

        The bit is raised whether or not the queue had room. The event happened;
        the queue only says whether there was somewhere to write it down. A full
        queue raises the device-dependent bit as well, because the overflow it
        records is itself an error in that class.
        """
        self.set_event_status(event_bit(entry.number))
        if self.errors.push(entry):
            self.set_event_status(event_bit(QUEUE_OVERFLOW_NUMBER))

    def read_event_status(self) -> int:
        """`*ESR?`: answer the register and clear it.

        Clearing on read is the behaviour that makes a polling loop subtly
        order-dependent, and reproducing that order dependence is the point
        rather than a side effect.
        """
        register, self.event_status = self.event_status, 0
        return register

    def set_event_status(self, bit: int) -> None:
        """Raise one bit of the event status register."""
        self.event_status |= bit

    def answer(self, response: str) -> None:
        """Put one query's answer in the output queue, where it waits to be read."""
        self.output.append(response)

    def take_output(self) -> tuple[str, ...]:
        """Every answer waiting, in the order they were produced, and empty after.

        A tuple rather than one joined string, because what joins two answers is
        the message separator and that belongs to the message language rather
        than to the instrument. Handing back the pieces is what keeps this
        module from having to know it.
        """
        answers, self.output = tuple(self.output), []
        return answers

    def status_byte(self) -> int:
        """`*STB?`: computed at the moment it is read, never stored.

        The message-available bit is the output queue holding something. The
        event summary bit is the event status register through its enable mask.
        The master summary bit is every other summary bit through the service
        request enable mask, so it is computed after the other two and never
        before. Reading the status byte does not clear anything, which is what
        separates it from `*ESR?`.
        """
        byte = 0
        if self.output:
            byte |= MESSAGE_AVAILABLE_BIT
        if self.event_status & self.event_status_enable:
            byte |= EVENT_SUMMARY_BIT
        if byte & self.service_request_enable:
            byte |= MASTER_SUMMARY_BIT
        return byte

    def self_test(self) -> int:
        """`*TST?`: zero, which is pass."""
        return SELF_TEST_PASSED
