"""The dispatch table: what each command answers, and what each refusal numbers.

One row per form, the same shape as the parser's table next door. A row cites
the rule it comes from, so the table reads against the rules rather than against
the dispatch.

Two citations appear and they are different weights.
`docs/decisions/0006-conformance-surface.md` is in this tree: it fixes the
mandatory common set, which of the two forms each member answers to, and the
error numbers with their messages, so a row citing it can be checked by opening
it, and three tests below read it rather than trusting this file. The rows about
what a profile declares cite `attrappe.profile.loader`'s schema, which is a
statement of what this emulator reads out of a profile.

The state the rows run against is one instrument per test. A shared one would
make the table order-dependent, and an order-dependent table is one where a row
passes because of the row above it.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from attrappe.device import Instrument
from attrappe.profile import load_profile
from attrappe.scpi import MANDATORY_COMMON, Command, Dispatch
from attrappe.scpi.dispatch import BY_ID as EXECUTION_BY_ID
from attrappe.scpi.dispatch import COMMON
from attrappe.scpi.dispatch import REFUSALS as EXECUTION_REFUSALS
from attrappe.scpi.dispatch import Refused as DispatchRefusal

INSTRUMENT_PROFILE = Path(__file__).parent / "fixtures" / "instrument"
RECORD = Path(__file__).parents[2] / "docs" / "decisions" / "0006-conformance-surface.md"

IDENTIFICATION = "Attrappe,EMULATED-DMM-DISPATCH,0000000002,0.1.0"

RECORD_SET = "docs/decisions/0006-conformance-surface.md, the mandatory common set"
NUMBERS = "docs/decisions/0006-conformance-surface.md, the error table"
SCHEMA = "the profile schema, as attrappe.profile.loader states it"

# A line of the record's common-command block: the mnemonic, and whether the
# form it lists is the query one.
COMMON_LINE = re.compile(r"^\*([A-Z]+)(\??)$")


@dataclass(frozen=True)
class Accepted:
    """A message the dispatch runs, and the bytes it answers with."""

    name: str
    message: str
    rule: str
    response: str | None


@dataclass(frozen=True)
class Refused:
    """A message the dispatch refuses, and the refusal each unit produces."""

    name: str
    message: str
    rule: str
    refusals: tuple[str, ...]


ACCEPTED: tuple[Accepted, ...] = (
    Accepted(
        name="identification answers the four fields the profile declares",
        message="*IDN?",
        rule=f"{RECORD_SET}: identification",
        response=IDENTIFICATION,
    ),
    Accepted(
        name="reset answers nothing",
        message="*RST",
        rule=f"{RECORD_SET}: reset",
        response=None,
    ),
    Accepted(
        name="clear status answers nothing",
        message="*CLS",
        rule=f"{RECORD_SET}: clear status",
        response=None,
    ),
    Accepted(
        name="the event status enable mask reads back what was written",
        message="*ESE 24;*ESE?",
        rule=f"{RECORD_SET}: event status enable, set and query",
        response="24",
    ),
    Accepted(
        name="the event status register is zero until something sets a bit",
        message="*ESR?",
        rule=f"{RECORD_SET}: event status register, query and clear",
        response="0",
    ),
    Accepted(
        name="the service request enable mask reads back what was written",
        message="*SRE 32;*SRE?",
        rule=f"{RECORD_SET}: service request enable, set and query",
        response="32",
    ),
    Accepted(
        name="the status byte is zero with nothing set and nothing enabled",
        message="*STB?",
        rule=f"{RECORD_SET}: status byte",
        response="0",
    ),
    Accepted(
        name="operation complete sets its own bit and the register reads it",
        message="*OPC;*ESR?",
        rule=f"{RECORD_SET}: operation complete, command form",
        response="1",
    ),
    Accepted(
        name="the operation complete query answers at once",
        message="*OPC?",
        rule=f"{RECORD_SET}: operation complete, query form",
        response="1",
    ),
    Accepted(
        name="the self-test passes",
        message="*TST?",
        rule=f"{RECORD_SET}: self-test",
        response="0",
    ),
    Accepted(
        name="wait to continue answers nothing and completes",
        message="*WAI",
        rule=f"{RECORD_SET}: wait to continue, with no overlapped commands to wait for",
        response=None,
    ),
    Accepted(
        name="two queries in one message are joined by the message separator",
        message="*TST?;*OPC?",
        rule=f"{SCHEMA}: the semicolon separates message units and their answers",
        response="0;1",
    ),
    Accepted(
        name="a setting reads back its declared default before anything writes it",
        message="SENS:VOLT:DC:RANG?",
        rule=f"{SCHEMA}: a parameter's default is what it reads as until written",
        response="10.0",
    ),
    Accepted(
        name="a setting reads back what was written to it",
        message="SENS:VOLT:DC:RANG 100;RANG?",
        rule=f"{SCHEMA}: a numeric parameter inside its declared range",
        response="100.0",
    ),
    Accepted(
        name="a number carrying the unit the parameter declares",
        message="SENS:VOLT:DC:RANG 100 V;RANG?",
        rule=f"{SCHEMA}: units on a numeric parameter",
        response="100.0",
    ),
    Accepted(
        name="MAX takes the declared maximum",
        message="SENS:VOLT:DC:RANG MAX;RANG?",
        rule=f"{SCHEMA}: MIN and MAX read the declared range",
        response="1000.0",
    ),
    Accepted(
        name="MIN takes the declared minimum",
        message="SENS:VOLT:DC:RANG MIN;RANG?",
        rule=f"{SCHEMA}: MIN and MAX read the declared range",
        response="0.1",
    ),
    Accepted(
        name="DEF takes the declared default on a parameter with no numeric range",
        message="SENS:FUNC CURRENT;FUNC DEF;FUNC?",
        rule=f"{SCHEMA}: DEF reads the default, which every parameter declares",
        response="VOLTAGE",
    ),
    Accepted(
        name="character data is answered in the spelling the profile declares",
        message="SENS:FUNC current;FUNC?",
        rule=f"{SCHEMA}: a character parameter's choices",
        response="CURRENT",
    ),
    Accepted(
        name="a boolean answers as a digit and takes the word",
        message="SENS:VOLT:DC OFF;DC?",
        rule=f"{SCHEMA}: a boolean parameter",
        response="0",
    ),
    Accepted(
        name="a boolean takes the digit as well as the word",
        message="SENS:VOLT:DC 0;DC?",
        rule=f"{SCHEMA}: a boolean parameter",
        response="0",
    ),
    Accepted(
        name="a string answers quoted",
        message='DISP:TEXT "warming up";TEXT?',
        rule=f"{SCHEMA}: a string parameter",
        response='"warming up"',
    ),
    Accepted(
        name="a query over two parameters answers both, separated as the profile declares",
        message="CONF:VOLT:DC?",
        rule=f"{SCHEMA}: the declared response separator",
        response="10.0,1e-05",
    ),
    Accepted(
        name="a command over two parameters takes both",
        message="CONF:VOLT:DC 100,0.0001;:CONF:VOLT:DC?",
        rule=f"{SCHEMA}: a node's parameters are positional in declaration order",
        response="100.0,0.0001",
    ),
    Accepted(
        name="a suffix inside the declared instances",
        message="ROUT:CHAN4 ON;:ROUT:CHAN4?",
        rule=f"{SCHEMA}: a node declares how many instances of itself exist",
        response="1",
    ),
    Accepted(
        name="an omitted suffix is the first instance",
        message="ROUT:CHAN ON;:ROUT:CHAN1?",
        rule=f"{SCHEMA}: an omitted suffix means one",
        response="1",
    ),
    Accepted(
        name="an action takes no parameters and answers nothing",
        message="DISP:TEXT:CLE",
        rule=f"{SCHEMA}: a node accepting the set form only",
        response=None,
    ),
    Accepted(
        name="a query-only node answers",
        message="CAL:COUN?",
        rule=f"{SCHEMA}: a node accepting the query form only",
        response="0.0",
    ),
)


REFUSED: tuple[Refused, ...] = (
    Refused(
        name="a common command that exists only as a query",
        message="*IDN",
        rule=f"{RECORD_SET}: identification is listed as a query",
        refusals=("header-is-not-a-command",),
    ),
    Refused(
        name="a common command that exists only as a command",
        message="*RST?",
        rule=f"{RECORD_SET}: reset is listed without a query form",
        refusals=("header-is-not-a-command",),
    ),
    Refused(
        name="a parameter on a common query that takes none",
        message="*IDN? 1",
        rule=f"{NUMBERS}: -108",
        refusals=("parameter-not-allowed",),
    ),
    Refused(
        name="an enable mask above the eight bits the register has",
        message="*ESE 256",
        rule=f"{NUMBERS}: -222",
        refusals=("data-out-of-range",),
    ),
    Refused(
        name="an enable command with no mask",
        message="*ESE",
        rule=f"{NUMBERS}: -109",
        refusals=("missing-parameter",),
    ),
    Refused(
        name="an enable command with two masks",
        message="*SRE 1,2",
        rule=f"{NUMBERS}: -108",
        refusals=("parameter-not-allowed",),
    ),
    Refused(
        name="a unit on an enable mask",
        message="*ESE 8 V",
        rule=f"{NUMBERS}: -138",
        refusals=("suffix-not-allowed",),
    ),
    Refused(
        name="a quoted string as an enable mask",
        message='*ESE "8"',
        rule=f"{NUMBERS}: -158",
        refusals=("string-data-not-allowed",),
    ),
    Refused(
        name="MAX as an enable mask, which has no declared range to read it from",
        message="*ESE MAX",
        rule=f"{NUMBERS}: -148",
        refusals=("character-data-not-allowed",),
    ),
    Refused(
        name="a header stopping on a branch",
        message="SENS",
        rule=f"{SCHEMA}: a node declaring no accepted form is a branch",
        refusals=("header-is-not-a-command",),
    ),
    Refused(
        name="a query on a branch",
        message="SENS:VOLT?",
        rule=f"{SCHEMA}: a node declaring no accepted form is a branch",
        refusals=("header-is-not-a-command",),
    ),
    Refused(
        name="a command form of a query-only node",
        message="CAL:COUN 5",
        rule=f"{SCHEMA}: a node accepting the query form only",
        refusals=("header-is-not-a-command",),
    ),
    Refused(
        name="a query form of a set-only node",
        message="DISP:TEXT:CLE?",
        rule=f"{SCHEMA}: a node accepting the set form only",
        refusals=("header-is-not-a-command",),
    ),
    Refused(
        name="a suffix above the instances the node declares",
        message="ROUT:CHAN5?",
        rule=f"{NUMBERS}: -114",
        refusals=("suffix-above-the-instances",),
    ),
    Refused(
        name="a number above the parameter's declared maximum",
        message="SENS:VOLT:DC:RANG 2000",
        rule=f"{NUMBERS}: -222",
        refusals=("data-out-of-range",),
    ),
    Refused(
        name="a unit that is not the one the parameter declares",
        message="SENS:VOLT:DC:RANG 100 A",
        rule=f"{NUMBERS}: -131",
        refusals=("suffix-is-not-the-declared-unit",),
    ),
    Refused(
        name="a unit on a parameter that declares none",
        message="SENS:VOLT:DC:NPLC 1 S",
        rule=f"{NUMBERS}: -138",
        refusals=("suffix-not-allowed",),
    ),
    Refused(
        name="character data where a number is declared",
        message="SENS:VOLT:DC:RANG ONE",
        rule=f"{NUMBERS}: -148",
        refusals=("character-data-not-allowed",),
    ),
    Refused(
        name="MIN on a parameter with no numeric range to read it from",
        message="SENS:FUNC MIN",
        rule=f"{NUMBERS}: -148",
        refusals=("character-data-not-allowed",),
    ),
    Refused(
        name="a quoted string where a number is declared",
        message='SENS:VOLT:DC:RANG "100"',
        rule=f"{NUMBERS}: -158",
        refusals=("string-data-not-allowed",),
    ),
    Refused(
        name="a number where character data is declared",
        message="SENS:FUNC 1",
        rule=f"{NUMBERS}: -128",
        refusals=("numeric-data-not-allowed",),
    ),
    Refused(
        name="character data that is not one of the declared choices",
        message="SENS:FUNC POWER",
        rule=f"{NUMBERS}: -224",
        refusals=("illegal-parameter-value",),
    ),
    Refused(
        name="a number that is neither one nor zero on a switch",
        message="SENS:VOLT:DC 2",
        rule=f"{NUMBERS}: -222",
        refusals=("data-out-of-range",),
    ),
    Refused(
        name="a word a switch does not take",
        message="SENS:VOLT:DC MAYBE",
        rule=f"{NUMBERS}: -224",
        refusals=("illegal-parameter-value",),
    ),
    Refused(
        name="a unit on a switch",
        message="SENS:VOLT:DC 1 V",
        rule=f"{NUMBERS}: -138",
        refusals=("suffix-not-allowed",),
    ),
    Refused(
        name="a quoted string where a switch is declared",
        message='SENS:VOLT:DC "ON"',
        rule=f"{NUMBERS}: -158",
        refusals=("string-data-not-allowed",),
    ),
    Refused(
        name="character data where a string is declared",
        message="DISP:TEXT HELLO",
        rule=f"{NUMBERS}: -148",
        refusals=("character-data-not-allowed",),
    ),
    Refused(
        name="a number where a string is declared",
        message="DISP:TEXT 5",
        rule=f"{NUMBERS}: -128",
        refusals=("numeric-data-not-allowed",),
    ),
    Refused(
        name="fewer parameters than the node declares",
        message="CONF:VOLT:DC 100",
        rule=f"{NUMBERS}: -109",
        refusals=("missing-parameter",),
    ),
    Refused(
        name="more parameters than the node declares",
        message="CONF:VOLT:DC 100,0.0001,2",
        rule=f"{NUMBERS}: -108",
        refusals=("parameter-not-allowed",),
    ),
    Refused(
        name="a parameter on a query of the tree",
        message="SENS:VOLT:DC:RANG? 1",
        rule=f"{NUMBERS}: -108",
        refusals=("parameter-not-allowed",),
    ),
)


@pytest.fixture
def dispatch() -> Dispatch:
    return Dispatch.for_instrument(Instrument(load_profile(INSTRUMENT_PROFILE)))


@pytest.mark.parametrize("row", ACCEPTED, ids=lambda row: row.name)
def test_an_accepted_form_answers_what_the_table_says(row: Accepted, dispatch: Dispatch) -> None:
    outcome = dispatch.execute(row.message)

    assert outcome.errors == (), f"{row.name}: {[str(error) for error in outcome.errors]}"
    assert outcome.response == row.response


@pytest.mark.parametrize("row", REFUSED, ids=lambda row: row.name)
def test_a_refused_form_produces_the_number_the_table_says(
    row: Refused, dispatch: Dispatch
) -> None:
    outcome = dispatch.execute(row.message)

    assert [error.refusal.id for error in outcome.errors] == list(row.refusals)
    assert [error.number for error in outcome.errors] == [
        EXECUTION_BY_ID[identifier].number for identifier in row.refusals
    ]


@pytest.mark.parametrize("row", REFUSED, ids=lambda row: row.name)
def test_a_refused_form_sends_no_response_bytes(row: Refused, dispatch: Dispatch) -> None:
    """No bytes at all rather than an empty string.

    That is what makes a refused query look to a driver exactly like it looks
    against a real instrument: the client waits, the read times out, and nothing
    arrives. A response of `""` would be a reply, and a driver would take it.
    """
    assert dispatch.execute(row.message).response is None


def test_every_row_cites_a_rule() -> None:
    """A row nobody can attribute to a rule is a row somebody invented."""
    rows: list[Accepted | Refused] = [*ACCEPTED, *REFUSED]
    for row in rows:
        assert row.rule.strip(), row.name


def test_every_refusal_in_the_table_is_reached_by_a_row() -> None:
    """A declared refusal no message produces is a number nothing answers with."""
    reached = {identifier for row in REFUSED for identifier in row.refusals}

    assert reached == {refusal.id for refusal in EXECUTION_REFUSALS}


def read_the_common_set() -> dict[str, set[str]]:
    """The record's common-command block, as the forms it lists per mnemonic."""
    forms: dict[str, set[str]] = {}
    for line in RECORD.read_text(encoding="utf-8").splitlines():
        token = line.strip().split(maxsplit=1)[:1]
        match = COMMON_LINE.match(token[0]) if token else None
        if match is None:
            continue
        forms.setdefault(match.group(1), set()).add("query" if match.group(2) else "set")
    return forms


