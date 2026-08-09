"""The emulator listens. It does not call out, and this is what refuses one.

`docs/decisions/0010-data-protection.md` states four properties and this is the
first of them: no version check, no telemetry, no crash reporting, no runtime
package lookup. The record is a statement in a document until something refuses
a violation of it, and #12 is open on exactly that.

## What is refused, and what is not

Every outbound connection to an address that is not loopback. That is the
property, and it is narrower and more checkable than "no socket": binding a
listener is what this program is for, an accepted connection is a client
arriving rather than the emulator leaving, and a socket pair inside the process
never reaches the host's network at all.

Loopback is allowed and the allowance is not free. `Server` opens a socket pair
to wake its selector loop, and on one of the supported operating systems that
pair is a loopback listener with a connection made to it, so a rule refusing
every connect would refuse the emulator's own shutdown. What the rule holds is
that nothing leaves this host. A connection to a loopback address does not, and
`test_the_guard_refuses_a_connection_that_leaves_the_host` is the case that
proves the rule still has teeth after the allowance.

Address resolution is not followed. A name that resolves to a loopback address
is refused here, because the guard reads the address it was handed rather than
what it would become. That is the safe direction: the refusal is stricter than
the property, never looser.

## What drives it

A session driven through every layer, and then the same again over a socket. The
list of messages is one per layer rather than one long one, so a layer that
stopped being reached would be visible as a message nobody sent rather than as a
number that moved.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from attrappe.profile import load_profile
from attrappe.transport import Server, Session

PROFILE = Path(__file__).parent / "scpi" / "fixtures" / "instrument"

# The addresses that do not leave this host. Literal rather than resolved, for
# the reason the module docstring gives.
LOOPBACK_ADDRESSES = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0", ""})

# How long a socket test waits for bytes before failing. Nothing is measured
# against it.
PATIENCE = 3.0

# One message per layer, so a layer that stopped being reached is a message
# nobody sent rather than a number that moved.
EVERY_LAYER = (
    # The parser, on a header in mixed short and long forms.
    "sens:VOLTAGE:dc:rang 100",
    # The dispatch, on a query that reads the value back.
    "SENS:VOLT:DC:RANG?",
    # The parameter table, on each of the four declared types.
    "SENS:FUNC CURRENT",
    "SENS:VOLT:DC OFF",
    'DISP:TEXT "warming up"',
    "CONF:VOLT:DC 100,0.0001",
    # The suffix walk, on a node with several instances.
    "ROUT:CHAN3 ON",
    # The refusal paths, one from the parser and one from the dispatch.
    "TRIG:SOUR IMM",
    "SENS:VOLT:DC:RANG 2000",
    # The common commands and the status registers.
    "*IDN?",
    "*ESE 24;*OPC;*ESR?;*STB?",
    "*TST?",
    "*RST",
    "*CLS",
    "*WAI",
)


class ReachedTheNetwork(AssertionError):
    """Raised where the emulator tried to leave this host."""


@dataclass
class Attempts:
    """Every outbound attempt made while the guard was in force."""

    addresses: list[object] = field(default_factory=list)

    @property
    def offhost(self) -> list[object]:
        return [where for where in self.addresses if not is_loopback(where)]


def is_loopback(address: object) -> bool:
    """True where the address stays on this host, refusing anything unreadable.

    A shape this does not understand counts as leaving. The guard is allowed to
    be stricter than the property and is never allowed to be looser.
    """
    if isinstance(address, (str, bytes)):
        return False
    if isinstance(address, tuple) and address:
        host = address[0]
        return isinstance(host, str) and host in LOOPBACK_ADDRESSES
    return False


@contextmanager
def refuses_to_call_out(monkeypatch: pytest.MonkeyPatch) -> Iterator[Attempts]:
    """Refuse every connection to an address that leaves this host.

    Three entry points rather than one. `connect` is what a stream socket uses
    and what `socket.create_connection` calls underneath, `connect_ex` is the
    same call answering a number instead of raising, and `sendto` reaches a
    destination with no connection at all, which is how a datagram would leave.
    """
    attempts = Attempts()
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_sendto = socket.socket.sendto

    def watched_connect(self: socket.socket, address: Any) -> None:
        attempts.addresses.append(address)
        if not is_loopback(address):
            raise ReachedTheNetwork(f"an outbound connection to {address!r}")
        original_connect(self, address)

    def watched_connect_ex(self: socket.socket, address: Any) -> int:
        attempts.addresses.append(address)
        if not is_loopback(address):
            raise ReachedTheNetwork(f"an outbound connection to {address!r}")
        return original_connect_ex(self, address)

    def watched_sendto(self: socket.socket, *arguments: Any) -> int:
        address = arguments[-1]
        attempts.addresses.append(address)
        if not is_loopback(address):
            raise ReachedTheNetwork(f"a datagram sent to {address!r}")
        return original_sendto(self, *arguments)

    monkeypatch.setattr(socket.socket, "connect", watched_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", watched_connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", watched_sendto)
    yield attempts


def drive(session: Session) -> None:
    """Every layer, once each, plus a draw from a named stream."""
    for message in EVERY_LAYER:
        session.deliver(message)
    session.stream("noise").random()


def test_a_session_driven_through_every_layer_opens_no_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The in-process transport reaches nothing, not even loopback.

    Stronger than the property, and it is the right assertion for this half:
    without a listener there is no socket the emulator has any reason to open,
    so the honest number here is zero rather than none-that-left.
    """
    with refuses_to_call_out(monkeypatch) as attempts:
        session = Session(load_profile(PROFILE), seed=7)
        drive(session)

    assert attempts.addresses == []
    assert session.operations == len(EVERY_LAYER)


