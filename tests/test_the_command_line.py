"""The operator surface: what it prints, what it refuses, and what it answers.

The listener is driven on a thread of its own, because serving blocks the thread
that called it and a socket conversation has two ends. `attrappe.cli.main` hands
the bound server to a callback for exactly that reason, and `emulator` below is
the only caller that passes one.

Nothing here waits on elapsed time to decide anything. The patience below bounds
how long a broken run holds the suite; no assertion is made about it.
"""

from __future__ import annotations

import shutil
import socket
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import pytest

from attrappe import cli
from attrappe.transport import DEFAULT_TERMINATOR, Server

PROFILE = Path(__file__).parent / "scpi" / "fixtures" / "instrument"
IDENTIFICATION = "Attrappe,EMULATED-DMM-DISPATCH,0000000002,0.1.0"

# The fixtures the loader issue wrote to be refused, and the one written to
# load. Read off the disk rather than listed here, so a fixture added by a later
# issue is covered by the validate leg below without anyone remembering to add
# it.
FIXTURES = Path(__file__).parent / "profile" / "fixtures"
BROKEN = sorted(entry for entry in FIXTURES.iterdir() if entry.name.startswith("broken-"))

# How long the suite waits for a listener to bind or for bytes to arrive before
# the test fails. Nothing is measured against it.
PATIENCE = 10.0

# An address in the range reserved for documentation, which is not assigned to
# any interface on the machine running this. Binding it fails on every supported
# operating system, which is what makes it a runtime failure a test can produce
# without taking a port away from anything.
UNBINDABLE = "192.0.2.1"

# The seed the startup lines and the two-session comparison are asserted
# against. Fixed, because the property under test is that the same seed comes
# back, and a drawn one would be asserted against itself.
SEED = 20260810

# A conversation that reaches the parser, the tree, the instrument, the error
# queue and the status registers, one message per layer rather than one long
# one. A layer that stopped being reached is then a message nobody sent rather
# than a number that moved.
CONVERSATION = (
    "*IDN?",
    "SENS:VOLT:DC:RANG 100",
    "SENS:VOLT:DC:RANG?",
    "CONF:VOLT:DC?",
    "NOSUCH:THING",
    "SYST:ERR?",
    "*ESR?",
    "*STB?",
)


@contextmanager
def emulator(argv: Sequence[str]) -> Iterator[Server]:
    """`attrappe.cli.main` on a thread, yielding the listener it bound.

    The command is stopped through the server's own wakeup rather than by
    closing a socket underneath it, which is what `Server.stop` is written
    against, and the exit code is asserted after the thread has joined.
    """
    bound: list[Server] = []
    answered: list[int] = []
    listening = threading.Event()

    def started(server: Server) -> None:
        bound.append(server)
        listening.set()

    def drive() -> None:
        try:
            answered.append(cli.main(list(argv), started=started))
        finally:
            listening.set()

    thread = threading.Thread(target=drive, name="command-line-under-test")
    thread.start()
    try:
        assert listening.wait(PATIENCE), "the command line neither bound nor returned"
        assert bound, f"the command line returned {answered} instead of listening"
        yield bound[0]
    finally:
        if bound:
            bound[0].wake()
        thread.join(PATIENCE)
        assert not thread.is_alive(), "the serving thread did not stop"
    assert answered == [cli.OK]


def read_one(client: socket.socket) -> bytes:
    """One answer with its terminator, and not a byte of the next one.

    A byte at a time, because a socket cannot give back what was read past the
    terminator, and two answers arriving in one packet is exactly what happens
    when a test sends the queries that produce them together.
    """
    client.settimeout(PATIENCE)
    terminator = DEFAULT_TERMINATOR.encode("ascii")
    held = bytearray()
    while not held.endswith(terminator):
        byte = client.recv(1)
        if not byte:
            break
        held.extend(byte)
    return bytes(held)


def converse(server: Server, messages: Sequence[str] = CONVERSATION) -> bytes:
    """Everything one client receives across one full session, as it arrived."""
    where = server.bound
    assert where is not None
    client = socket.create_connection(where, timeout=PATIENCE)
    try:
        held = bytearray()
        for message in messages:
            client.sendall((message + DEFAULT_TERMINATOR).encode("ascii"))
            if "?" in message:
                held.extend(read_one(client))
        return bytes(held)
    finally:
        client.close()


