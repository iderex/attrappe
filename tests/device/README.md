Tests for `attrappe.device`: the instrument model, its state, the error queue
and the status registers.

`test_the_instrument_state.py` covers the settings store, the reset and the
status registers, without a message in front of them. What a command answers is
proved in `tests/scpi/test_the_dispatch.py`, which drives the same object
through the wire; what is here is what the wire cannot reach or cannot
separate, such as a reset telling two parameters of the same name on two
different nodes apart.

It reads the dispatch's profile fixture rather than a second one, because two
fixtures declaring almost the same instrument drift, and the properties tested
here are the ones that fixture was built to have.

The error queue is #23 and the events that set the status bits are #24. Both
land in this directory.
