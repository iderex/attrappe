"""Walk a parsed command into the tree, run it, and answer or refuse by number.

    from attrappe.device import Instrument
    from attrappe.scpi import Dispatch

    dispatch = Dispatch.for_instrument(Instrument(profile))
    outcome = dispatch.execute("*IDN?")

`attrappe.scpi.parser` decides whether a message is well formed. This decides
whether a well-formed command means anything on this instrument: whether the
header is a command rather than a branch it stops halfway down, whether the
suffix names an instance that exists, whether the parameters are of the declared
types, and whether each one is inside its declared range.

## The two tables, and why the numbers are split across them

The parser refuses a message for its FORM and this refuses one for its FIT, and
`docs/decisions/0006-conformance-surface.md` fixes both sets of numbers. The
parser's own docstring names the six it leaves here for exactly this reason:
`-108`, `-109`, `-128`, `-138`, `-148` and `-158` are all answers about a
parameter measured against the command it was sent to, and the parser has no
command to measure against.

`REFUSALS` below is this module's half. Two numbers appear in both tables,
`-113` and `-114`, under different ids and for different cases: the parser
refuses a header no node answers to and a suffix below one, and this refuses a
header stopping on a branch and a suffix above the instances a node declares. A
number is the record's; a case belongs to the site that produces it.

## What a message comes to

`execute` answers an `Outcome`. Its `response` is the answers of every query in
the message joined by the message separator, or None when nothing answered,
which is the "either a response string or nothing" the dispatch owes.

Two separators are in play and they are not the same one. Several queries in one
message are joined by the semicolon that separated them, which is fixed by the
language; several values inside one query's answer are joined by the separator
the profile declares, because that one is the device's. Collapsing the two would
put commas between the answers of two queries, and a driver splitting the reply
of `CONF:VOLT:DC?;*IDN?` on commas would then read six values where there are
two answers.

`errors` carries the parser's refusals first and this module's after them,
because `parse` reports the two as separate lists and the interleaving is not
recoverable from what it answers.

A refused unit produces no response bytes at all. That is what makes a query for
a missing command look to a driver exactly like it looks against a real
instrument: the client waits, the read times out, and nothing arrives.

## Every refusal reaches the error queue, and it reaches it here

`execute` pushes each refusal into the instrument's queue as it happens, which
is what makes the queue the one place an error is recorded rather than one of
two places an error might be recorded. The parser's refusals go in first,
because a message is read before any of its units runs, and each unit's own
refusal goes in when that unit is reached. So `MEAS:XYZ?;SYST:ERR?` answers with
the undefined header the first unit produced, in the order a real instrument
answers it.

The queue is on the instrument rather than on this dispatch because `*CLS`
empties it and the instrument is what `*CLS` acts on, and because a session's
errors belong to its instrument for the same reason its settings do.

`SYSTem:ERRor[:NEXT]?` and `SYSTem:ERRor:COUNt?` are the part of `0006`'s
mandatory system subsystem that reads the queue, and they are implemented here
as core nodes grafted into the vocabulary rather than as something a profile
declares. `SYSTem:VERSion?` is the third member of that subsystem and is not
here: it answers a command-language version, which is a statement about
conformance rather than a read of the queue, and nothing in this tree or in any
profile declares one.

## What this does not do yet, named rather than approximated

The refusals do not set the event status bits, which is #24 along with the
message-available bit and the operation-complete query that waits for a running
integration.

A query takes no parameters here. A real instrument accepts `MIN`, `MAX` and
`DEF` on many of them and answers the declared bound instead of the current
value; this answers `-108` instead, which is a documented gap in the subset
`0006` declares rather than a wrong answer to a form this accepts.

A setting reads back in the shortest decimal form that round-trips, not in the
fixed-width exponent form a bench instrument uses. The exact string shape a
device produces is #32's, and inventing one here would be a second answer for
that issue to disagree with.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from attrappe.device import (
    OPERATION_COMPLETE_BIT,
    REGISTER_MAXIMUM,
    REGISTER_MINIMUM,
    Entry,
    Instance,
    Instrument,
)
from attrappe.profile import Node, Parameter
from attrappe.scpi.parser import (
    MESSAGE_SEPARATOR,
    CharacterValue,
    Command,
    NamedValue,
    NumericValue,
    ParseError,
    Refusal,
    StringValue,
    Value,
    Vocabulary,
    parse,
)

# The character data a boolean parameter accepts, beyond the numbers one and
# zero. A device that took only the numbers would refuse the spelling every
# driver writes.
BOOLEAN_WORDS = {"ON": True, "OFF": False}

# The named values, in the long forms `attrappe.scpi.parser` resolves them to.
MINIMUM = "MINIMUM"
MAXIMUM = "MAXIMUM"
DEFAULT = "DEFAULT"

# The numbers and the standard messages are
# `docs/decisions/0006-conformance-surface.md`'s and are not re-decided here.
# What each row adds is the case: which shape of command this dispatch answers
# with that number.
REFUSALS: tuple[Refusal, ...] = (
    Refusal(
        id="parameter-not-allowed",
        number=-108,
        message="Parameter not allowed",
        case="more parameters than the command declares, and any parameter at all on a query",
    ),
    Refusal(
        id="missing-parameter",
        number=-109,
        message="Missing parameter",
        case="fewer parameters than the command declares",
    ),
    Refusal(
        id="header-is-not-a-command",
        number=-113,
        message="Undefined header",
        case="a header that resolves to a node the profile declares, in a form that node "
        "does not accept: a branch a header stopped on, a query on a set-only node, or a "
        "command form of a query-only node",
    ),
    Refusal(
        id="suffix-above-the-instances",
        number=-114,
        message="Header suffix out of range",
        case="a numeric suffix above the number of instances the node declares",
    ),
    Refusal(
        id="numeric-data-not-allowed",
        number=-128,
        message="Numeric data not allowed",
        case="a number where the parameter declares character or string data",
    ),
    Refusal(
        id="suffix-not-allowed",
        number=-138,
        message="Suffix not allowed",
        case="a unit suffix on a parameter that declares no units",
    ),
    Refusal(
        id="suffix-is-not-the-declared-unit",
        number=-131,
        message="Invalid suffix",
        case="a well-formed unit suffix that is not the unit the parameter declares",
    ),
    Refusal(
        id="character-data-not-allowed",
        number=-148,
        message="Character data not allowed",
        case="character data where the parameter declares a number or a string, and "
        "MIN or MAX on a parameter that has no numeric range to take them from",
    ),
    Refusal(
        id="string-data-not-allowed",
        number=-158,
        message="String data not allowed",
        case="a quoted string where the parameter declares something else",
    ),
    Refusal(
        id="data-out-of-range",
        number=-222,
        message="Data out of range",
        case="a number outside the parameter's declared minimum and maximum, and an "
        "enable-register value outside the eight bits the register has",
    ),
    Refusal(
        id="illegal-parameter-value",
        number=-224,
        message="Illegal parameter value",
        case="character data that is not one of the choices the parameter declares",
    ),
)

BY_ID: dict[str, Refusal] = {refusal.id: refusal for refusal in REFUSALS}


@dataclass(frozen=True)
class Refused:
    """One refusal from the dispatch, with the unit it came from and the detail.

    The same shape as the parser's `ParseError` and deliberately a separate
    type: one is a statement about a message, the other a statement about a
    command, and a caller looking at a list of both can tell which stage refused
    without reading the detail. Both render as the number and the message, which
    is the form the error queue in #23 holds.
    """

    refusal: Refusal
    detail: str
    unit: str

    @property
    def number(self) -> int:
        return self.refusal.number

    def __str__(self) -> str:
        return f'{self.refusal.number},"{self.refusal.message}; {self.detail}"'


# What a message can be refused by: the parser's stage and this one. The error
# queue takes this union rather than one of the two, because a queue holding
# only half the refusals is a queue a driver reads as a clean run.
Error = ParseError | Refused


def queue_entry(error: Error) -> Entry:
    """The error queue entry one refusal becomes.

    One function rather than a method on each of the two refusal types, because
    the transport produces refusals of its own for bytes that never reached a
    parser and it converts them through this as well. Three call sites building
    an entry each would be three chances to drop the detail.
    """
    return Entry(error.refusal.number, error.refusal.message, error.detail)


@dataclass(frozen=True)
class Outcome:
    """What a message came to: the bytes to send back, and what was refused."""

    response: str | None = None
    errors: tuple[Error, ...] = ()


def refuse(identifier: str, detail: str, command: Command) -> Refused:
    """One refusal, keyed by the id of the row that carries its number."""
    return Refused(BY_ID[identifier], detail, command.source)


@dataclass(frozen=True)
class CommonCommand:
    """One of the common commands, and the two forms it answers to.

    `on_set` is the form with no question mark and `on_query` the form with one.
    A command carrying None for either refuses that form as an undefined header,
    which is what a real instrument does: `*IDN` without the mark is not the
    identification command with a missing response, it is not a command.
    """

    mnemonic: str
    summary: str
    on_set: Callable[[Dispatch, Command], Refused | None] | None = None
    on_query: Callable[[Dispatch, Command], str | Refused] | None = None


def _identification(dispatch: Dispatch, command: Command) -> str | Refused:
    return dispatch.instrument.profile.identification


def _reset(dispatch: Dispatch, command: Command) -> Refused | None:
    dispatch.instrument.reset()
    return None


def _clear_status(dispatch: Dispatch, command: Command) -> Refused | None:
    dispatch.instrument.clear_status()
    return None


def _set_event_status_enable(dispatch: Dispatch, command: Command) -> Refused | None:
    mask = _register_argument(command)
    if isinstance(mask, Refused):
        return mask
    dispatch.instrument.event_status_enable = mask
    return None


def _event_status_enable(dispatch: Dispatch, command: Command) -> str | Refused:
    return str(dispatch.instrument.event_status_enable)


def _event_status(dispatch: Dispatch, command: Command) -> str | Refused:
    return str(dispatch.instrument.read_event_status())


def _set_service_request_enable(dispatch: Dispatch, command: Command) -> Refused | None:
    mask = _register_argument(command)
    if isinstance(mask, Refused):
        return mask
    dispatch.instrument.service_request_enable = mask
    return None


def _service_request_enable(dispatch: Dispatch, command: Command) -> str | Refused:
    return str(dispatch.instrument.service_request_enable)


def _status_byte(dispatch: Dispatch, command: Command) -> str | Refused:
    return str(dispatch.instrument.status_byte())


def _operation_complete(dispatch: Dispatch, command: Command) -> Refused | None:
    dispatch.instrument.set_event_status(OPERATION_COMPLETE_BIT)
    return None


def _operation_complete_query(dispatch: Dispatch, command: Command) -> str | Refused:
    """Answers at once, because nothing here runs after the command that started it.

    `0006` records that this emulator has no overlapped commands. The query that
    waits for a running integration is #34's, and it arrives with the thing
    there is to wait for rather than as a wait over nothing.
    """
    return "1"


def _self_test(dispatch: Dispatch, command: Command) -> str | Refused:
    return str(dispatch.instrument.self_test())


def _wait(dispatch: Dispatch, command: Command) -> Refused | None:
    """Parses, does nothing, completes. `0006` writes this out rather than leaving
    it as a surprise: with no overlapped commands there is nothing to wait for,
    and that is the correct behaviour for a device with nothing outstanding."""
    return None


# The mandatory common set. `0006` fixes which commands are in it and which of
# the two forms each one answers to, and `tests/scpi/test_the_dispatch.py` reads
# that record and compares it with this tuple, so the set here cannot drift from
# the set there without the suite saying so.
COMMON: tuple[CommonCommand, ...] = (
    CommonCommand("IDN", "identification", on_query=_identification),
    CommonCommand("RST", "reset", on_set=_reset),
    CommonCommand("CLS", "clear status", on_set=_clear_status),
    CommonCommand(
        "ESE",
        "event status enable",
        on_set=_set_event_status_enable,
        on_query=_event_status_enable,
    ),
    CommonCommand("ESR", "event status register, query and clear", on_query=_event_status),
    CommonCommand(
        "SRE",
        "service request enable",
        on_set=_set_service_request_enable,
        on_query=_service_request_enable,
    ),
    CommonCommand("STB", "status byte", on_query=_status_byte),
    CommonCommand(
        "OPC",
        "operation complete",
        on_set=_operation_complete,
        on_query=_operation_complete_query,
    ),
    CommonCommand("TST", "self-test", on_query=_self_test),
    CommonCommand("WAI", "wait to continue", on_set=_wait),
)

MANDATORY_COMMON: frozenset[str] = frozenset(entry.mnemonic for entry in COMMON)
COMMON_BY_MNEMONIC: dict[str, CommonCommand] = {entry.mnemonic: entry for entry in COMMON}


def _error_next(dispatch: Dispatch, command: Command) -> str | Refused:
    """`SYSTem:ERRor?`: the oldest entry, removed, or the no-error entry."""
    return str(dispatch.instrument.errors.take())


def _error_count(dispatch: Dispatch, command: Command) -> str | Refused:
    """`SYSTem:ERRor:COUNt?`: how many entries are waiting, without removing any."""
    return str(dispatch.instrument.errors.count)


# The part of `0006`'s mandatory system subsystem that reads the error queue,
# built as nodes so a header resolves to it through the same walk every other
# header takes. Long forms and short forms are the standard's spellings, which
# is what a driver sends.
#
# `SYSTem:ERRor?` and `SYSTem:ERRor:NEXT?` are one command under two headers,
# which is what the record's `[:NEXT]` means, so both resolve to the same
# handler rather than one delegating to the other.
SYSTEM_NODES: tuple[Node, ...] = (
    Node(
        long="SYSTEM",
        short="SYST",
        path=("SYSTEM",),
        children=(
            Node(
                long="ERROR",
                short="ERR",
                path=("SYSTEM", "ERROR"),
                accepts="query",
                children=(
                    Node(
                        long="NEXT",
                        short="NEXT",
                        path=("SYSTEM", "ERROR", "NEXT"),
                        accepts="query",
                    ),
                    Node(
                        long="COUNT",
                        short="COUN",
                        path=("SYSTEM", "ERROR", "COUNT"),
                        accepts="query",
                    ),
                ),
            ),
        ),
    ),
)

# What each core header answers with. A path in this table is answered by its
# handler instead of by the parameters under its node, which is what makes these
# commands the core's: they read state no profile declares.
SYSTEM_ANSWERS: dict[tuple[str, ...], Callable[[Dispatch, Command], str | Refused]] = {
    ("SYSTEM", "ERROR"): _error_next,
    ("SYSTEM", "ERROR", "NEXT"): _error_next,
    ("SYSTEM", "ERROR", "COUNT"): _error_count,
}

SYSTEM_BY_PATH: dict[tuple[str, ...], Node] = {
    node.path: node for root in SYSTEM_NODES for node in root.walk()
}


@dataclass
class Dispatch:
    """One instrument and the vocabulary its messages are read against."""

    instrument: Instrument
    vocabulary: Vocabulary

    @classmethod
    def for_instrument(cls, instrument: Instrument) -> Dispatch:
        """The vocabulary built from the instrument's own profile and this set.

        The common set is handed to the parser from here rather than declared
        there, which is what `attrappe.scpi.parser` says it is waiting for: the
        parser cannot refuse `*XYZ` without knowing which asterisk commands
        exist, and the answer belongs to whatever implements them.
        """
        return cls(
            instrument=instrument,
            vocabulary=Vocabulary.from_profile(instrument.profile, MANDATORY_COMMON, SYSTEM_NODES),
        )

    def node_at(self, path: tuple[str, ...]) -> Node | None:
        """The node a header resolved to: the core's subsystem, then the profile's.

        The same precedence the vocabulary was built with. A profile declaring
        `SYSTem:ERRor` of its own would otherwise resolve through the core in
        the parser and through its own node here, and the two answers would be
        for different commands.
        """
        return SYSTEM_BY_PATH.get(path) or self.instrument.node_at(path)

    def execute(self, message: str) -> Outcome:
        """Read one message and run every command in it that resolves.

        Every unit is attempted. A unit that refuses stops nothing, for the same
        reason the parser reads on: a sender who made one mistake and a sender
        who made five should be able to tell the two messages apart.
        """
        parsed = parse(message, self.vocabulary)
        errors: list[Error] = list(parsed.errors)
        answers: list[str] = []

        for error in parsed.errors:
            self._record(error)

        for command in parsed.commands:
            outcome = self._one(command)
            if isinstance(outcome, Refused):
                errors.append(outcome)
                self._record(outcome)
            elif outcome is not None:
                answers.append(outcome)

        return Outcome(
            response=MESSAGE_SEPARATOR.join(answers) if answers else None,
            errors=tuple(errors),
        )

    def _record(self, error: Error) -> None:
        """Put one refusal in the instrument's queue.

        Every refusal this module produces and every refusal the parser handed
        it goes through here, so a path that refuses without recording would be
        a call to `_one` whose result nothing looks at, rather than a missing
        line somebody has to notice.
        """
        self.instrument.errors.push(queue_entry(error))

    def _one(self, command: Command) -> str | Refused | None:
        if command.common:
            return self._common(command)
        return self._tree(command)

    def _common(self, command: Command) -> str | Refused | None:
        entry = COMMON_BY_MNEMONIC[command.path[0]]
        if command.query:
            if entry.on_query is None:
                return refuse(
                    "header-is-not-a-command",
                    f"*{entry.mnemonic} takes no query form; it is the {entry.summary} command",
                    command,
                )
            if command.parameters:
                return refuse(
                    "parameter-not-allowed",
                    f"no parameter on *{entry.mnemonic}?; got {len(command.parameters)}",
                    command,
                )
            return entry.on_query(self, command)

        if entry.on_set is None:
            return refuse(
                "header-is-not-a-command",
                f"*{entry.mnemonic} exists only as a query; *{entry.mnemonic}? is the "
                f"{entry.summary}",
                command,
            )
        return entry.on_set(self, command)

    def _tree(self, command: Command) -> str | Refused | None:
        """A header that walked the tree: check the instance, the form, the values."""
        node = self.node_at(command.path)
        if node is None:
            # The parser resolved the header against this same profile, so this
            # is unreachable through `execute`. It is a refusal rather than an
            # assertion because a caller may build a `Command` by hand, and a
            # crash is a worse answer to that than a number.
            return refuse(
                "header-is-not-a-command",
                f"a header this profile declares; got {':'.join(command.path)}",
                command,
            )

        instance = self._instance(command)
        if isinstance(instance, Refused):
            return instance

        if command.query:
            if not node.queryable:
                return refuse(
                    "header-is-not-a-command",
                    self._not_a_command(node.accepts, "a query"),
                    command,
                )
            if command.parameters:
                return refuse(
                    "parameter-not-allowed",
                    f"no parameter on a query; got {len(command.parameters)}",
                    command,
                )
            answer = SYSTEM_ANSWERS.get(command.path)
            if answer is not None:
                return answer(self, command)
            return self._answer(node.parameters, instance)

        if not node.settable:
            return refuse(
                "header-is-not-a-command",
                self._not_a_command(node.accepts, "a command"),
                command,
            )
        return self._apply(node.parameters, instance, command)

    @staticmethod
    def _not_a_command(accepts: str | None, form: str) -> str:
        if accepts is None:
            return f"a header that is a command; this one stops on a branch, which takes no {form}"
        return f"a form this node accepts, which is {accepts}; got {form}"

    def _instance(self, command: Command) -> Instance | Refused:
        """The walked path, refusing a suffix above what a node declares.

        Every step is checked and not only the last. `ROUTe9:CHANnel1` on a
        device with two routes is out of range at the route, and an emulator
        that only looked at the leaf would answer for route one instead.
        """
        for depth, (mnemonic, suffix) in enumerate(
            zip(command.path, command.suffixes, strict=True), start=1
        ):
            node = self.node_at(command.path[:depth])
            if node is not None and suffix > node.suffixes:
                return refuse(
                    "suffix-above-the-instances",
                    f"a suffix of at most {node.suffixes} on {mnemonic}; got {suffix}",
                    command,
                )
        return tuple(zip(command.path, command.suffixes, strict=True))

    def _answer(self, parameters: tuple[Parameter, ...], instance: Instance) -> str:
        """The current values of a node's parameters, in declaration order."""
        separator = self.instrument.profile.separator
        return separator.join(
            _rendered(parameter, self.instrument.value(instance, parameter))
            for parameter in parameters
        )

    def _apply(
        self, parameters: tuple[Parameter, ...], instance: Instance, command: Command
    ) -> Refused | None:
        """Check every value against its parameter, then write, or write nothing.

        Nothing is written until every value has been accepted. A command whose
        second parameter is out of range leaves the first one alone, which is
        what "leaves the setting unchanged" has to mean once a command carries
        more than one.
        """
        if len(command.parameters) > len(parameters):
            return refuse(
                "parameter-not-allowed",
                f"at most {len(parameters)} parameter(s); got {len(command.parameters)}",
                command,
            )
        if len(command.parameters) < len(parameters):
            return refuse(
                "missing-parameter",
                f"{len(parameters)} parameter(s); got {len(command.parameters)}",
                command,
            )

        accepted: list[tuple[Parameter, object]] = []
        for parameter, value in zip(parameters, command.parameters, strict=True):
            checked = _checked(parameter, value, command)
            if isinstance(checked, Refused):
                return checked
            accepted.append((parameter, checked))

        for parameter, stored in accepted:
            self.instrument.write(instance, parameter, stored)
        return None


