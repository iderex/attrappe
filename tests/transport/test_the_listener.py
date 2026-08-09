"""The listener: what it binds, how it frames, and what it does on the way out.

These are the tests that need a port, and they ask the operating system for a
free one rather than choosing a number. `docs/decisions/0003-time.md` keeps a
real clock on the socket-level tests deliberately, because a timeout is a race
between two parties and a race with one side frozen is not the thing being
tested. Nothing here waits on elapsed time to decide anything: every assertion
is on bytes that arrived, and the read timeout below is a limit on how long a
failing test takes rather than a thing being measured.

The server is driven on a thread of its own, because a socket conversation has
two ends and one of them cannot be the code waiting for the other.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

from attrappe.profile import load_profile
from attrappe.transport import (
    DEFAULT_MAXIMUM_MESSAGE,
    DEFAULT_PORT,
    DEFAULT_TERMINATOR,
    LOOPBACK,
    Server,
)

PROFILE = Path(__file__).parents[1] / "scpi" / "fixtures" / "instrument"
IDENTIFICATION = "Attrappe,EMULATED-DMM-DISPATCH,0000000002,0.1.0"

# How long a client waits for bytes before the test fails. Long enough that a
# loaded machine does not fail a working server, short enough that a broken one
# does not hold the suite. Nothing is measured against it.
PATIENCE = 10.0

# How long a client waits when the correct answer is that nothing arrives. This
# one bounds a negative assertion, so it is short on purpose: every second here
# is a second the suite spends proving an absence.
BRIEF = 0.4

RESTARTS = 100

# How many messages the client that never reads sends before it goes. Enough
# that the listener takes several of them out of one read, which is the shape
# the defect needs: the first answer finds the peer gone and the rest are still
# in the buffer behind it.
IMPOLITE_MESSAGES = 60

# How long one stepped turn of the loop waits, and how many turns are taken
# after the impolite client has gone. The wait bounds a turn with nothing ready
# rather than measuring anything, and the count is small because everything the
# turn has to see is already in the socket by then.
STEP = 0.2
STEPS_AFTER_THE_CLOSE = 6


@pytest.fixture
def server() -> Iterator[Server]:
    """A listener on a port the operating system picked, serving on its own thread."""
    running = Server(load_profile(PROFILE), port=0, seed=4242)
    running.start()
    running.run_in_background()
    try:
        yield running
    finally:
        running.stop()


@pytest.fixture
def clients() -> Iterator[list[socket.socket]]:
    """Every socket a test opened, closed whether it passed or not.

    An unclosed socket is a ResourceWarning, and this repository's
    configuration makes a warning an error, so a leak here fails the run rather
    than scrolling past in it.
    """
    opened: list[socket.socket] = []
    try:
        yield opened
    finally:
        for client in opened:
            client.close()


def connect(server: Server, clients: list[socket.socket]) -> socket.socket:
    where = server.bound
    assert where is not None
    client = socket.create_connection(where, timeout=PATIENCE)
    clients.append(client)
    return client


def ask(client: socket.socket, message: str) -> str:
    """Send one message and read one answer, up to the terminator."""
    client.sendall((message + DEFAULT_TERMINATOR).encode("ascii"))
    return read_one(client)


def read_one(client: socket.socket, patience: float = PATIENCE) -> str:
    """One answer, and not a byte of the next one.

    A byte at a time, because a socket has no way to give back what was read
    past the terminator. Reading a block instead would take the answers to two
    queries in one call whenever they arrive together, which is exactly what
    they do when a test sends both in one packet, and the failure that produces
    depends on how the two ends were scheduled.
    """
    client.settimeout(patience)
    held = bytearray()
    terminator = DEFAULT_TERMINATOR.encode("ascii")
    while not held.endswith(terminator):
        byte = client.recv(1)
        if not byte:
            break
        held.extend(byte)
    return held.decode("ascii").removesuffix(DEFAULT_TERMINATOR)


def silence(client: socket.socket) -> bool:
    """True when nothing arrives within the brief patience above."""
    client.settimeout(BRIEF)
    try:
        return client.recv(1024) == b""
    except TimeoutError:
        return True


def test_the_default_bind_is_loopback() -> None:
    """The property `docs/decisions/0010-data-protection.md` states.

    The port is asked for as zero so the assertion is about the interface and
    not about whether this machine happens to have 5025 free, and the default
    port is asserted separately off the declared value.
    """
    with Server(load_profile(PROFILE), port=0) as bound:
        where = bound.bound
        assert where is not None
        assert where[0] == LOOPBACK

    assert Server(load_profile(PROFILE)).host == LOOPBACK
    assert Server(load_profile(PROFILE)).port == DEFAULT_PORT


def test_the_assigned_port_is_reported_when_zero_was_requested(server: Server) -> None:
    """What lets a suite run several of these at once without agreeing on numbers."""
    where = server.bound
    assert where is not None
    assert where[1] != 0


def test_the_announcement_names_what_was_bound_rather_than_what_was_asked_for(
    server: Server,
) -> None:
    where = server.bound
    assert where is not None
    announcement = server.announcement()

    assert f"{where[0]}:{where[1]}" in announcement
    assert "seed 4242" in announcement
    assert "port 0" not in announcement


def test_nothing_is_bound_before_start_and_nothing_after_stop() -> None:
    """The three states are read into names before any of them is asserted.

    Asserting on `bound` three times in a row would be three assertions about
    one expression, and the checker narrows the first one over the other two.
    """
    idle = Server(load_profile(PROFILE), port=0)

    before, silent = idle.bound, idle.announcement()
    idle.start()
    during = idle.bound
    idle.stop()
    after = idle.bound

    assert before is None
    assert "not listening" in silent
    assert during is not None
    assert after is None


def test_two_concurrent_connections_have_independent_state(
    server: Server, clients: list[socket.socket]
) -> None:
    """The done-condition the issue leads with: change one, read the other's default."""
    first = connect(server, clients)
    second = connect(server, clients)

    assert ask(first, "SENS:VOLT:DC:RANG 100;RANG?") == "100.0"

    assert ask(second, "SENS:VOLT:DC:RANG?") == "10.0"
    assert ask(first, "SENS:VOLT:DC:RANG?") == "100.0"


