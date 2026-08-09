"""Read a profile directory, refuse a bad one loudly, and construct what it declares.

    from attrappe.profile import load_profile

    profile = load_profile(Path("profiles/bench-multimeter"))

`docs/decisions/0005-profiles.md` is what this implements. A profile is a
directory holding a declarative file, `profile.toml`, and an optional Python
module, `behaviour.py`. The declarative half is read here. The code half is
never executed by this function: `load_code_half` does that and has to be
called on purpose, because loading a profile from an untrusted source runs the
source and the record says so in as many words.

Validation finishes before anything is constructed, and it reports every problem
it found rather than the first. A contributor writing their first profile
against a loader that stops at problem one learns the format by running it
again, and the format has enough rules that this takes a while.

Every problem carries the file it is in, the key it is about, and what was
expected. A message saying only that a profile is invalid tells somebody with a
two-hundred-line command tree nothing they can act on.

What this refuses, and each one is a fixture under `tests/profile/fixtures`:

- a parameter whose declared range does not contain its own default
- a node whose short form is not a prefix of its long form
- a node declared twice
- a node whose parent is not declared, which cannot be placed in a tree
- a node declaring a form it accepts that is not one of the declared forms
- a node declaring fewer than one instance of itself
- a node accepting a query with no parameter to answer from
- a response separator that is empty
- an unknown key, rather than ignoring it, because an ignored key is a typo
  that silently does nothing
- the shape rules underneath those: a missing required key, a value of the
  wrong type, an empty mnemonic, a queue depth below one, and an identity field
  carrying the comma that separates the identification response's own fields

What it does not carry yet. The quirk overlays that `0005-profiles.md` puts in
the declarative half have no keys here, so a profile declaring one is refused as
an unknown key. #38 is the issue that adds them, and it adds the schema for them
at the same time; inventing that schema here would be guessing at what a quirk
looks like before any quirk exists.
"""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

# The two halves of a profile directory. Both names are fixed rather than
# configurable: a profile whose file names vary is one a reader has to open to
# understand, and there is nothing to gain from the freedom.
DECLARATIVE_FILE = "profile.toml"
CODE_FILE = "behaviour.py"

# The declared keys, per table. Anything outside these sets is refused. The sets
# are the schema, and they are here rather than spread through the checks below
# so that the answer to "what may a profile say" is one screen.
TOP_LEVEL_KEYS = frozenset({"identity", "error_queue", "response", "node", "parameter"})
IDENTITY_KEYS = ("manufacturer", "model", "serial", "firmware")
ERROR_QUEUE_KEYS = frozenset({"depth"})
RESPONSE_KEYS = frozenset({"separator"})
NODE_REQUIRED = ("path", "short")
NODE_KEYS = frozenset((*NODE_REQUIRED, "accepts", "suffixes"))

# What a node accepts, which decides whether a header resolving to it is a
# command at all. A node declaring none of them is a branch: it exists so its
# children have somewhere to hang, and a header stopping on it is undefined.
# The forms are separate because a device has command-only nodes such as an
# immediate trigger and query-only nodes such as a reading, and collapsing the
# two would make the emulator answer a form the device refuses.
ACCEPTED_FORMS = ("set", "query", "both")
ACCEPTS_SET = ("set", "both")
ACCEPTS_QUERY = ("query", "both")

# How many instances of a node exist, which is what a numeric suffix selects
# among. One is the default and it is not the absence of a suffix: SCPI reads an
# omitted suffix as one, so a node declaring one instance answers to both `CHAN`
# and `CHAN1` and refuses `CHAN2`.
DEFAULT_SUFFIXES = 1

# The separator between the values of a query that answers with several. A
# profile may declare another; a device that answers with a different character
# is a device a driver splits wrongly.
DEFAULT_SEPARATOR = ","
PARAMETER_REQUIRED = ("node", "name", "type", "default")
PARAMETER_KEYS = frozenset(
    (*PARAMETER_REQUIRED, "minimum", "maximum", "choices", "units", "survives_reset")
)

