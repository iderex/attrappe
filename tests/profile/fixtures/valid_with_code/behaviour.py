"""The optional code half of a profile fixture.

It records that it ran, in the module itself, so a test can tell an executed
module from an unexecuted one. A real code half carries the measurement model;
this one carries the smallest observable effect, because what is under test is
when the module is executed and not what it does.

The assignment is at import time on purpose. That is what makes loading a
profile from an untrusted source run that source, which
`docs/decisions/0005-profiles.md` states and does not mitigate.
"""

EXECUTED = True
