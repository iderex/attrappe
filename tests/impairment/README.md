Tests for `attrappe.impairment`: the reading pipeline, the physical stages and
the fault schedule.

Empty until the physical-plausibility milestone lands. The stages are the tests
that need the manual clock and a seeded stream most. `tests/conftest.py` carries
the seeded stream now, in the `session` fixture, and it carries no clock: there
is none in the package for it to hand out, and #16 stays open on that fixture.
