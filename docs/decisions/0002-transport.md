# 0002. Three transport surfaces, and the two that are refused

## Context

A driver library reaches an instrument through a resource string, and the string
names a transport. Which transports this emulator answers on decides whether an
unmodified driver can attach at all, and it decides what the host has to grant
before the test suite can run.

The transports a driver library can open are a raw TCP socket, an RPC-based
instrument protocol reached through a port mapper on port 111, a newer high-level
instrument protocol on a high port, the USB test-and-measurement class, and
serial. They differ enormously in what they cost the host. A socket costs
nothing. A port mapper below port 1024 costs a privileged bind. A USB class or a
serial port pair costs a device node, and on one of the target operating systems
that is a kernel-level driver install.

## Options considered

The raw TCP socket first, because it is the cheapest thing a driver can attach
to.

The RPC-based protocol first, because a number of drivers default to it and a
resource string written for it will not fall back.

A simulated backend inside the client library, with no socket at all, which is
what the existing dummy instruments do.

## Decision

Three surfaces, in this order of commitment.

A raw TCP socket is the primary surface and the only one required for the parity
goal. It is reached with a socket-style resource string of the form
`TCPIP0::<host>::<port>::SOCKET`, it listens on a configurable port, the default
port is `5025`, and it uses a configurable message terminator whose default is a
single newline, `\n`, the byte `0x0A`, with no carriage return before it.

An in-process transport with no socket at all is the second surface. It is the
same session object driven directly by a caller in the same process, so the
parser, the command tree and the impairment stack are exercised without a
listener and without a port.

The high-port instrument protocol, HiSLIP, is a later optional surface. It is
planned and it is not required for the first release.

Two transports are refused. The RPC-based protocol, VXI-11, is deliberately not
implemented. Serial is deliberately not implemented in the headless path.

## Reasons

The raw socket needs nothing from the host. No kernel driver, no device node, no
permission grant, no display. That is the same requirement the headless record
makes of every test here, and a transport that could not meet it would break that
requirement on the first day rather than on some later one.

The RPC-based protocol depends on a port mapper on port 111, which is below the
privileged threshold on the systems this runs on, so binding it needs elevation.
A transport an unprivileged test process cannot start is not one this project can
gate on. Shipping it as an untested extra would be worse than not having it,
because an untested transport in a release is a claim nobody checked.

Serial needs a real or virtual port pair. On one of the target operating systems
that pair is a kernel-level device install, which is hardware-bound by the
definition the headless record uses, so it belongs in the separately named
hardware-bound harness if it is ever built and never in the default suite.

The in-process transport exists because most of what this project will get wrong
is in the parser and in the physics, not in the socket. Driving those through a
listener turns every unit test into a network test, with the flakiness that
implies, and it buys no coverage of the parser that a direct call does not
already buy.

HiSLIP is worth having eventually. Some drivers prefer it, and unlike the
RPC-based protocol it is implementable without elevation because its port is
high. It waits because it adds a second framing layer underneath every
session-level test and earns nothing for the stated goal until a driver that
needs it is in the parity harness.

## Costs accepted

A driver whose only supported resource string is the RPC form will not attach.
That is a real and known gap, and it is a gap in the thing this board exists to
demonstrate. It gets named in the parity report rather than discovered by a user
who has already written their test suite against it.

A configurable terminator is a configuration surface, and it is one that will get
set wrong. A wrong terminator looks exactly like a hang: the client waits for a
byte the emulator has already decided not to send. The operator documentation
owes a sentence about that and the troubleshooting section owes the case.

A default port fixes a number that some other process on the host may already
hold. The startup output says which port was bound, so a collision is a message
rather than a mystery.

## Consequences

The server issue in the wire milestone builds one listener and no more.

The parity harness in the driver-parity milestone uses socket-style resource
strings, so a driver that cannot form one is out of scope for that harness and is
listed in its report.

Anything needing a device node goes to the hardware-bound harness named in the
headless record.

## Status

Accepted.
