# Third-party notices

## banksman

- Project: banksman — lease shared devices and emulators to parallel coding agents.
- Copyright: Evgenii Plokhov and contributors.
- Source: https://github.com/Twinsen81/banksman
- License: Apache License 2.0. The full text is in [LICENSE](LICENSE).
- Changes in this distribution: OpenCode session identity, session-first ownership, session-aware
  guards and status labels, plus the OpenCode adapter. Upstream files that changed are marked by
  the Git history. The downstream changes and the adapter are maintained in this repository.

## OpenCode plugin API

- The plugin imports `@opencode/plugin` from the OpenCode runtime. The dependency is provided by
  OpenCode and is not bundled in this repository. See the OpenCode project for its license.
- The adb shim and the plugin use only the Python standard library and Node.js built-ins.

## Python standard library

- Python is distributed under the Python Software Foundation License. This project uses the
  standard library only; it does not vendor Python itself.
