# Data protection

What this software writes, where it writes it, and what leaves the host. Written
for the person deciding whether to run it on a laboratory machine, and meant to
be read before that decision rather than after.

[decisions/0010-data-protection.md](decisions/0010-data-protection.md) is where
the four properties below were decided and where the options that were rejected
are written down. This document states what the tree actually does.

## The four properties

No outbound connection. The emulator makes none. There is no version check, no
telemetry, no crash reporting and no package lookup at runtime. It listens, and
it does not call out. `tests/test_nothing_calls_out.py` is the test that refuses
one: it drives a full session in process and again over a socket, and it fails
if anything connects to an address that is not loopback.

Loopback by default. The listener binds the loopback interface unless the
`--host` option says otherwise, and the interface and port that were bound are
printed at startup. Binding anywhere else is a change an operator makes on
purpose.

Local-only artefacts. Everything the emulator produces is written to the host
and stays there. Nothing in it uploads a file or offers to. What it writes is
the list below.

Export by file rather than by transmission. The only way anything leaves is an
operator picking up a file and sending it. That is the federation paragraph
further down.

## What the emulator writes to disk

One entry per place in the package that opens or creates a path on the host.

The list is checked against the code rather than maintained by hand.
`tests/test_the_data_protection_section.py` reads the package's syntax tree,
finds every call that opens or creates a path, and compares what it found with
the headings below. A write added to the package with no entry here fails the
suite, and an entry here naming a place the package no longer writes from fails
it too, so the list cannot quietly go stale in either direction.

Each heading names the file, the function and the call, because that is the key
the comparison is made on.

### `src/attrappe/cli.py`, in `destination`, through `open`

The startup log, and only when `--log` names a file. Without that option the
same lines go to standard output and no file is written. The file is created, or
truncated if it is already there, when the command starts.

It holds six lines and nothing else. The emulator's answers to a client go to
the socket and never here.

- `profile`, the profile's name and the directory it was loaded from. The
  directory is a path on this host, and a path on this host commonly carries a
  user name.
- `identification`, the identification string a client reads back. It comes from
  the profile and says nothing about the machine.
- `listening`, the interface and port that were bound. Where an operator has
  bound something other than loopback, this is an address of this host.
- `seed`, a number.
- `fault schedule`, fixed text.
- `configuration`, the configuration file that was read, or the words saying
  none was. A path on this host, with the same consequence as the first entry.

## What is not written, today

There is no session log, no recorded transcript and no record of what a driver
exercised. Those are things this project intends to produce and they do not
exist, which is why the list above has one entry rather than four. Each of them
arrives with an entry of its own, because the test above is what makes that not
optional.

## Federation

There is no export helper in this software. Nothing here packages a session,
and nothing here sends one.

So federation today is an operator taking a file from the list above and sending
it themselves, and what such an export contains is exactly what that list says
the file contains, field by field. Reading it before sending is the operator's
step and cannot be anyone else's: the software has no way to know what is
sensitive in a given deployment, and a path that is ordinary on one machine
carries a person's name on another.

Where a helper for this is added later, it writes a file and stops. It does not
transmit, and its file appears in the list above under the same check.

## Binding beyond loopback

The emulator has no authentication, no authorisation and no transport security.
Anything that can reach the port can drive the emulated instrument and read
everything it answers.

Loopback is the default and it is a default rather than a control. An operator
who passes `--host` has put an unauthenticated service on that interface, and
nothing in the software stops them or asks again. On a laboratory network the
first consequence is not a data-protection one: somebody's script finds the
port, attaches, and reads plausible numbers off a device that is not there.
[../SECURITY.md](../SECURITY.md) states the same thing as a threat model.

## A profile can carry code

A profile directory may hold a `behaviour.py` beside its declaration, and
loading that half executes it.
[decisions/0005-profiles.md](decisions/0005-profiles.md) is where that was
decided, and there is no sandbox around it. Reading a profile's declaration does
not run anything; running the code half is a separate call a caller makes on
purpose.

A profile from a source you do not trust is a program from a source you do not
trust, and what it writes to this host is its own business rather than this
document's.

## What the check does not reach

The list above is derived from the package's syntax tree, so it covers what this
software's own code opens and nothing else. It does not reach a path written by
a profile's code half, which is the paragraph above. It does not reach the
bytecode cache the interpreter writes beside the source. It does not reach a
file opened through a name resolved at runtime, and it says nothing about a
dependency, because the runtime dependency list is empty.

One more, and it is the narrowest. An entry is a file, a function and the call
that wrote, so a second file opened the same way inside the same function would
fall under the entry already there and would not show up as a new one. What that
costs and why the alternative is worse is written in the test itself.

Those are named so that the cover is not read as total.
