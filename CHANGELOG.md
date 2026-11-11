# Changelog

All notable changes to **banksman-opencode**, the downstream integration, are documented here.
Upstream banksman changes are in [docs/upstream-CHANGELOG.md](docs/upstream-CHANGELOG.md).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project follows Semantic Versioning for the integration layer. The upstream package remains
banksman 0.2.0 under its own versioning.

## [Unreleased]

### Added

- OpenCode session identity: `OPENCODE_SESSION_ID`, plus `OPENCODE=1` / `AI_AGENT=opencode`
  detection when no `opencode` process is in the caller's tree (for example a Gradle daemon).
- Session-first ownership in the lease store: the shared `opencode serve` PID no longer makes
  another session's leases the caller's.
- Session-aware adb and Gradle guards, and the session in `status` / `held` labels.
- `opencode/adb-shim.py`: an `adb` wrapper for OpenCode sessions that adopts or acquires the
  session lease and then delegates to the banksman adb guard.
- `opencode/plugin/`: an OpenCode plugin that injects `BANKSMAN_LEASE` and `ANDROID_SERIAL` into
  Gradle device commands and releases the lease on `session.idle` / `session.deleted`.
- `scripts/install-opencode.sh`, documentation, and this downstream changelog.
- Tests for OpenCode identity, session isolation, adb guard, Gradle guard and status labels.

### Fixed

- `guard.events()` now has the `Caller.session` property it expects, so guard events carry the
  session instead of being silently dropped by `record()`.

## [0.1.0] - 2026-11-11

### Added

- Initial downstream of banksman 0.2.0 for OpenCode: session identity, adb shim, Gradle plugin,
  configuration example and setup notes.
