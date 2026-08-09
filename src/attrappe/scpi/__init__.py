"""The message language: parsing, the command tree, and dispatch.

`parser` reads a received message into commands and refusals. It executes
nothing and decides nothing about what a command means.

`dispatch` is what decides. It walks a parsed command into the tree the profile
declares, checks the instance, the form and the parameters, runs the command
against an `attrappe.device.Instrument`, and answers either a response or a
refusal by number. The mandatory common commands are implemented there, and the
set of them is what the parser takes as its `common` argument.
"""

from attrappe.scpi.dispatch import COMMON, MANDATORY_COMMON, Dispatch, Outcome, Refused
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
    "CharacterValue",
    "Command",
    "Dispatch",
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
]
