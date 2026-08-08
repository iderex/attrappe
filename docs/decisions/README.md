# Decision records

Every decision that shapes the architecture is written down here with its
reasons, before the code that depends on it exists. A record is one file, one
decision, and it is never edited to change what it decided.

## The shape

One file per decision, named `NNNN-short-slug.md`, with a four-digit sequence
that is never reused. `0000-template.md` carries the sections every record has,
in the order every record has them: Context, Options considered, Decision,
Reasons, Costs accepted, Consequences, Status.

Status is one of proposed, accepted, or superseded by NNNN.

## Superseding, not editing

A decision that turns out wrong gets a new record superseding it. The old record
keeps its text and its Status line changes to name the record that replaced it.
Nothing else in it moves.

An edited record reads as though the decision was always the current one, which
removes the evidence that something was learned, and that evidence is the reason
these files exist rather than a paragraph in the README.

## The records

| Number | Title | Status |
| --- | --- | --- |
| [0001](0001-implementation-language.md) | Implementation language and toolchain | Accepted |
| [0002](0002-transport.md) | Three transport surfaces, and the two that are refused | Accepted |
| [0003](0003-time.md) | A virtual clock, and the two places wall time is allowed | Accepted |
| [0004](0004-randomness.md) | Seeded randomness, with a named stream per impairment | Accepted |
| [0005](0005-profiles.md) | Device profiles are data for the command tree and code for the physics | Accepted |
| [0006](0006-conformance-surface.md) | How much of the message standard and the command language this implements | Accepted |
| [0007](0007-fault-schedule.md) | Faults are scheduled declaratively, not sprinkled probabilistically | Accepted |
| [0008](0008-headless.md) | Headless without elevation is a birth requirement, and hardware-bound work is named separately | Accepted |
| [0009](0009-first-instrument.md) | The first instrument is a bench multimeter | Accepted |
| [0010](0010-data-protection.md) | Personal data never leaves the host unless the operator federates | Accepted |

[0000-template.md](0000-template.md) is the template and is not a decision, so it
is not in the table.

## What nothing checks

This index is written by hand and nothing refuses a record that is missing from
it, a row pointing at a file that does not exist, or a Status here that
contradicts the Status in the record. A reader who doubts a row opens the file.
The commands that answer the same questions from the tree are:

```
$ git ls-files 'docs/decisions/*.md'
$ for f in docs/decisions/[0-9]*.md; do
    printf '%s | %s | %s\n' "$f" "$(head -1 "$f")" \
      "$(awk '/^## Status/{getline; getline; print; exit}' "$f")"
  done
```