def test_the_mandatory_common_set_is_the_record_s_set() -> None:
    """Read out of the record rather than written here a second time.

    `0006` says none of the mandatory common commands may be dropped from the
    first release. A set declared in the code and a set declared in the record
    that agree only because somebody kept them in step is what this refuses.
    """
    forms = read_the_common_set()

    assert forms, "no common-command block was found in the record"
    assert MANDATORY_COMMON == set(forms)


def test_each_common_command_answers_the_forms_the_record_lists() -> None:
    """The record lists `*ESE` and `*ESE?` separately, and so it decides both."""
    forms = read_the_common_set()

    implemented = {
        entry.mnemonic: {
            *(["set"] if entry.on_set is not None else []),
            *(["query"] if entry.on_query is not None else []),
        }
        for entry in COMMON
    }

    assert implemented == forms


def test_every_refusal_carries_the_number_and_message_the_record_fixes() -> None:
    """The numbers and the standard messages are the record's, quoted back exactly."""
    fixed = {}
    for line in RECORD.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[0].startswith("-") and parts[0][1:].isdigit():
            fixed[int(parts[0])] = parts[1]

    assert fixed, "no error table was found in the record"
    for refusal in EXECUTION_REFUSALS:
        assert refusal.number in fixed, refusal.id
        assert refusal.message == fixed[refusal.number], refusal.id


