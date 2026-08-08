# 0004. Seeded randomness, with a named stream per impairment

## Context

Noise on a reading, thermal drift, the jitter on a settling time, whether this
particular read times out, and whether this particular response comes back
malformed are all random draws. There will be many of them, and the whole point
of the later milestones is that more get added.

A test suite that fails intermittently is worse than no test dependency at all,
because it teaches everyone who sees it to re-run rather than to read. And the
value this project offers is that somebody whose measurement software broke can
hand the maintainer of that software a seed and get the same failure back.
Neither survives an unseeded draw anywhere in the stack.

## Options considered

One global generator seeded once per process.

One generator per session, with every impairment drawing from it in turn.

A named stream per impairment, every stream derived from one session seed and the
stream name.

## Decision

One seed per session. It is printed at startup, it is settable from the profile
configuration and from the command line, and when neither sets it the session
chooses one and prints the one it chose.

Every impairment draws from its own named stream. A stream is derived from the
session seed and the stream name by a stable hash of the two, not by consuming
draws from a shared generator and not by an offset counted in the order
impairments happen to be constructed.

The generator is an explicit instance carried in the session and passed to
whatever needs it. Nothing in this project calls a module-level random function.
The module-level functions in the standard library draw from one hidden global
instance, which is the shared generator this record refuses, reached by a
different spelling.

## Reasons

Deriving each stream from the seed and its name means adding an impairment does
not move any existing stream. With one shared generator, adding a single draw
anywhere shifts every subsequent draw, so a change to the noise model silently
changes which read times out, and every recorded reproduction in every bug report
becomes invalid at the same moment. That failure is quiet, it is total, and
nothing in a test suite catches it, because every test still passes against the
new sequence.

A printed seed is what makes a bug report actionable. Without it a user can say
the software broke and can say nothing a second party can act on.

A per-session seed rather than a per-process one is what lets one emulator
process serve several test sessions without entangling them. Two sessions opened
against one process are two independent reproductions, and a process-wide
generator would make the second one depend on how far the first one had got.

An explicit generator instance rather than the module-level functions is what
makes the rule checkable. A rule about which functions are called is a rule a
linter can refuse; a rule about which instance a module-level call happens to
reach is not. This is the same shape as the clock decision, for the same reason.

## Costs accepted

A stable hash from name to stream makes stream names part of the compatibility
surface. Renaming an impairment changes its draws and invalidates every
reproduction that named it. That is accepted and it gets stated in the operator
documentation, because the alternative is a scheme where renaming nothing still
invalidates everything.

Deriving streams by name costs a hash per stream at construction, which is
nothing, and it costs a discipline about naming, which is real. Two impairments
that pick the same stream name share a stream and neither one is obviously
wrong at the call site.

The rule against module-level random functions is a rule, and until a check
refuses it, it is a habit. The scaffolding milestone owes a lint rule that names
the module and refuses the call, with a test showing it bites on a one-line
violation. Until that rule exists this section is a statement in a document and
nothing more.

## Consequences

Every impairment in the physical-plausibility milestone and every fault source in
the failure-modes milestone declares its stream name, and the name is part of
what its record says.

The fault schedule is reproducible given the seed and the sequence of commands,
which is what its tests assert rather than asserting a distribution.

The session carries a generator the same way it carries a clock, so the two
constructors that make a session testable are the two this record and the clock
record create between them.

## Status

Accepted.
