# Install

## Requirements

- Python 3.11 or newer, with `venv`/`pip` or [`uv`](https://docs.astral.sh/uv/).
- Linux or macOS.
- Android SDK with `platform-tools` and `emulator`, and at least one AVD.
- OpenCode 2.2 or newer for the plugin.

No runtime Python dependencies are needed beyond the standard library.

## 1. Get the CLI on PATH

From a checkout of this repository:

```sh
git clone https://github.com/arodriguezvaz/banksman-opencode.git
cd banksman-opencode
mkdir -p "$HOME/.local/bin"
ln -sf "$PWD/bin/banksman" "$HOME/.local/bin/banksman"
banksman version
```

`bin/banksman` runs the source tree directly. If you prefer an isolated environment:

```sh
uv tool install --from "$PWD" banksman   # or: python3 -m venv .venv && . .venv/bin/activate && pip install -e .
```

## 2. Configuration

```sh
mkdir -p "$HOME/.config/banksman"
cp opencode/config.example.toml "$HOME/.config/banksman/config.toml"
chmod 600 "$HOME/.config/banksman/config.toml"
```

The example allows every AVD present at discovery time, grants AVDs that Android Studio started,
and enables the strict guard. Review it before use:

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

`banksman admin discover --all --yes` writes the actual allowlist to
`~/.config/banksman/inventory.toml`. A new AVD is not offered until discovery runs again.

## 3. The adb guard and the OpenCode shim

Banksman's generated wrapper is the guard. Keep it outside PATH:

```sh
mkdir -p "$HOME/.local/share/banksman/bin"
banksman admin adb-shim > "$HOME/.local/share/banksman/bin/adb"
chmod 755 "$HOME/.local/share/banksman/bin/adb"
```

The OpenCode-aware shim goes first on PATH:

```sh
cp opencode/adb-shim.py "$HOME/.local/bin/adb"
chmod 755 "$HOME/.local/bin/adb"
```

Outside OpenCode (a normal terminal, Android Studio, an older tool), the shim passes through to
the generated wrapper. Inside OpenCode it reads `OPENCODE_SESSION_ID`, adopts the session's lease
or acquires one, then delegates to the wrapper.

> **Warning:** this shadows the system `adb` for your shell and for OpenCode. That is intentional;
> it is how the guard sees the call. Android Studio uses its own absolute adb and is unaffected.

## 4. Gradle guard

```sh
mkdir -p "$HOME/.gradle/init.d" "$HOME/.gradle/banksman"
banksman admin gradle-guard > "$HOME/.gradle/init.d/banksman-gradle-guard.gradle"
banksman admin gradle-guard --part > "$HOME/.gradle/banksman/gradle-guard.gradle"
```

The init script fails open if banksman is missing or cannot start; `banksman admin doctor`
checks both files.

## 5. OpenCode plugin

Copy or symlink `opencode/plugin/` to
`$HOME/.config/opencode/plugins/banksman-opencode/` and add it to `opencode.jsonc`:

```jsonc
{
  "plugins": ["/home/you/.config/opencode/plugins/banksman-opencode"]
}
```

Use an absolute path. After changing plugin code, restart the service once:

```sh
opencode service restart
```

The plugin uses `tool.execute.before`, because that hook receives the OpenCode `sessionID`; the
shell hook does not. It injects `BANKSMAN_LEASE` and `ANDROID_SERIAL` into Gradle device commands
and releases the lease on `session.idle` / `session.deleted`.

## 6. Permissions and agent rules

Keep operator commands out of the agents. Add rules like these to `opencode.jsonc`:

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
  ]
}
```

Add a short `AGENTS.md` section:

```markdown
## Android emulators are shared

- One AVD belongs to one OpenCode session at a time.
- The banksman-opencode shim/plugin acquire the lease automatically.
- Do not run `emulator` or `adb emu kill`; `banksman admin` is operator-only.
- If a command is refused because another holder leases the device, wait or ask for another AVD.
- For long work, use `banksman run --where kind=emulator -- <command>`.
- `banksman status` shows the holder; `banksman held` shows your leases.
```

## 7. Discover and verify

```sh
banksman admin discover --all --yes
banksman admin doctor
banksman status
```

`banksman admin doctor` may warn `adb-path` because `~/.local/bin/adb` is the OpenCode shim, not
the generated wrapper. The shim delegates to the wrapper, and the `adb-wrapper` check verifies it;
the warning is expected.

## 8. New AVDs

The inventory is policy, not a cache. After creating an AVD in Android Studio:

```sh
banksman admin discover --all --yes
```

Run operator commands from a normal terminal, not from an OpenCode shell (the permissions above
deny `banksman admin` there).

## Uninstall

Remove `~/.local/bin/adb`, `~/.local/bin/banksman`, the plugin directory, the Gradle guard files,
and the banksman config/state. Restore the system adb by deleting the shim; `/usr/bin/adb` or the
SDK adb takes over again. The emulator itself is not managed by this repository.