# A parameter's type decides which of the optional keys are required, which are
# allowed, and what a range containing the default means for it.
PARAMETER_TYPES = ("numeric", "boolean", "character", "string")
RANGE_KEYS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "numeric": ("minimum", "maximum"),
    "boolean": (),
    "character": ("choices",),
    "string": (),
}
UNITS_ALLOWED_FOR = frozenset({"numeric"})


@dataclass(frozen=True)
class Problem:
    """One refusal: where it is, which key it is about, and what was expected."""

    file: str
    key: str
    expected: str

    def __str__(self) -> str:
        where = f"{self.file}: {self.key}" if self.key else self.file
        return f"{where}: {self.expected}"


class ProfileError(Exception):
    """A profile that failed validation, carrying every problem found in it.

    The profile is named in the message. A run that loads several profiles and
    prints one of these without the name leaves the operator to guess which
    directory it was about.
    """

    def __init__(self, profile: str, problems: Sequence[Problem]) -> None:
        self.profile = profile
        self.problems: tuple[Problem, ...] = tuple(problems)
        heading = f"profile {profile}: {len(self.problems)} problem(s)"
        super().__init__("\n".join([heading, *(f"  {problem}" for problem in self.problems)]))


@dataclass(frozen=True)
class Parameter:
    """One setting under one node: its type, its range, its default, its units."""

    node: str
    name: str
    type: str
    default: object
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] | None = None
    units: str | None = None
    survives_reset: bool = False


@dataclass(frozen=True)
class Node:
    """One mnemonic in the command tree, with its short form and its children.

    `path` is the long forms from the root down to and including this node, so a
    node knows where it sits without a reference back to its parent.

    `accepts` is None on a branch, which is a node that exists only to carry
    children. `suffixes` is how many instances of the node exist, counting from
    one.
    """

    long: str
    short: str
    path: tuple[str, ...]
    children: tuple[Node, ...] = ()
    parameters: tuple[Parameter, ...] = ()
    accepts: str | None = None
    suffixes: int = DEFAULT_SUFFIXES

    @property
    def settable(self) -> bool:
        return self.accepts in ACCEPTS_SET

    @property
    def queryable(self) -> bool:
        return self.accepts in ACCEPTS_QUERY

    def walk(self) -> list[Node]:
        """This node and every node below it, parents before children."""
        found = [self]
        for child in self.children:
            found.extend(child.walk())
        return found


@dataclass(frozen=True)
class Profile:
    """A loaded profile: the identification response, the tree, the queue depth.

    `code_half` is the path to the optional Python module, or None when the
    directory has none. It is a path rather than a module because nothing here
    executes it.
    """

    name: str
    directory: Path
    identification: str
    error_queue_depth: int
    roots: tuple[Node, ...]
    code_half: Path | None
    separator: str = DEFAULT_SEPARATOR

    def nodes(self) -> list[Node]:
        """Every node in the tree, parents before children."""
        found: list[Node] = []
        for root in self.roots:
            found.extend(root.walk())
        return found

    def parameters(self) -> list[Parameter]:
        """Every parameter in the tree, in the order their nodes appear."""
        return [parameter for node in self.nodes() for parameter in node.parameters]


def load_profile(directory: Path) -> Profile:
    """Validate the declarative half of a profile directory and construct it.

    Raises `ProfileError` carrying every problem found. Nothing is constructed
    while a problem stands, so a caller never holds a half-built tree.
    """
    name = directory.name or str(directory)
    source = directory / DECLARATIVE_FILE
    document, problems = _read_declaration(source)
    if problems:
        raise ProfileError(name, problems)

    problems = _validate(document)
    if problems:
        raise ProfileError(name, problems)

    code_half = directory / CODE_FILE
    return _construct(
        name=name,
        directory=directory,
        document=document,
        code_half=code_half if code_half.is_file() else None,
    )


def load_code_half(profile: Profile) -> ModuleType | None:
    """Import and execute the profile's Python module, or answer None if it has none.

    Separate from `load_profile` and never called by it. Loading a profile from
    an untrusted source runs that source, `docs/decisions/0005-profiles.md` says
    this project does not sandbox it, and a caller that wants the behaviour half
    says so here rather than getting it as a side effect of reading a file.
    """
    if profile.code_half is None:
        return None

    module_name = f"attrappe.profile.loaded.{profile.name.replace('-', '_')}"
    specification = importlib.util.spec_from_file_location(module_name, profile.code_half)
    if specification is None or specification.loader is None:
        raise ProfileError(
            profile.name,
            [Problem(CODE_FILE, "", "a Python module the interpreter can load")],
        )
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    specification.loader.exec_module(module)
    return module


