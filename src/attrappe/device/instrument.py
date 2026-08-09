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

## What the registers hold, and what they do not hold yet

The event status register, its enable mask and the service request enable mask
are real 8-bit registers here, and the status byte is computed from them at the
moment it is read rather than stored. `*ESR?` answers and clears, which is the
behaviour that makes a polling loop order-dependent.

The bits are not yet set by the events that cause them. A command error, an
execution error, a device-dependent error and a query error each own a bit, and
nothing in this module sets any of them: the errors are produced by the dispatch
and recorded by the error queue, and wiring the events to the bits is #24. The
message-available bit is the same case one step further out, because there is no
output buffer to be available from until the session in #26 exists. Both are
absences rather than approximations: the register answers zero for a bit nothing
has set, which is what it should answer, and it will answer one when #24 sets
it.

Operation complete is the exception, and it is not an event wired from
elsewhere: `*OPC` sets its own bit, which is the whole of what that command
does. `docs/decisions/0006-conformance-surface.md` records that this emulator has
no overlapped commands, so an operation is complete when the command that
started it returns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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

# The status byte. The message-available bit is named here and never set, for
# the reason the module docstring gives: there is no output buffer yet.
MESSAGE_AVAILABLE_BIT = 1 << 4
EVENT_SUMMARY_BIT = 1 << 5
MASTER_SUMMARY_BIT = 1 << 6

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
    _nodes: dict[tuple[str, ...], Node] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._nodes = {node.path: node for node in self.profile.nodes()}

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
        """`*CLS`: clear the event status register.

        The enable masks are not cleared, because clearing them is what `*ESE 0`
        and `*SRE 0` are for and a driver that armed them expects them to stay
        armed. The error queue is cleared by this command as well and is not
        here to clear: it is #23's, and this method is where that lands.
        """
        self.event_status = 0

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

    def status_byte(self) -> int:
        """`*STB?`: computed at the moment it is read, never stored.

        The event summary bit is the event status register through its enable
        mask, and the master summary bit is every other summary bit through the
        service request enable mask. Reading the status byte does not clear
        anything, which is what separates it from `*ESR?`.

        The message-available bit is not set by anything yet, for the reason the
        module docstring gives, so a driver polling for a response to arrive
        polls forever against this emulator until #24 and #26 land. That is a
        gap rather than a wrong answer: nothing here produces the buffered
        response the bit would be about.
        """
        byte = 0
        if self.event_status & self.event_status_enable:
            byte |= EVENT_SUMMARY_BIT
        if byte & self.service_request_enable:
            byte |= MASTER_SUMMARY_BIT
        return byte

    def self_test(self) -> int:
        """`*TST?`: zero, which is pass."""
        return SELF_TEST_PASSED
