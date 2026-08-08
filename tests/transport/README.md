Tests for `attrappe.transport`: the listener, the sessions and the framing.

Empty until #26 lands. `docs/decisions/0002-transport.md` names an in-process
transport beside the socket, so most of what lands here needs no port; a test
that does need one asks the operating system for a free port rather than
choosing a number.
