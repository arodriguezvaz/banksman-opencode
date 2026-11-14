# banksman-opencode

**Unofficial OpenCode integration for [banksman](https://github.com/Twinsen81/banksman): one
Android emulator per OpenCode session, without agents fighting over `adb` or Gradle.**

> This is a downstream distribution, not the official banksman project. It is not affiliated with
> or endorsed by the banksman authors. The upstream project and its Apache-2.0 license are
> credited below.

[![CI](https://github.com/arodriguezvaz/banksman-opencode/actions/workflows/ci.yml/badge.svg)](https://github.com/arodriguezvaz/banksman-opencode/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

## Why

OpenCode runs every session under one `opencode serve` process. Upstream banksman identifies a
holder by the nearest agent process, so all OpenCode sessions look like one holder and can use
each other's emulator. This distribution adds OpenCode session identity to the engine, an `adb`
shim that acquires the session's lease, and a plugin that does the same for Gradle device tasks.

## Install

Requirements: Linux or macOS, Python 3.11+, the Android SDK (`platform-tools`, `emulator`) with at
least one AVD, and OpenCode 2.2 or newer. The package uses only the Python standard library.

```sh
# From a checkout:
./install.sh --dry-run       # show every file it would write
./install.sh                 # ask once, then write
./install.sh --yes           # or apply without questions

# Without a checkout:
curl -fsSL https://raw.githubusercontent.com/arodriguezvaz/banksman-opencode/main/install.sh | sh
```

`install.sh` puts the fork on `PATH` and runs `banksman admin install-opencode`, which writes:

| What | Where |
|---|---|
| banksman adb wrapper (the guard) | `~/.local/share/banksman/bin/adb` |
| OpenCode adb shim | `~/.local/bin/adb` |
| Gradle guard | `~/.gradle/init.d/` and `~/.gradle/banksman/` |
| Example configuration | `~/.config/banksman/config.toml` (never overwritten) |
| Plugin | `~/.config/opencode/plugins/banksman-opencode/` |

It prints the `plugins` line for `opencode.jsonc` (optional: OpenCode discovers the plugin in
`~/.config/opencode/plugins/`; listing it pins it explicitly), and the permissions that keep
`banksman admin` and raw adb paths away from agents. Then allow the AVDs and check the install:

```sh
banksman admin discover --all --yes    # or ./install.sh --yes --discover
banksman admin doctor
```

Run `banksman admin` from a normal terminal: the OpenCode permissions deny it to agents.

## How it works

```text
OpenCode session A ── adb ... ──> adb shim ──> banksman lease + adb guard ──> emulator-5554
                   └─ ./gradlew ... ──> plugin ──> ANDROID_SERIAL + lease ──> Gradle guard

OpenCode session B ── adb ... ──> adb shim ──> "held by session A" (refused)
```

- **Lease**: an exclusive, temporary reservation for one AVD. It has an owner, a session, a
  device serial and an expiry.
- **Shim**: reads `OPENCODE_SESSION_ID`, adopts or acquires the session's lease, and delegates to
  the banksman adb wrapper, which decides whether the call may run.
- **Plugin**: rewrites Gradle device commands with `BANKSMAN_LEASE` and `ANDROID_SERIAL`, and
  releases the lease on `session.idle` / `session.deleted` without stopping the AVD.

## Limits

This is a guardrail, not a sandbox: absolute-path adb, Android Studio's own deploy and tools that
talk to the adb server directly bypass it. See [docs/limits.md](docs/limits.md).

## Documentation

- [docs/install.md](docs/install.md) — every option, the manual path, upgrades and uninstall.
- [docs/troubleshooting.md](docs/troubleshooting.md) — “held by”, plugin, Gradle and lease issues.
- [docs/architecture.md](docs/architecture.md) — components, request flows and state.
- [docs/opencode.md](docs/opencode.md) — what the fork changes in banksman.
- [docs/limits.md](docs/limits.md) — what the guard does not cover.

## Upstream and license

- Upstream: [Twinsen81/banksman](https://github.com/Twinsen81/banksman) (Apache-2.0).
- The OpenCode session support, the shim, the plugin and this installer live in this repository.

This distribution is licensed under the **Apache License 2.0**. See [LICENSE](LICENSE),
[NOTICE](NOTICE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

## Resumen en español

`banksman-opencode` es una integración **no oficial** de banksman para OpenCode. Un AVD pertenece
a una sesión cada vez; las demás esperan o reciben un rechazo claro.

```sh
./install.sh --dry-run    # ver el plan
./install.sh              # instalar
banksman admin discover --all --yes
banksman admin doctor
```

El instalador escribe el shim de `adb`, el guard de Gradle, la configuración de ejemplo y el
plugin, e imprime la línea que hay que añadir a `opencode.jsonc`. Es un guardrail, no un sandbox:
las rutas absolutas de `adb` y Android Studio se lo saltan. Licencia Apache-2.0, con atribución a
banksman. No es un proyecto oficial.