def test_a_refusal_renders_as_the_number_and_the_message(dispatch: Dispatch) -> None:
    """The rendered form is what the error queue in #23 will hold."""
    outcome = dispatch.execute("SENS:VOLT:DC:RANG 2000")

    assert str(outcome.errors[0]).startswith('-222,"Data out of range; ')


def test_an_unknown_header_is_the_parser_s_refusal_and_no_response(dispatch: Dispatch) -> None:
    """The two stages both reach `errors`, and a driver sees one list."""
    outcome = dispatch.execute("TRIG:SOUR IMM")

    assert outcome.response is None
    assert [error.number for error in outcome.errors] == [-113]


def test_a_refused_unit_does_not_stop_the_units_after_it(dispatch: Dispatch) -> None:
    """A sender who made one mistake and one who made two can tell them apart."""
    outcome = dispatch.execute("SENS:VOLT:DC:RANG 2000;*IDN?")

    assert outcome.response == IDENTIFICATION
    assert [error.number for error in outcome.errors] == [-222]


def test_a_refused_value_leaves_the_setting_unchanged(dispatch: Dispatch) -> None:
    dispatch.execute("SENS:VOLT:DC:RANG 100")

    refused = dispatch.execute("SENS:VOLT:DC:RANG 2000")

    assert refused.errors[0].number == -222
    assert dispatch.execute("SENS:VOLT:DC:RANG?").response == "100.0"