def logged(log: Path) -> list[str]:
    """The startup lines the command wrote, in order."""
    return log.read_text(encoding="utf-8").splitlines()


def a_profile_directory(where: Path, name: str) -> Path:
    """A copy of the instrument fixture under a name, for the search path."""
    made = where / name
    made.mkdir(parents=True)
    shutil.copy(PROFILE / "profile.toml", made / "profile.toml")
    return made


def test_no_arguments_produce_an_error_naming_what_is_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`attrappe` alone says a command is missing and names the three there are."""
    assert cli.main([]) == cli.BAD_INVOCATION
    said = capsys.readouterr().err
    assert "no command" in said
    for command in ("run", "list", "validate"):
        assert command in said


def test_run_with_no_profile_anywhere_names_what_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing profile names the three places one may come from, not one."""
    monkeypatch.chdir(tmp_path)
    assert cli.main(["run"]) == cli.BAD_INVOCATION
    said = capsys.readouterr().err
    assert "needs a profile" in said
    assert "attrappe list" in said
    assert "configuration file" in said


def test_starting_with_a_profile_prints_the_five_startup_lines(tmp_path: Path) -> None:
    """Each of the five, asserted separately, and the sixth for the file that was not read.

    The port is the one the operating system gave back rather than the zero that
    was asked for, which is the whole reason the line reports what was bound.
    """
    log = tmp_path / "startup.log"
    argv = ["run", str(PROFILE), "--port", "0", "--seed", str(SEED), "--log", str(log)]
    with emulator(argv) as server:
        where = server.bound
        assert where is not None
        lines = logged(log)

    assert lines[0] == f"profile: {PROFILE.name} from {PROFILE}"
    assert lines[1] == f"identification: {IDENTIFICATION}"
    assert lines[2] == f"listening: {where[0]}:{where[1]}"
    assert lines[3] == f"seed: {SEED}"
    assert lines[4] == "fault schedule: none in force"
    assert lines[5] == "configuration: none read"
    assert len(lines) == 6
    assert where[1] != 0


def test_the_port_in_the_startup_line_is_the_one_a_client_connects_to(tmp_path: Path) -> None:
    """The line is read, dialled, and answered, which is what a bug report needs of it."""
    log = tmp_path / "startup.log"
    argv = ["run", str(PROFILE), "--port", "0", "--seed", str(SEED), "--log", str(log)]
    with emulator(argv) as server:
        announced = next(line for line in logged(log) if line.startswith("listening: "))
        host, port = announced.removeprefix("listening: ").rsplit(":", 1)
        client = socket.create_connection((host, int(port)), timeout=PATIENCE)
        try:
            client.sendall(f"*IDN?{DEFAULT_TERMINATOR}".encode("ascii"))
            answered = read_one(client)
        finally:
            client.close()
        assert server.bound == (host, int(port))
    assert answered.decode("ascii") == IDENTIFICATION + DEFAULT_TERMINATOR


