#!/usr/bin/env bash
# Install the banksman-opencode CLI, config, adb shim, Gradle guard and OpenCode plugin.
#
# It does not edit opencode.jsonc: it prints the snippet to add. Run with --dry-run first.
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DRY_RUN=0
ASSUME_YES=0

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --yes) ASSUME_YES=1 ;;
        -h|--help)
            echo "usage: $0 [--dry-run] [--yes]"
            exit 0
            ;;
        *)
            echo "unknown argument: $arg" >&2
            exit 2
            ;;
    esac
done

BIN="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/banksman"
PLUGIN_DIR="$HOME/.config/opencode/plugins/banksman-opencode"
WRAPPER_DIR="$HOME/.local/share/banksman/bin"
GRADLE_INIT="$HOME/.gradle/init.d/banksman-gradle-guard.gradle"
GRADLE_PART="$HOME/.gradle/banksman/gradle-guard.gradle"
BANKSMAN="$BIN/banksman"

say() { printf '%s\n' "$*"; }
run() {
    say "+ $*"
    if [ "$DRY_RUN" -eq 0 ]; then
        "$@"
    fi
}
copy() {
    say "+ cp $1 $2"
    if [ "$DRY_RUN" -eq 0 ]; then
        cp "$1" "$2"
    fi
}
copy_tree() {
    say "+ cp -R $1/. $2/"
    if [ "$DRY_RUN" -eq 0 ]; then
        mkdir -p "$2"
        cp -R "$1/." "$2/"
    fi
}

say "banksman-opencode installer"
say "repository: $ROOT"
if [ "$DRY_RUN" -eq 1 ]; then
    say "dry run: no files will change"
fi

run mkdir -p "$BIN" "$CONFIG_DIR" "$PLUGIN_DIR" "$WRAPPER_DIR" "$(dirname "$GRADLE_INIT")" "$(dirname "$GRADLE_PART")"

# CLI
if [ -e "$BANKSMAN" ] && [ ! -L "$BANKSMAN" ]; then
    say "note: $BANKSMAN exists and is not a symlink; leaving it alone"
else
    run ln -sf "$ROOT/bin/banksman" "$BANKSMAN"
fi

# Config: never overwrite an existing config.
if [ -e "$CONFIG_DIR/config.toml" ]; then
    say "config already exists: $CONFIG_DIR/config.toml (not overwritten)"
else
    copy "$ROOT/opencode/config.example.toml" "$CONFIG_DIR/config.toml"
    run chmod 600 "$CONFIG_DIR/config.toml"
fi

# banksman's generated adb wrapper: the guard.
say "generating the banksman adb wrapper"
if [ "$DRY_RUN" -eq 0 ]; then
    "$BANKSMAN" admin adb-shim > "$WRAPPER_DIR/adb"
    chmod 755 "$WRAPPER_DIR/adb"
fi

# OpenCode-aware adb shim, first on PATH. This shadows the system adb; that is intentional.
copy "$ROOT/opencode/adb-shim.py" "$BIN/adb"
run chmod 755 "$BIN/adb"

# Gradle guard.
if [ "$DRY_RUN" -eq 0 ]; then
    "$BANKSMAN" admin gradle-guard > "$GRADLE_INIT"
    "$BANKSMAN" admin gradle-guard --part > "$GRADLE_PART"
    chmod 644 "$GRADLE_INIT" "$GRADLE_PART"
fi

# Plugin.
copy_tree "$ROOT/opencode/plugin" "$PLUGIN_DIR"

if [ "$ASSUME_YES" -eq 1 ]; then
    run "$BANKSMAN" admin discover --all --yes
else
    say "next: $BANKSMAN admin discover --all --yes   # allow the AVDs you want"
fi

if [ "$DRY_RUN" -eq 0 ]; then
    "$BANKSMAN" admin doctor || true
fi

cat <<EOF

Next:
1. Add the plugin to ~/.config/opencode/opencode.jsonc:
   "plugins": ["$PLUGIN_DIR"]

2. Add the permissions from docs/install.md (deny banksman admin and raw adb paths).

3. Restart OpenCode once:
   opencode service restart

Check:
   banksman status
   banksman held
EOF
