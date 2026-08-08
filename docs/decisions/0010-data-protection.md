# 0010. Personal data never leaves the host unless the operator federates

## Context

This emulator will run on laboratory machines and, where the documentation says
it fits, in teaching labs. Both carry data about people, and both are places
where a background network call is discovered late and remembered for a long
time.

Several things a program of this kind usually does would send data off the host:
a version check on startup, crash or error reporting, usage telemetry, a package
index lookup at runtime, or a bug-report helper that uploads a session
transcript. Some of that data is personal. Session logs carry user names, host
names, local paths and, in a teaching context, the identity of whoever was at the
bench.

## Options considered

No outbound traffic at all, ever.

Outbound traffic off by default, on by opt-in, which is the shape most projects
settle on.

Anonymous telemetry on by default with an opt-out.

## Decision

Four properties, and the emulator holds all four.

No outbound connection. The emulator makes none. No version check, no telemetry,
no crash reporting, no runtime package lookup. It listens, it does not call out.

Loopback by default. It binds to the loopback interface unless configuration says
otherwise, binding anywhere else is an explicit change an operator makes, and the
startup output says which interface and which port were bound.

Local-only artefacts. All logs, transcripts and recorded sessions are written to
the host and stay there. Nothing in the product uploads them or offers to.

Export by file rather than by transmission. Federation is the word for the only
exception, and it is always an operator action taken deliberately: exporting a
session or a profile and sending it somewhere. Where the project provides a
helper for that, the helper writes a file and stops. It never transmits. What
such a file contains is listed in the documentation, field by field, so the
operator can read the list before deciding and can compare it against the file
afterwards.

The documentation states all four in a section of its own, in plain terms, and
that section is part of the first release rather than a later addition.

## Reasons

An emulator has no need to reach the network. Every reason a program of this kind
usually has for calling out is a convenience for the project's maintainers paid
for out of the operator's trust, and this one can be built without any of them,
so the trade is not worth making even once.

Loopback by default because the failure mode of the other default is an emulator
reachable from a laboratory network, answering to anyone who connects, in a
building where the real instruments are. Somebody's script finds it, attaches,
and reads plausible numbers off a device that is not there. That is a
wrong-answers problem first and a data-protection problem second, and the two
arrive together.

A helper that writes a file rather than transmitting one moves the decision to
where it belongs. The operator can open the file, read it, remove what they do
not want to share, and then send it themselves through whatever route their
organisation already permits.

Listing the fields is what makes the statement checkable. A promise that an
export is anonymous is a claim about code the operator has not read. A list of
fields is something they can hold next to the file and disagree with.

Stating it in the documentation at first release rather than after, because the
statement is the deliverable. An implementation with these properties and no
documentation of them offers the operator nothing to rely on, and an operator who
has to read the source to find out has not been given anything.

## Costs accepted

No telemetry means no usage data, so decisions about what to build next come from
what people say rather than from what they do. That is accepted, and it means
this project will be wrong about its own usage in ways it cannot measure.

No version check means an operator can run an outdated release without being
told, including one with a fault this project later fixed. The documentation
names where releases are announced and leaves the checking to them.

A test that would need the network is refused, which is the same constraint the
headless record already imposes for its own reasons. Where a test genuinely needs
one, it is hardware-bound and it does not gate a merge.

## Consequences

The wire milestone sets the loopback default and prints the bound interface.

The first-release milestone carries the documentation section and its field list.

The dependency set is audited for anything that phones home, and a dependency
that does is not added. The audit leg in the quality milestone is where the
dependency set is examined, and this property is a reason to read the result
rather than only its exit code.

## Status

Accepted.
