"""The message language: parsing, the command tree, and dispatch.

`parser` reads a received message into commands and refusals. It executes
nothing and decides nothing about what a command means.

`dispatch` is what decides. It walks a parsed command into the tree the profile
declares, checks the instance, the form and the parameters, runs the command
against an `attrappe.device.Instrument`, and answers either a response or a
refusal by number. The mandatory common commands are implemented there, and the
set of them is what the parser takes as its `common` argument. So is the part of
the mandatory system subsystem that reads the error queue, which the parser
takes as its `core` argument for the same reason.

Every refusal either stage produces is pushed into the instrument's error queue
by the dispatch, so a client asking what went wrong asks one question and gets
both stages' answers.
"""

from attrappe.scpi.dispatch import (
    COMMON,
    MANDATORY_COMMON,
    SYSTEM_ANSWERS,
    SYSTEM_NODES,
    Dispatch,
    Error,
    Outcome,
    Refused,
    queue_entry,
)
from attrappe.scpi.parser import (
    BY_ID,
    DEFAULT_SUFFIX,
    REFUSALS,
    CharacterValue,
    Command,
    NamedValue,
    NumericValue,
    Parsed,
    ParseError,
    Refusal,
    StringValue,
    Value,
    Vocabulary,
    parse,
)

__all__ = [
    "BY_ID",
    "COMMON",
    "DEFAULT_SUFFIX",
    "MANDATORY_COMMON",
    "REFUSALS",
    "SYSTEM_ANSWERS",
    "SYSTEM_NODES",
    "CharacterValue",
    "Command",
    "Dispatch",
    "Error",
    "NamedValue",
    "NumericValue",
    "Outcome",
    "ParseError",
    "Parsed",
    "Refusal",
    "Refused",
    "StringValue",
    "Value",
    "Vocabulary",
    "parse",
    "queue_entry",
]
