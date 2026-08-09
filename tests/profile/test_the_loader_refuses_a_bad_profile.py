"""What the profile loader accepts, and what it refuses and why.

One fixture directory per refusal rule, under `fixtures/`, each holding exactly
one defect. The assertion per broken fixture is that the loader reports exactly
one problem and names the key the defect is in, which is stronger than asserting
that it refused: a loader that refuses everything would pass the weaker form.

`broken-several-problems` is the one fixture with more than one defect. It is
what proves validation finishes before it reports, rather than stopping at the
first thing it found.

Deleting a rule from `attrappe.profile.loader` reddens the case that names it,
and the transcript of that is in the pull-request body rather than here, because
a comment claiming a test bites is not the same as having watched it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from attrappe.profile import (
    ProfileError,
    load_code_half,
    load_profile,
    main,
)

FIXTURES = Path(__file__).parent / "fixtures"
VALID = FIXTURES / "valid"
VALID_WITH_CODE = FIXTURES / "valid_with_code"


def keys(refused: ProfileError) -> list[str]:
    return [problem.key for problem in refused.problems]


def test_the_valid_fixture_loads_and_its_tree_matches_the_declaration() -> None:
    """The node count is derived from the tree and compared with the file.

    Counting the entries in the text rather than writing the number here is
    what makes the assertion about the loader. A literal would agree with the
    loader and with nothing else the day somebody adds a node to the fixture.
    """
    declaration = (VALID / "profile.toml").read_text(encoding="utf-8")
    declared_nodes = declaration.count("\n[[node]]\n")
    declared_parameters = declaration.count("\n[[parameter]]\n")

    profile = load_profile(VALID)

    assert declared_nodes == 13
    assert len(profile.nodes()) == declared_nodes
    assert len(profile.parameters()) == declared_parameters
    assert profile.identification == "Attrappe,EMULATED-DMM-1,0000000001,0.1.0"
    assert profile.error_queue_depth == 16


def test_the_tree_is_a_tree_and_not_a_flat_list() -> None:
    """A node's children hang off it, and its path says where it sits."""
    profile = load_profile(VALID)

    assert sorted(root.long for root in profile.roots) == ["CONFIGURE", "MEASURE", "SENSE"]

    by_path = {node.path: node for node in profile.nodes()}
    sense_dc = by_path[("SENSE", "VOLTAGE", "DC")]
    assert sense_dc.short == "DC"
    assert sorted(child.long for child in sense_dc.children) == ["NPLCYCLES", "RANGE"]

    every_path = set(by_path)
    for path in every_path:
        if len(path) > 1:
            assert path[:-1] in every_path


def test_a_parameter_carries_its_range_its_default_and_its_reset_rule() -> None:
    profile = load_profile(VALID)
    by_name = {(parameter.node, parameter.name): parameter for parameter in profile.parameters()}

    voltage_range = by_name[("SENSE:VOLTAGE:DC:RANGE", "value")]
    assert (voltage_range.minimum, voltage_range.maximum) == (0.1, 1000.0)
    assert voltage_range.default == 10.0
    assert voltage_range.units == "V"
    assert voltage_range.survives_reset is False

    autorange = by_name[("CONFIGURE:VOLTAGE:DC", "autorange")]
    assert autorange.choices == ("ON", "OFF", "ONCE")

    autozero = by_name[("SENSE:VOLTAGE:DC", "autozero")]
    assert autozero.default is True
    assert autozero.survives_reset is True


@pytest.mark.parametrize(
    ("fixture", "key"),
    [
        ("broken-default-outside-range", "parameter[0].default"),
        ("broken-short-form-not-a-prefix", "node[1].short"),
        ("broken-duplicate-node", "node[2].path"),
        ("broken-parent-not-declared", "node[1].path"),
        ("broken-accepts-not-a-declared-form", "node[1].accepts"),
        ("broken-suffix-count-below-one", "node[1].suffixes"),
        ("broken-query-answers-from-nothing", "node[1].accepts"),
        ("broken-separator-is-empty", "response.separator"),
    ],
)
def test_each_broken_fixture_is_refused_with_the_key_it_is_wrong_in(fixture: str, key: str) -> None:
    """Exactly one problem, and it names the key.

    Exactly one rather than at least one. A loader that reported a second
    problem here would be reporting one about a part of the fixture that is
    correct, and the fixture would then be proving less than it claims.
    """
    with pytest.raises(ProfileError) as refused:
        load_profile(FIXTURES / fixture)

    assert keys(refused.value) == [key]
    assert refused.value.profile == fixture
    assert fixture in str(refused.value)
    assert key in str(refused.value)


def test_a_node_carries_what_it_accepts_and_how_many_of_it_there_are() -> None:
    """The keys the dispatch reads, and the defaults for a node declaring neither.

    A node with no `accepts` is a branch, which is the safe reading of an absent
    key: a header stopping there is refused rather than answered. One instance
    is the SCPI default and it is not the absence of a suffix, so a node
    declaring nothing answers to both spellings of the first instance.
    """
    profile = load_profile(VALID)
    by_path = {node.path: node for node in profile.nodes()}

    branch = by_path[("SENSE",)]
    assert branch.accepts is None
    assert branch.settable is False
    assert branch.queryable is False
    assert branch.suffixes == 1


def test_the_response_separator_defaults_to_the_comma_the_valid_fixture_omits() -> None:
    """The valid fixture declares no `[response]`, so the default is what it gets."""
    assert "[response]" not in (VALID / "profile.toml").read_text(encoding="utf-8")

    assert load_profile(VALID).separator == ","


