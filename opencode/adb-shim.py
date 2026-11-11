#!/usr/bin/env python3
"""OpenCode-aware adb shim.

It gives the calling OpenCode session a banksman lease before a device command, then runs the
banksman adb wrapper so that the guard checks the usual rules. A shell outside OpenCode is passed
through unchanged.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

BANKSMAN = "/home/andres/.local/bin/banksman"
WRAPPER = "/home/andres/.local/share/banksman/bin/adb"
HOST_COMMANDS = {
    "devices",
    "version",
    "help",
    "--help",
    "start-server",
    "wait-for-device",
    "get-state",
}
FORBIDDEN = (("emu", "kill"), ("kill-server",))


def subcommand(arguments: list[str]) -> str:
    i = 0
    while i < len(arguments):
        word = arguments[i]
        if word in ("-s", "-t", "-P", "-H", "-L"):
            i += 2
            continue
        if word.startswith("-"):
            i += 1
            continue
        return word
    return ""


def fail(message: str, status: int = 75) -> None:
    print(f"banksman-opencode: {message}", file=sys.stderr)
    raise SystemExit(status)


def run(command: list[str], env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def main() -> None:
    arguments = sys.argv[1:]
    session = os.environ.get("OPENCODE_SESSION_ID")
    if not session:
        # The user's own terminal, Android Studio, or an older tool: keep the normal path.
        os.execv(WRAPPER, [WRAPPER, *arguments])

    command = subcommand(arguments)
    if command in HOST_COMMANDS:
        os.execv(WRAPPER, [WRAPPER, *arguments])
    if any(all(part in arguments for part in forbidden) for forbidden in FORBIDDEN):
        fail("no está permitido apagar el emulador ni el servidor adb desde un agente; usa banksman status", 1)
    if os.environ.get("BANKSMAN_LEASE"):
        # The OpenCode plugin already acquired the lease and put its token in the command.
        os.execv(WRAPPER, [WRAPPER, *arguments])

    env = {
        **os.environ,
        "OPENCODE": "1",
        "AI_AGENT": "opencode",
        "OPENCODE_SESSION_ID": session,
    }

    lease = None
    try:
        found = run([BANKSMAN, "held", "--json"], env, 15)
    except (OSError, subprocess.TimeoutExpired):
        found = None
    if found is not None and found.returncode == 0:
        try:
            leases = json.loads(found.stdout).get("leases") or []
            if leases:
                lease = leases[0]
        except (ValueError, AttributeError):
            lease = None

    if lease is None:
        try:
            acquired = run(
                [
                    BANKSMAN,
                    "acquire",
                    "--where", "kind=emulator",
                    "--start",
                    "--for", f"opencode:{session}",
                    "--expect", "30m",
                    "--wait", "25s",
                    "--json",
                ],
                env,
                240,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            fail(f"no pude pedir el emulador: {error}")
        if acquired.returncode != 0:
            message = (acquired.stderr or acquired.stdout or "no pude adquirir el emulador").strip()
            fail(message)
        try:
            lease = json.loads(acquired.stdout)["parts"][0]
        except (ValueError, KeyError, IndexError, TypeError):
            fail("banksman devolvió una respuesta que no entiendo")

    env["BANKSMAN_LEASE"] = str(lease["lease_id"])
    serial = lease.get("serial")
    if serial:
        env["ANDROID_SERIAL"] = str(serial)
    os.execve(WRAPPER, [WRAPPER, *arguments], env)


if __name__ == "__main__":
    main()
