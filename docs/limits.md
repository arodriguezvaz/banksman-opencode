# Limits

`banksman-opencode` coordinates agents that go through its configured paths. It is not a
security boundary and it does not make an emulator multi-user.

## The guard is a guardrail, not a sandbox

The adb guard is a wrapper on `PATH`. These paths bypass it:

- an absolute path to adb, such as `/usr/bin/adb` or the SDK's `platform-tools/adb`;
- Android Studio's own deploy and Device Manager, which use bundled adb;
- a tool that talks to the adb server on `localhost:5037` directly;
- a user or process that stops or wipes the emulator outside adb.

OpenCode permissions in this repository deny the most common absolute paths and destructive
commands, but a determined process running as the same user can still bypass a wrapper. If you
need a hard boundary, run agents under a separate user account or use a port-level adb broker.

## Android Studio

The shim can adopt an AVD that Android Studio started (`unmanaged = "grant"`), but Android Studio
does not respect the lease. If you use the same AVD in Studio while an agent holds it, you can
still interfere. Use a separate AVD for the human, or wait for `banksman status` to show it free.
If you need Studio itself to be gated, use a port-level broker such as AdbHarbor; it replaces the
PATH/path-based guard with a broker on port 5037.

## Multiple instances of one AVD

An AVD launched as several emulators with `-read-only` has no single serial that banksman can
assign to a lease. Use separate AVDs for parallel work; `Medium_Phone` and `Pixel_8` are different
resources, two read-only copies of `Medium_Phone` are not.

## New AVDs

`banksman admin discover` writes an allowlist. A new AVD in Android Studio is not offered until
you run `banksman admin discover --all --yes` again. This is deliberate: discovery is a human
gate, not an auto-widening policy. A systemd timer or a shell alias can run it periodically if
you create AVDs often.

## Leases expire

A lease is released on `session.idle`/`session.deleted` by the plugin, or expires after the idle
timeout (20 minutes by default) or the hard cap (3 hours). If the plugin is disabled, a lease can
hold an AVD until the timeout or until you run `banksman release --lease <id>`.

## Plugin loading

OpenCode's plugin loader is new and may cache a failed load. The adb shim is independent of the
plugin, so `adb` stays gated. If Gradle automation stops working, restart OpenCode once:

```sh
opencode service restart
```

Then check `banksman status` and `banksman admin doctor`.

## Beta upstream

This distribution is based on banksman 0.2.0, which is beta. Until 1.0.0, commands and file
formats can change between minor versions. Pin the version you install and re-run
`banksman admin doctor` after an upgrade; the doctor names the generated files to save again.

## Fail-open

The guard fails open when it cannot decide, because a guard that blocks every device is worse
than a short time without protection. If banksman cannot start, the adb wrapper runs the saved
adb and says the call is not checked. The Gradle guard behaves the same way.

## Secrets and personal data

The guard is not a security boundary, but the files it writes are private: the lease store is
`0700`, leases and logs are `0600`, and config/inventory must be `0600`. Do not put tokens or
credentials in `AGENTS.md`, prompts or committed config. The OpenCode plugin's debug output, if
enabled, may include session IDs; keep it out of public logs.
