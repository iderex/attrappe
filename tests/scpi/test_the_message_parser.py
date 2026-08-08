"""The parser table: every accepted form, every refused form, and its number.

One row per form. A row cites the rule it comes from, so the table can be read
against the rules rather than against the parser, and a row nobody can attribute
to a rule is a row somebody invented.

Two kinds of citation appear, and they are different weights.
`docs/decisions/0006-conformance-surface.md` is in this tree and fixes the error
numbers and their messages, so a row citing it can be checked by opening it. The
rows about message syntax and the command-tree walk cite the language rule the
parser implements, written out in `attrappe.scpi.parser`'s own docstring. That
is a statement of what this parser does and what a driver assumes, not a
transcription of a standard nobody here can open, and it is worth reading as the
weaker of the two.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from attrappe.profile import load_profile
from attrappe.scpi import (
    BY_ID,
    DEFAULT_SUFFIX,
    REFUSALS,
    CharacterValue,
    NamedValue,
    NumericValue,
    Parsed,
    StringValue,
    Value,
    Vocabulary,
    parse,
)

VOCABULARY_PROFILE = Path(__file__).parent / "fixtures" / "vocabulary"

# The common commands the table uses. They are passed in rather than declared in
# the parser: which of them are mandatory is 0006's and implementing them is
# #22's, so a list inside the parser would be a third copy of the same set.
COMMON = frozenset({"IDN", "RST", "CLS", "OPC"})


@dataclass(frozen=True)
class Expected:
    """One command a message is expected to come to."""

    path: tuple[str, ...]
    query: bool = False
    common: bool = False
    parameters: tuple[Value, ...] = ()
    suffixes: tuple[int, ...] | None = None


@dataclass(frozen=True)
class Accepted:
    """A message the parser accepts, and what it comes to."""

    name: str
    message: str
    rule: str
    commands: tuple[Expected, ...]


@dataclass(frozen=True)
class Refused:
    """A message the parser refuses, and the refusal each unit produces."""

    name: str
    message: str
    rule: str
    refusals: tuple[str, ...]
    commands: tuple[Expected, ...] = field(default=())


NUMBERS = "docs/decisions/0006-conformance-surface.md, the error table"
LANGUAGE = "the message language, as attrappe.scpi.parser states it"

ACCEPTED: tuple[Accepted, ...] = (
    Accepted(
        name="a common command in its query form",
        message="*IDN?",
        rule=f"{LANGUAGE}: the leading asterisk form, outside the tree",
        commands=(Expected(path=("IDN",), query=True, common=True),),
    ),
    Accepted(
        name="every mnemonic in its short form",
        message="MEAS:VOLT:DC?",
        rule=f"{LANGUAGE}: the short form of a header is accepted",
        commands=(Expected(path=("MEASURE", "VOLTAGE", "DC"), query=True),),
    ),
    Accepted(
        name="every mnemonic in its long form",
        message="MEASURE:VOLTAGE:DC?",
        rule=f"{LANGUAGE}: the long form of a header is accepted",
        commands=(Expected(path=("MEASURE", "VOLTAGE", "DC"), query=True),),
    ),
    Accepted(
        name="a header in lower case",
        message="measure:voltage:dc?",
        rule=f"{LANGUAGE}: header matching is case insensitive",
        commands=(Expected(path=("MEASURE", "VOLTAGE", "DC"), query=True),),
    ),
    Accepted(
        name="the short and long forms mixed in one header",
        message="SENSE:VOLT:DC:RANGE?",
        rule=f"{LANGUAGE}: the two forms are per mnemonic, not per header",
        commands=(Expected(path=("SENSE", "VOLTAGE", "DC", "RANGE"), query=True),),
    ),
    Accepted(
        name="a numeric suffix on a node",
        message="ROUT:CHAN2",
        rule=f"{LANGUAGE}: a numeric suffix selects among identical nodes",
        commands=(Expected(path=("ROUTE", "CHANNEL"), suffixes=(1, 2)),),
    ),
    Accepted(
        name="a node with no numeric suffix",
        message="ROUT:CHAN",
        rule=f"{LANGUAGE}: an absent suffix is {DEFAULT_SUFFIX}",
        commands=(Expected(path=("ROUTE", "CHANNEL"), suffixes=(1, 1)),),
    ),
    Accepted(
        name="the walk resuming under the previous header",
        message=":SENS:VOLT:DC:RANG 10;NPLC 1",
        rule=f"{LANGUAGE}: after a unit the path is the header minus its last mnemonic",
        commands=(
            Expected(path=("SENSE", "VOLTAGE", "DC", "RANGE"), parameters=(NumericValue(10.0),)),
            Expected(path=("SENSE", "VOLTAGE", "DC", "NPLCYCLES"), parameters=(NumericValue(1.0),)),
        ),
    ),
    Accepted(
        name="a leading colon putting the walk back at the root",
        message="SENS:VOLT:DC:RANG 10;:MEAS:VOLT:DC?",
        rule=f"{LANGUAGE}: a leading colon resets the path before the header is read",
        commands=(
            Expected(path=("SENSE", "VOLTAGE", "DC", "RANGE"), parameters=(NumericValue(10.0),)),
            Expected(path=("MEASURE", "VOLTAGE", "DC"), query=True),
        ),
    ),
    Accepted(
        name="a common command leaving the path where it was",
        message=":SENS:VOLT:DC:RANG 10;*CLS;NPLC 1",
        rule=f"{LANGUAGE}: a common command takes no part in the tree walk",
        commands=(
            Expected(path=("SENSE", "VOLTAGE", "DC", "RANGE"), parameters=(NumericValue(10.0),)),
            Expected(path=("CLS",), common=True),
            Expected(path=("SENSE", "VOLTAGE", "DC", "NPLCYCLES"), parameters=(NumericValue(1.0),)),
        ),
    ),
    Accepted(
        name="a one-mnemonic header leaving the path at the root",
        message="ROUT:CHAN;*RST",
        rule=f"{LANGUAGE}: the path after a unit is its header minus the last mnemonic",
        commands=(
            Expected(path=("ROUTE", "CHANNEL")),
            Expected(path=("RST",), common=True),
        ),
    ),
    Accepted(
        name="a decimal number with no exponent",
        message="SENS:VOLT:DC:RANG 1.5",
        rule=f"{LANGUAGE}: decimal numeric program data",
        commands=(
            Expected(path=("SENSE", "VOLTAGE", "DC", "RANGE"), parameters=(NumericValue(1.5),)),
        ),
    ),
    Accepted(
        name="a decimal number with an exponent",
        message="SENS:VOLT:DC:RANG -1.5E-3",
        rule=f"{LANGUAGE}: decimal numeric program data with an exponent",
        commands=(
            Expected(path=("SENSE", "VOLTAGE", "DC", "RANGE"), parameters=(NumericValue(-0.0015),)),
        ),
    ),
    Accepted(
        name="a number with no digits before the point",
        message="SENS:VOLT:DC:RANG .5",
        rule=f"{LANGUAGE}: decimal numeric program data",
        commands=(
            Expected(path=("SENSE", "VOLTAGE", "DC", "RANGE"), parameters=(NumericValue(0.5),)),
        ),
    ),
    Accepted(
        name="a number with a unit suffix after a space",
        message="SENS:VOLT:DC:RANG 10 V",
        rule=f"{LANGUAGE}: a unit suffix follows the number, with or without a space",
        commands=(
            Expected(
                path=("SENSE", "VOLTAGE", "DC", "RANGE"),
                parameters=(NumericValue(10.0, "V"),),
            ),
        ),
    ),
    Accepted(
        name="a number with a unit suffix and no space",
        message="SENS:VOLT:DC:RANG 10MV",
        rule=f"{LANGUAGE}: a unit suffix follows the number, with or without a space",
        commands=(
            Expected(
                path=("SENSE", "VOLTAGE", "DC", "RANGE"),
                parameters=(NumericValue(10.0, "MV"),),
            ),
        ),
    ),
    Accepted(
        name="the named minimum in its short form",
        message="SENS:VOLT:DC:RANG MIN",
        rule=f"{LANGUAGE}: MINimum, MAXimum and DEFault are accepted wherever a value is",
        commands=(
            Expected(path=("SENSE", "VOLTAGE", "DC", "RANGE"), parameters=(NamedValue("MINIMUM"),)),
        ),
    ),
    Accepted(
        name="the named maximum in its long form",
        message="SENS:VOLT:DC:RANG? MAXIMUM",
        rule=f"{LANGUAGE}: MINimum, MAXimum and DEFault are accepted wherever a value is",
        commands=(
            Expected(
                path=("SENSE", "VOLTAGE", "DC", "RANGE"),
                query=True,
                parameters=(NamedValue("MAXIMUM"),),
            ),
        ),
    ),
    Accepted(
        name="the named default",
        message="SENS:VOLT:DC:RANG DEF",
        rule=f"{LANGUAGE}: MINimum, MAXimum and DEFault are accepted wherever a value is",
        commands=(
            Expected(path=("SENSE", "VOLTAGE", "DC", "RANGE"), parameters=(NamedValue("DEFAULT"),)),
        ),
    ),
    Accepted(
        name="character program data",
        message="SENS:FUNC ONCE",
        rule=f"{LANGUAGE}: character program data",
        commands=(Expected(path=("SENSE", "FUNCTION"), parameters=(CharacterValue("ONCE"),)),),
    ),
    Accepted(
        name="a spelling between the short and long forms of a named value",
        message="SENS:FUNC MINI",
        rule=f"{LANGUAGE}: only MIN, MINIMUM and their pairs are named values; the rest "
        "is character data, and whether it is legal there is the parameter's answer",
        commands=(Expected(path=("SENSE", "FUNCTION"), parameters=(CharacterValue("MINI"),)),),
    ),
    Accepted(
        name="a double-quoted string",
        message='SENS:FUNC "VOLT:DC"',
        rule=f"{LANGUAGE}: string program data in either quote character",
        commands=(Expected(path=("SENSE", "FUNCTION"), parameters=(StringValue("VOLT:DC"),)),),
    ),
    Accepted(
        name="a single-quoted string with a doubled quote in it",
        message="DISP:TEXT 'it''s here'",
        rule=f"{LANGUAGE}: a quote inside a string is written twice",
        commands=(Expected(path=("DISPLAY", "TEXT"), parameters=(StringValue("it's here"),)),),
    ),
    Accepted(
        name="a double-quoted string with a doubled quote in it",
        message='DISP:TEXT "say ""hello"""',
        rule=f"{LANGUAGE}: a quote inside a string is written twice",
        commands=(Expected(path=("DISPLAY", "TEXT"), parameters=(StringValue('say "hello"'),)),),
    ),
    Accepted(
        name="a string carrying the message separator",
        message='DISP:TEXT "one;two"',
        rule=f"{LANGUAGE}: the message separator inside a string is not a separator",
        commands=(Expected(path=("DISPLAY", "TEXT"), parameters=(StringValue("one;two"),)),),
    ),
    Accepted(
        name="a string carrying the parameter separator",
        message="DISP:TEXT 'one,two'",
        rule=f"{LANGUAGE}: the parameter separator inside a string is not a separator",
        commands=(Expected(path=("DISPLAY", "TEXT"), parameters=(StringValue("one,two"),)),),
    ),
    Accepted(
        name="a comma-separated list of parameters",
        message="ROUT:CHAN 1,2,3",
        rule=f"{LANGUAGE}: parameters are separated by commas",
        commands=(
            Expected(
                path=("ROUTE", "CHANNEL"),
                parameters=(NumericValue(1.0), NumericValue(2.0), NumericValue(3.0)),
            ),
        ),
    ),
    Accepted(
        name="a list mixing a number, a named value and a string",
        message="ROUT:CHAN 1, MAX, 'here'",
        rule=f"{LANGUAGE}: parameters in one list need not be of one kind",
        commands=(
            Expected(
                path=("ROUTE", "CHANNEL"),
                parameters=(NumericValue(1.0), NamedValue("MAXIMUM"), StringValue("here")),
            ),
        ),
    ),
    Accepted(
        name="a message ending in a terminator",
        message="*IDN?\n",
        rule=f"{LANGUAGE}: the terminator delimits the message and is not part of it",
        commands=(Expected(path=("IDN",), query=True, common=True),),
    ),
)


