"""The message language: parsing, the command tree, and dispatch.

`parser` reads a received message into commands and refusals. It executes
nothing and decides nothing about what a command means; the dispatch is #22 and
lands beside it.
"""

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
    "DEFAULT_SUFFIX",
    "REFUSALS",
    "CharacterValue",
    "Command",
    "NamedValue",
    "NumericValue",
    "ParseError",
    "Parsed",
    "Refusal",
    "StringValue",
    "Value",
    "Vocabulary",
    "parse",
]