def _register_argument(command: Command) -> int | Refused:
    """The one eight-bit mask an enable command takes."""
    if not command.parameters:
        return refuse("missing-parameter", "one mask; got none", command)
    if len(command.parameters) > 1:
        return refuse(
            "parameter-not-allowed",
            f"one mask; got {len(command.parameters)}",
            command,
        )
    value = command.parameters[0]
    if not isinstance(value, NumericValue):
        return _wrong_kind(value, "a whole number", command)
    if value.suffix is not None:
        return refuse("suffix-not-allowed", f"no unit on a mask; got {value.suffix}", command)
    mask = int(value.value)
    if mask != value.value or not REGISTER_MINIMUM <= mask <= REGISTER_MAXIMUM:
        return refuse(
            "data-out-of-range",
            f"a whole number from {REGISTER_MINIMUM} to {REGISTER_MAXIMUM}; got {value.value:g}",
            command,
        )
    return mask


def _wrong_kind(value: Value, wanted: str, command: Command) -> Refused:
    """The refusal for a value of the wrong kind, by the kind that arrived."""
    if isinstance(value, StringValue):
        return refuse("string-data-not-allowed", f"{wanted}; got a quoted string", command)
    if isinstance(value, NumericValue):
        return refuse("numeric-data-not-allowed", f"{wanted}; got a number", command)
    if isinstance(value, NamedValue):
        return refuse("character-data-not-allowed", f"{wanted}; got {value.name}", command)
    return refuse("character-data-not-allowed", f"{wanted}; got {value.text}", command)


