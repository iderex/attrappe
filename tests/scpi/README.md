Tests for `attrappe.scpi`: the message parser, the command tree and the
dispatch.

`test_the_message_parser.py` is the parser's table. One row per accepted form
and per refused form, each citing the rule it comes from, so the table reads
against the rules rather than against the parser.

`test_the_dispatch.py` is the same shape over what a well-formed command means
on a particular instrument: what each mandatory common command answers, and
which number refuses a header that stops on a branch, a suffix above the
instances a node declares, or a parameter that does not fit the one it was sent
to. Three of its tests read
`docs/decisions/0006-conformance-surface.md` rather than restating it, so the
mandatory set, the forms each member answers to, and the error numbers cannot
drift from the record without the suite saying so.

`fixtures/vocabulary` is the profile the parser table is read against. It is a
profile rather than a tree built in the test file, because the parser takes its
vocabulary from a loaded profile and a hand-built tree would prove the parser
against a second idea of what a profile produces. It is chosen for what the
table needs rather than for resembling an instrument.

`fixtures/instrument` is the dispatch's, and it is a second profile rather than
the same one because the two tables need different things: the parser's wants
header shapes, and this one wants a node of each accepted form, a node with
several instances, a query answering with two values, and a parameter of each
declared type.
