"""Configuration shared by both harnesses.

`--device` is declared here rather than in `tests/hardware_bound/conftest.py`
because pytest reads command-line options only from an initial conftest, and a
subdirectory conftest is not one. The option is read there, where it is
reported.
"""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Name the device the hardware-bound harness ran against.

    Nothing probes for hardware. A probe is a device node, a driver call or a
    permission prompt depending on the operating system, and the headless
    record refuses all three in this repository. So the device is stated by
    whoever runs the harness and the harness repeats what it was told, which is
    a claim by a person rather than a measurement, and reads as one.
    """
    parser.addoption(
        "--device",
        action="store",
        default="",
        metavar="NAME",
        help=(
            "the instrument the hardware-bound harness is running against; "
            "left unset, that harness reports that no device was present"
        ),
    )
