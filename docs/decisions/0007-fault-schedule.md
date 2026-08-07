# 0007. Faults are scheduled declaratively, not sprinkled probabilistically

## Context

The failure modes this board exists for are events. One read in five hundred
times out. A response after a range change comes back truncated. The instrument
stops answering entirely after a particular command.

Measurement software gets these wrong at specific moments, and a test has to be
able to put the moment somewhere specific.

A probability per operation cannot do that in any strict sense. It can carry an
assertion about a rate over ten thousand reads, and it cannot carry an assertion
about what happens to the read that fails, which is the interesting part.

## Options considered

A probability per fault type, drawn on every operation.

A declarative schedule.

Both, with the schedule available as an override on top of the probabilities.

## Decision

A fault schedule is a declarative list of rules. A rule names the fault, the
trigger, and the effect. A trigger is one of: every Nth matching operation, the
Nth matching operation exactly, a window of instrument time, an operation
matching a command pattern, or a random draw at a stated rate from a named
stream.

The random trigger exists and is not the default. A profile ships with a schedule
that is deterministic, and rate-based triggers are opt-in for soak runs.

The schedule is evaluated against instrument time from the clock in record 0003,
never against wall time. Operation counters are per session.

## Reasons

Every-Nth and exactly-N triggers are what make an assertion possible. A test can
say the five hundredth read times out and then assert what the software under
test did with it. That is a machine-decidable statement and it is the whole point
of the exercise.

Command-pattern triggers are what express a real firmware quirk, which is almost
never a random event. Instruments misbehave after a particular state change, and
a rate-based model cannot say that.

Rate-based triggers still exist because a soak run wants them, and because a real
instrument does have genuinely stochastic failures. Making them opt-in keeps the
default suite reproducible.

Keying to instrument time rather than to wall time means a time-window fault is
reproducible under the manual clock, which is the only way a warm-up-related
fault can be tested at all.

## Costs accepted

A declarative schedule is a small language, and small languages grow. The
validation of the schedule needs to be strict and the error messages need to name
the offending rule, or profile authors will fight it.

Deterministic defaults mean the default configuration is, in one narrow sense,
less realistic than a random one. The documentation says so, and points at the
soak configuration for the other behaviour.

## Consequences

The failure-modes milestone builds the schedule engine first and the individual
fault effects after it.

The breaking test is written entirely against exact triggers, so its expectation
table is a table of certainties rather than a table of rates.

## Status

Accepted.
