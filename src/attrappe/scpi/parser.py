"""Turn a received message into parsed commands, and refuse the rest by number.

    from attrappe.scpi import Vocabulary, parse

    parsed = parse(":SENS:VOLT:DC:RANG 10;NPLC MIN", vocabulary)

Nothing here executes anything. `parse` answers a structure and a list of
refusals, and what happens to either is the dispatch in #22.

## The vocabulary is an argument

A parser cannot refuse an undefined header without knowing which headers exist,
and it cannot refuse the in-between form of a mnemonic without knowing that
`MEASure` abbreviates to `MEAS`. Both are in the profile, per
`docs/decisions/0006-conformance-surface.md`, which puts everything beyond the
mandatory subsystem there. So the vocabulary is handed in, the same way the
clock and the generator are handed in everywhere else in this package. A parser
that declared its own tree would be #22 and #25 doing their work a third time
and disagreeing with both later.

`Vocabulary.from_profile` builds one from a loaded profile. The set of common
commands is passed alongside it rather than written here: which of them are
mandatory is `0006`'s and implementing them is #22's, and a list in this file
would be a third copy of it.

## The tree walk

The rules this implements, which is the command-tree traversal a driver
assumes:

- The path is at the root when a message begins.
- A header beginning with a colon puts the path back at the root before the
  header is read.
- A header is read relative to the current path.
- After a message unit, the path becomes that header's mnemonics except the
  last, so `:SENS:VOLT:DC:RANG 10;NPLC 1` sets the range and then the aperture
  under the same subsystem.
- A common command, which is the leading-asterisk form, does not take part in
  any of this and leaves the path where it was.
- A refused unit changes nothing, including the path. An instrument that moved
  its path on a header it could not resolve would make the next unit in the
  same message fail for a reason the sender cannot see.

## What a refusal produces

`REFUSALS` is the table, as data, keyed by an id. Each row carries the number
and the standard message that `0006` fixes for it, and the case this parser
produces it for. #23 asks for a test driven from this table rather than from a
second hand-written list, and this is the table it means.

`-100`, the generic command error, is deliberately not in it. The issue this
implements asks for the standard number for the case and not a generic one, so
a case with no better number than `-100` is one this parser does not refuse.

## What this does not decide

Whether a parameter is of the type its command takes, whether the right number
of them arrived, and whether a unit suffix is the unit the parameter declares.
All three need the parameter table matched against a particular command, which
is the dispatch. That is why `-108`, `-109`, `-128`, `-138`, `-148` and `-158`
are absent here: they are refusals about a parameter's fit rather than its
form.

A suffix is recognised by its spelling and not by its meaning. `10 XYZ` parses,
with `XYZ` carried through as the suffix, because whether `XYZ` is a unit this
command accepts is the parameter table's answer. `10 V2` is refused, because it
cannot be a unit suffix under any parameter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from attrappe.profile import Node, Profile

# The suffix a mnemonic carries when it does not carry one. Stated here because
# a default that is only in the code is one every reader has to derive.
DEFAULT_SUFFIX = 1

MESSAGE_SEPARATOR = ";"
PARAMETER_SEPARATOR = ","
HEADER_SEPARATOR = ":"
QUERY_MARK = "?"
COMMON_MARK = "*"
QUOTES = ("'", '"')

# The named values every SCPI parameter position accepts, and their short forms.
# A spelling between the two is not one of these and is carried through as
# character data, because whether it is legal there is the parameter's answer.
NAMED_VALUES = {
    "MIN": "MINIMUM",
    "MINIMUM": "MINIMUM",
    "MAX": "MAXIMUM",
    "MAXIMUM": "MAXIMUM",
    "DEF": "DEFAULT",
    "DEFAULT": "DEFAULT",
}

MNEMONIC = re.compile(r"^([A-Za-z]+)([0-9]*)$")
NUMBER = re.compile(r"^[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
UNIT_SUFFIX = re.compile(r"^[A-Za-z]+$")
CHARACTER_DATA = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
STARTS_A_NUMBER = re.compile(r"^[+-.0-9]")
# What is left of `1e`, `1E+` and the like once the number pattern has taken the
# digits it could. An exponent marker with no exponent is a broken number rather
# than a number carrying a unit called `e`.
BROKEN_EXPONENT = re.compile(r"^[eE][+-]?$")


@dataclass(frozen=True)
class Refusal:
    """One row of the refusal table: the number, its message, and the case."""

    id: str
    number: int
    message: str
    case: str


# The numbers and the messages are `docs/decisions/0006-conformance-surface.md`'s
# and are not re-decided here. What each row adds is the case: which shape of
# message this parser answers with that number. Where two numbers could be read
# as fitting a case, the row says which one this parser produces, because the
# record fixes the table and not the mapping onto a parser's own states.
REFUSALS: tuple[Refusal, ...] = (
    Refusal(
        id="invalid-character",
        number=-101,
        message="Invalid character",
        case="a character that cannot appear in the element it appears in, such as "
        "a header or a parameter carrying a symbol",
    ),
    Refusal(
        id="syntax-error",
        number=-102,
        message="Syntax error",
        case="an element that cannot be read as anything: an empty mnemonic, a "
        "mnemonic starting with a digit, a data element that is absent between two "
        "separators, or a quoted string that is never closed",
    ),
    Refusal(
        id="invalid-separator",
        number=-103,
        message="Invalid separator",
        case="two elements where a separator was owed: two parameters with no comma "
        "between them, or two message separators with no unit between them",
    ),
    Refusal(
        id="undefined-header",
        number=-113,
        message="Undefined header",
        case="a syntactically correct header the vocabulary does not define, which "
        "includes every spelling between a mnemonic's short form and its long form",
    ),
    Refusal(
        id="header-suffix-out-of-range",
        number=-114,
        message="Header suffix out of range",
        case="a numeric suffix below one; suffixes count from one and a zeroth "
        "channel is not a channel",
    ),
    Refusal(
        id="numeric-data-error",
        number=-120,
        message="Numeric data error",
        case="a parameter that begins as a number and is not one, such as a second "
        "decimal point or an exponent with no digits",
    ),
    Refusal(
        id="invalid-suffix",
        number=-131,
        message="Invalid suffix",
        case="a unit suffix that no unit could be spelled as, such as one carrying a digit",
    ),
)

BY_ID: dict[str, Refusal] = {refusal.id: refusal for refusal in REFUSALS}


@dataclass(frozen=True)
class ParseError:
    """One refusal, with the unit it came from and what was wrong with it."""

    refusal: Refusal
    detail: str
    unit: str

    @property
    def number(self) -> int:
        return self.refusal.number

    def __str__(self) -> str:
        return f'{self.refusal.number},"{self.refusal.message}; {self.detail}"'


@dataclass(frozen=True)
class NumericValue:
    """A decimal number, with the unit suffix as written or None."""

    value: float
    suffix: str | None = None


@dataclass(frozen=True)
class NamedValue:
    """MINIMUM, MAXIMUM or DEFAULT, resolved to its long form."""

    name: str


@dataclass(frozen=True)
class CharacterValue:
    """Character program data, carried in the case it was written in."""

    text: str


@dataclass(frozen=True)
class StringValue:
    """A quoted string, with the doubling of the enclosing quote resolved."""

    value: str


Value = NumericValue | NamedValue | CharacterValue | StringValue

# A walked header path: one long-form mnemonic and its numeric suffix per step.
Walked = tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class Command:
    """One parsed message unit.

    `path` is the long forms of the mnemonics the header resolved to, root
    first, so a caller never has to know which spelling arrived. `suffixes`
    carries one entry per mnemonic. `common` is the leading-asterisk form, whose
    `path` is the single mnemonic without the asterisk.
    """

    path: tuple[str, ...]
    suffixes: tuple[int, ...] = ()
    query: bool = False
    common: bool = False
    parameters: tuple[Value, ...] = ()
    source: str = ""


@dataclass(frozen=True)
class Parsed:
    """What a message came to: the commands it carried and what was refused."""

    commands: tuple[Command, ...] = ()
    errors: tuple[ParseError, ...] = ()


@dataclass(frozen=True)
class Vocabulary:
    """The headers that exist: a command tree, and the common commands.

    Both are handed in. `common` holds the mnemonics without their asterisk, in
    whatever case, and is compared case insensitively.
    """

    roots: tuple[Node, ...] = ()
    common: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_profile(cls, profile: Profile, common: frozenset[str] | set[str]) -> Vocabulary:
        return cls(roots=profile.roots, common=frozenset(name.upper() for name in common))

    def children_of(self, path: tuple[str, ...]) -> tuple[Node, ...]:
        """The nodes reachable one step below `path`, the roots for an empty path."""
        nodes = self.roots
        for mnemonic in path:
            for node in nodes:
                if node.long == mnemonic:
                    nodes = node.children
                    break
            else:
                return ()
        return nodes


def parse(message: str, vocabulary: Vocabulary) -> Parsed:
    """Read one message into its commands, collecting every refusal in it.

    A refused unit produces an error and no command, and the units after it are
    still read. An instrument that stopped at the first bad unit would leave the
    sender unable to tell a message with one mistake from a message with five.
    """
    commands: list[Command] = []
    errors: list[ParseError] = []
    # The current path, carrying each mnemonic's suffix with it. The suffix
    # belongs to the path and not to the unit that wrote it: a unit resuming
    # under `ROUTe2:CHANnel` is under channel two, and dropping the suffix here
    # would silently put it under channel one.
    path: Walked = ()

    for unit in _split(message.rstrip("\r\n"), MESSAGE_SEPARATOR):
        stripped = unit.strip()
        if not stripped:
            errors.append(
                ParseError(BY_ID["invalid-separator"], "a message unit with nothing in it", unit)
            )
            continue
        outcome, path = _unit(stripped, vocabulary, path)
        if isinstance(outcome, Command):
            commands.append(outcome)
        else:
            errors.extend(outcome)

    return Parsed(commands=tuple(commands), errors=tuple(errors))


def _unit(
    unit: str, vocabulary: Vocabulary, path: Walked
) -> tuple[Command | list[ParseError], Walked]:
    """One message unit, and the header path the next unit starts from."""
    header, parameter_text = _split_off_parameters(unit)
    if not header:
        return [ParseError(BY_ID["syntax-error"], "a unit with no header", unit)], path

    query = header.endswith(QUERY_MARK)
    if query:
        header = header[: -len(QUERY_MARK)]

    if header.startswith(COMMON_MARK):
        return _common(unit, header, query, parameter_text, vocabulary), path

    start: Walked
    if header.startswith(HEADER_SEPARATOR):
        header, start = header[1:], ()
    else:
        start = path

    resolved = _resolve(unit, header, start, vocabulary)
    if isinstance(resolved, list):
        return resolved, path

    parameters = _parameters(unit, parameter_text)
    if isinstance(parameters, list):
        return parameters, path

    full = start + resolved
    command = Command(
        path=tuple(mnemonic for mnemonic, _ in full),
        suffixes=tuple(suffix for _, suffix in full),
        query=query,
        parameters=parameters,
        source=unit,
    )
    return command, full[:-1]


def _common(
    unit: str, header: str, query: bool, parameter_text: str, vocabulary: Vocabulary
) -> Command | list[ParseError]:
    """A leading-asterisk command, which is outside the tree and never in it."""
    mnemonic = header[len(COMMON_MARK) :]
    if not mnemonic.isalpha():
        return [
            ParseError(
                BY_ID["syntax-error"],
                f"a common command mnemonic of letters only; got {mnemonic!r}",
                unit,
            )
        ]
    if mnemonic.upper() not in vocabulary.common:
        return [
            ParseError(
                BY_ID["undefined-header"],
                f"the vocabulary defines no common command {COMMON_MARK}{mnemonic.upper()}",
                unit,
            )
        ]
    parameters = _parameters(unit, parameter_text)
    if isinstance(parameters, list):
        return parameters
    return Command(
        path=(mnemonic.upper(),),
        query=query,
        common=True,
        parameters=parameters,
        source=unit,
    )


def _resolve(
    unit: str, header: str, start: Walked, vocabulary: Vocabulary
) -> Walked | list[ParseError]:
    """Walk the header down the tree from `start`, or say why it does not walk."""
    walked: list[tuple[str, int]] = []
    candidates = vocabulary.children_of(tuple(mnemonic for mnemonic, _ in start))

    for spelling in header.split(HEADER_SEPARATOR):
        match = MNEMONIC.match(spelling)
        if match is None:
            return [_bad_mnemonic(unit, spelling)]
        written, digits = match.group(1).upper(), match.group(2)
        suffix = int(digits) if digits else DEFAULT_SUFFIX
        if digits and suffix < 1:
            return [
                ParseError(
                    BY_ID["header-suffix-out-of-range"],
                    f"a suffix of one or more on {written}; got {suffix}",
                    unit,
                )
            ]
        for node in candidates:
            if written in (node.long, node.short):
                walked.append((node.long, suffix))
                candidates = node.children
                break
        else:
            return [
                ParseError(
                    BY_ID["undefined-header"],
                    _undefined_detail(written, candidates, start, tuple(walked)),
                    unit,
                )
            ]

    return tuple(walked)


def _undefined_detail(
    written: str, candidates: tuple[Node, ...], start: Walked, walked: Walked
) -> str:
    """Say what was not found, and say when it was an in-between spelling.

    The in-between case is the one worth naming. Somebody who sent `MEASU` is
    not guessing at a header, they wrote a mnemonic in a form no instrument
    accepts, and a message that only says the header is undefined sends them
    looking for a missing subsystem.
    """
    under = ":".join(mnemonic for mnemonic, _ in (*start, *walked)) or "the root"
    for node in candidates:
        if node.long.startswith(written) or written.startswith(node.short):
            return (
                f"{written} is neither the short form {node.short} nor the long form "
                f"{node.long}, and a spelling between the two is not a header"
            )
    return f"nothing under {under} is named {written}"


def _bad_mnemonic(unit: str, spelling: str) -> ParseError:
    """An empty mnemonic, one starting with a digit, or one carrying a symbol."""
    if not spelling:
        return ParseError(BY_ID["syntax-error"], "an empty mnemonic between colons", unit)
    if not spelling.isalnum():
        return ParseError(
            BY_ID["invalid-character"],
            f"a mnemonic of letters and digits; got {spelling!r}",
            unit,
        )
    return ParseError(
        BY_ID["syntax-error"],
        f"a mnemonic starting with a letter; got {spelling!r}",
        unit,
    )


def _split_off_parameters(unit: str) -> tuple[str, str]:
    """The header, and everything after the first unquoted run of whitespace."""
    for index, character, inside in _scan(unit):
        if not inside and character.isspace():
            return unit[:index], unit[index + 1 :]
    return unit, ""


def _parameters(unit: str, text: str) -> tuple[Value, ...] | list[ParseError]:
    """Every parameter in the unit, or the refusals the first bad one produced."""
    if not text.strip():
        return ()

    values: list[Value] = []
    for element in _split(text, PARAMETER_SEPARATOR):
        outcome = _value(unit, element.strip())
        if isinstance(outcome, ParseError):
            return [outcome]
        values.append(outcome)
    return tuple(values)


def _value(unit: str, element: str) -> Value | ParseError:
    """One parameter, classified, or the number that refuses it."""
    if not element:
        return ParseError(BY_ID["syntax-error"], "a parameter between two commas", unit)

    if element[0] in QUOTES:
        return _string(unit, element)

    if STARTS_A_NUMBER.match(element):
        return _numeric(unit, element)

    if CHARACTER_DATA.match(element):
        named = NAMED_VALUES.get(element.upper())
        return NamedValue(named) if named else CharacterValue(element)

    if any(character.isspace() for character in element):
        return ParseError(
            BY_ID["invalid-separator"],
            f"a comma between parameters; got {element!r} as one element",
            unit,
        )
    return ParseError(
        BY_ID["invalid-character"],
        f"a parameter of a form the language has; got {element!r}",
        unit,
    )


def _string(unit: str, element: str) -> StringValue | ParseError:
    """A quoted string in either quote character, with the doubling resolved."""
    quote = element[0]
    if len(element) < 2 or element[-1] != quote:
        return ParseError(BY_ID["syntax-error"], f"a closing {quote} on {element!r}", unit)
    body = element[1:-1]
    # Every quote inside the body has to be a doubled one. An odd run of them
    # means the string closed early and the rest is not a string at all.
    index = 0
    resolved: list[str] = []
    while index < len(body):
        character = body[index]
        if character == quote:
            if index + 1 >= len(body) or body[index + 1] != quote:
                return ParseError(
                    BY_ID["syntax-error"],
                    f"a doubled {quote} for one inside a string; got {element!r}",
                    unit,
                )
            resolved.append(quote)
            index += 2
            continue
        resolved.append(character)
        index += 1
    return StringValue("".join(resolved))


def _numeric(unit: str, element: str) -> NumericValue | ParseError:
    """A decimal number with an optional unit suffix, or why it is neither."""
    match = NUMBER.match(element)
    if match is None:
        return ParseError(BY_ID["numeric-data-error"], f"a decimal number; got {element!r}", unit)
    number = match.group(0)
    written = element[len(number) :]
    remainder = written.strip()
    if not remainder:
        return NumericValue(float(number))
    if BROKEN_EXPONENT.match(remainder):
        return ParseError(
            BY_ID["numeric-data-error"],
            f"digits after the exponent in {element!r}",
            unit,
        )
    if STARTS_A_NUMBER.match(remainder):
        # A space before the second number means a comma was owed between two
        # parameters. No space means one parameter that is not a number.
        if written != remainder:
            return ParseError(
                BY_ID["invalid-separator"],
                f"a comma between parameters; got {element!r} as one element",
                unit,
            )
        return ParseError(
            BY_ID["numeric-data-error"],
            f"one number; got {element!r}, which continues after {number!r}",
            unit,
        )
    if not remainder.isalnum():
        return ParseError(
            BY_ID["invalid-character"],
            f"a unit suffix of letters after {number!r}; got {remainder!r}",
            unit,
        )
    if not UNIT_SUFFIX.match(remainder):
        return ParseError(
            BY_ID["invalid-suffix"],
            f"a unit suffix of letters after {number!r}; got {remainder!r}",
            unit,
        )
    return NumericValue(float(number), remainder)


def _split(text: str, separator: str) -> list[str]:
    """Split on a separator that is not inside a quoted string.

    A message may carry a string parameter holding a semicolon or a comma, and
    splitting on the character first would cut it in half and refuse both
    halves for reasons neither of them has.
    """
    parts: list[str] = []
    cut = 0
    for index, character, inside in _scan(text):
        if not inside and character == separator:
            parts.append(text[cut:index])
            cut = index + 1
    parts.append(text[cut:])
    return parts


def _scan(text: str) -> list[tuple[int, str, bool]]:
    """Every character with whether it is inside a quoted string.

    A doubled quote inside a string stays inside it. Without that, `'it''s'`
    reads as a string, a bare `s` and an empty string, so a semicolon after the
    apostrophe would be taken as a message separator and the unit would be cut
    in half.
    """
    scanned: list[tuple[int, str, bool]] = []
    quote: str | None = None
    index = 0
    while index < len(text):
        character = text[index]
        if quote is None:
            if character in QUOTES:
                quote = character
                scanned.append((index, character, True))
            else:
                scanned.append((index, character, False))
            index += 1
            continue
        if character == quote:
            if text[index + 1 : index + 2] == quote:
                scanned.append((index, character, True))
                scanned.append((index + 1, character, True))
                index += 2
                continue
            quote = None
        scanned.append((index, character, True))
        index += 1
    return scanned