def _checked(parameter: Parameter, value: Value, command: Command) -> object | Refused:
    """One parameter's value, measured against what the profile declares for it."""
    if isinstance(value, NamedValue):
        return _named(parameter, value, command)
    if parameter.type == "numeric":
        return _numeric(parameter, value, command)
    if parameter.type == "boolean":
        return _boolean(parameter, value, command)
    if parameter.type == "character":
        return _character(parameter, value, command)
    return _string(parameter, value, command)


def _named(parameter: Parameter, value: NamedValue, command: Command) -> object | Refused:
    """MIN, MAX and DEF, which every parameter position accepts in the language.

    DEF has a meaning on every parameter, because every parameter declares a
    default. MIN and MAX have one only where a numeric range exists to read
    them out of, and on anything else they are character data the parameter
    cannot take.
    """
    if value.name == DEFAULT:
        return parameter.default
    if parameter.type != "numeric" or parameter.minimum is None or parameter.maximum is None:
        return refuse(
            "character-data-not-allowed",
            f"{value.name} on a parameter with a numeric range; {parameter.name} declares none",
            command,
        )
    return parameter.minimum if value.name == MINIMUM else parameter.maximum


def _numeric(parameter: Parameter, value: Value, command: Command) -> object | Refused:
    if not isinstance(value, NumericValue):
        return _wrong_kind(value, "a number", command)
    if value.suffix is not None:
        if parameter.units is None:
            return refuse(
                "suffix-not-allowed",
                f"no unit on {parameter.name}, which declares none; got {value.suffix}",
                command,
            )
        if value.suffix.upper() != parameter.units.upper():
            return refuse(
                "suffix-is-not-the-declared-unit",
                f"the unit {parameter.units} on {parameter.name}; got {value.suffix}",
                command,
            )
    # Narrowing rather than a guard, and the reason it is not proved by a test:
    # the loader refuses a numeric parameter that declares no minimum and
    # maximum, so no loaded profile reaches the other side of this. It is here
    # because the two fields are optional on `Parameter`, which they are because
    # the three other types have no range.
    if parameter.minimum is not None and parameter.maximum is not None:
        if not parameter.minimum <= value.value <= parameter.maximum:
            return refuse(
                "data-out-of-range",
                f"a value from {parameter.minimum:g} to {parameter.maximum:g}; got {value.value:g}",
                command,
            )
    return value.value


