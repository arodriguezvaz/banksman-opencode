# Architecture

`banksman-opencode` is a small OpenCode-specific layer over banksman. The engine is banksman:
leases, the wait loop, the reaper, the adb guard, the Gradle guard, AVD discovery and the
configuration/inventory. This repository adds the session identity and the two adapters that make
the engine transparent to OpenCode.

## Components

| Component | Where | Role |
|---|---|---|
| banksman fork | `src/banksman` | The engine, plus OpenCode session identity |
| `banksman` launcher | `bin/banksman` | Runs the fork from the checkout, standard library only |
| adb shim | `opencode/adb-shim.py` | Reads the OpenCode session, adopts/acquires a lease, then runs banksman's adb wrapper |
| banksman adb wrapper | generated: `~/.local/share/banksman/bin/adb` | The guard: permits or refuses an adb call |
| OpenCode plugin | `opencode/plugin/` | Rewrites Gradle device commands with the lease/serial and releases on idle |
| Gradle guard | `~/.gradle/init.d` + `~/.gradle/banksman` | Checks install/uninstall/connected tasks against leases |
| config/inventory | `~/.config/banksman/` | Which AVDs agents may use, timeouts, strict mode |

## Request flow

### adb

```text
OpenCode session A
  │  OPENCODE_SESSION_ID=ses_a
  ▼
adb shim
  ├─ banksman held --json          (adopt a lease already held by ses_a)
  └─ banksman acquire --where kind=emulator --start --json   (otherwise)
  ▼
BANKSMAN_LEASE=... ANDROID_SERIAL=emulator-5554
  ▼
banksman adb wrapper / guard
  ├─ lease is ses_a's → adb runs
  └─ lease is ses_b's → refused with the holder's name
  ▼
emulator-5554
```

Read-only host commands (`adb devices`, `adb version`, `adb start-server`, …) pass through
without a lease. Destructive commands (`adb emu kill`, `adb kill-server`) are blocked by the shim
and by OpenCode permissions.

### Gradle

```text
OpenCode session A
  │  tool.execute.before (sessionID is available here)
  ▼
plugin
  ├─ banksman acquire --where kind=emulator --start --json
  └─ export BANKSMAN_LEASE=... ANDROID_SERIAL=...
  ▼
./gradlew installDebug / connectedDebugAndroidTest
  ▼
banksman Gradle guard
  ├─ checks the task graph and the devices of the build
  └─ refuses another holder's AVD before compiling
```

OpenCode's shell hook does not receive the session id; its tool hook does. That is why the
plugin uses `tool.execute.before`, not `shell.create.before`.

## Lease lifecycle

1. A session asks for a device. The shim or plugin calls `banksman acquire --where kind=emulator`.
2. Banksman chooses a free allowed AVD, starts it if needed, waits for boot and records the
   serial. The lease is held by the session; the owner process is only a liveness hint.
3. The guard permits calls while the lease is held and refuses calls on another session's AVD.
4. On `session.idle` or `session.deleted`, the plugin releases the lease. The AVD stays running;
   the next session gets it without a cold boot.
5. If the holder crashes or the plugin is disabled, the lease expires after the idle timeout
   (20 minutes by default) or the hard cap.

## Why the fork

Upstream banksman identifies a holder by the nearest agent process and, optionally, an
agent-specific session variable. OpenCode runs all sessions under one `opencode serve` process,
so the process tree says "one holder". The fork adds:

- `OPENCODE_SESSION_ID` as a session variable;
- `OPENCODE=1` / `AI_AGENT=opencode` detection when the caller is outside the agent tree (for
  example a Gradle daemon that inherits the client environment);
- session-first ownership in `store._mine`, so the shared PID cannot expose another session's
  leases;
- session-aware guard decisions and labels.

It is a small, upstreamable change; the adapter (shim, plugin, docs) is intentionally separate.

## Automatic vs manual

Banksman's own contract is "run the command under a lease":

```sh
banksman run --where kind=emulator -- ./gradlew connectedDebugAndroidTest
```

The adapters make that implicit:

- the shim does it for `adb`;
- the plugin does it for Gradle device tasks and releases on idle.

Without the plugin, use `banksman run` for Gradle. Without the shim, use `banksman run` for adb.
The guard remains the same.

## State

- `~/.config/banksman/config.toml`: configuration, mode 0600.
- `~/.config/banksman/inventory.toml`: allowed AVDs/devices, mode 0600.
- `/tmp/banksman-<uid>`: lease store, private to the user.
- `~/.local/state/banksman/`: log, lease-end record and quarantines.
- `~/.local/share/banksman/bin/adb`: generated guard wrapper.
- `~/.local/bin/adb`: the OpenCode shim; it delegates to the wrapper.

## Security model

The guard is a coordination guardrail, not a sandbox. It protects honest agents and scripts that
go through the configured paths; it cannot stop absolute-path adb, Android Studio's own deploy,
a tool that talks to the adb server directly, or a user who stops the emulator. See
[limits.md](limits.md).