def test_a_profile_is_loaded_without_reaching_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No runtime package lookup, which the record names among the four.

    Loading a profile reads a file. A loader that resolved something over the
    network would be the version check the record refuses, wearing a different
    name.
    """
    with refuses_to_call_out(monkeypatch) as attempts:
        load_profile(PROFILE)

    assert attempts.addresses == []


def test_a_full_session_over_a_socket_reaches_nothing_off_this_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The listener, a client, every layer, and the shutdown afterwards.

    The client's own connection is made inside the guard as well, so what this
    asserts is that of everything that connected, nothing connected anywhere
    but here.
    """
    answered = b""
    with refuses_to_call_out(monkeypatch) as attempts:
        with Server(load_profile(PROFILE), port=0, seed=7) as server:
            server.run_in_background()
            where = server.bound
            assert where is not None
            client = socket.create_connection(where, timeout=PATIENCE)
            try:
                for message in EVERY_LAYER:
                    client.sendall((message + "\n").encode("ascii"))
                client.settimeout(PATIENCE)
                answered = client.recv(4096)
            except TimeoutError:
                # Read before the assertions rather than raised through them.
                # An emulator that called out takes its serving loop down with
                # it, and the answer then never arrives; failing here would
                # report the silence and not the reason for it.
                pass
            finally:
                client.close()

    assert attempts.offhost == []
    assert attempts.addresses, "nothing connected at all, so nothing was examined"
    assert answered, "the listener answered nothing, so nothing was driven through it"


def test_the_guard_refuses_a_connection_that_leaves_the_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The near-miss, and it is what stops the three tests above being decoration.

    One line reaching a routable address, in the place the emulator would put a
    version check, and the guard refuses it. Without this the tests above would
    pass just as well against a guard that had stopped refusing anything, and
    the allowance for loopback is exactly the kind of change that produces one.

    The address is in the range reserved for documentation, so a machine that
    somehow ran the connection would not reach a service belonging to anyone.
    """
    with pytest.raises(ReachedTheNetwork):
        with refuses_to_call_out(monkeypatch):
            session = Session(load_profile(PROFILE), seed=7)
            drive(session)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as calling_out:
                calling_out.connect(("192.0.2.1", 443))


@pytest.mark.parametrize(
    "address",
    [
        ("192.0.2.1", 443),
        ("example.invalid", 80),
        ("::2", 443, 0, 0),
        "/tmp/a-path-is-not-an-address",
        None,
    ],
    ids=["a routable address", "a name", "an address family", "a path", "a shape"],
)
def test_the_guard_reads_an_address_it_does_not_understand_as_leaving(address: object) -> None:
    """Stricter than the property, never looser, including for a shape it lacks."""
    assert not is_loopback(address)


@pytest.mark.parametrize(
    "address",
    [("127.0.0.1", 5025), ("::1", 5025, 0, 0), ("localhost", 5025)],
    ids=["the loopback address", "the loopback address in six", "the loopback name"],
)
def test_the_guard_allows_what_stays_on_this_host(address: object) -> None:
    assert is_loopback(address)


def test_the_record_states_the_four_properties() -> None:
    """The other half of the done-condition, read out of the record.

    Quoted from the file rather than described, because a test asserting that a
    document says something has to open the document.
    """
    record = Path(__file__).parents[1] / "docs" / "decisions" / "0010-data-protection.md"
    lines = record.read_text(encoding="utf-8").splitlines()
    openers = [line.split(".")[0] for line in lines if line and not line.startswith((" ", "#"))]

    for property_name in (
        "No outbound connection",
        "Loopback by default",
        "Local-only artefacts",
        "Export by file rather than by transmission",
    ):
        assert property_name in openers, property_name