def test_a_command_refused_on_its_second_value_writes_neither(dispatch: Dispatch) -> None:
    """Whatever "leaves the setting unchanged" means, it cannot mean half of it."""
    refused = dispatch.execute("CONF:VOLT:DC 100,2")

    assert refused.errors[0].number == -222
    assert dispatch.execute("CONF:VOLT:DC?").response == "10.0,1e-05"


def test_reset_restores_the_defaults_and_leaves_the_survivors_alone(dispatch: Dispatch) -> None:
    """The two parameters here are both called `value`, on two different nodes.

    A reset keyed by the parameter name alone would drop both or keep both, and
    the fixture declares one surviving and one not so that the two cannot agree
    by accident.
    """
    dispatch.execute("SENS:VOLT:DC:RANG 100;NPLC 1;:SENS:VOLT:DC OFF")

    dispatch.execute("*RST")

    assert dispatch.execute("SENS:VOLT:DC:RANG?").response == "10.0"
    assert dispatch.execute("SENS:VOLT:DC:NPLC?").response == "1.0"
    assert dispatch.execute("SENS:VOLT:DC?").response == "0"


def test_reset_does_not_touch_the_enable_masks(dispatch: Dispatch) -> None:
    """A driver that armed the service request before configuring keeps it armed."""
    dispatch.execute("*ESE 24;*SRE 32")

    dispatch.execute("*RST")

    assert dispatch.execute("*ESE?").response == "24"
    assert dispatch.execute("*SRE?").response == "32"


