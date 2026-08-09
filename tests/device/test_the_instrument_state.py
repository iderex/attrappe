"""The instrument model on its own, without a message in front of it.

`tests/scpi/test_the_dispatch.py` drives the same object through the wire, which
is where the commands are proved. What is here is what a message cannot reach or
cannot separate: that a setting nobody wrote costs nothing to hold, that a reset
tells two parameters of the same name on two nodes apart, and that the status
byte is arithmetic over the registers rather than a value somebody stored.

The profile is the dispatch's fixture rather than a second one. Two fixtures
declaring almost the same instrument would drift, and the interesting properties
here are the ones that fixture was built to have.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from attrappe.device import (
    COMMAND_ERROR_BIT,
    EVENT_SUMMARY_BIT,
    MASTER_SUMMARY_BIT,
    OPERATION_COMPLETE_BIT,
    SELF_TEST_PASSED,
    Instrument,
)
from attrappe.profile import Parameter, Profile, load_profile

PROFILE = Path(__file__).parents[1] / "scpi" / "fixtures" / "instrument"

RANGE = ("SENSE", "VOLTAGE", "DC", "RANGE")
NPLCYCLES = ("SENSE", "VOLTAGE", "DC", "NPLCYCLES")
CHANNEL = ("ROUTE", "CHANNEL")


@pytest.fixture
def profile() -> Profile:
    return load_profile(PROFILE)


@pytest.fixture
def instrument(profile: Profile) -> Instrument:
    return Instrument(profile)


def parameter_of(instrument: Instrument, path: tuple[str, ...], name: str) -> Parameter:
    node = instrument.node_at(path)
    assert node is not None, path
    for parameter in node.parameters:
        if parameter.name == name:
            return parameter
    raise AssertionError(f"{':'.join(path)} declares no parameter named {name}")


def instance(path: tuple[str, ...], *suffixes: int) -> tuple[tuple[str, int], ...]:
    """The walked path a dispatched command produces, with a suffix per step."""
    filled = suffixes or tuple(1 for _ in path)
    return tuple(zip(path, filled, strict=True))


def test_a_setting_nobody_wrote_reads_as_its_declared_default(instrument: Instrument) -> None:
    """Nothing is stored until something writes it.

    A node declaring several hundred instances would otherwise cost an entry per
    instance before a client had said anything, and the store would be full of
    values indistinguishable from the defaults they were copied from.
    """
    parameter = parameter_of(instrument, RANGE, "value")

    assert instrument.settings == {}
    assert instrument.value(instance(RANGE), parameter) == parameter.default


def test_two_instances_of_one_node_hold_two_values(instrument: Instrument) -> None:
    parameter = parameter_of(instrument, CHANNEL, "state")

    instrument.write(instance(CHANNEL, 1, 3), parameter, True)

    assert instrument.value(instance(CHANNEL, 1, 3), parameter) is True
    assert instrument.value(instance(CHANNEL, 1, 4), parameter) is False


def test_a_reset_tells_two_parameters_of_one_name_on_two_nodes_apart(
    instrument: Instrument,
) -> None:
    """Both are called `value`. One survives a reset and the other does not.

    A reset keyed by the parameter name alone drops both or keeps both, and
    either way it is right about one of them by accident.
    """
    volatile = parameter_of(instrument, RANGE, "value")
    survivor = parameter_of(instrument, NPLCYCLES, "value")
    instrument.write(instance(RANGE), volatile, 100.0)
    instrument.write(instance(NPLCYCLES), survivor, 1.0)

    instrument.reset()

    assert instrument.value(instance(RANGE), volatile) == volatile.default
    assert instrument.value(instance(NPLCYCLES), survivor) == 1.0


def test_a_reset_leaves_the_registers_alone(instrument: Instrument) -> None:
    """A driver that armed the service request before configuring keeps it armed."""
    instrument.event_status_enable = 24
    instrument.service_request_enable = 32
    instrument.set_event_status(OPERATION_COMPLETE_BIT)

    instrument.reset()

    assert instrument.event_status_enable == 24
    assert instrument.service_request_enable == 32
    assert instrument.event_status == OPERATION_COMPLETE_BIT


def test_clearing_the_status_leaves_the_masks_alone(instrument: Instrument) -> None:
    instrument.event_status_enable = 24
    instrument.set_event_status(OPERATION_COMPLETE_BIT)

    instrument.clear_status()

    assert instrument.event_status == 0
    assert instrument.event_status_enable == 24


def test_reading_the_event_status_register_clears_it(instrument: Instrument) -> None:
    instrument.set_event_status(OPERATION_COMPLETE_BIT)

    assert instrument.read_event_status() == OPERATION_COMPLETE_BIT
    assert instrument.read_event_status() == 0


def test_the_status_byte_is_the_registers_through_their_masks(instrument: Instrument) -> None:
    """Computed at the moment it is read, and nothing about it is stored.

    The bit is raised by a condition the enable mask does not pass, so the same
    register answers two different status bytes as the mask moves. A stored
    value cannot do that, and a constant cannot do it either.
    """
    instrument.set_event_status(COMMAND_ERROR_BIT)

    assert instrument.status_byte() == 0

    instrument.event_status_enable = COMMAND_ERROR_BIT
    assert instrument.status_byte() == EVENT_SUMMARY_BIT

    instrument.service_request_enable = EVENT_SUMMARY_BIT
    assert instrument.status_byte() == EVENT_SUMMARY_BIT | MASTER_SUMMARY_BIT


def test_reading_the_status_byte_clears_nothing(instrument: Instrument) -> None:
    instrument.event_status_enable = OPERATION_COMPLETE_BIT
    instrument.set_event_status(OPERATION_COMPLETE_BIT)

    assert instrument.status_byte() == EVENT_SUMMARY_BIT
    assert instrument.status_byte() == EVENT_SUMMARY_BIT
    assert instrument.read_event_status() == OPERATION_COMPLETE_BIT


def test_the_self_test_passes(instrument: Instrument) -> None:
    """Zero is pass. There is no hardware to test and no self-test model.

    A profile that wants a failing self-test gets one as a quirk in #38, which
    is where a device that reports success while leaving a setting altered
    belongs.
    """
    assert instrument.self_test() == SELF_TEST_PASSED


def test_a_path_the_tree_does_not_have_is_not_a_node(instrument: Instrument) -> None:
    assert instrument.node_at(("TRIGGER", "SOURCE")) is None
    assert instrument.node_at(RANGE) is not None
