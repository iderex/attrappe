Tests for `attrappe.transport`: the listener, the sessions and the framing.

`test_the_session.py` needs no port. `docs/decisions/0002-transport.md` names an
in-process transport beside the socket, and it is the same session object a
connected client drives, so the seed, the named streams and the instrument state
are all provable without a listener. The stream tests are the ones worth reading
first: what they hold is that adding a stream does not move an existing one,
which is the property `docs/decisions/0004-randomness.md` exists for and the one
whose failure no suite catches.

`test_the_listener.py` is the half that needs a port, and it asks the operating
system for a free one rather than choosing a number, so several of these can run
at once. The server is driven on a thread of its own, because a socket
conversation has two ends and one of them cannot be the code waiting for the
other.

Both read the dispatch's profile fixture in `tests/scpi/fixtures/instrument`. A
third profile declaring almost the same instrument would drift against the two
that exist.

Nothing here measures elapsed time. The read timeouts bound how long a failing
test takes; a read that costs the configured integration time is #34 and a fault
that delays a response is #36, and both arrive with the clock
`docs/decisions/0003-time.md` decides.