@pytest.mark.parametrize(
    ("declared", "separator"),
    [
        ('\n[response]\nseparator = "|"\n', "|"),
        # A table that declares nothing is not a defect. It is a profile whose
        # author opened the section and had nothing to put in it, and the
        # default is what the section would have said.
        ("\n[response]\n", ","),
    ],
)
def test_a_declared_response_separator_is_read(
    tmp_path: Path, declared: str, separator: str
) -> None:
    valid = (VALID / "profile.toml").read_text(encoding="utf-8")
    (tmp_path / "profile.toml").write_text(valid + declared, encoding="utf-8")

    assert load_profile(tmp_path).separator == separator


def test_a_response_section_that_is_not_a_table_is_refused(tmp_path: Path) -> None:
    """Written above the tables, because a bare key after one belongs to it."""
    valid = (VALID / "profile.toml").read_text(encoding="utf-8")
    (tmp_path / "profile.toml").write_text("response = 5\n" + valid, encoding="utf-8")

    with pytest.raises(ProfileError) as refused:
        load_profile(tmp_path)

    assert keys(refused.value) == ["response"]


def test_every_problem_is_reported_and_not_only_the_first() -> None:
    """Five defects of five kinds come back together.

    This is the leg the issue asks for when it says validation is complete
    before anything is constructed. A loader that raised on the unknown key at
    the top of the file would satisfy every other test here.
    """
    with pytest.raises(ProfileError) as refused:
        load_profile(FIXTURES / "broken-several-problems")

    assert keys(refused.value) == [
        "notes",
        "identity.firmware",
        "error_queue.depth",
        "node[1].short",
        "parameter[0].default",
    ]


def test_an_unknown_key_is_refused_by_adding_one_character_to_the_valid_fixture(
    tmp_path: Path,
) -> None:
    """`depth` becomes `depths`, and the profile that loaded stops loading.

    The mutation is asserted to be one character long, so the test cannot drift
    into a rewritten fixture that refuses for some other reason.
    """
    valid = (VALID / "profile.toml").read_text(encoding="utf-8")
    mutated = valid.replace("depth = 16", "depths = 16", 1)
    assert len(mutated) == len(valid) + 1

    (tmp_path / "profile.toml").write_text(mutated, encoding="utf-8")
    with pytest.raises(ProfileError) as refused:
        load_profile(tmp_path)

    # The unknown key, and the required key that is now absent because of it.
    assert "error_queue.depths" in keys(refused.value)
    assert "error_queue.depth" in keys(refused.value)


def test_the_valid_fixture_still_loads_from_a_copy(tmp_path: Path) -> None:
    """The control for the mutation above: the same bytes, unmutated, load.

    Without it, the previous test would pass just as well against a loader that
    refuses anything outside its own fixture directory.
    """
    valid = (VALID / "profile.toml").read_text(encoding="utf-8")
    (tmp_path / "profile.toml").write_text(valid, encoding="utf-8")

    assert len(load_profile(tmp_path).nodes()) == 13


def test_a_missing_declarative_file_is_refused_and_names_the_profile(tmp_path: Path) -> None:
    directory = tmp_path / "no-declaration"
    directory.mkdir()

    with pytest.raises(ProfileError) as refused:
        load_profile(directory)

    assert refused.value.profile == "no-declaration"
    assert "profile.toml" in str(refused.value)


def test_a_declarative_file_that_is_not_toml_is_refused(tmp_path: Path) -> None:
    (tmp_path / "profile.toml").write_text("[identity\n", encoding="utf-8")

    with pytest.raises(ProfileError) as refused:
        load_profile(tmp_path)

    assert "valid TOML" in str(refused.value)


def test_loading_a_profile_does_not_execute_its_code_half() -> None:
    """The module is found and named, and nothing runs it.

    `docs/decisions/0005-profiles.md` says loading a profile from an untrusted
    source runs that source and that this project does not sandbox it. That is
    true of `load_code_half` and it is deliberately not true of reading the
    declaration, so an operator can validate a profile they do not trust.
    """
    profile = load_profile(VALID_WITH_CODE)

    assert profile.code_half == VALID_WITH_CODE / "behaviour.py"
    assert not [name for name in sys.modules if name.startswith("attrappe.profile.loaded.")]


def test_the_code_half_runs_only_when_it_is_asked_for() -> None:
    module = load_code_half(load_profile(VALID_WITH_CODE))

    assert module is not None
    assert module.EXECUTED is True


def test_a_profile_with_no_code_half_is_not_an_error() -> None:
    profile = load_profile(VALID)

    assert profile.code_half is None
    assert load_code_half(profile) is None


def test_the_command_line_answers_zero_on_a_good_profile(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([str(VALID)]) == 0

    printed = capsys.readouterr().out
    assert "13 node(s)" in printed
    assert "Attrappe,EMULATED-DMM-1,0000000001,0.1.0" in printed


def test_the_command_line_answers_non_zero_and_names_the_profile(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A bad profile is a non-zero exit and a message naming which profile.

    The exit code is read from the function rather than from a spawned process.
    The other half of the sentence in #25, that the emulator does not start, is
    not asserted anywhere: there is no emulator in this tree to start, and #26
    and #27 are where that becomes assertable.
    """
    assert main([str(FIXTURES / "broken-duplicate-node")]) == 1

    printed = capsys.readouterr()
    assert printed.out == ""
    assert "broken-duplicate-node" in printed.err
    assert "node[2].path" in printed.err