def test_two_connections_get_two_seeds_and_both_are_reproducible(
    server: Server, clients: list[socket.socket]
) -> None:
    """Derived from the server's seed and the ordinal, not shared and not random.

    Sharing would make the second session's sequence depend on how far the
    first one had got, which is the entanglement `0004-randomness.md` refuses.
    """
    connect(server, clients)
    connect(server, clients)
    ask(clients[0], "*IDN?")
    ask(clients[1], "*IDN?")

    seeds = [session.seed for session in server.sessions]

    assert len(set(seeds)) == 2

    with Server(load_profile(PROFILE), port=0, seed=4242) as twin:
        twin.run_in_background()
        again = [socket.create_connection(_where(twin), timeout=PATIENCE) for _ in range(2)]
        clients.extend(again)
        ask(again[0], "*IDN?")
        ask(again[1], "*IDN?")

        assert [session.seed for session in twin.sessions] == seeds


def _where(server: Server) -> tuple[str, int]:
    where = server.bound
    assert where is not None
    return where


def test_a_query_answers_with_the_terminator_the_server_frames_on(
    server: Server, clients: list[socket.socket]
) -> None:
    client = connect(server, clients)
    client.sendall(b"*IDN?\n")
    client.settimeout(PATIENCE)

    assert client.recv(1024) == (IDENTIFICATION + "\n").encode("ascii")


def test_several_messages_in_one_packet_are_several_messages(
    server: Server, clients: list[socket.socket]
) -> None:
    client = connect(server, clients)

    client.sendall(b"SENS:VOLT:DC:RANG 100\nSENS:VOLT:DC:RANG?\n*TST?\n")

    assert read_one(client) == "100.0"
    assert read_one(client) == "0"


def test_one_message_split_across_packets_is_one_message(
    server: Server, clients: list[socket.socket]
) -> None:
    client = connect(server, clients)

    for byte in b"*IDN?\n":
        client.sendall(bytes([byte]))

    assert read_one(client) == IDENTIFICATION


def test_a_command_that_answers_nothing_sends_no_bytes(
    server: Server, clients: list[socket.socket]
) -> None:
    """A refused unit and a command with no response are both silence on the wire."""
    client = connect(server, clients)

    client.sendall(b"*RST\nSENS:VOLT:DC:RANG 2000\n")

    assert silence(client)


def test_a_message_longer_than_the_limit_is_refused_rather_than_accepted(
    server: Server, clients: list[socket.socket]
) -> None:
    """Refused as a message, and the connection is still usable afterwards.

    The oversize message is a header this profile would otherwise answer for,
    so a server that accepted it would answer rather than refuse, and the
    assertion tells the two apart by what comes back.
    """
    client = connect(server, clients)
    oversize = "SENS:VOLT:DC:RANG " + "9" * DEFAULT_MAXIMUM_MESSAGE

    client.sendall((oversize + "\n").encode("ascii"))

    assert ask(client, "SENS:VOLT:DC:RANG?") == "10.0"
    assert [refusal.number for refusal in server.sessions[0].refusals] == [-363]


def test_a_client_that_never_terminates_is_refused_at_the_bound(
    server: Server, clients: list[socket.socket]
) -> None:
    """The wrong-terminator case, which is the one that actually happens.

    Both assertions are made before any terminator is sent, and that is the
    whole of what separates this from the test above it. A server that only
    checked the length of a message it had already cut out would still refuse
    this one, once the terminator finally arrived; for a client sending the
    wrong terminator it never arrives, and until then the bytes are held in
    this process. So what is asserted here is that the refusal exists and the
    bytes are gone while the client is still mid-message.
    """
    client = connect(server, clients)

    client.sendall(b"?" * (DEFAULT_MAXIMUM_MESSAGE * 3))
    assert silence(client)

    assert [refusal.number for refusal in server.sessions[0].refusals] == [-363]
    assert sum(server.buffered) <= DEFAULT_MAXIMUM_MESSAGE

    assert ask(client, "\n*IDN?") == IDENTIFICATION


