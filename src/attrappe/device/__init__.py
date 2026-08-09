"""The instrument model: state, settings, the error queue and status reporting.

`instrument` holds what a message can change: the settings a node declares, the
reset that takes them back to their declared defaults, and the status registers.

`errors` is the queue every refusal is recorded in, at the depth the profile
declares. An instrument carries one and the dispatch pushes into it, so a client
reading the error queue reads what the parser refused and what the dispatch
refused through one question. The events that set the status bits from those
same errors are #24.
"""

from attrappe.device.errors import (
    MINIMUM_DEPTH,
    NO_ERROR,
    NO_ERROR_MESSAGE,
    NO_ERROR_NUMBER,
    QUEUE_OVERFLOW,
    QUEUE_OVERFLOW_MESSAGE,
    QUEUE_OVERFLOW_NUMBER,
    Entry,
    ErrorQueue,
)
from attrappe.device.instrument import (
    COMMAND_ERROR_BIT,
    DEVICE_ERROR_BIT,
    EVENT_SUMMARY_BIT,
    EXECUTION_ERROR_BIT,
    MASTER_SUMMARY_BIT,
    MESSAGE_AVAILABLE_BIT,
    OPERATION_COMPLETE_BIT,
    QUERY_ERROR_BIT,
    REGISTER_MAXIMUM,
    REGISTER_MINIMUM,
    SELF_TEST_PASSED,
    Instance,
    Instrument,
)

__all__ = [
    "COMMAND_ERROR_BIT",
    "DEVICE_ERROR_BIT",
    "EVENT_SUMMARY_BIT",
    "EXECUTION_ERROR_BIT",
    "MASTER_SUMMARY_BIT",
    "MESSAGE_AVAILABLE_BIT",
    "MINIMUM_DEPTH",
    "NO_ERROR",
    "NO_ERROR_MESSAGE",
    "NO_ERROR_NUMBER",
    "OPERATION_COMPLETE_BIT",
    "QUERY_ERROR_BIT",
    "QUEUE_OVERFLOW",
    "QUEUE_OVERFLOW_MESSAGE",
    "QUEUE_OVERFLOW_NUMBER",
    "REGISTER_MAXIMUM",
    "REGISTER_MINIMUM",
    "SELF_TEST_PASSED",
    "Entry",
    "ErrorQueue",
    "Instance",
    "Instrument",
]