@pytest.mark.parametrize("broken", BROKEN, ids=lambda entry: entry.name)
def test_validate_refuses_every_broken_fixture_profile(
    broken: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-zero on each one, with the code that means a refused profile."""
    assert cli.main(["validate", str(broken)]) == cli.BAD_PROFILE
    assert capsys.readouterr().err.strip()


def test_there_are_broken_fixtures_to_refuse() -> None:
    """The parametrisation above reads a directory, and an empty read passes vacuously."""
    assert len(BROKEN) >= 9


def test_validate_accepts_the_profile_the_loader_accepts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Zero on a good profile, and it says what it read rather than only passing."""
    assert cli.main(["validate", str(PROFILE)]) == cli.OK
    assert PROFILE.name in capsys.readouterr().out


def test_validate_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """The subcommand exists so a contributor can check their work without a port.

    A socket constructed at all fails this, which is stricter than the promise
    and is the safe direction.
    """

    def refuse(*arguments: object, **keywords: object) -> socket.socket:
        raise AssertionError("validate constructed a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    assert cli.main(["validate", str(PROFILE)]) == cli.OK


def test_list_names_every_profile_on_the_search_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every directory holding a declaration is named, and nothing else is."""
    a_profile_directory(tmp_path, "bench")
    a_profile_directory(tmp_path, "counter")
    (tmp_path / "not-a-profile").mkdir()

    assert cli.main(["--profile-path", str(tmp_path), "list"]) == cli.OK
    said = capsys.readouterr().out

    named = {line.split(":", 1)[0] for line in said.splitlines() if not line.startswith("searched")}
    assert named == {"bench", "counter"}


def test_list_names_every_shipped_profile(capsys: pytest.CaptureFixture[str]) -> None:
    """The shipped directory, whatever is in it, read off the disk rather than listed here.

    Nothing is shipped in this tree, so the set is empty and the subcommand says
    so. #28 lands the first profile, and this test names it that day without
    being edited.
    """
    shipped = {entry.name for entry in cli.profiles_in(cli.SHIPPED_PROFILES)}

    assert cli.main(["list"]) == cli.OK
    said = capsys.readouterr().out

    named = {line.split(":", 1)[0] for line in said.splitlines() if not line.startswith("searched")}
    assert named - {"no profile on the search path"} == shipped
    assert str(cli.SHIPPED_PROFILES) in said


def test_list_says_where_it_looked_when_it_found_nothing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A run that searched an empty directory does not read as one that searched a full one."""
    assert cli.main(["--profile-path", str(tmp_path), "list"]) == cli.OK
    said = capsys.readouterr().out
    assert f"searched: {tmp_path} (0 profile(s))" in said
    assert "no profile on the search path" in said


def test_list_says_which_name_an_earlier_directory_answers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two directories offering one name, and the one `run` would take is the one named."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    a_profile_directory(first, "bench")
    a_profile_directory(second, "bench")

    argv = ["--profile-path", str(first), "--profile-path", str(second), "list"]
    assert cli.main(argv) == cli.OK
    said = capsys.readouterr().out

    assert f"bench: {first / 'bench'}" in said
    assert f"bench: shadowed by an earlier directory, at {second / 'bench'}" in said


def test_a_name_resolves_against_the_search_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A bare name is looked up; the same name as a path is read where it was written."""
    a_profile_directory(tmp_path, "bench")
    assert cli.main(["--profile-path", str(tmp_path), "validate", "bench"]) == cli.OK
    assert "bench" in capsys.readouterr().out


def test_a_name_that_resolves_to_nothing_says_where_it_looked(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The message names the directories searched, so the next command is obvious."""
    assert cli.main(["--profile-path", str(tmp_path), "validate", "bench"]) == cli.BAD_INVOCATION
    said = capsys.readouterr().err
    assert str(tmp_path) in said
    assert "attrappe list" in said


def test_a_path_that_is_not_there_is_reported_as_a_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A mistyped path is corrected by looking at the disk, so the message names it.

    Not the search path, which is what a mistyped name gets, and the two
    messages are different because the next thing to do is different.
    """
    missing = tmp_path / "nowhere" / "bench"
    assert cli.main(["validate", str(missing)]) == cli.BAD_INVOCATION
    said = capsys.readouterr().err
    assert f"no profile directory at {missing}" in said


def test_the_configuration_file_supplies_what_no_flag_gave(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The file names the profile and the seed, and the startup output names the file."""
    monkeypatch.chdir(tmp_path)
    log = tmp_path / "startup.log"
    configuration = tmp_path / cli.CONFIGURATION_FILE
    configuration.write_text(
        f'profile = "{PROFILE.as_posix()}"\nseed = {SEED}\nport = 0\n',
        encoding="utf-8",
    )

    with emulator(["run", "--log", str(log)]):
        lines = logged(log)

    assert f"seed: {SEED}" in lines
    assert f"configuration: {cli.CONFIGURATION_FILE}" in lines
    # Written into the file with forward slashes, because TOML reads a backslash
    # as an escape. What comes back is the path spelled the way the host spells
    # one, which is what a reader of the startup line expects to see.
    assert f"profile: {PROFILE.name} from {Path(PROFILE.as_posix())}" in lines


def test_a_flag_wins_over_the_configuration_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One key set in both places, and the flag is the one that reaches the output."""
    monkeypatch.chdir(tmp_path)
    log = tmp_path / "startup.log"
    (tmp_path / cli.CONFIGURATION_FILE).write_text(
        f'profile = "{PROFILE.as_posix()}"\nseed = 11\nport = 0\n',
        encoding="utf-8",
    )

    with emulator(["run", "--seed", str(SEED), "--log", str(log)]):
        lines = logged(log)

    assert f"seed: {SEED}" in lines
    assert "seed: 11" not in lines


def test_a_configuration_file_that_was_asked_for_and_is_not_there_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Named and absent is a bad invocation; the default absent is the ordinary case."""
    missing = tmp_path / "nowhere.toml"
    assert cli.main(["--config", str(missing), "list"]) == cli.BAD_INVOCATION
    assert str(missing) in capsys.readouterr().err


def test_an_unknown_configuration_key_is_refused_with_the_key_named(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An ignored key is a typo that silently does nothing, so it is not ignored."""
    configuration = tmp_path / "attrappe.toml"
    configuration.write_text("prt = 5025\n", encoding="utf-8")
    assert cli.main(["--config", str(configuration), "list"]) == cli.BAD_INVOCATION
    said = capsys.readouterr().err
    assert "prt" in said
    assert "port" in said


def test_a_configured_port_of_the_wrong_type_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`true` is an int to isinstance and is not a port, which is the case this catches."""
    configuration = tmp_path / "attrappe.toml"
    configuration.write_text("port = true\n", encoding="utf-8")
    assert cli.main(["--config", str(configuration), "list"]) == cli.BAD_INVOCATION
    assert "port has to be int" in capsys.readouterr().err


def test_a_configured_profile_path_that_is_not_a_list_of_strings_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A list is the declared type and its members are paths, so a number in it is refused."""
    configuration = tmp_path / "attrappe.toml"
    configuration.write_text("profile_path = [1, 2]\n", encoding="utf-8")
    assert cli.main(["--config", str(configuration), "list"]) == cli.BAD_INVOCATION
    assert "list of strings" in capsys.readouterr().err


def test_a_configuration_file_that_is_not_toml_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A malformed file is a bad invocation rather than a traceback over the operator's terminal."""
    configuration = tmp_path / "attrappe.toml"
    configuration.write_text("port = = 1\n", encoding="utf-8")
    assert cli.main(["--config", str(configuration), "list"]) == cli.BAD_INVOCATION
    assert "not readable as TOML" in capsys.readouterr().err


def test_the_configured_search_path_is_read_and_the_flag_replaces_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The file's list is used when no flag gives one, and is replaced whole when one does."""
    configured = tmp_path / "configured"
    flagged = tmp_path / "flagged"
    a_profile_directory(configured, "from-the-file")
    a_profile_directory(flagged, "from-the-flag")
    configuration = tmp_path / "attrappe.toml"
    configuration.write_text(
        f'profile_path = ["{configured.as_posix()}"]\n',
        encoding="utf-8",
    )

    assert cli.main(["--config", str(configuration), "list"]) == cli.OK
    assert "from-the-file" in capsys.readouterr().out

    argv = ["--config", str(configuration), "--profile-path", str(flagged), "list"]
    assert cli.main(argv) == cli.OK
    said = capsys.readouterr().out
    assert "from-the-flag" in said
    assert "from-the-file" not in said


def test_a_bad_flag_a_bad_profile_and_a_runtime_failure_have_three_codes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The three conditions the issue asks to be distinguishable, in one place.

    1 is absent from the set on purpose: the interpreter exits 1 on an uncaught
    exception, and a crash reading as a refused profile is the confusion this
    numbering avoids.
    """
    assert cli.main(["--nonsense", "list"]) == cli.BAD_INVOCATION
    capsys.readouterr()

    assert cli.main(["validate", str(BROKEN[0])]) == cli.BAD_PROFILE
    capsys.readouterr()

    argv = ["run", str(PROFILE), "--host", UNBINDABLE, "--port", "0"]
    assert cli.main(argv) == cli.RUNTIME_FAILURE
    assert "cannot listen on" in capsys.readouterr().err

    assert cli.OK not in {cli.BAD_INVOCATION, cli.BAD_PROFILE, cli.RUNTIME_FAILURE}
    assert 1 not in {cli.OK, cli.BAD_INVOCATION, cli.BAD_PROFILE, cli.RUNTIME_FAILURE}


def test_a_log_destination_that_cannot_be_opened_is_a_runtime_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The log is opened before anything is bound, so this never leaves a port held."""
    unwritable = tmp_path / "nowhere" / "startup.log"
    argv = ["run", str(PROFILE), "--port", "0", "--log", str(unwritable)]
    assert cli.main(argv) == cli.RUNTIME_FAILURE
    assert str(unwritable.name) in capsys.readouterr().err


def test_running_a_profile_the_loader_refuses_never_binds(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The half of the loader issue that could not be proven there: a bad profile starts nothing.

    Every problem in the profile is reported, not the first, which is what the
    loader promises and what a contributor reads.
    """
    several = FIXTURES / "broken-several-problems"
    assert cli.main(["run", str(several), "--port", "0"]) == cli.BAD_PROFILE
    said = capsys.readouterr().err
    assert len(said.strip().splitlines()) > 1


def test_two_runs_on_one_seed_produce_one_session_byte_for_byte(tmp_path: Path) -> None:
    """The same seed, the same commands, and the same bytes back, compared as bytes.

    What this proves today is that the seed reaches the session and that the
    answers do not depend on anything outside the conversation. No response in
    this tree carries a random draw yet: noise is #30 and the stages that draw
    are milestone 4, so the impairment half of this property is asserted in
    `test_one_seed_gives_a_connection_one_named_stream` below, over the
    mechanism those stages will take their draws from.
    """
    transcripts: list[bytes] = []
    announcements: list[list[str]] = []
    for run in ("first", "second"):
        log = tmp_path / f"{run}.log"
        argv = ["run", str(PROFILE), "--port", "0", "--seed", str(SEED), "--log", str(log)]
        with emulator(argv) as server:
            transcripts.append(converse(server))
        announcements.append(logged(log))

    assert transcripts[0] == transcripts[1]
    assert transcripts[0]

    # Every startup line but the port, which is the one fact that is the
    # operating system's to choose and not the seed's to reproduce.
    said = [
        [line for line in lines if not line.startswith("listening: ")] for lines in announcements
    ]
    assert said[0] == said[1]


def test_two_runs_on_two_seeds_are_two_sessions(tmp_path: Path) -> None:
    """The comparison above is worth something only if a different seed is visible.

    It is visible in the startup line rather than in the answers, because
    nothing stochastic reaches a response in this tree yet. That is the whole of
    what changes with the seed today, and this test says so rather than
    asserting a difference that would not appear.
    """
    seen: list[str] = []
    for seed in (SEED, SEED + 1):
        log = tmp_path / f"{seed}.log"
        argv = ["run", str(PROFILE), "--port", "0", "--seed", str(seed), "--log", str(log)]
        with emulator(argv):
            pass
        seen.append(next(line for line in logged(log) if line.startswith("seed: ")))

    assert seen == [f"seed: {SEED}", f"seed: {SEED + 1}"]


def test_one_seed_gives_a_connection_one_named_stream(tmp_path: Path) -> None:
    """The reproducibility an impairment will rest on, over the mechanism it will use.

    A stage draws from a named stream, and the stream is derived from the
    session seed and the name. Two runs of the command line on one seed give the
    first connection the same stream, and a different seed gives it a different
    one. `docs/decisions/0004-randomness.md` is where that is required.
    """
    drawn: dict[int, float] = {}
    for seed in (SEED, SEED, SEED + 1):
        argv = [
            "run",
            str(PROFILE),
            "--port",
            "0",
            "--seed",
            str(seed),
            "--log",
            str(tmp_path / f"{seed}.log"),
        ]
        with emulator(argv) as server:
            where = server.bound
            assert where is not None
            client = socket.create_connection(where, timeout=PATIENCE)
            try:
                client.sendall(f"*IDN?{DEFAULT_TERMINATOR}".encode("ascii"))
                read_one(client)
                assert server.sessions
                value = server.sessions[0].stream("noise").random()
            finally:
                client.close()
        drawn.setdefault(seed, value)
        assert drawn[seed] == value

    assert drawn[SEED] != drawn[SEED + 1]


def test_an_interrupt_is_how_this_stops_and_it_leaves_no_port_held(tmp_path: Path) -> None:
    """Ctrl-C is the ordinary way out, so it exits zero and releases what it bound.

    The interrupt is raised from inside the run rather than sent as a signal,
    because a signal delivered to the process running the suite is a signal to
    the suite. Where it is raised is where the operator's would arrive: inside
    the serving call, after the startup lines are out.
    """
    bound: list[Server] = []

    def interrupt(server: Server) -> None:
        assert server.bound is not None
        bound.append(server)
        raise KeyboardInterrupt

    log = tmp_path / "startup.log"
    argv = ["run", str(PROFILE), "--port", "0", "--seed", str(SEED), "--log", str(log)]

    assert cli.main(argv, started=interrupt) == cli.OK
    assert len(logged(log)) == 6
    assert bound[0].bound is None
