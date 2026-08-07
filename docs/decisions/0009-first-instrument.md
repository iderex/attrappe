# 0009. The first instrument is a bench multimeter

## Context

One instrument class goes first and shapes everything after it. The profile
format, the impairment list and the parity harness are all designed against
whatever is in front of them, and designing against three device classes at once
produces something that fits none of them.

The candidates are a bench multimeter, a programmable power supply, a function
generator, a source-measure unit and an oscilloscope. Each exercises the emulator
differently, so the choice deserves an argument rather than a default.

## Options considered

A multimeter.

A power supply, on the grounds that it is simpler.

An oscilloscope, on the grounds that it is the hardest and would prove the
design.

## Decision

The first profile is a bench multimeter of the widely cloned six-and-a-half-digit
kind. The second, added once the abstraction has survived the first, is a
programmable power supply. An oscilloscope is not in the first release.

## Reasons

A multimeter exercises the full impairment list and almost nothing else. Noise on
a reading, drift with temperature, a warm-up specification the manual actually
states, quantisation set by the digit count, an integration time measured in
power-line cycles that costs real delay, autoranging with a settling penalty, and
an overload sentinel that is a specific large number rather than an error. That
is the entire physical-plausibility milestone in one device.

It is the most driver-covered instrument in both target libraries, which is what
the parity goal needs. A parity claim about a device with one obscure driver
proves less.

It is a query-response device with almost no asynchronous behaviour, so the first
profile does not have to solve triggering and buffered acquisition at the same
time as everything else.

Its command set is small enough to write completely from a manual, so the first
profile can be genuinely complete rather than a sketch. Completeness is what lets
a driver attach unmodified, which is half the stated goal.

A power supply comes second because it adds the one thing a multimeter has none
of: an output that changes the world, with a protection trip that latches. State
machines and latching faults then get exercised before the profile format is set
in stone.

An oscilloscope is refused for now. Waveform transfer, block data formats and
trigger state machines are a different project's worth of surface, and starting
there would delay every impairment this board is actually about.

## Costs accepted

Designing the profile format against one device class means the second device
will find something wrong with it. That is expected, and it is why the power
supply is planned rather than deferred indefinitely.

Nothing in the first release will speak to instruments that use block data
transfer. The documentation says so rather than leaving it as an unexplained gap.

## Consequences

The physical-plausibility milestone builds its impairments against this device
and its manual.

The driver-parity milestone selects drivers for this device class in both target
libraries.

The breaking test is written as a multimeter-reading program.

## Status

Accepted.