REFUSED: tuple[Refused, ...] = (
    Refused(
        name="a spelling between the short and long forms of a mnemonic",
        message="SENS:VOLTA:DC:RANG 1",
        rule=f"{NUMBERS}, -113; {LANGUAGE}: the forms between the two are not headers",
        refusals=("undefined-header",),
    ),
    Refused(
        name="a header shorter than the short form",
        message="SENS:VOL:DC:RANG 1",
        rule=f"{NUMBERS}, -113; {LANGUAGE}: the forms between the two are not headers",
        refusals=("undefined-header",),
    ),
    Refused(
        name="a header the vocabulary does not have",
        message="TRIG:SOUR IMM",
        rule=f"{NUMBERS}, -113",
        refusals=("undefined-header",),
    ),
    Refused(
        name="a common command the vocabulary does not have",
        message="*FOO",
        rule=f"{NUMBERS}, -113",
        refusals=("undefined-header",),
    ),
    Refused(
        name="a child that exists under a different parent",
        message="MEAS:VOLT:DC:RANG 1",
        rule=f"{NUMBERS}, -113; {LANGUAGE}: a header is read against the current path",
        refusals=("undefined-header",),
    ),
    Refused(
        name="a numeric suffix of zero",
        message="ROUT:CHAN0",
        rule=f"{NUMBERS}, -114; {LANGUAGE}: suffixes count from one",
        refusals=("header-suffix-out-of-range",),
    ),
    Refused(
        name="an empty mnemonic between two colons",
        message="SENS::VOLT 1",
        rule=f"{NUMBERS}, -102",
        refusals=("syntax-error",),
    ),
    Refused(
        name="a mnemonic starting with a digit",
        message="1SENS 1",
        rule=f"{NUMBERS}, -102; {LANGUAGE}: a mnemonic starts with a letter",
        refusals=("syntax-error",),
    ),
    Refused(
        name="a common command mnemonic carrying a digit",
        message="*ID2N?",
        rule=f"{NUMBERS}, -102; {LANGUAGE}: a common command mnemonic is letters",
        refusals=("syntax-error",),
    ),
    Refused(
        name="a string that is never closed",
        message='SENS:FUNC "unclosed',
        rule=f"{NUMBERS}, -102",
        refusals=("syntax-error",),
    ),
    Refused(
        name="a single quote inside a string that was not doubled",
        message="DISP:TEXT 'it's'",
        rule=f"{NUMBERS}, -102; {LANGUAGE}: a quote inside a string is written twice",
        refusals=("syntax-error",),
    ),
    Refused(
        name="a parameter absent between two commas",
        message="ROUT:CHAN 1,,2",
        rule=f"{NUMBERS}, -102",
        refusals=("syntax-error",),
    ),
    Refused(
        name="a symbol in a mnemonic",
        message="SE$NS:VOLT 1",
        rule=f"{NUMBERS}, -101",
        refusals=("invalid-character",),
    ),
    Refused(
        name="a symbol after a number",
        message="ROUT:CHAN 1.0$",
        rule=f"{NUMBERS}, -101",
        refusals=("invalid-character",),
    ),
    Refused(
        name="two parameters with no comma between them",
        message="ROUT:CHAN 1 2",
        rule=f"{NUMBERS}, -103; {LANGUAGE}: parameters are separated by commas",
        refusals=("invalid-separator",),
    ),
    Refused(
        name="two character parameters with no comma between them",
        message="SENS:FUNC ON OFF",
        rule=f"{NUMBERS}, -103; {LANGUAGE}: parameters are separated by commas",
        refusals=("invalid-separator",),
    ),
    Refused(
        name="two message separators with no unit between them",
        message="*RST;;*CLS",
        rule=f"{NUMBERS}, -103",
        refusals=("invalid-separator",),
        commands=(
            Expected(path=("RST",), common=True),
            Expected(path=("CLS",), common=True),
        ),
    ),
    Refused(
        name="a number with two decimal points",
        message="ROUT:CHAN 1.2.3",
        rule=f"{NUMBERS}, -120",
        refusals=("numeric-data-error",),
    ),
    Refused(
        name="an exponent with no digits",
        message="ROUT:CHAN 1E",
        rule=f"{NUMBERS}, -120",
        refusals=("numeric-data-error",),
    ),
    Refused(
        name="a unit suffix carrying a digit",
        message="SENS:VOLT:DC:RANG 10V2",
        rule=f"{NUMBERS}, -131; {LANGUAGE}: a unit suffix is spelled in letters",
        refusals=("invalid-suffix",),
    ),
    Refused(
        name="two bad units in one message, both reported",
        message="TRIG:SOUR IMM;ROUT:CHAN0",
        rule=f"{LANGUAGE}: a message carries several units and each is answered",
        refusals=("undefined-header", "header-suffix-out-of-range"),
    ),
    Refused(
        name="a good unit after a bad one",
        message="TRIG:SOUR IMM;*IDN?",
        rule=f"{LANGUAGE}: a refused unit does not stop the units after it",
        refusals=("undefined-header",),
        commands=(Expected(path=("IDN",), query=True, common=True),),
    ),
    Refused(
        name="a refused unit leaving the path where it was",
        message=":SENS:VOLT:DC:RANG 1;TRIG;NPLC 1",
        rule=f"{LANGUAGE}: a refused unit changes nothing, the path included",
        refusals=("undefined-header",),
        commands=(
            Expected(path=("SENSE", "VOLTAGE", "DC", "RANGE"), parameters=(NumericValue(1.0),)),
            Expected(path=("SENSE", "VOLTAGE", "DC", "NPLCYCLES"), parameters=(NumericValue(1.0),)),
        ),
    ),
)


