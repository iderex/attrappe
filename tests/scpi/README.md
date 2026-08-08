Tests for `attrappe.scpi`: the message parser, the command tree and the
dispatch.

`test_the_message_parser.py` is the parser's table. One row per accepted form
and per refused form, each citing the rule it comes from, so the table reads
against the rules rather than against the parser.

`fixtures/vocabulary` is the profile the table is read against. It is a profile
rather than a tree built in the test file, because the parser takes its
vocabulary from a loaded profile and a hand-built tree would prove the parser
against a second idea of what a profile produces. It is chosen for what the
table needs rather than for resembling an instrument.

The dispatch has no test here yet. #22 brings the first one.
