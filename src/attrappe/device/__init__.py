"""The instrument model: state, settings, the error queue and status reporting.

`instrument` holds what a message can change: the settings a node declares, the
reset that takes them back to their declared defaults, and the status registers.
The error queue is #23 and lands beside it; the events that set the status bits
are #24.
"""

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
    "OPERATION_COMPLETE_BIT",
    "QUERY_ERROR_BIT",
    "REGISTER_MAXIMUM",
    "REGISTER_MINIMUM",
    "SELF_TEST_PASSED",
    "Instance",
    "Instrument",
]
