# Troubleshooting

Start with `banksman admin doctor` and `banksman status`. The doctor compares every saved file
with what this banksman writes and names the command that fixes it; `status` says who holds each
resource and when it can be free.

## "refused: emulator-5554 is held by another holder"

Another OpenCode session holds the AVD. This is the guard working.

- `banksman status` shows the holder, the session and the time left.
- `banksman held` shows the leases of the current session and the refused calls of its process.
- Wait for the other session, ask for another AVD, or (as the operator) `banksman release --lease
  <id>`.
- Do not run `adb emu kill` or `adb kill-server`: both are blocked, and they break the other
  session.

## `adb devices` says "no device here is yours"

The command ran without a lease. `adb devices` is a host command: it lists devices but grants
nothing. Use a device command (`adb shell`, `adb install`) or acquire one explicitly:

```sh
banksman acquire --where kind=emulator --start
```

## The doctor warns `adb-path`

The first `adb` on the `PATH` is not the OpenCode shim, or the shim is not first.

- The shim is `~/.local/bin/adb`; the wrapper that it runs is
  `~/.local/share/banksman/bin/adb`.
- Put `~/.local/bin` before the SDK's `platform-tools` in `~/.profile` or `~/.bashrc`, then open
  a new shell.
- `banksman admin install-opencode --yes` restores both files.

## Gradle says "the device tasks of this build are not checked"

- `~/.gradle/init.d/banksman-gradle-guard.gradle` or `~/.gradle/banksman/gradle-guard.gradle` is
  missing or belongs to another version: run `banksman admin install-opencode --yes`.
- Gradle older than 7.4 does not apply the guard. `./gradlew --version` shows the version.
- The guard fails open when banksman cannot start: run `banksman admin doctor` in the same shell
  that runs the build.

## The plugin does not load

- `banksman admin doctor` reports `opencode-plugin` when the saved copy differs from this version,
  and `opencode-config` when the configuration cannot be read.
- The plugin is discovered from `~/.config/opencode/plugins/banksman-opencode`; the entry in
  `opencode.jsonc` only pins it explicitly.
- Restart the service once after changing plugin files: `opencode service restart`. Configuration
  changes alone reload without a restart.
- The adb shim does not depend on the plugin: `adb` keeps working when the plugin fails to load.
  Gradle then needs `banksman run --where kind=emulator -- ./gradlew ...`.

## A lease seems stuck

A lease ends on `session.idle` / `session.deleted` (the plugin releases it), after the idle
timeout (20 minutes without a banksman or adb call), at the hard cap (3 hours), or when its owner
process is gone for the grace period (5 minutes). The AVD stays running after a release.

- `banksman status` shows the deadline of each lease.
- `banksman release --lease <id>` releases one as the operator; `--all` releases every lease of
  the caller.
- The optional reap job (`banksman admin reap-agent`) is what applies the timeouts while no
  banksman command runs. Without it, the next `banksman` command does the same work.

## A new AVD is not offered

Discovery is a human gate. After creating an AVD in Android Studio:

```sh
banksman admin discover --all --yes
```

## The emulator does not start

- `banksman status` and `banksman admin doctor` first.
- The output of the emulator is in `~/.local/state/banksman/emulator/<AVD>.log`.
- `--sdk` and `--avd-home` tell the installer where they are; `banksman admin doctor` checks the
  SDK and the emulator program.

## A person and an agent use the same emulator

The guard cannot stop Android Studio's own adb. Use a separate AVD for the person, or wait until
`banksman status` shows the AVD free. See [limits.md](limits.md).

## Where the records are

- `~/.local/state/banksman/log.jsonl`: append-only history of leases and guard decisions.
- `~/.local/state/banksman/emulator/`: the emulator log and the record of managed emulators.
- `~/.local/state/banksman/trace.jsonl`: opt-in, with full command lines; off by default.
- `/tmp/banksman-<uid>/`: the leases, one JSON file per resource.
