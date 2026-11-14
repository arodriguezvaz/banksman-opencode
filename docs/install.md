# Install

## Requirements

- Linux or macOS.
- Python 3.11 or newer. No `pip`, `venv`, `uv` or npm is needed: the package uses only the
  standard library.
- The Android SDK with `platform-tools` and `emulator`, and at least one AVD.
- OpenCode 2.2 or newer for the plugin.

## Quick start

From a checkout:

```sh
./install.sh --dry-run     # show every file it would write, and write nothing
./install.sh               # print the plan, ask once, apply
./install.sh --yes         # apply without questions
```

Without a checkout:

```sh
curl -fsSL https://raw.githubusercontent.com/arodriguezvaz/banksman-opencode/main/install.sh | sh
```

`install.sh` downloads the source to `~/.local/share/banksman-opencode` when it does not run from
a checkout, links `~/.local/bin/banksman`, and runs `banksman admin install-opencode`. Pin a
release with `BANKSMAN_REF=v0.2.0`; change the install directory with `BANKSMAN_HOME`.

The command writes:

| File | Content |
|---|---|
| `~/.local/share/banksman/bin/adb` | banksman's adb wrapper: the guard |
| `~/.local/bin/adb` | the OpenCode shim, which acquires the session's lease first |
| `~/.gradle/init.d/banksman-gradle-guard.gradle` | Gradle init script |
| `~/.gradle/banksman/gradle-guard.gradle` | the part that checks the device tasks |
| `~/.config/banksman/config.toml` | the example configuration, only when it does not exist |
| `~/.config/opencode/plugins/banksman-opencode/` | the plugin (`index.ts`, `package.json`) |

Every file is compared first: an identical file is left alone, a different file is replaced with a
backup beside it (`*.bak-YYYYmmdd-HHMMSS`), and the configuration is never replaced unless you
pass `--overwrite-config`.

### Options

| Option | Effect |
|---|---|
| `--dry-run` | show the plan and write nothing |
| `--yes` | apply without asking; required when stdin is not a terminal |
| `--sdk PATH` | the Android SDK, when it is not `~/Android/Sdk` |
| `--avd-home PATH` | the AVD directory, when it is not `~/.android/avd` |
| `--adb PATH` | the adb that the wrapper runs, when it is not the adb of the SDK |
| `--no-adb` | skip the two adb files |
| `--no-gradle` | skip the Gradle guard |
| `--no-plugin` | skip the plugin |
| `--no-config` | skip the example configuration |
| `--overwrite-config` | replace an existing configuration with the example, after a backup |
| `--write-config` | add the plugin to the `plugins` array of `opencode.jsonc`, after a backup |
| `--discover` | allow every discovered instance and account (`admin discover --all --yes`) |
| `--uninstall` | remove the files that the installer writes; keep config, inventory and leases |

The installer finishes with `banksman admin doctor`, so its output already says what is missing.

## OpenCode configuration

OpenCode discovers the plugin directory `~/.config/opencode/plugins/banksman-opencode` on its own.
Adding it to `opencode.jsonc` is optional; it pins the plugin explicitly. The installer prints the
line. With `--write-config` it inserts it into the first existing `~/.config/opencode/opencode.jsonc`
or `opencode.json`, keeps a backup, and leaves the file untouched when it cannot do so safely.

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "plugins": ["/home/you/.config/opencode/plugins/banksman-opencode"],
}
```

Use an absolute path. OpenCode reloads configuration without a restart; if the plugin does not
appear, restart the service once with `opencode service restart`.

## Permissions for agents

Keep operator commands and raw adb paths away from agents. Add rules like these to the global
`~/.config/opencode/opencode.jsonc`:

```jsonc
{
  "permissions": [
    { "action": "shell", "resource": "*Sdk/emulator/emulator*", "effect": "deny" },
    { "action": "shell", "resource": "*emulator -avd*", "effect": "deny" },
    { "action": "shell", "resource": "*Sdk/platform-tools/adb*", "effect": "deny" },
    { "action": "shell", "resource": "/usr/bin/adb*", "effect": "deny" },
    { "action": "shell", "resource": "*adb*emu kill*", "effect": "deny" },
    { "action": "shell", "resource": "*adb kill-server*", "effect": "deny" },
    { "action": "shell", "resource": "*banksman admin*", "effect": "deny" },
    { "action": "shell", "resource": "*banksman release --all*", "effect": "deny" },
    { "action": "shell", "resource": "*banksman release --force*", "effect": "deny" }
  ],
}
```

`banksman admin` is operator-only: run it from a normal terminal, not from an agent session.

## Discover and verify

```sh
banksman admin discover --all --yes    # or: ./install.sh --yes --discover
banksman admin doctor
banksman status
```

`admin discover` writes the allowlist of AVDs to `~/.config/banksman/inventory.toml`. It is a human
gate, not a cache: a new AVD is not offered until discovery runs again.

The example configuration allows every AVD present at discovery time, grants AVDs that Android
Studio started, and enables the strict guard:

```toml
[holder]
agents = ["opencode", "claude", "codex"]

[kinds.emulator]
preset = "android-emulator"
preselect = ["*"]
unmanaged = "grant"
boot_timeout = "4m"
start_args = ["-no-window", "-no-audio", "-no-boot-anim", "-gpu", "swiftshader_indirect"]

[guard]
strict = true
```

## Upgrade

```sh
git pull                # or re-run install.sh, which refreshes the copy
./install.sh --yes
banksman admin doctor
```

The installer replaces the files that this banksman writes and keeps a backup of each one that
changed. The doctor names every saved copy that belongs to another version.

## Uninstall

```sh
banksman admin install-opencode --uninstall
```

This removes the adb shim, the wrapper, the Gradle guard and the plugin. It keeps the
configuration, the inventory and the leases; release the leases first with `banksman release
--all`, and remove `~/.config/banksman` by hand when it is no longer needed. Remove the plugin
entry from `opencode.jsonc`, and delete the `~/.local/bin/banksman` symlink if you installed it
with `install.sh`.

## Manual path

Every piece has a command of its own, which the installer uses:

```sh
banksman admin adb-shim        # print the guard wrapper
banksman admin gradle-guard    # print the Gradle init script
banksman admin gradle-guard --part
banksman admin doctor          # check what is saved
```

The OpenCode shim and the plugin are files of the package (`src/banksman/opencode-adb-shim.py`,
`src/banksman/opencode-plugin.ts`, `src/banksman/opencode-plugin.json`), so the installer is the
supported way to save a copy that `doctor` can check.
