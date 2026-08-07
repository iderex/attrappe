# 0001. Implementation language and toolchain

## Context

Two things get built here. An emulator that answers on a socket, and a harness
that drives real instrument-control drivers against it.

The second one is pinned. Those drivers are Python libraries, and to run them you
run Python. The first one is free, because it sits behind a byte-oriented socket
and could be written in anything that can open one.

Nothing depends on the answer yet, which is the only moment at which the question
is cheap to ask. A language is not a thing to arrive at by habit, and by the time
twenty modules exist the choice has already been made by whoever wrote the first
one.

## Options considered

Python for both halves.

A compiled language for the emulator, with Python confined to the harness.

A compiled core with Python bindings over it.

## Decision

Python is the implementation language for the emulator and for the harness. One
language, one toolchain, one test runner. The minimum supported version is 3.11,
and the project is tested against 3.11 up to the current release.

## Reasons

The harness is not optional and is not portable to another language. The parity
goal is stated in terms of two Python libraries talking to the emulator
unmodified, so a Python runtime sits in this project's dependency set whatever
else is chosen. A second language buys a second toolchain, a second dependency
audit, a second coverage story and a second set of CI jobs, and the emulator core
is the smaller half of the work.

The audience already has Python installed. The people who would use this are the
people writing measurement software against those libraries. A test dependency
they can install with the tool they already use gets adopted. One that needs a
separate toolchain gets evaluated and put off.

Performance does not push back. An instrument answers a few hundred queries a
second at the outside, over a link whose own latency dominates, and the expensive
part of this emulator is deliberately pretending to be slow. There is no
throughput number in this project that Python misses.

The properties this project needs to make refusable are properties of behaviour
over a socket, not properties of the implementation language. A test asserting
that the five hundredth read times out is the same test in any language, and
Python does not weaken it.

3.11 is the floor because it is the oldest release still receiving security fixes
across the useful life of a first release, and because the typing features the
profile layer leans on are stable there without conditional imports.

## Costs accepted

An operator without a Python environment cannot run this without acquiring one.
That cost is paid in the release milestone by shipping something that does not
require managing an environment by hand, and not by changing the language.

Python makes it easy to write a fault-injection layer that is accidentally
non-deterministic. Dictionary iteration order, set ordering and hash seeding have
all bitten this class of program before. The clock record and the randomness
record exist partly to hold that line, and each owes a check rather than a
sentence.

A single static binary with no runtime to install is not available here, and a
compiled language would have given it away.

## Consequences

The toolchain in the scaffolding milestone is a Python one. The CI matrix is
Python versions, starting at 3.11.

Any later component that genuinely cannot be Python is a new decision record
naming the force, holding it to its smallest surface, and saying what it costs.
It is not a quiet addition to a build file.

## Status

Accepted.
