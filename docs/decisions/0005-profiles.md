# 0005. Device profiles are data for the command tree and code for the physics

## Context

A bench instrument has a few hundred commands, most of them settings with a type,
a range, a default and a persistence rule. It also has perhaps a dozen genuinely
behavioural surfaces: what a measurement returns, what happens on overload, what
the front end does while it is settling.

Those two halves fail in opposite directions. The command tree is a large flat
table, and a table written as code drifts against what it describes. The
behaviour behind a command is a model with state, and a model expressed as data
becomes a small unreadable programming language.

## Options considered

Everything as data in a declarative file.

Everything as code in a Python class.

A split, with the command tree as data and the behaviour as code.

## Decision

A profile is a directory containing a declarative file describing the identity,
the command tree and the parameter table, plus an optional Python module
providing behaviour hooks. The declarative format is TOML.

The declarative half covers the identification response, the command tree with
short and long forms, each parameter's type, range, default, units and whether it
survives a reset, the error-queue depth, and the quirk overlays. The code half
covers the measurement model and anything that has to look at instrument state.

A profile with no code half is legal and produces a working but physically dull
instrument. That is deliberately the easy thing to write.

Loading a profile executes the Python module inside it. A profile from an
untrusted source is untrusted code, and this project does not sandbox it.

## Reasons

The command tree is the part that gets compared against a manual, and a reader
comparing a table to a manual should be reading a table. Expressed as decorators
on methods it is skimmable by nobody and it drifts silently.

The physics is the part this board exists for, and it is not expressible as data
without inventing an expression language. Every project that has tried has ended
up with a worse Python embedded in strings.

TOML rather than YAML because the failure modes are smaller. No significant
whitespace, no surprising type coercion of version-like strings, no anchors, and
the parser is in the standard library from the version floor set in record 0001,
so it costs no dependency.

A profile with no code half being legal is what makes the first contribution
cheap. Somebody with a manual and no interest in modelling noise can still
contribute a command tree, and the physics can be added later by somebody else.

## Costs accepted

Two files per profile is more structure than one, and contributors will put
things in the wrong half. The profile documentation owes a clear line, and the
loader owes an error message that says which half a thing belongs in.

A Python module inside a profile means a profile is executable code. Loading a
profile from an untrusted source is running that source. That gets stated plainly
in the operator documentation rather than mitigated by a sandbox this project has
no way to make sound. Nothing in this repository refuses an untrusted profile
today, and the operator is the only control there is.

## Consequences

The profile loader is a wire-milestone issue and validates the declarative half
against a schema that refuses a bad profile loudly rather than falling back to a
default.

The first instrument in the physical-plausibility milestone is the first user of
the code half.

The quirk overlays in the failure-modes milestone live in the declarative half.

## Status

Accepted.