def test_a_byte_outside_the_alphabet_is_refused(
    server: Server, clients: list[socket.socket]
) -> None:
    client = connect(server, clients)

    client.sendall(b"*IDN\xff?\n")
    assert silence(client)

    assert ask(client, "*IDN?") == IDENTIFICATION
    assert [refusal.number for refusal in server.sessions[0].refusals] == [-101]


def test_a_declared_terminator_is_the_one_it_frames_on(clients: list[socket.socket]) -> None:
    """A terminator that is not the default, and more than one byte of it."""
    with Server(load_profile(PROFILE), port=0, terminator="\r\n") as other:
        other.run_in_background()
        client = socket.create_connection(_where(other), timeout=PATIENCE)
        clients.append(client)

        client.sendall(b"*IDN?\r\n")
        client.settimeout(PATIENCE)

        assert client.recv(1024) == (IDENTIFICATION + "\r\n").encode("ascii")


def test_a_client_that_disconnects_leaves_the_server_serving(
    server: Server, clients: list[socket.socket]
) -> None:
    first = connect(server, clients)
    ask(first, "*IDN?")
    first.close()

    second = connect(server, clients)

    assert ask(second, "*IDN?") == IDENTIFICATION


def test_a_client_that_closes_without_reading_leaves_the_server_serving(
    clients: list[socket.socket],
) -> None:
    """The impolite client, which is the ordinary one.

    A driver whose run ended, a client that timed out and gave up, a process
    that was interrupted: none of them read what they asked for. The listener
    takes several of their messages out of one read, finds the peer gone while
    answering the first, and has to not fall over the rest.

    This one steps the loop from the test thread rather than running it on a
    thread of its own. The defect is in the order of three things inside one
    call, and against a background thread whether they happen in that order at
    all depends on how the two ends were scheduled: the first version of this
    test ran the loop in the background, passed, and went on passing with both
    halves of the repair deleted. Stepping makes the order the test's rather
    than the operating system's.

    Two assertions, because a dead loop shows up as both: the step itself does
    not raise, and a client connecting afterwards is still served.
    """
    stepped = Server(load_profile(PROFILE), port=0)
    stepped.start()
    try:
        impolite = socket.create_connection(_where(stepped), timeout=PATIENCE)
        clients.append(impolite)
        stepped.serve(STEP)

        for _ in range(IMPOLITE_MESSAGES):
            impolite.sendall(b"*IDN?\n")
        impolite.close()
        for _ in range(STEPS_AFTER_THE_CLOSE):
            stepped.serve(STEP)

        assert stepped.sessions == ()

        polite = socket.create_connection(_where(stepped), timeout=PATIENCE)
        clients.append(polite)
        stepped.serve(STEP)
        polite.sendall(b"*IDN?\n")
        stepped.serve(STEP)

        assert read_one(polite) == IDENTIFICATION
    finally:
        stepped.stop()


def test_starting_a_server_that_is_already_listening_is_refused(server: Server) -> None:
    with pytest.raises(RuntimeError):
        server.start()
    with pytest.raises(RuntimeError):
        server.run_in_background()


def test_serving_before_starting_is_refused() -> None:
    with pytest.raises(RuntimeError):
        Server(load_profile(PROFILE), port=0).serve()


def test_stopping_twice_and_stopping_what_never_started_are_both_fine() -> None:
    idle = Server(load_profile(PROFILE), port=0)
    idle.stop()

    idle.start()
    idle.stop()
    idle.stop()

    assert idle.bound is None


def test_a_hundred_starts_and_stops_in_one_process_exhaust_nothing() -> None:
    """The done-condition about shutdown, and it is about handles rather than ports.

    Each round asks for a port of zero, so this is not a hundred rounds against
    one number. What it would catch is a listener, a selector or a socket pair
    that stop does not release: a hundred of any of those leaked is a hundred
    handles this process still holds, and the round after that fails.
    """
    profile = load_profile(PROFILE)
    ports = set()
    for _ in range(RESTARTS):
        running = Server(profile, port=0)
        host, port = running.start()
        ports.add(port)
        assert host == LOOPBACK
        running.stop()

    assert len(ports) > 1, "the operating system handed out one port a hundred times"


def test_a_port_released_by_stop_can_be_bound_again() -> None:
    """The other half of a clean shutdown: the number goes back."""
    profile = load_profile(PROFILE)
    first = Server(profile, port=0)
    _, port = first.start()
    first.stop()

    second = Server(profile, port=port)
    try:
        assert second.start()[1] == port
    finally:
        second.stop()
