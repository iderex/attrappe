"""The error queue: what a refusal becomes, and what a full queue does.

    from attrappe.device import Entry, ErrorQueue

    queue = ErrorQueue(profile.error_queue_depth)
    queue.push(Entry(-113, "Undefined header", "MEAS:XYZ"))
    queue.take()

An entry is a number, the standard message for its class, and optional detail.
The numbers and the messages are `docs/decisions/0006-conformance-surface.md`'s,
transcribed nowhere in this module: an entry is handed the pair by whoever
produced the refusal, and the two constants below are the only ones the queue
itself owns because they are the only two no refusal produces.

## First in, first out, and full is not the same as closed

A queue at its depth does not refuse further errors and does not drop the oldest
one. The last entry becomes the overflow entry and everything after it is
discarded, so what a client reads back is the earliest errors it made and then a
statement that it stopped being told. Dropping the oldest instead would leave a
client reading the five most recent errors of a run that made five hundred, and
the first mistake, which is the one that caused the rest, would be the one entry
guaranteed to be gone.

That is also why the overflow entry replaces rather than appends. A queue of
depth two holding two errors has nowhere to put a third, and appending the
overflow entry would make the queue three deep, which is a depth the profile
does not declare and a driver reading a fixed number of entries does not expect.

## Reading an empty queue is an answer rather than a refusal

`take` on an empty queue answers the no-error entry, which is what the standard
requires and what a driver's polling loop reads to decide it has drained the
queue. A queue that raised or answered nothing would leave that loop with no
terminating condition.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The two entries the queue produces itself rather than receiving. Both numbers
# and both messages are `0006`'s error table, and
# `tests/device/test_the_error_queue.py` reads them out of that record rather
# than agreeing with this file.
NO_ERROR_NUMBER = 0
NO_ERROR_MESSAGE = "No error"
QUEUE_OVERFLOW_NUMBER = -350
QUEUE_OVERFLOW_MESSAGE = "Queue overflow"

# The shallowest queue that is a queue. The loader refuses a profile declaring
# less, and this is the same bound at the other end, for a queue built by a
# caller that never went through a profile.
MINIMUM_DEPTH = 1


@dataclass(frozen=True)
class Entry:
    """One error a client can read back: its number, its message, its detail.

    Rendered in the form `attrappe.scpi`'s two refusal types render in, because
    a client reads one string and cannot tell which stage produced it. The
    detail is what makes an entry worth reading, and it is optional because the
    two entries the queue produces itself have nothing to add to their message.
    """

    number: int
    message: str
    detail: str = ""

    def __str__(self) -> str:
        return f'{self.number},"{self.message}{f"; {self.detail}" if self.detail else ""}"'


NO_ERROR = Entry(NO_ERROR_NUMBER, NO_ERROR_MESSAGE)
QUEUE_OVERFLOW = Entry(QUEUE_OVERFLOW_NUMBER, QUEUE_OVERFLOW_MESSAGE)


@dataclass
class ErrorQueue:
    """One instrument's error queue, at the depth its profile declares.

    One of these per instrument and therefore one per session, for the same
    reason nothing else in `attrappe.device` is a class attribute: two clients
    on one listener each made their own mistakes and neither should be reading
    the other's.
    """

    depth: int
    entries: list[Entry] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.depth < MINIMUM_DEPTH:
            raise ValueError(
                f"an error queue holds at least {MINIMUM_DEPTH} entry; got {self.depth}"
            )

    @property
    def count(self) -> int:
        """What the error-count query answers: how many entries are waiting."""
        return len(self.entries)

    def push(self, entry: Entry) -> bool:
        """Record one error, or record that the queue stopped recording them.

        Assigning the overflow entry over a queue that already overflowed is
        the discard: the entry is already there, so the second and the five
        hundredth error after the queue filled change nothing.

        Answers whether the entry was dropped instead of held. The caller needs
        it because the overflow is an error in its own right and belongs in the
        event status register even on the five hundredth push, where this queue
        has nothing left to change.
        """
        if len(self.entries) < self.depth:
            self.entries.append(entry)
            return False
        self.entries[-1] = QUEUE_OVERFLOW
        return True

    def take(self) -> Entry:
        """The oldest entry, removed, or the no-error entry when there is none."""
        if not self.entries:
            return NO_ERROR
        return self.entries.pop(0)

    def clear(self) -> None:
        """`*CLS`: the queue is empty and the overflow, if there was one, is gone."""
        self.entries.clear()
