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

`test_the_error_queue.py` covers the queue: its order, the depth its profile
declares, what a full one does, and the assertion that every refusal either
stage of the message language can produce ends up in it. That last one is driven
from the two refusal tables, so a refusal added with nothing that provokes it
turns this directory red rather than quietly becoming an error nothing records.

It reads a second fixture, `fixtures/queue`, and the reasons are in the fixture
itself: a queue two entries deep so an overflow is three messages, and a
`SYSTem` subsystem of the profile's own beside the one the core implements.

`test_the_status_report.py` covers the other side of the registers: which event
raises which bit, driven through a session rather than by setting a register by
hand, and the status byte over the output queue an answer waits in. It shares
both fixtures, because a command error is provoked by the same message here as
it is next door and the shallow queue is what makes an overflow three messages.

One of the five bits has no event in this tree, and that file's own header says
which and why, with a check that reddens the day one arrives.
