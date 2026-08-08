Tests for `attrappe.profile`: loading a device profile and refusing a bad one.

`docs/decisions/0005-profiles.md` is what a test here checks the loader against.

## The fixtures

`fixtures/` holds one profile directory per case. `valid` is the profile the
accepting tests read, `valid_with_code` is the smaller one that carries the
optional Python half, and each `broken-*` directory carries exactly one defect
so that the test naming it can assert exactly one problem rather than at least
one.

`valid_with_code` is spelled with underscores where its neighbours use hyphens.
It is the only fixture holding a `.py` file, the type checker reads every file
under `tests`, and a directory with a hyphen in it is not a name a module path
can carry.

Adding a refusal rule to the loader means adding a fixture here for it. A rule
with no fixture is one nothing has watched refuse anything.