@pytest.fixture(scope="module")
def vocabulary() -> Vocabulary:
    return Vocabulary.from_profile(load_profile(VOCABULARY_PROFILE), COMMON)


def check(parsed: Parsed, expected: tuple[Expected, ...]) -> None:
    assert len(parsed.commands) == len(expected)
    for got, want in zip(parsed.commands, expected, strict=True):
        assert got.path == want.path
        assert got.query is want.query
        assert got.common is want.common
        assert got.parameters == want.parameters
        if want.suffixes is not None:
            assert got.suffixes == want.suffixes


@pytest.mark.parametrize("row", ACCEPTED, ids=lambda row: row.name)
def test_an_accepted_form_comes_to_what_the_table_says(
    row: Accepted, vocabulary: Vocabulary
) -> None:
    parsed = parse(row.message, vocabulary)

    assert parsed.errors == (), f"{row.name}: {[str(e) for e in parsed.errors]}"
    check(parsed, row.commands)


@pytest.mark.parametrize("row", REFUSED, ids=lambda row: row.name)
def test_a_refused_form_produces_the_number_the_table_says(
    row: Refused, vocabulary: Vocabulary
) -> None:
    parsed = parse(row.message, vocabulary)

    assert [error.refusal.id for error in parsed.errors] == list(row.refusals)
    assert [error.number for error in parsed.errors] == [
        BY_ID[identifier].number for identifier in row.refusals
    ]
    check(parsed, row.commands)


