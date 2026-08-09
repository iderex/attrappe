"""The listener a driver connects to, and the framing underneath it.

    from attrappe.transport import Server

    with Server(profile, port=0) as server:
        host, port = server.bound

`docs/decisions/0002-transport.md` makes the raw TCP socket the primary surface
and the only one required for the parity goal, reached with a resource string of
the form `TCPIP0::<host>::<port>::SOCKET`. This is that surface and no other.

## One thread, and the reason it is not one per connection

The listener, the wakeup and every open connection are multiplexed in one
selector loop on one thread. Several clients are served at once and each keeps
its own session, so the concurrency the issue asks for is there; what is not
there is a thread per client, and the reason is what `stop` has to do. A thread
blocked in `recv` is stopped either by closing the socket underneath it, which
is a race on every platform and an error on some, or by a timeout it wakes up
on, which puts real elapsed time into a shutdown a test performs a hundred
times. The selector wakes on a byte written to a socket pair instead, so `stop`
returns as soon as the loop notices, and it notices immediately.

## The framing, and what bounds it

Bytes accumulate per connection until the configured terminator arrives, and
what precedes it is one message. The default terminator is a single newline with
no carriage return before it, which is `0002`'s.

A buffer that passes the configured maximum with no terminator in it is refused
with `-363` and thrown away, and everything up to the next terminator is thrown
away with it. Refusing rather than growing is the point: a client that never
sends a terminator is otherwise a client that allocates memory in this process
until something dies, and a wrong terminator is the most common configuration
mistake there is on this surface.

A byte outside the message alphabet is refused with `-101`. The alphabet is
ASCII, because that is what the message language is written in, and a message
carrying anything else is one this emulator would have to guess at.

## The loopback default

The bound interface defaults to loopback and binding anywhere else is an
explicit argument. `docs/decisions/0010-data-protection.md` states the property
and gives the reason the other default is worse: an emulator reachable from a
laboratory network answers to anyone who connects, in a building where the real
instruments are.

`announcement` is the line naming the interface, the port and the seed that were
actually bound and chosen, rather than the ones that were asked for. Printing it
is #27's, which is the command line an operator runs; a library that printed on
its own would print into a test suite.

## What is not here yet

Nothing in this file measures time. A read that costs the configured integration
time is #34 and a fault that delays a response is #36; both arrive with the
clock `0003-time.md` decides, and there is no clock in this tree.

The refusals reach `Session.refusals`, which is a list rather than the queue with
a depth and an overflow behaviour that #23 builds.
"""

from __future__ import annotations

import selectors
import socket
import threading
from dataclasses import dataclass, field
from types import TracebackType

from attrappe.profile import Profile
from attrappe.scpi import Refusal, Refused
from attrappe.transport.session import Session, choose_seed, stream_seed

# The loopback address and the port `0002-transport.md` fixes as the default.
LOOPBACK = "127.0.0.1"
DEFAULT_PORT = 5025

# The terminator that record fixes: one newline, and no carriage return before
# it. It is configurable because instruments disagree about it, and a wrong one
# looks exactly like a hang.
DEFAULT_TERMINATOR = "\n"

# How many bytes may accumulate on one connection with no terminator in them.
# Chosen as a round number well above any message this language produces and far
# below anything that matters to a host: the number is a bound rather than a
# budget, and what it prevents is unbounded growth rather than a large message.
DEFAULT_MAXIMUM_MESSAGE = 4096

# What one read takes from the socket. Smaller than the bound above, so a
# connection sending more than the bound in one burst still meets it.
READ_SIZE = 1024

# The alphabet the message language is written in.
ENCODING = "ascii"

# The numbers and the standard messages are
# `docs/decisions/0006-conformance-surface.md`'s. What each row adds is the case
# the framing produces it for, and both are cases with no command in them yet.
REFUSALS: tuple[Refusal, ...] = (
    Refusal(
        id="input-buffer-overrun",
        number=-363,
        message="Input buffer overrun",
        case="bytes accumulating past the configured maximum with no terminator among "
        "them, which is what a client sending the wrong terminator does",
    ),
    Refusal(
        id="byte-outside-the-message-alphabet",
        number=-101,
        message="Invalid character",
        case="a byte the message alphabet has no character for, arriving on the wire "
        "before anything can be read as a header or a parameter",
    ),
)

BY_ID: dict[str, Refusal] = {refusal.id: refusal for refusal in REFUSALS}


@dataclass
class Connection:
    """One open socket, the session behind it, and the bytes not yet framed."""

    socket: socket.socket
    session: Session
    buffer: bytearray = field(default_factory=bytearray)
    discarding: bool = False


