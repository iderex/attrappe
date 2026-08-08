# 0008. Headless without elevation is a birth requirement, and hardware-bound work is named separately

## Context

The point of this board is measurement software tested in continuous integration
before the hardware arrives. A test suite that needs a display, a device node, a
driver install or an administrator prompt cannot run there, which would leave
this project unable to meet its own premise while still appearing to work on the
machine of whoever wrote it.

A project that acquires a display dependency or a privileged step recovers from
it slowly and expensively, because by then a dozen tests depend on the thing and
none of them says so.

## Options considered

Require it and enforce it, meaning the default suite states its constraints and
something refuses a test that breaks them.

Require it and trust it, meaning the constraints are written in a document and
whoever adds a test remembers.

Allow a privileged tier from the start, on the grounds that some behaviour needs
one anyway.

## Decision

Every test in the default suite runs under six constraints:

    no display
    no elevation
    no kernel driver
    no device node
    no physical device
    no outbound network

The default suite is the one the gate runs and the one a contributor runs locally
with a single command. Those are the same suite, selected the same way, and not
two suites that happen to agree.

Anything that cannot meet all six runs in a separate harness with an honest name.
The harness is called the hardware-bound harness. It lives in its own directory,
every test in it carries an explicit registered marker, and the default run
deselects that marker by configuration rather than by a naming convention or by a
flag a contributor has to remember to pass.

The hardware-bound harness never gates a merge. Its results are never reported in
a way that could be read as covering the default suite, and a run of it states
which device it ran against or that no device was present.

Its membership on the day this record is written is: anything using a serial port
pair, anything using the USB test-and-measurement class, anything comparing the
emulator against a physical instrument, and any soak run long enough to need real
elapsed time.

## Reasons

Naming the harness honestly is the whole mechanism. A suite called integration
tests that quietly needs a device is a suite that gets skipped in continuous
integration and then gets reported as passing, because a skip and a pass look
alike in a summary line. Calling it hardware-bound puts the reason for the skip
in the name of the thing skipped.

Excluding by configuration rather than by convention means a new hardware-bound
test does not join the default run because its author forgot a naming pattern.
The default run states its selection, and the marker is registered so that a
misspelled marker is a warning rather than a test that silently belongs to
neither harness.

No outbound network is in the list for two reasons that arrive at the same place.
A test reaching a package index or an advisory service is a test that fails when
the network does, which is a flake nobody can reproduce. And it is the same
property the data-protection record asks of the product, so a suite that reaches
the network is a suite that cannot notice the product doing it.

The hardware-bound harness not gating a merge is not a lowering of the standard.
A gate that cannot run is not a gate. Requiring one that the gate machine cannot
satisfy produces either a permanently red mainline or a quietly disabled check,
and both are worse than a harness that says what it is.

## Costs accepted

Some real behaviour will only ever be checked by hand against a real instrument.
That gap is permanent. It is stated in the parity report rather than papered
over, and the parity report is worth less for it, honestly.

Two harnesses means two ways to run tests and a contributor who runs the wrong
one. The contributor documentation owes one command for the default case and a
clearly separate section for the other, and the separate section owes the
sentence that its result covers nothing the default run covers.

The six constraints are a list in a document until something refuses a test that
breaks one. The scaffolding milestone owes the marker and the exclusion, with a
test that fails if a marked test runs in a default invocation. The other five
constraints are not refused by anything and are not claimed to be: a test that
opens an outbound socket passes today.

## Consequences

The transport record already refuses the transports that would need elevation, so
the two records agree rather than one of them being the real rule.

The clock record is what lets warm-up and drift be tested without real elapsed
time, which is what keeps the soak run the only timing member of the
hardware-bound harness rather than the first of many.

The scaffolding milestone builds the marker and the exclusion. The breaking-test
milestone puts the soak run in the hardware-bound harness.

## Status

Accepted.
