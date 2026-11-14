# OpenCode integration

This fork adds first-class OpenCode sessions to banksman 0.2.0 and ships the small adapter that
OpenCode needs. Installation is in [install.md](install.md); this page explains what the adapter
does.

## What the fork changes

Upstream banksman knows Claude Code and Codex sessions; OpenCode runs every session under one
`opencode serve` process, so the process tree alone cannot tell sessions apart.

- `identity.py`: `OPENCODE_SESSION_ID` is a session variable, and `OPENCODE=1` /
  `AI_AGENT=opencode` identify the agent when no `opencode` process is in the caller's tree (for
  example a Gradle daemon).
- `store.py`: when the caller has an OpenCode session, the session is the identity. The shared
  `opencode serve` PID no longer makes leases of other sessions the caller's.
- `guard.py`: the adb and Gradle guards compare the session before the process, and guard events
  carry the session.
- `console.py`: `status`, `held` and `log` show a short session id.

The changes are covered by `tests/test_opencode.py` and the rest of the suite.

## Components

1. **Installer** (`banksman admin install-opencode`): writes the adb wrapper, the shim, the
   Gradle guard, the example configuration and the plugin from the copies in the package, so
   `banksman admin doctor` can check them.
2. **adb shim** (`src/banksman/opencode-adb-shim.py`): an `adb` wrapper for OpenCode shells. It
   reads `OPENCODE_SESSION_ID`, adopts the session's lease with `banksman held`, or asks for one
   with `banksman acquire --where kind=emulator --start`, and then runs the banksman adb wrapper
   so the normal guard applies. Outside OpenCode it passes through unchanged.
3. **Plugin** (`src/banksman/opencode-plugin.ts`): OpenCode's shell hook does not receive the
   session id, so the plugin uses `tool.execute.before`, which does, and rewrites Gradle device
   commands with `BANKSMAN_LEASE` and `ANDROID_SERIAL`. It releases the session's lease on
   `session.idle` and `session.deleted` without stopping the AVD.

The shim and the plugin are independent: if the plugin is disabled or failed to load, adb still
works through the shim; the plugin covers `./gradlew ...` device tasks.

## Behaviour

- One AVD belongs to one session at a time.
- `adb shell`, `adb install`, Gradle `install*` / `uninstall*` / `connected*` acquire the lease
  automatically.
- `adb devices` and other host commands pass without a lease; `adb devices` also says on standard
  error which devices the session holds.
- A second session waits in `acquire --wait` and then gets a clear refusal. It never shares the
  AVD.
- `release` leaves the AVD running; `release --end` stops it.
- `banksman status` shows `opencode · ses_… · worktree · purpose`.

## Known limits

The guard is a guardrail, not a sandbox. Android Studio's own adb, an absolute-path adb, and a
tool that talks to the adb server directly bypass it. `-read-only` multi-instance AVDs have no
single serial; a new AVD needs another `banksman admin discover`. The full list is in
[limits.md](limits.md).

## Upstream

`origin` is this fork; `upstream` is `https://github.com/Twinsen81/banksman.git`. The OpenCode
identity change is small enough to propose upstream. Keep the fork pinned to 0.2.0 until then.