def _read_declaration(source: Path) -> tuple[dict[str, Any], list[Problem]]:
    """The parsed declarative file, or the one problem that stopped it being read."""
    try:
        text = source.read_bytes()
    except OSError as absent:
        return {}, [Problem(DECLARATIVE_FILE, "", f"a readable declarative file ({absent})")]
    try:
        document = tomllib.loads(text.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as unreadable:
        return {}, [Problem(DECLARATIVE_FILE, "", f"valid TOML ({unreadable})")]
    return document, []


def _validate(document: dict[str, Any]) -> list[Problem]:
    """Every problem in the declaration, in the order the file declares them.

    Every leg runs. None of them stops the others, because the point of this
    function is the whole list.
    """
    problems: list[Problem] = []
    problems.extend(_unknown_keys("", document, TOP_LEVEL_KEYS))
    problems.extend(_validate_identity(document.get("identity")))
    problems.extend(_validate_error_queue(document.get("error_queue")))
    problems.extend(_validate_response(document.get("response")))
    declared = _validate_nodes(document.get("node"), problems)
    _validate_parameters(document.get("parameter"), declared, problems)
    _check_a_query_has_something_to_answer(document, problems)
    return problems


def _check_a_query_has_something_to_answer(
    document: dict[str, Any], problems: list[Problem]
) -> None:
    """Refuse a node accepting a query with no parameter under it.

    A query is answered from the values of its node's parameters, so a node with
    none answers with no bytes at all. That is worse than a refusal: the client
    reads an empty response where it expected a value, and the profile it came
    from said the command was there.

    This is where a reading command will meet the loader. `MEASure:VOLTage:DC?`
    answers from the measurement model rather than from a parameter table, so
    the profile format needs a way to say that a node's answer comes from the
    code half, and that is the reading pipeline's to add rather than something
    to invent here for a node that does not exist yet.
    """
    entries = document.get("node")
    parameters = document.get("parameter")
    if not isinstance(entries, list):
        return

    answered: set[tuple[str, ...]] = set()
    if isinstance(parameters, list):
        for entry in parameters:
            node = entry.get("node") if isinstance(entry, dict) else None
            if isinstance(node, str) and node:
                answered.add(tuple(mnemonic.upper() for mnemonic in node.split(":")))

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or entry.get("accepts") not in ACCEPTS_QUERY:
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            continue
        if tuple(mnemonic.upper() for mnemonic in path.split(":")) not in answered:
            problems.append(
                Problem(
                    DECLARATIVE_FILE,
                    f"node[{index}].accepts",
                    "at least one parameter under the node, since a query is answered from "
                    f'them; nothing declares one under "{path}"',
                )
            )


def _unknown_keys(prefix: str, table: dict[str, Any], allowed: frozenset[str]) -> list[Problem]:
    """Refuse a key nobody declared, naming it and listing what was allowed.

    Ignoring an unknown key turns a typo into a setting that silently does
    nothing, which is the failure this repository would meet as a profile whose
    error-queue depth was never applied because it was spelled `depths`.
    """
    return [
        Problem(
            DECLARATIVE_FILE,
            f"{prefix}{key}",
            f"one of the declared keys: {', '.join(sorted(allowed))}",
        )
        for key in table
        if key not in allowed
    ]


def _validate_identity(identity: object) -> list[Problem]:
    """The four fields the identification response is built from.

    All four are required, none may be empty, and none may carry a comma,
    because the response is those four fields separated by commas and a comma
    inside one of them is a fifth field a driver will read as one.
    """
    if identity is None:
        return [Problem(DECLARATIVE_FILE, "identity", "a table declaring the identity fields")]
    if not isinstance(identity, dict):
        return [Problem(DECLARATIVE_FILE, "identity", "a table, not a value")]

    problems = _unknown_keys("identity.", identity, frozenset(IDENTITY_KEYS))
    for field in IDENTITY_KEYS:
        key = f"identity.{field}"
        value = identity.get(field)
        if value is None:
            problems.append(Problem(DECLARATIVE_FILE, key, "a value, since all four are required"))
        elif not isinstance(value, str) or not value.strip():
            problems.append(Problem(DECLARATIVE_FILE, key, "a non-empty string"))
        elif "," in value:
            problems.append(
                Problem(
                    DECLARATIVE_FILE,
                    key,
                    "a string with no comma, which separates the identification fields",
                )
            )
    return problems


def _validate_error_queue(error_queue: object) -> list[Problem]:
    """The queue depth. #23 is the queue this feeds and it takes its depth here."""
    if error_queue is None:
        return [Problem(DECLARATIVE_FILE, "error_queue", "a table declaring the queue depth")]
    if not isinstance(error_queue, dict):
        return [Problem(DECLARATIVE_FILE, "error_queue", "a table, not a value")]

    problems = _unknown_keys("error_queue.", error_queue, ERROR_QUEUE_KEYS)
    depth = error_queue.get("depth")
    if depth is None:
        problems.append(Problem(DECLARATIVE_FILE, "error_queue.depth", "a value"))
    elif isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        problems.append(
            Problem(DECLARATIVE_FILE, "error_queue.depth", "a whole number of one or more")
        )
    return problems


def _validate_response(response: object) -> list[Problem]:
    """The separator between the values of a query answering with several.

    The whole table is optional, because a profile whose every query answers
    with one value has nothing to say here and the default is the comma every
    such device uses. What is refused is a declared separator that is empty,
    which is a device whose two-value response a driver reads as one value.
    """
    if response is None:
        return []
    if not isinstance(response, dict):
        return [Problem(DECLARATIVE_FILE, "response", "a table, not a value")]

    problems = _unknown_keys("response.", response, RESPONSE_KEYS)
    separator = response.get("separator")
    if separator is None:
        return problems
    if not isinstance(separator, str) or not separator:
        problems.append(Problem(DECLARATIVE_FILE, "response.separator", "a non-empty string"))
    return problems


def _validate_nodes(node_entries: object, problems: list[Problem]) -> dict[tuple[str, ...], int]:
    """Check every node and answer the paths that are declared, keyed uppercase.

    The answer is what the parameter check needs, so the two do not each build
    their own idea of which nodes exist and disagree about it later.
    """
    declared: dict[tuple[str, ...], int] = {}
    if node_entries is None:
        problems.append(Problem(DECLARATIVE_FILE, "node", "at least one [[node]] entry"))
        return declared
    if not isinstance(node_entries, list) or not node_entries:
        problems.append(Problem(DECLARATIVE_FILE, "node", "a non-empty list of [[node]] entries"))
        return declared

    for index, entry in enumerate(node_entries):
        key = f"node[{index}]"
        if not isinstance(entry, dict):
            problems.append(Problem(DECLARATIVE_FILE, key, "a [[node]] table"))
            continue
        problems.extend(_unknown_keys(f"{key}.", entry, NODE_KEYS))
        path = _node_path(key, entry, problems)
        if path is None:
            continue
        _check_short_form(key, entry, path, problems)
        _check_accepts(key, entry, problems)
        _check_suffixes(key, entry, problems)
        if path in declared:
            problems.append(
                Problem(
                    DECLARATIVE_FILE,
                    f"{key}.path",
                    f"a path no earlier node declares; node[{declared[path]}] already declares "
                    f'"{":".join(path)}"',
                )
            )
            continue
        declared[path] = index

    for path, index in sorted(declared.items(), key=lambda item: item[1]):
        if len(path) > 1 and path[:-1] not in declared:
            problems.append(
                Problem(
                    DECLARATIVE_FILE,
                    f"node[{index}].path",
                    f'a declared parent; nothing declares "{":".join(path[:-1])}"',
                )
            )
    return declared


def _node_path(key: str, entry: dict[str, Any], problems: list[Problem]) -> tuple[str, ...] | None:
    """The node's path as uppercase mnemonics, or None when it cannot be read."""
    path = entry.get("path")
    if path is None:
        problems.append(Problem(DECLARATIVE_FILE, f"{key}.path", "a value, since it is required"))
        return None
    if not isinstance(path, str) or not path:
        problems.append(
            Problem(DECLARATIVE_FILE, f"{key}.path", "a non-empty colon-separated string")
        )
        return None

    mnemonics = path.split(":")
    for mnemonic in mnemonics:
        if not mnemonic or not mnemonic.isalnum() or not mnemonic[0].isalpha():
            problems.append(
                Problem(
                    DECLARATIVE_FILE,
                    f"{key}.path",
                    "colon-separated mnemonics, each starting with a letter and "
                    f'otherwise letters and digits; got "{path}"',
                )
            )
            return None
    return tuple(mnemonic.upper() for mnemonic in mnemonics)


def _check_short_form(
    key: str, entry: dict[str, Any], path: tuple[str, ...], problems: list[Problem]
) -> None:
    """Refuse a short form that is not a prefix of the long form it abbreviates.

    A real instrument accepts the short form and the long form and refuses
    everything between them. That refusal is only expressible where the short
    form is a prefix, so a profile declaring `VLT` for `VOLTAGE` describes a
    device the parser cannot implement.
    """
    short = entry.get("short")
    long = path[-1]
    if short is None:
        problems.append(Problem(DECLARATIVE_FILE, f"{key}.short", "a value, since it is required"))
        return
    if not isinstance(short, str) or not short:
        problems.append(Problem(DECLARATIVE_FILE, f"{key}.short", "a non-empty string"))
        return
    if not long.startswith(short.upper()):
        problems.append(
            Problem(
                DECLARATIVE_FILE,
                f"{key}.short",
                f'a prefix of the long form "{long}"; got "{short}"',
            )
        )


def _check_accepts(key: str, entry: dict[str, Any], problems: list[Problem]) -> None:
    """Refuse a form that is none of the declared ones.

    Absent is legal and means a branch. A misspelling would otherwise be read as
    a branch too, and a node that quietly accepts nothing is a subsystem the
    emulator answers `-113` for while the profile says it is there.
    """
    accepts = entry.get("accepts")
    if accepts is None:
        return
    if not isinstance(accepts, str) or accepts not in ACCEPTED_FORMS:
        problems.append(
            Problem(
                DECLARATIVE_FILE,
                f"{key}.accepts",
                f"one of {', '.join(ACCEPTED_FORMS)}; got {accepts!r}",
            )
        )


def _check_suffixes(key: str, entry: dict[str, Any], problems: list[Problem]) -> None:
    """Refuse an instance count below one, since suffixes count from one."""
    suffixes = entry.get("suffixes")
    if suffixes is None:
        return
    if isinstance(suffixes, bool) or not isinstance(suffixes, int) or suffixes < 1:
        problems.append(
            Problem(DECLARATIVE_FILE, f"{key}.suffixes", "a whole number of one or more")
        )


def _validate_parameters(
    parameter_entries: object,
    declared: dict[tuple[str, ...], int],
    problems: list[Problem],
) -> None:
    """Check every parameter: its node, its type, its range and its default."""
    if parameter_entries is None:
        return
    if not isinstance(parameter_entries, list):
        problems.append(Problem(DECLARATIVE_FILE, "parameter", "a list of [[parameter]] entries"))
        return

    seen: dict[tuple[tuple[str, ...], str], int] = {}
    for index, entry in enumerate(parameter_entries):
        key = f"parameter[{index}]"
        if not isinstance(entry, dict):
            problems.append(Problem(DECLARATIVE_FILE, key, "a [[parameter]] table"))
            continue
        problems.extend(_unknown_keys(f"{key}.", entry, PARAMETER_KEYS))
        for required in PARAMETER_REQUIRED:
            if entry.get(required) is None:
                problems.append(
                    Problem(
                        DECLARATIVE_FILE,
                        f"{key}.{required}",
                        "a value, since it is required",
                    )
                )

        node_path = _parameter_node(key, entry, declared, problems)
        name = entry.get("name")
        if node_path is not None and isinstance(name, str) and name:
            identity = (node_path, name.upper())
            if identity in seen:
                problems.append(
                    Problem(
                        DECLARATIVE_FILE,
                        f"{key}.name",
                        f"a name no earlier parameter on this node declares; "
                        f"parameter[{seen[identity]}] already declares it",
                    )
                )
            else:
                seen[identity] = index
        elif name is not None and (not isinstance(name, str) or not name):
            problems.append(Problem(DECLARATIVE_FILE, f"{key}.name", "a non-empty string"))

        _check_parameter_type(key, entry, problems)


def _parameter_node(
    key: str,
    entry: dict[str, Any],
    declared: dict[tuple[str, ...], int],
    problems: list[Problem],
) -> tuple[str, ...] | None:
    """The node a parameter hangs off, refused when nothing declares it."""
    node = entry.get("node")
    if node is None:
        return None
    if not isinstance(node, str) or not node:
        problems.append(Problem(DECLARATIVE_FILE, f"{key}.node", "a non-empty string"))
        return None
    path = tuple(mnemonic.upper() for mnemonic in node.split(":"))
    if path not in declared:
        problems.append(
            Problem(DECLARATIVE_FILE, f"{key}.node", f'a declared node; nothing declares "{node}"')
        )
        return None
    return path


def _check_parameter_type(key: str, entry: dict[str, Any], problems: list[Problem]) -> None:
    """The type, the keys that type requires, and the default sitting inside them."""
    kind = entry.get("type")
    if kind is None:
        return
    if not isinstance(kind, str) or kind not in PARAMETER_TYPES:
        problems.append(
            Problem(DECLARATIVE_FILE, f"{key}.type", f"one of {', '.join(PARAMETER_TYPES)}")
        )
        return

    required = RANGE_KEYS_BY_TYPE[kind]
    for range_key in ("minimum", "maximum", "choices"):
        present = entry.get(range_key) is not None
        if range_key in required and not present:
            problems.append(
                Problem(
                    DECLARATIVE_FILE,
                    f"{key}.{range_key}",
                    f"a value, since a {kind} parameter declares its range with "
                    f"{' and '.join(required)}",
                )
            )
        elif range_key not in required and present:
            problems.append(
                Problem(
                    DECLARATIVE_FILE,
                    f"{key}.{range_key}",
                    f"no value, since a {kind} parameter has no such range",
                )
            )
    if entry.get("units") is not None and kind not in UNITS_ALLOWED_FOR:
        problems.append(
            Problem(DECLARATIVE_FILE, f"{key}.units", f"no value, since a {kind} has no units")
        )
    if entry.get("survives_reset") is not None and not isinstance(
        entry.get("survives_reset"), bool
    ):
        problems.append(Problem(DECLARATIVE_FILE, f"{key}.survives_reset", "true or false"))

    if kind == "numeric":
        _check_numeric_default(key, entry, problems)
    elif kind == "character":
        _check_character_default(key, entry, problems)
    elif kind == "boolean":
        if not isinstance(entry.get("default"), bool):
            problems.append(Problem(DECLARATIVE_FILE, f"{key}.default", "true or false"))
    elif kind == "string":
        if entry.get("default") is not None and not isinstance(entry.get("default"), str):
            problems.append(Problem(DECLARATIVE_FILE, f"{key}.default", "a string"))


def _check_numeric_default(key: str, entry: dict[str, Any], problems: list[Problem]) -> None:
    """Refuse a numeric parameter whose range does not contain its own default.

    A default outside its range is a device that answers a reset with a value it
    would refuse if you sent it, and the software that meets it has no way to
    tell which of the two is wrong.
    """
    minimum = _number(key, "minimum", entry, problems)
    maximum = _number(key, "maximum", entry, problems)
    default = _number(key, "default", entry, problems)
    if minimum is None or maximum is None or default is None:
        return
    if minimum > maximum:
        problems.append(
            Problem(
                DECLARATIVE_FILE,
                f"{key}.minimum",
                f"a value at or below the maximum {maximum}; got {minimum}",
            )
        )
        return
    if not minimum <= default <= maximum:
        problems.append(
            Problem(
                DECLARATIVE_FILE,
                f"{key}.default",
                f"a value inside the declared range {minimum} to {maximum}; got {default}",
            )
        )


def _check_character_default(key: str, entry: dict[str, Any], problems: list[Problem]) -> None:
    """Refuse a character parameter whose choices do not contain its own default."""
    choices = entry.get("choices")
    default = entry.get("default")
    if choices is None:
        return
    if (
        not isinstance(choices, list)
        or not choices
        or not all(isinstance(choice, str) and choice for choice in choices)
    ):
        problems.append(
            Problem(DECLARATIVE_FILE, f"{key}.choices", "a non-empty list of non-empty strings")
        )
        return
    if default is None:
        return
    if not isinstance(default, str):
        problems.append(Problem(DECLARATIVE_FILE, f"{key}.default", "a string"))
        return
    if default.upper() not in {choice.upper() for choice in choices}:
        problems.append(
            Problem(
                DECLARATIVE_FILE,
                f"{key}.default",
                f'one of the declared choices {", ".join(choices)}; got "{default}"',
            )
        )


def _number(key: str, field: str, entry: dict[str, Any], problems: list[Problem]) -> float | None:
    """A numeric value, refusing the boolean that Python would otherwise accept."""
    value = entry.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        problems.append(Problem(DECLARATIVE_FILE, f"{key}.{field}", "a number"))
        return None
    return float(value)


def _construct(
    name: str,
    directory: Path,
    document: dict[str, Any],
    code_half: Path | None,
) -> Profile:
    """Build the identification response, the tree and the parameter table.

    Reached only once validation found nothing, so every read below is of a
    value some check above already agreed with.
    """
    identity = document["identity"]
    identification = ",".join(identity[field] for field in IDENTITY_KEYS)

    parameters: dict[tuple[str, ...], list[Parameter]] = {}
    for entry in document.get("parameter", []):
        path = tuple(mnemonic.upper() for mnemonic in entry["node"].split(":"))
        parameters.setdefault(path, []).append(
            Parameter(
                node=":".join(path),
                name=entry["name"],
                type=entry["type"],
                default=entry["default"],
                minimum=entry.get("minimum"),
                maximum=entry.get("maximum"),
                choices=tuple(entry["choices"]) if entry.get("choices") is not None else None,
                units=entry.get("units"),
                survives_reset=bool(entry.get("survives_reset", False)),
            )
        )

    shorts: dict[tuple[str, ...], str] = {}
    accepts: dict[tuple[str, ...], str | None] = {}
    suffixes: dict[tuple[str, ...], int] = {}
    order: list[tuple[str, ...]] = []
    for entry in document["node"]:
        path = tuple(mnemonic.upper() for mnemonic in entry["path"].split(":"))
        shorts[path] = entry["short"].upper()
        accepts[path] = entry.get("accepts")
        suffixes[path] = int(entry.get("suffixes", DEFAULT_SUFFIXES))
        order.append(path)

    children: dict[tuple[str, ...], list[tuple[str, ...]]] = {path: [] for path in order}
    roots: list[tuple[str, ...]] = []
    for path in order:
        if len(path) == 1:
            roots.append(path)
        else:
            children[path[:-1]].append(path)

    def build(path: tuple[str, ...]) -> Node:
        return Node(
            long=path[-1],
            short=shorts[path],
            path=path,
            children=tuple(build(child) for child in children[path]),
            parameters=tuple(parameters.get(path, ())),
            accepts=accepts[path],
            suffixes=suffixes[path],
        )

    response = document.get("response", {})
    return Profile(
        name=name,
        directory=directory,
        identification=identification,
        error_queue_depth=document["error_queue"]["depth"],
        roots=tuple(build(path) for path in roots),
        code_half=code_half,
        separator=response.get("separator", DEFAULT_SEPARATOR),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Validate a profile directory and say so. Non-zero when it is refused.

    This is the shape #27's validate subcommand calls rather than a second
    implementation of it. It starts nothing: there is no emulator in this tree
    to start, so the half of #25 that says the emulator does not start on a bad
    profile is not proven here and is #26's and #27's to prove.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate a profile directory and report every problem in it."
    )
    parser.add_argument("directory", help="the profile directory to read")
    arguments = parser.parse_args(argv)

    try:
        profile = load_profile(Path(arguments.directory))
    except ProfileError as refused:
        print(refused, file=sys.stderr)
        return 1
    print(f"profile {profile.name}: {len(profile.nodes())} node(s), {profile.identification}")
    return 0
