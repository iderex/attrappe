"""The command line an operator runs, and the lines it prints before it serves.

    python -m attrappe run tests/scpi/fixtures/instrument
    python -m attrappe list
    python -m attrappe validate tests/scpi/fixtures/instrument

Three subcommands and no more. `run` starts a listener from a profile, `list`
names the profiles it can find, and `validate` reads a profile directory and
reports every problem in it without opening a socket, which is what a
contributor writing their first profile needs.

## The startup output is a bug report

Five lines, one fact each: the profile that was loaded, the identification
string a client will read back, the interface and port that were actually bound,
the seed, and the fault schedule in force. A sixth line names the configuration
file that was read, or says none was, because a value nobody can trace to a flag
has to be traceable to a file.

Bound rather than asked for. A port of zero is a request; the number a client
connects to is what the operating system gave back, and `Server.announcement`
exists for the same reason.

Everything an operator would have to retype into a bug report is in those six
lines, and a session is reproduced from the profile, the seed and the commands.

## Where the profiles come from

A profile is named by a path or by a name. A path is used as it stands. A name
is looked for in the search path: the directories `--profile-path` gives, or
those the configuration file gives when the flag does not, and then the shipped
directory beside this module.

No profile is shipped. That directory does not exist in this tree and #28 is the
issue that lands the first one, so a name resolves to nothing today and `list`
says so rather than printing an empty list that reads as a clean run. A path
still works, which is what the suite and a contributor writing a profile use.

## The fault schedule line, and the flag that is not here

The line is printed and it always says none. There is no fault schedule engine
in this tree: #35 builds it, and the trigger kinds it will implement are
`docs/decisions/0007-fault-schedule.md`'s. So there is no `--fault-schedule`
flag, because a flag that took a file and applied nothing would make the line
above say a schedule was in force while nothing read it, which is worse than the
missing option.

## Exit codes

Four of them, and 1 is deliberately not among them: the interpreter exits 1 on
an uncaught exception, so leaving it free keeps a crash from reading as one of
the conditions below.

- 0, the run did what it was asked.
- 2, the invocation was wrong. An unknown flag, no profile anywhere, a name that
  resolves to nothing, a configuration file that will not read. This is
  argparse's own code for a bad command line and the rest are put with it.
- 3, the profile was refused. Every problem in it is on standard error.
- 4, a runtime failure. The port is taken, the interface does not exist, the log
  destination cannot be opened.

## What this writes to disk

Nothing, unless `--log` names a file, and then the six lines above go there
instead of to standard output. That is the only path this program writes, and
#57 is the issue that states the whole set field by field.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from attrappe.profile import DECLARATIVE_FILE, Profile, ProfileError, load_profile
from attrappe.profile import main as validate_a_profile
from attrappe.transport import LOOPBACK, Server, choose_seed
from attrappe.transport.server import DEFAULT_PORT

# The exit codes, for the reasons the module docstring gives.
OK = 0
BAD_INVOCATION = 2
BAD_PROFILE = 3
RUNTIME_FAILURE = 4

# Where a profile name is looked for when the search path has nothing else in
# it. Beside this module rather than in the checkout, so that an installed
# distribution carries its profiles with it. Nothing is there yet.
SHIPPED_PROFILES = Path(__file__).parent / "profiles"

# The configuration file read when `--config` names none, in the directory the
# command was run from. One file rather than a search up the tree: a
# configuration picked up from a parent directory is one an operator did not
# know they had, and this command prints which file it read for that reason.
CONFIGURATION_FILE = "attrappe.toml"

# What a configuration file may say, and what each value has to be. Each key is
# the long form of a flag with the dashes turned into an underscore, so a reader
# who knows one knows the other. An unknown key is refused rather than ignored,
# for the reason the profile loader refuses one: an ignored key is a typo that
# silently does nothing while the value the operator meant to set stays at its
# default.
CONFIGURATION_KEYS: dict[str, type] = {
    "profile": str,
    "host": str,
    "port": int,
    "seed": int,
    "log": str,
    "profile_path": list,
}

# The name of the program in its own messages. `sys.argv[0]` is a path that
# differs between `python -m attrappe`, an installed console script and a
# checkout, and a message that differs by how it was invoked is one two
# transcripts cannot be compared across.
PROGRAM = "attrappe"


class Invalid(Exception):
    """A bad invocation, carrying the sentence the operator reads."""


@dataclass(frozen=True)
class Settings:
    """Everything `run` needs, after the flags have won over the file."""

    directory: Path
    host: str
    port: int
    seed: int
    log: Path | None
    configuration: Path | None


def build_parser() -> argparse.ArgumentParser:
    """The whole command line, in one place.

    `run` and `validate` take their profile as an optional positional, because
    the configuration file may name it instead. What is missing is reported
    below rather than by argparse, which would call a profile missing while a
    file three lines away supplied it.
    """
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="An instrument emulator a measurement driver connects to.",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        type=Path,
        help=(
            f"the configuration file to read; without this, {CONFIGURATION_FILE} in the "
            "current directory is read when it is there"
        ),
    )
    parser.add_argument(
        "--profile-path",
        metavar="DIR",
        type=Path,
        action="append",
        help=(
            "a directory to look for profile names in; repeatable, and given once it "
            "replaces the list a configuration file gives"
        ),
    )

    subcommands = parser.add_subparsers(dest="command", metavar="COMMAND")

    starting = subcommands.add_parser(
        "run",
        help="start an emulator from a profile and serve until interrupted",
    )
    starting.add_argument(
        "profile",
        nargs="?",
        help="a profile name from `list`, or a path to a profile directory",
    )
    starting.add_argument("--host", metavar="ADDRESS", help=f"interface to bind ({LOOPBACK})")
    starting.add_argument("--port", metavar="PORT", type=int, help=f"port to bind ({DEFAULT_PORT})")
    starting.add_argument(
        "--seed",
        metavar="NUMBER",
        type=int,
        help="the session seed to print and to derive every named stream from",
    )
    starting.add_argument(
        "--log",
        metavar="FILE",
        type=Path,
        help="write the startup lines to this file instead of to standard output",
    )

    subcommands.add_parser("list", help="name the profiles on the search path")

    checking = subcommands.add_parser(
        "validate",
        help="read a profile and report every problem in it, opening no socket",
    )
    checking.add_argument(
        "profile",
        nargs="?",
        help="a profile name from `list`, or a path to a profile directory",
    )

    return parser


def read_configuration(path: Path) -> dict[str, object]:
    """One configuration file, refusing an unknown key and a value of the wrong type.

    Raises `Invalid`, because a configuration this command cannot read is a bad
    invocation and not a bad profile: nothing has been asked of the loader yet.
    """
    try:
        document: dict[str, object] = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as unreadable:
        raise Invalid(f"cannot read {path}: {unreadable}") from unreadable
    except tomllib.TOMLDecodeError as malformed:
        raise Invalid(f"{path} is not readable as TOML: {malformed}") from malformed

    for key, value in document.items():
        check_configured(path, key, value)
    return document


def check_configured(path: Path, key: str, value: object) -> None:
    """Refuse one configuration entry the flags could not have produced."""
    wanted = CONFIGURATION_KEYS.get(key)
    if wanted is None:
        allowed = ", ".join(sorted(CONFIGURATION_KEYS))
        raise Invalid(f"{path}: unknown key {key!r}; this file takes {allowed}")
    # `bool` is a subclass of `int`, so a port declared as `true` passes an
    # isinstance check against int and binds port one.
    if isinstance(value, bool) or not isinstance(value, wanted):
        got = type(value).__name__
        raise Invalid(f"{path}: {key} has to be {wanted.__name__}, and it is {got}")
    if isinstance(value, list) and not all(isinstance(entry, str) for entry in value):
        raise Invalid(f"{path}: {key} has to be a list of strings")


def configuration_for(named: Path | None) -> tuple[Path | None, dict[str, object]]:
    """The configuration that applies, and the file it came from, or None.

    A file named on the command line and not there is a bad invocation. The
    default file not being there is the ordinary case and reports nothing.
    """
    if named is not None:
        if not named.is_file():
            raise Invalid(f"no configuration file at {named}")
        return named, read_configuration(named)
    fallback = Path(CONFIGURATION_FILE)
    if fallback.is_file():
        return fallback, read_configuration(fallback)
    return None, {}


def search_path(flag: Sequence[Path] | None, configured: object) -> tuple[Path, ...]:
    """Where a profile name is looked for, in the order it is looked for.

    The flag wins whole rather than adding to the file's list, so an operator
    who gives one on the command line gets the one they gave, and not that one
    behind two they forgot were in a file.
    """
    if flag:
        given = tuple(flag)
    elif isinstance(configured, list):
        given = tuple(Path(str(entry)) for entry in configured)
    else:
        given = ()
    return (*given, SHIPPED_PROFILES)


def looks_like_a_path(named: str) -> bool:
    """Whether the operator wrote a path rather than a name.

    A separator, a drive or a trailing slash makes it a path. The distinction
    decides which message a miss produces, and the two are worth telling apart:
    a mistyped path is corrected by looking at the disk, and a mistyped name is
    corrected by running `list`.
    """
    return len(Path(named).parts) > 1 or named in (".", "..") or named.endswith(("/", "\\"))


def resolve(named: str, search: Sequence[Path]) -> Path:
    """The directory a profile argument means, or `Invalid` naming where it was sought."""
    if looks_like_a_path(named):
        written = Path(named)
        if written.is_dir():
            return written
        raise Invalid(f"no profile directory at {written}")
    for directory in search:
        candidate = directory / named
        if candidate.is_dir():
            return candidate
    where = ", ".join(str(directory) for directory in search)
    raise Invalid(
        f"no profile named {named!r} in {where}; `{PROGRAM} list` names what is there, "
        "and a path to a directory works in place of a name"
    )


def profiles_in(directory: Path) -> list[Path]:
    """The profile directories directly inside one directory, in a stable order.

    A directory holding the declarative file is a profile. Nothing is loaded
    here: naming what is there is this subcommand's job and saying whether it
    loads is `validate`'s, and a `list` that hid a broken profile would hide the
    one the contributor is looking for.
    """
    if not directory.is_dir():
        return []
    return sorted(entry for entry in directory.iterdir() if (entry / DECLARATIVE_FILE).is_file())


def startup_lines(server: Server, profile: Profile, settings: Settings) -> list[str]:
    """The six lines, in the order the module docstring fixes them."""
    where = server.bound
    listening = "nothing bound" if where is None else f"{where[0]}:{where[1]}"
    read = "none read" if settings.configuration is None else str(settings.configuration)
    return [
        f"profile: {profile.name} from {profile.directory}",
        f"identification: {profile.identification}",
        f"listening: {listening}",
        f"seed: {server.seed}",
        "fault schedule: none in force",
        f"configuration: {read}",
    ]


@contextmanager
def destination(path: Path | None) -> Iterator[TextIO]:
    """Standard output, or the file `--log` named.

    Newlines are written as they are rather than translated, so the file holds
    the same bytes on every operating system and two transcripts compare.
    """
    if path is None:
        yield sys.stdout
        return
    handle = path.open("w", encoding="utf-8", newline="\n")
    try:
        yield handle
    finally:
        handle.close()


def start(
    settings: Settings,
    out: TextIO,
    started: Callable[[Server], None] | None,
) -> int:
    """Load, bind, write the six lines, and serve until something stops it."""
    try:
        profile = load_profile(settings.directory)
    except ProfileError as refused:
        print(refused, file=sys.stderr)
        return BAD_PROFILE

    server = Server(profile, host=settings.host, port=settings.port, seed=settings.seed)
    try:
        server.start()
    except OSError as failure:
        print(
            f"{PROGRAM}: cannot listen on {settings.host}:{settings.port}: {failure}",
            file=sys.stderr,
        )
        return RUNTIME_FAILURE

    try:
        for line in startup_lines(server, profile, settings):
            print(line, file=out)
        out.flush()
        if started is not None:
            started(server)
        server.serve_forever()
    except KeyboardInterrupt:
        # The ordinary way an operator stops this. It is not a failure, and it
        # does not print a traceback over the transcript they are about to paste
        # into a bug report.
        pass
    finally:
        server.stop()
    return OK


def name_the_profiles(search: Sequence[Path], out: TextIO) -> int:
    """Name every profile on the search path, and say where it looked.

    Where it looked is printed whether or not anything was found, so a run that
    searched one directory cannot be read as one that searched the set and found
    nothing in it.
    """
    found: list[Path] = []
    for directory in search:
        inside = profiles_in(directory)
        state = f"{len(inside)} profile(s)" if directory.is_dir() else "not present"
        print(f"searched: {directory} ({state})", file=out)
        found.extend(inside)

    if not found:
        print("no profile on the search path", file=out)
        return OK

    seen: set[str] = set()
    for entry in found:
        if entry.name in seen:
            # An earlier directory on the path answers this name, and `run`
            # would take that one. Saying so beats two lines a reader has to
            # guess between.
            print(f"{entry.name}: shadowed by an earlier directory, at {entry}", file=out)
            continue
        seen.add(entry.name)
        print(f"{entry.name}: {entry}", file=out)
    return OK


def settings_from(
    arguments: argparse.Namespace,
    directory: Path,
    configured: dict[str, object],
    source: Path | None,
) -> Settings:
    """The flags over the file over the defaults, one key at a time.

    The seed is the one default that is not a constant. It is drawn only when
    neither the flag nor the file gave one, because a session that took a drawn
    seed and printed it is reproducible and a session that quietly reused a
    fixed one is not.
    """
    configured_seed = configured.get("seed")
    if arguments.seed is not None:
        seed = int(arguments.seed)
    elif configured_seed is not None:
        seed = int(str(configured_seed))
    else:
        seed = choose_seed()

    host = arguments.host if arguments.host is not None else configured.get("host", LOOPBACK)
    port = arguments.port if arguments.port is not None else configured.get("port", DEFAULT_PORT)
    log = arguments.log if arguments.log is not None else as_path(configured.get("log"))
    return Settings(
        directory=directory,
        host=str(host),
        port=int(str(port)),
        seed=seed,
        log=log,
        configuration=source,
    )


def as_path(value: object) -> Path | None:
    """A configured path, or None when the file set none."""
    return None if value is None else Path(str(value))


def dispatch(
    command: str,
    arguments: argparse.Namespace,
    started: Callable[[Server], None] | None,
) -> int:
    """One command, with the configuration file already allowed to speak."""
    source, configured = configuration_for(arguments.config)
    search = search_path(arguments.profile_path, configured.get("profile_path"))

    if command == "list":
        return name_the_profiles(search, sys.stdout)

    named = arguments.profile if arguments.profile is not None else configured.get("profile")
    if named is None:
        raise Invalid(
            f"{command} needs a profile: a name from `{PROGRAM} list`, a path to a profile "
            "directory, or a `profile` key in a configuration file"
        )
    directory = resolve(str(named), search)

    if command == "validate":
        # The loader's own entry point rather than a second implementation of
        # it, so the problems a contributor reads here are the problems the
        # emulator would refuse to start on, printed by the same code. Its
        # non-zero is mapped onto this command's code for a refused profile.
        return OK if validate_a_profile([str(directory)]) == OK else BAD_PROFILE

    settings = settings_from(arguments, directory, configured, source)
    with destination(settings.log) as out:
        return start(settings, out, started)


def main(
    argv: Sequence[str] | None = None,
    *,
    started: Callable[[Server], None] | None = None,
) -> int:
    """Run one command and answer its exit code.

    `started` is called once the listener is bound and the startup lines are
    written, with the server, and before serving begins. Serving blocks the
    thread that called this, so a caller that has to stop the listener as well
    as start it has no other way to reach it: the suite drives `main` on a
    thread of its own and takes the server here. Nothing an operator runs passes
    it.
    """
    parser = build_parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as leaving:
        # argparse writes its own message and raises. Answering the code keeps
        # this a function a caller can call rather than one that ends their
        # process, and `--help` comes through here with a code of zero.
        code = leaving.code
        return code if isinstance(code, int) else BAD_INVOCATION

    command: str | None = arguments.command
    if command is None:
        print(
            f"{PROGRAM}: no command. `run` starts an emulator from a profile, `list` names "
            "the profiles it can find, and `validate` reads a profile and reports every "
            f"problem in it. `{PROGRAM} --help` says what each one takes.",
            file=sys.stderr,
        )
        return BAD_INVOCATION

    try:
        return dispatch(command, arguments, started)
    except Invalid as wrong:
        print(f"{PROGRAM}: {wrong}", file=sys.stderr)
        return BAD_INVOCATION
    except OSError as failure:
        # The log destination is the one that reaches here: it is opened after
        # the invocation has been read and before anything has been bound.
        print(f"{PROGRAM}: {failure}", file=sys.stderr)
        return RUNTIME_FAILURE