def test_clear_status_clears_the_register_and_not_the_masks(dispatch: Dispatch) -> None:
    dispatch.execute("*ESE 24;*OPC")

    dispatch.execute("*CLS")

    assert dispatch.execute("*ESR?").response == "0"
    assert dispatch.execute("*ESE?").response == "24"


def test_the_event_status_register_clears_on_read(dispatch: Dispatch) -> None:
    """The behaviour that makes a polling loop order-dependent, which is the point."""
    dispatch.execute("*OPC")

    assert dispatch.execute("*ESR?").response == "1"
    assert dispatch.execute("*ESR?").response == "0"


def test_the_status_byte_is_computed_from_the_masks_at_the_moment_it_is_read(
    dispatch: Dispatch,
) -> None:
    """The same event answers three different status bytes as the masks move.

    A constant cannot do that, and `0006` says why it matters: software that
    polls the status byte is the fragile software this board exists to break
    honestly.
    """
    dispatch.execute("*OPC")

    assert dispatch.execute("*STB?").response == "0"

    dispatch.execute("*ESE 1")
    assert dispatch.execute("*STB?").response == "32"

    dispatch.execute("*SRE 32")
    assert dispatch.execute("*STB?").response == "96"


def test_reading_the_status_byte_clears_nothing(dispatch: Dispatch) -> None:
    dispatch.execute("*ESE 1;*OPC")

    assert dispatch.execute("*STB?").response == "32"
    assert dispatch.execute("*STB?").response == "32"
    assert dispatch.execute("*ESR?").response == "1"


