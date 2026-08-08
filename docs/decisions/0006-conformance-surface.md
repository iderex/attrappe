# 0006. How much of the message standard and the command language this implements

## Context

A driver library opens a session and immediately sends a handful of commands
common to every instrument. It gives up quickly when one of them is missing or
answers wrongly, and it gives up before any of this project's interesting
behaviour has had a chance to run. Which of those are implemented, and how
faithfully, therefore decides whether the parity goal is reachable at all. It is
not a detail to be discovered while writing the parser.

Two layers stack here. A message-level standard defines the common commands with
a leading asterisk, the status-reporting registers, and the rules for how
messages are terminated and how a query response is produced. A command-language
standard defines the hierarchical command tree, the short and long forms, the
numeric suffix rules, and an error queue with numbered entries taken from a
published table.

## Options considered

Implement only what a specific driver happens to send, discovered by watching one
driver and stopping when it stops complaining.

Implement the message-level standard in full for its mandatory set, and a
documented subset of the command language.

Implement everything in both.

## Decision

The mandatory common commands are implemented in full. That set is:

    *IDN?   identification
    *RST    reset
    *CLS    clear status
    *ESE    event status enable, set
    *ESE?   event status enable, query
    *ESR?   event status register, query and clear
    *SRE    service request enable, set
    *SRE?   service request enable, query
    *STB?   status byte, query
    *OPC    operation complete, command form
    *OPC?   operation complete, query form
    *TST?   self-test, query
    *WAI    wait to continue

The status-reporting model is implemented as a real model. The status byte is
computed from the event status register, the event status enable register and the
service request enable register at the moment it is read, rather than returned as
a constant or as a value a profile writes directly.

The command language is implemented as the tree walker plus the mandatory system
subsystem. That subsystem is:

    SYSTem:ERRor[:NEXT]?    the oldest entry in the error queue, and remove it
    SYSTem:ERRor:COUNt?     how many entries the queue holds
    SYSTem:VERSion?         the command-language version the emulator answers to

The error numbers the core produces, and their standard messages, are:

    0     No error
    -100  Command error
    -101  Invalid character
    -102  Syntax error
    -103  Invalid separator
    -104  Data type error
    -108  Parameter not allowed
    -109  Missing parameter
    -113  Undefined header
    -114  Header suffix out of range
    -120  Numeric data error
    -128  Numeric data not allowed
    -131  Invalid suffix
    -138  Suffix not allowed
    -148  Character data not allowed
    -158  String data not allowed
    -200  Execution error
    -220  Parameter error
    -221  Settings conflict
    -222  Data out of range
    -224  Illegal parameter value
    -350  Queue overflow
    -363  Input buffer overrun
    -400  Query error
    -410  Query INTERRUPTED
    -420  Query UNTERMINATED

Everything else in the command language is per profile. A profile adds
subsystems, and a profile may add device-specific error numbers, which are the
positive ones and the ones outside the published table.

No deviation from either standard lives in the core. A deviation exists only as a
named quirk in a profile, declared in that profile, and it is reachable only when
that profile is loaded.

## Reasons

The mandatory set is what a driver sends before it will talk to anything. A
missing operation-complete query is not a missing feature, it is a driver that
waits for a response that never arrives, and to the person running it that is
indistinguishable from a hung instrument. The parity goal fails at the first
connection and the failure teaches nobody anything.

The status model is computed rather than faked because measurement software reads
it to decide when a reading is ready. Software that polls the status byte in a
loop is exactly the fragile software this board exists to break honestly, and it
cannot be broken honestly against a constant: a constant either satisfies the
poll immediately every time or never satisfies it, and the interesting failures
are the ones in between.

Real error numbers matter because drivers switch on them. A driver that treats a
particular negative number as a recoverable command error and anything else as
fatal is common, and an emulator inventing its own numbers exercises the wrong
branch of that driver, so the test passes or fails for a reason unrelated to
anything real.

Keeping deviations in profiles rather than in the core is what keeps the phrase
firmware quirk meaningful. A quirk that lives in the core is reachable under
every profile including the ones that do not have it, which makes it not a quirk
but a bug in this project.

## Costs accepted

The status-reporting model is more work than it looks and is the part nobody
thanks you for. It is on the critical path anyway, so the cost is paid early
rather than avoided.

Declaring the command language a documented subset means some driver somewhere
will send something unimplemented. The answer is the undefined-header error,
`-113`, which is what a real instrument does, so at least the failure has the
right shape and appears in the right place.

`*WAI` is in the list above and the issue that ordered this record did not name
it. It is in the mandatory set of the message-level standard, so a record
claiming that set in full while omitting it would be making a claim this
repository could not stand behind. This emulator has no overlapped commands
today, which makes `*WAI` a command that parses, does nothing and completes. That
is the correct behaviour for a device with nothing outstanding, and it is written
here rather than left as a surprise to whoever implements it.

The error table above is transcribed from the published standard and not from a
run of anything, because there is nothing here yet to run. It is a decision about
which numbers the core will produce, and the parser issue that implements it owes
a test per number rather than a second transcription.

## Consequences

The wire milestone has separate issues for the parser, the tree dispatch, the
error queue and the status model. None of them may be dropped from the first
release, because between them they are this record.

A profile that wants a subsystem gets it by declaring it, and the core gains
nothing when it does.

What this project may say in public about conformance is not decided here. This
record says what is implemented. Whether the implemented subset may be described
as conforming, and in what words, is an open question for the maintainer, and
nothing in this record answers it.

## Status

Accepted.