def test_every_row_cites_a_rule() -> None:
    """A row nobody can attribute to a rule is a row somebody invented."""
    rows: list[Accepted | Refused] = [*ACCEPTED, *REFUSED]
    for row in rows:
        assert row.rule.strip(), row.name


def test_every_refusal_in_the_table_is_reached_by_a_row() -> None:
    """A declared refusal no message produces is a number nothing answers with.

    The parser's table is what #23 drives its own test from, so a row in it that
    nothing reaches would put a number on that issue's list which no path in
    this parser can produce.
    """
    reached = {identifier for row in REFUSED for identifier in row.refusals}

    assert reached == {refusal.id for refusal in REFUSALS}


def test_every_refusal_carries_the_number_and_message_the_record_fixes() -> None:
    """The numbers and the standard messages are 0006's, quoted back exactly.

    Read out of the record rather than written here a second time, because a
    second transcription is what the record itself warns this issue against.
    """
    record = Path(__file__).parents[2] / "docs" / "decisions" / "0006-conformance-surface.md"
    lines = record.read_text(encoding="utf-8").splitlines()
    fixed = {}
    for line in lines:
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[0].startswith("-") and parts[0][1:].isdigit():
            fixed[int(parts[0])] = parts[1]

    assert fixed, "no error table was found in the record"
    for refusal in REFUSALS:
        assert refusal.number in fixed, refusal.id
        assert refusal.message == fixed[refusal.number], refusal.id


def test_a_refusal_renders_as_the_number_and_the_message(vocabulary: Vocabulary) -> None:
    """The rendered form is what the error queue in #23 will hold."""
    parsed = parse("TRIG:SOUR IMM", vocabulary)

    assert str(parsed.errors[0]).startswith('-113,"Undefined header; ')


def test_the_in_between_form_is_told_apart_from_an_unknown_subsystem(
    vocabulary: Vocabulary,
) -> None:
    """Both are -113, and the detail says which of the two happened.

    Somebody who wrote `VOLTA` is not guessing at a subsystem, and a message
    that only says the header is undefined sends them looking for one.
    """
    between = parse("SENS:VOLTA:DC:RANG 1", vocabulary).errors[0]
    unknown = parse("TRIG:SOUR IMM", vocabulary).errors[0]

    assert between.number == unknown.number == -113
    assert "neither the short form VOLT nor the long form VOLTAGE" in between.detail
    assert "nothing under the root is named TRIG" in unknown.detail


def test_an_empty_message_is_one_refusal_and_no_command(vocabulary: Vocabulary) -> None:
    parsed = parse("", vocabulary)

    assert parsed.commands == ()
    assert [error.refusal.id for error in parsed.errors] == ["invalid-separator"]