@dataclass
class Server:
    """A listener on one interface and one port, one session per connection.

    `port` may be zero, in which case the operating system assigns one and
    `bound` reports it. That is what lets a suite run several of these at once
    without agreeing on numbers first.
    """

    profile: Profile
    host: str = LOOPBACK
    port: int = DEFAULT_PORT
    terminator: str = DEFAULT_TERMINATOR
    maximum_message: int = DEFAULT_MAXIMUM_MESSAGE
    seed: int = field(default_factory=choose_seed)
    _listener: socket.socket | None = field(default=None, repr=False)
    _selector: selectors.BaseSelector | None = field(default=None, repr=False)
    _wake_in: socket.socket | None = field(default=None, repr=False)
    _wake_out: socket.socket | None = field(default=None, repr=False)
    _connections: dict[socket.socket, Connection] = field(default_factory=dict, repr=False)
    _accepted: int = field(default=0, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)

    @property
    def bound(self) -> tuple[str, int] | None:
        """The interface and port actually bound, or None when nothing is."""
        if self._listener is None:
            return None
        host, port = self._listener.getsockname()[:2]
        return str(host), int(port)

    @property
    def sessions(self) -> tuple[Session, ...]:
        """The sessions of the connections open now, oldest first."""
        return tuple(connection.session for connection in self._connections.values())

    @property
    def buffered(self) -> tuple[int, ...]:
        """Bytes held per open connection, waiting for a terminator.

        This is what the bound is about, so it is readable rather than private:
        a claim that a connection was refused rather than buffered without
        bound is a claim about this number.
        """
        return tuple(len(connection.buffer) for connection in self._connections.values())

    def announcement(self) -> str:
        """The line a caller prints at startup, naming what was bound.

        What was bound rather than what was asked for, because a port of zero
        was asked for and a port of zero is not what a client connects to.
        """
        where = self.bound
        if where is None:
            return "attrappe: not listening"
        host, port = where
        return (
            f"attrappe: listening on {host}:{port}, "
            f"profile {self.profile.name}, seed {self.seed}, "
            f"terminator {self.terminator!r}"
        )

    def start(self) -> tuple[str, int]:
        """Bind, listen, and answer the interface and port that were bound."""
        if self._listener is not None:
            raise RuntimeError("this server is already listening")

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind((self.host, self.port))
            listener.listen()
            listener.setblocking(False)
        except BaseException:
            listener.close()
            raise

        self._wake_out, self._wake_in = socket.socketpair()
        self._wake_in.setblocking(False)
        self._listener = listener
        self._selector = selectors.DefaultSelector()
        self._selector.register(listener, selectors.EVENT_READ)
        self._selector.register(self._wake_in, selectors.EVENT_READ)
        host, port = listener.getsockname()[:2]
        return str(host), int(port)

    def serve_forever(self) -> None:
        """Handle connections until `stop` is called. This is what #27 runs."""
        while self.serve():
            pass

    def run_in_background(self) -> None:
        """Serve on a thread of its own, so a caller can go on doing something.

        The thread is what a client on the same process needs: a socket
        conversation has two ends and one of them cannot be the code waiting for
        the other. `stop` joins it before it closes anything, so nothing here
        closes a socket the loop is about to read.
        """
        if self._thread is not None:
            raise RuntimeError("this server is already serving")
        self._thread = threading.Thread(target=self.serve_forever, name="attrappe-serve")
        self._thread.start()

    def stop(self) -> None:
        """Stop serving, close every connection and release the port.

        Safe to call twice, and safe to call on a server that never started.
        Releasing the port is what lets a suite start and stop this a hundred
        times in one process, and closing every socket is what keeps the run
        from ending in a warning about a socket nobody closed, which this
        repository's configuration makes an error.
        """
        if self._thread is not None:
            self.wake()
            self._thread.join()
            self._thread = None
        for connection in list(self._connections.values()):
            self._close(connection)
        if self._selector is not None:
            if self._listener is not None:
                self._selector.unregister(self._listener)
            if self._wake_in is not None:
                self._selector.unregister(self._wake_in)
            self._selector.close()
            self._selector = None
        for held in (self._listener, self._wake_in, self._wake_out):
            if held is not None:
                held.close()
        self._listener = None
        self._wake_in = None
        self._wake_out = None

    def wake(self) -> None:
        """Break a `serve` call out of its wait, from another thread."""
        if self._wake_out is not None:
            self._wake_out.send(b"\0")

    def serve(self, timeout: float | None = None) -> bool:
        """Handle whatever is ready, once. False when `wake` was called.

        A caller loops on this. It is one step rather than a loop of its own so
        that the thing driving it decides when to stop, which is what lets a
        test drive the loop from the thread it is asserting on.
        """
        if self._selector is None:
            raise RuntimeError("this server is not listening")

        awake = True
        for key, _ in self._selector.select(timeout):
            if key.fileobj is self._wake_in:
                self._drain_wakeup()
                awake = False
            elif key.fileobj is self._listener:
                self._accept()
            elif isinstance(key.fileobj, socket.socket):
                self._read(key.fileobj)
        return awake

    def __enter__(self) -> Server:
        self.start()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop()

    def _drain_wakeup(self) -> None:
        if self._wake_in is None:
            return
        try:
            self._wake_in.recv(READ_SIZE)
        except BlockingIOError:
            pass

    def _accept(self) -> None:
        """Take one connection and give it its own session.

        Each session's seed is derived from this server's seed and the ordinal
        of the connection, so two clients on one process are two independent
        reproductions and both are reproducible. Deriving rather than sharing is
        `0004-randomness.md`'s rule one level up: a shared seed would make the
        second session's sequence depend on how far the first one had got.
        """
        if self._listener is None or self._selector is None:
            return
        try:
            client, _ = self._listener.accept()
        except BlockingIOError:
            return
        client.setblocking(False)
        self._accepted += 1
        session = Session(self.profile, seed=stream_seed(self.seed, f"session:{self._accepted}"))
        self._connections[client] = Connection(socket=client, session=session)
        self._selector.register(client, selectors.EVENT_READ)

    def _read(self, client: socket.socket) -> None:
        connection = self._connections.get(client)
        if connection is None:
            return
        try:
            chunk = client.recv(READ_SIZE)
        except BlockingIOError:
            return
        except OSError:
            self._close(connection)
            return
        if not chunk:
            self._close(connection)
            return
        connection.buffer.extend(chunk)
        self._frame(connection)

    def _frame(self, connection: Connection) -> None:
        """Cut the buffer into messages, refusing one that will not fit.

        Two shapes of oversize, and both are refused. A message that arrives
        whole and is longer than the bound is refused when it is cut out. A
        client that never sends a terminator never gets that far, so the bound
        is checked on the unterminated buffer as well and the connection then
        discards up to the next terminator: without that second check the
        commonest configuration mistake on this surface, a wrong terminator,
        would be a client allocating memory in this process until something
        died.

        Refused once either way. `discarding` is what stops the terminator that
        finally arrives from producing a second refusal for the same bytes.
        """
        terminator = self.terminator.encode(ENCODING)
        while True:
            cut = connection.buffer.find(terminator)
            if cut < 0:
                if not connection.discarding and len(connection.buffer) > self.maximum_message:
                    self._refuse_the_length(connection, len(connection.buffer))
                    connection.discarding = True
                if connection.discarding:
                    connection.buffer.clear()
                return

            message = bytes(connection.buffer[:cut])
            del connection.buffer[: cut + len(terminator)]
            if connection.discarding:
                connection.discarding = False
                continue
            if len(message) > self.maximum_message:
                self._refuse_the_length(connection, len(message))
                continue
            self._run(connection, message)
            if connection.socket not in self._connections:
                # The message just run found the peer gone and closed the
                # connection. What is left in the buffer is for a client that
                # is not there, and running it would answer into a socket this
                # loop has already closed.
                return

    def _refuse_the_length(self, connection: Connection, held: int) -> None:
        connection.session.record(
            Refused(
                BY_ID["input-buffer-overrun"],
                f"a message of at most {self.maximum_message} byte(s) before the terminator; "
                f"got {held} and still no terminator",
                "",
            )
        )

    def _refuse_the_alphabet(self, connection: Connection, outside: int) -> None:
        connection.session.record(
            Refused(
                BY_ID["byte-outside-the-message-alphabet"],
                f"bytes the {ENCODING} alphabet has characters for; got {outside} that it does not",
                "",
            )
        )

    def _run(self, connection: Connection, message: bytes) -> None:
        try:
            text = message.decode(ENCODING)
        except UnicodeDecodeError:
            outside = sum(1 for byte in message if byte > 0x7F)
            self._refuse_the_alphabet(connection, outside)
            return
        outcome = connection.session.deliver(text)
        if outcome.response is None:
            return
        try:
            connection.socket.sendall((outcome.response + self.terminator).encode(ENCODING))
        except OSError:
            self._close(connection)

    def _close(self, connection: Connection) -> None:
        """Close one connection, and do nothing at all the second time.

        The second time happens. One read can carry several messages, the first
        of them can be the one that finds the peer gone, and what closed the
        connection then is inside the loop that is still framing the rest. A
        second close asks the selector for a socket whose file descriptor is
        now `-1`, which it answers with a `ValueError` rather than a miss, and
        that ends the serving thread for every client on it.
        """
        if connection.socket not in self._connections:
            return
        self._connections.pop(connection.socket, None)
        if self._selector is not None:
            try:
                self._selector.unregister(connection.socket)
            except KeyError:
                pass
        connection.socket.close()
