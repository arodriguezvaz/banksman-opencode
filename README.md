# banksman-opencode

**Unofficial OpenCode integration for [banksman](https://github.com/Twinsen81/banksman): one Android emulator per OpenCode session, without agents fighting over `adb` or Gradle.**

> This is a downstream distribution, not the official banksman project. It is not affiliated with or endorsed by the banksman authors. The upstream project and its Apache-2.0 license are credited below.

[![CI](https://github.com/arodriguezvaz/banksman-opencode/actions/workflows/ci.yml/badge.svg)](https://github.com/arodriguezvaz/banksman-opencode/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

## Why

OpenCode runs every session under one `opencode serve` process. Upstream banksman 0.2.0 understands Claude Code and Codex sessions, but not OpenCode: without a session identity, all OpenCode shells look like one holder and can use each other's emulator.

This downstream adds:

- **OpenCode session identity** to banksman (`OPENCODE_SESSION_ID`, and `OPENCODE=1` / `AI_AGENT=opencode` for processes outside the agent tree).
- **An `adb` shim** that acquires the calling session's lease automatically.
- **An OpenCode plugin** that injects the lease and `ANDROID_SERIAL` into Gradle device commands and releases the lease when the session goes idle.
- **Documentation, config and an installer** so the setup is reproducible.

The emulator gate itself is still banksman: leases, the queue/wait, the adb guard, the Gradle guard, AVD discovery and the reaper are upstream code.

## How it works

```text
OpenCode session A ── adb ... ──> adb shim ──> banksman lease + adb guard ──> emulator-5554
                   └─ ./gradlew ... ──> plugin ──> ANDROID_SERIAL + lease ──> Gradle guard

OpenCode session B ── adb ... ──> adb shim ──> "held by session A" (refused)
```

- **Lease**: an exclusive, temporary reservation for one AVD. It has an owner, a device serial and an expiry.
- **Serial**: the adb name of the device, such as `emulator-5554`.
- **Guard**: the adb wrapper and the Gradle init script check that the lease is yours before a device command runs.
- **`BANKSMAN_LEASE` / `ANDROID_SERIAL`**: the lease token and the device serial that the guard reads.

## Quick start

See [docs/install.md](docs/install.md) for the full setup. The short version:

```sh
git clone https://github.com/arodriguezvaz/banksman-opencode.git
cd banksman-opencode

# Put the fork on PATH
ln -sf "$PWD/bin/banksman" "$HOME/.local/bin/banksman"

# Configuration (every AVD, Studio-started AVDs grantable, strict guard)
mkdir -p "$HOME/.config/banksman"
cp opencode/config.example.toml "$HOME/.config/banksman/config.toml"
chmod 600 "$HOME/.config/banksman/config.toml"
banksman admin discover --all --yes

# banksman's generated adb wrapper (the guard)
mkdir -p "$HOME/.local/share/banksman/bin"
banksman admin adb-shim > "$HOME/.local/share/banksman/bin/adb"
chmod 755 "$HOME/.local/share/banksman/bin/adb"

# The OpenCode-aware shim, first on PATH
cp opencode/adb-shim.py "$HOME/.local/bin/adb"
chmod 755 "$HOME/.local/bin/adb"

# Gradle guard
banksman admin gradle-guard > "$HOME/.gradle/init.d/banksman-gradle-guard.gradle"
mkdir -p "$HOME/.gradle/banksman"
banksman admin gradle-guard --part > "$HOME/.gradle/banksman/gradle-guard.gradle"
```

Install `opencode/plugin/` under `$HOME/.config/opencode/plugins/banksman-opencode`, add it to the `plugins` array in `opencode.jsonc`, restart OpenCode, and deny `banksman admin` / raw adb paths in OpenCode permissions. The installer prints the exact snippets:

```sh
./scripts/install-opencode.sh --dry-run   # show every change
./scripts/install-opencode.sh --yes       # apply, then discover AVDs
```

## Automatic or manual

With the shim and plugin, agents do not need to know about leases:

- `adb shell`, `adb install`, screenshots, etc. are gated by the shim.
- `./gradlew installDebug` / `connectedDebugAndroidTest` get `ANDROID_SERIAL` from the plugin.

Without the plugin, banksman still works exactly as upstream documents:

```sh
banksman run --where kind=emulator -- ./gradlew connectedDebugAndroidTest
banksman run --where kind=emulator -- adb shell ...
```

The adb shim continues to gate `adb`; Gradle needs either the plugin or `banksman run`. See [docs/architecture.md](docs/architecture.md).

## Tested

- Upstream banksman test suite with the OpenCode changes: **1706 passed, 17 skipped** (with `umask 022` and `LC_ALL=C`).
- Real AVD: own session `adb shell` passes; a second session is refused; `adb devices` stays available; release leaves the AVD running.
- Real Gradle: a dry-run receives `ANDROID_SERIAL`/`BANKSMAN_LEASE`; a build from another session is refused before compiling.
- OpenCode permissions block `banksman admin`, raw absolute `adb` paths, `adb emu kill` and `adb kill-server`.

## Limits

This is a guardrail, not a sandbox. Android Studio's own adb, absolute-path adb and tools that talk to the adb server directly bypass the path wrapper. See [docs/limits.md](docs/limits.md) for the full list, including `-read-only` instances and new AVDs.

## Upstream

- Upstream: [Twinsen81/banksman](https://github.com/Twinsen81/banksman)
- Downstream/adapters: this repository

The OpenCode session support lives in this downstream. Upstream banksman remains the lease/guard engine; the adb shim, the plugin and this README are integration code and are not part of the upstream project.

## License and attribution

This distribution is licensed under the **Apache License 2.0**. It includes banksman, Copyright Evgenii Plokhov, also under Apache-2.0. See [LICENSE](LICENSE), [NOTICE](NOTICE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The name `banksman-opencode` is descriptive. This project does not use the upstream logo and does not claim to be the official banksman project.

---

## Resumen en español

`banksman-opencode` es una integración **no oficial** de banksman para OpenCode. Añade identidad de sesión de OpenCode al motor, un shim de `adb` que pide el lease automáticamente y un plugin que hace lo mismo con Gradle y libera el emulador al quedar la sesión idle.

- Un AVD pertenece a una sesión cada vez; las demás esperan o reciben un rechazo claro.
- `adb` funciona sin plugin; Gradle necesita el plugin o `banksman run --where kind=emulator -- <comando>`.
- Es un guardrail, no un sandbox: Android Studio y las rutas absolutas de `adb` se lo saltan.
- Licencia Apache-2.0, con atribución a banksman. No es un proyecto oficial.
