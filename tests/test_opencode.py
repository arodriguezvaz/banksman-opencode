"""OpenCode sessions: one server process, many sessions, and one lease per session."""

import os

import pytest
from helpers import FakeSystem

from banksman.config import HolderRules, load_config
from banksman.console import holder_label
from banksman.guard import check, check_gradle, events
from banksman.history import REFUSED
from banksman.identity import find_holder
from banksman.lease import Holder, SerialSeen, Session
from banksman.store import Store

OWNER_A = "/work/tree-a"
OWNER_B = "/work/tree-b"
SERVER = 700
SHELL = 701
SESSION_A = Session("opencode", "ses_a")
SESSION_B = Session("opencode", "ses_b")
ENV_A = {"OPENCODE": "1", "OPENCODE_SESSION_ID": "ses_a"}
ENV_B = {"OPENCODE": "1", "OPENCODE_SESSION_ID": "ses_b"}


@pytest.fixture
def system():
    """The OpenCode server, a shell of one session, and the test process under it."""
    machine = FakeSystem()
    machine.spawn(SERVER, program="/usr/local/bin/opencode")
    machine.spawn(SHELL, parent=SERVER)
    machine.parents[os.getpid()] = SHELL
    return machine


def holder(session, owner=OWNER_A):
    return Holder(owner, owner_pid=SERVER, agent=session.agent, session=session.session_id)


def lease(store, system, resource, serial, session, owner=OWNER_A):
    granted = store.acquire(resource, "emulator", holder(session, owner))
    store.observe([SerialSeen(resource, "emulator", serial, system.now)])
    return granted


def test_find_holder_reads_the_opencode_session_without_a_known_process(tmp_path):
    # The default agents are claude and codex. OpenCode's environment is enough: no process
    # named opencode is in the tree of the Gradle daemon.
    (tmp_path / ".git").mkdir()
    machine = FakeSystem()
    machine.spawn(SERVER, program="/usr/local/bin/opencode")
    machine.spawn(SHELL, parent=SERVER)
    found = find_holder(
        machine.process_table(),
        HolderRules(),
        cwd=str(tmp_path),
        env=ENV_A,
        pid=SHELL,
    )
    assert (found.agent, found.session) == ("opencode", "ses_a")


def test_find_holder_reads_the_opencode_session_of_a_gradle_daemon(tmp_path):
    # A Gradle daemon is not below the OpenCode process tree. The init script gives it the
    # environment of the client, and from_env reads the session from there.
    (tmp_path / ".git").mkdir()
    machine = FakeSystem()
    machine.spawn(800, program="/usr/lib/jvm/bin/java")
    found = find_holder(
        machine.process_table(),
        HolderRules(),
        cwd=str(tmp_path),
        env=ENV_A,
        pid=800,
        from_env=True,
    )
    assert (found.agent, found.session, found.owner_pid) == ("opencode", "ses_a", None)


def test_two_opencode_sessions_of_one_server_keep_separate_leases(state_dir, system):
    store = Store(state_dir, system)
    first = lease(store, system, "emu-1", "emulator-5554", SESSION_A)
    second = lease(store, system, "emu-2", "emulator-5556", SESSION_B)

    assert [each.resource for each in store.held_by(SERVER, SESSION_A)] == ["emu-1"]
    assert [each.resource for each in store.held_by(SERVER, SESSION_B)] == ["emu-2"]
    assert store.labelled(SERVER, "tests", SESSION_A) == {}

    released = store.release_all(SERVER, session=SESSION_B)
    assert [each.resource for each, _ in released] == ["emu-2"]
    assert [each.resource for each in store.held_by(SERVER, SESSION_A)] == ["emu-1"]
    assert store.held_by(SERVER, SESSION_B) == []
    assert first.lease_id != second.lease_id


def test_a_command_of_another_session_is_refused(state_dir, system):
    store = Store(state_dir, system)
    lease(store, system, "emu-1", "emulator-5554", SESSION_B, OWNER_B)

    decision = check(
        ["-s", "emulator-5554", "shell", "true"],
        load_config(),
        ENV_A,
        system,
        lambda: [],
    )
    assert decision.verdict is not None
    assert decision.verdict.action == REFUSED
    assert "emulator-5554" in decision.verdict.text

    own = check(
        ["-s", "emulator-5554", "shell", "true"],
        load_config(),
        ENV_B,
        system,
        lambda: [],
    )
    assert own.verdict is None


def test_the_guard_event_carries_the_opencode_session(state_dir, system):
    store = Store(state_dir, system)
    lease(store, system, "emu-1", "emulator-5554", SESSION_B, OWNER_B)
    decision = check(
        ["-s", "emulator-5554", "shell", "true"],
        load_config(),
        ENV_A,
        system,
        lambda: [],
    )
    assert decision.verdict is not None
    found = events(
        decision.verdict,
        decision.verdict.caller.holder(),
        system.wall_clock(),
    )
    assert [event.session for event in found] == ["ses_a"]


def test_the_gradle_guard_uses_the_opencode_session(state_dir, system):
    store = Store(state_dir, system)
    lease(store, system, "emu-1", "emulator-5554", SESSION_B, OWNER_B)
    gradle_env_a = {**ENV_A, "ANDROID_SERIAL": "emulator-5554"}

    decision = check_gradle(
        [":app:installDebug"],
        load_config(),
        gradle_env_a,
        system,
        listing=lambda: [],
        serials=("emulator-5554",),
    )
    assert decision.verdict is not None
    assert decision.verdict.action == REFUSED

    own = check_gradle(
        [":app:installDebug"],
        load_config(),
        {**ENV_B, "ANDROID_SERIAL": "emulator-5554"},
        system,
        listing=lambda: [],
        serials=("emulator-5554",),
    )
    assert own.verdict is None


def test_status_shows_the_opencode_session(state_dir, system):
    store = Store(state_dir, system)
    lease(store, system, "emu-1", "emulator-5554", SESSION_A)
    shown = holder_label(store.held_by(SERVER, SESSION_A)[0])
    assert "opencode" in shown
    assert "ses_a" in shown