def _boolean(parameter: Parameter, value: Value, command: Command) -> object | Refused:
    if isinstance(value, CharacterValue):
        word = BOOLEAN_WORDS.get(value.text.upper())
        if word is None:
            return refuse(
                "illegal-parameter-value",
                f"one of {', '.join(sorted(BOOLEAN_WORDS))}, 0 or 1; got {value.text}",
                command,
            )
        return word
    if not isinstance(value, NumericValue):
        return _wrong_kind(value, "ON, OFF, 0 or 1", command)
    if value.suffix is not None:
        return refuse(
            "suffix-not-allowed",
            f"no unit on {parameter.name}, which is a switch; got {value.suffix}",
            command,
        )
    if value.value not in (0.0, 1.0):
        return refuse(
            "data-out-of-range",
            f"0 or 1 on {parameter.name}; got {value.value:g}",
            command,
        )
    return value.value == 1.0


def _character(parameter: Parameter, value: Value, command: Command) -> object | Refused:
    if not isinstance(value, CharacterValue):
        return _wrong_kind(value, "one of the declared choices", command)
    choices = parameter.choices or ()
    for choice in choices:
        if choice.upper() == value.text.upper():
            return choice
    return refuse(
        "illegal-parameter-value",
        f"one of {', '.join(choices)}; got {value.text}",
        command,
    )


def _string(parameter: Parameter, value: Value, command: Command) -> object | Refused:
    if not isinstance(value, StringValue):
        return _wrong_kind(value, "a quoted string", command)
    return value.value


def _rendered(parameter: Parameter, value: object) -> str:
    """One setting as a driver reads it back.

    A boolean answers as the digit rather than the word, which is what an
    instrument answers and what a driver parses. A string answers quoted,
    because an unquoted one is indistinguishable from character data.
    """
    if parameter.type == "boolean":
        return "1" if value else "0"
    if parameter.type == "string":
        return f'"{value}"'
    if isinstance(value, float):
        return repr(value)
    return str(value)
