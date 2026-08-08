"""The hardware-bound harness.

`docs/decisions/0008-headless.md` names this directory and what belongs in it:
anything that cannot meet all six constraints of the default suite. Its
membership on the day that record was written is anything using a serial port
pair, anything using the USB test-and-measurement class, anything comparing the
emulator against a physical instrument, and any soak run long enough to need
real elapsed time.

Every test here carries the `hardware_bound` marker. The marker is what the
default run deselects, by `addopts` in `pyproject.toml`, so a test that lands
here without it joins the default run and takes its constraints with it. There
is nothing in this repository that refuses that, and it is worth knowing rather
than assuming: the exclusion is by marker and this directory is a convention
around it.

The directory holds no test yet. The first one it is owed is the soak run, in
#46.
"""

import pytest


def pytest_report_header(config: pytest.Config) -> str:
    """Say which device this run was told about, or that there was none.

    The headless record requires that a run of this harness states which device
    it ran against or that no device was present, because a skip and a pass look
    alike in a summary line and this harness is the one that gets skipped.
    """
    device = str(config.getoption("--device") or "")
    if not device:
        return "hardware-bound harness: no device was present, --device was not given"
    return f"hardware-bound harness: ran against {device}, as stated by --device"
