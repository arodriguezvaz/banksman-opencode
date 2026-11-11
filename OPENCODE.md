# OpenCode integration

This fork adds first-class OpenCode sessions to banksman 0.2.0 and ships the small adapter that
OpenCode needs. Upstream banksman knows Claude Code and Codex sessions; OpenCode runs every
session under one `opencode serve` process, so the process tree alone cannot tell sessions apart.

## What the fork changes

- `identity.py`: `OPENCODE_SESSION_ID` is a session variable, and `OPENCODE=1` /
  `AI_AGENT=opencode` identify the agent when no `opencode` process is in the caller's tree
  (for example a Gradle daemon).
- `store.py`: when the caller has an OpenCode session, the session is the identity. The shared
  `opencode serve` PID no longer makes leases of other sessions the caller's.
- `guard.py`: the adb and Gradle guards compare the session before the process, and guard events
  carry the session.
- `console.py`: `status`/`held`/`log` show a short session id.

The changes are covered by `tests/test_opencode.py`. The full suite passes: 1706 passed,
17 skipped (with `umask 0022` and `LC_ALL=C`).

## Components

1. `bin/banksman`: runs this fork from the checkout, standard library only.
2. `opencode/adb-shim.py`: an `adb` wrapper for OpenCode shells. It reads `OPENCODE_SESSION_ID`
   from the real process environment, adopts the session's lease with `banksman held`, or asks
   for one with `banksman acquire --where kind=emulator --start`, then executes the banksman adb
   wrapper so the normal guard applies. Outside OpenCode it passes through unchanged.
3. `opencode/plugin/`: the OpenCode plugin. OpenCode's shell hook does not receive the session id,
   so the plugin uses `tool.execute.before`, which does, and rewrites Gradle device commands with
   `BANKSMAN_LEASE` and `ANDROID_SERIAL`. It also releases the session's lease on `session.idle`
   and `session.deleted` without stopping the AVD.

The adb shim and the plugin are independent: if the plugin is disabled or the service did not
reload it, adb still works through the shim. The plugin covers `./gradlew ...` device tasks.

## Install

```sh
# CLI
ln -sf /home/andres/src/banksman-opencode/bin/banksman ~/.local/bin/banksman
banksman version

# config: every AVD discovered, Studio-started AVDs may be granted, strict guard
chmod 600 ~/.config/banksman/config.toml
banksman admin discover --all --yes

# banksman's own adb wrapper (the guard); keep it outside PATH
mkdir -p ~/.local/share/banksman/bin
banksman admin adb-shim > ~/.local/share/banksman/bin/adb
chmod 755 ~/.local/share/banksman/bin/adb

# the OpenCode-aware adb shim, first on PATH
cp /home/andres/src/banksman-opencode/opencode/adb-shim.py ~/.local/bin/adb
chmod 755 ~/.local/bin/adb

# Gradle guard
banksman admin gradle-guard > ~/.gradle/init.d/banksman-gradle-guard.gradle
mkdir -p ~/.gradle/banksman
banksman admin gradle-guard --part > ~/.gradle/banksman/gradle-guard.gradle
```

Enable the plugin in `~/.config/opencode/opencode.jsonc`:

```jsonc
{
  "plugins": ["/home/andres/.config/opencode/plugins/banksman-opencode"]
}
```

Copy `opencode/plugin/` to that directory, or symlink it. After changing plugin code, restart the
OpenCode service once: `opencode service restart`.

## Recommended config

See `opencode/config.example.toml`. The important parts:

```toml
[holder]
agents = ["opencode", "claude", "codex"]

[kinds.emulator]
preset = "android-emulator"
preselect = ["*"]
unmanaged = "grant"
start_args = ["-no-window", "-no-audio", "-no-boot-anim", "-gpu", "swiftshader_indirect"]

[guard]
strict = true
```

`preselect = ["*"]` plus `discover --all --yes` allows every AVD present at discovery time.
A new AVD needs another `banksman admin discover --all --yes` (or a timer).

## Behaviour

- One AVD belongs to one session at a time.
- `adb shell`, `adb install`, Gradle `install*`/`uninstall*`/`connected*` acquire the lease
  automatically.
- `adb devices` and other host commands pass without a lease.
- A second session waits in `acquire --wait` and then gets a clear refusal. It never shares the
  AVD.
- `release` leaves the AVD running; `release --end` stops it.
- `banksman status` shows `opencode · ses_… · worktree · purpose`.

## Known limits

- The guard is a guardrail, not a sandbox. Android Studio's own adb, an absolute-path adb, and a
  tool that talks to the adb server directly bypass it. Use separate AVDs if a person and an
  agent must work at the same time, or use a port-level broker such as AdbHarbor.
- OpenCode's plugin loader may cache a failed load until the service restarts. The adb shim does
  not depend on the plugin.
- `-read-only` multi-instance AVDs do not get a unique serial; use separate AVDs.
- New AVDs are not allowed until `banksman admin discover` runs again.
- The guard fails open when banksman cannot decide. The fork is based on banksman 0.2.0 (beta).
- `banksman admin` must stay unavailable to agents; deny it in OpenCode permissions.

## Upstream

`origin` is this fork; `upstream` is `https://github.com/Twinsen81/banksman.git`. The OpenCode
identity change is small enough to propose upstream. Keep the fork pinned to 0.2.0 until then.
