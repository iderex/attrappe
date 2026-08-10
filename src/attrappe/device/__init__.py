"""The instrument model: state, settings, the error queue and status reporting.

`instrument` holds what a message can change: the settings a node declares, the
reset that takes them back to their declared defaults, and the status registers.

`errors` is the queue every refusal is recorded in, at the depth the profile
declares. An instrument carries one and the dispatch pushes into it through
`Instrument.record`, which is also what raises the event status bit for the same
error, so a client asking `SYSTem:ERRor?` and a client asking `*ESR?` are told
about the same refusals.
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
    ERROR_CLASSES,
    EVENT_SUMMARY_BIT,
    EXECUTION_ERROR_BIT,
    FIRST_DEVICE_SPECIFIC_NUMBER,
    MASTER_SUMMARY_BIT,
    MESSAGE_AVAILABLE_BIT,
    OPERATION_COMPLETE_BIT,
    QUERY_ERROR_BIT,
    REGISTER_MAXIMUM,
    REGISTER_MINIMUM,
    SELF_TEST_PASSED,
    Instance,
    Instrument,
    event_bit,
)

__all__ = [
    "COMMAND_ERROR_BIT",
    "DEVICE_ERROR_BIT",
    "ERROR_CLASSES",
    "EVENT_SUMMARY_BIT",
    "EXECUTION_ERROR_BIT",
    "FIRST_DEVICE_SPECIFIC_NUMBER",
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
    "event_bit",
]