def test_two_instances_of_one_node_are_two_settings(dispatch: Dispatch) -> None:
    dispatch.execute("ROUT:CHAN1 ON")

    assert dispatch.execute("ROUT:CHAN1?").response == "1"
    assert dispatch.execute("ROUT:CHAN2?").response == "0"


def test_the_response_separator_is_the_one_the_profile_declares(dispatch: Dispatch) -> None:
    """Replaced rather than declared in a second fixture.

    The assertion is about the join reading the profile, and a second profile
    directory would prove the same thing while adding a file whose only defect
    would be one character.
    """
    profile = dataclasses.replace(dispatch.instrument.profile, separator="|")
    piped = Dispatch.for_instrument(Instrument(profile))

    assert piped.execute("CONF:VOLT:DC?").response == "10.0|1e-05"
    assert piped.execute("*TST?;*OPC?").response == "0;1", "the unit separator is not the profile's"


def test_a_command_built_by_hand_for_a_header_this_profile_lacks_is_refused(
    dispatch: Dispatch,
) -> None:
    """The guard behind `execute`, which `execute` itself cannot reach.

    The parser resolves a header against the same profile this walks, so no
    message produces a command naming a path the tree does not have. A caller
    building one by hand can, and a crash is a worse answer to that than a
    number.
    """
    invented = Command(path=("TRIGGER", "SOURCE"), suffixes=(1, 1), source="TRIG:SOUR")

    refusal = dispatch._one(invented)

    assert isinstance(refusal, DispatchRefusal)
    assert refusal.number == -113
