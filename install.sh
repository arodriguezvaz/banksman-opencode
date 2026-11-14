#!/bin/sh
# Install banksman-opencode from a checkout, or from GitHub, and then the OpenCode integration.
#
# From a checkout:
#     ./install.sh
# From GitHub, without a checkout:
#     curl -fsSL https://raw.githubusercontent.com/arodriguezvaz/banksman-opencode/main/install.sh | sh
#
# Every argument goes to `banksman admin install-opencode`, for example --dry-run or --yes. Set
# BANKSMAN_REF to a tag or a branch, for example BANKSMAN_REF=v0.2.0.
set -eu

REF=${BANKSMAN_REF:-main}
DEST=${BANKSMAN_HOME:-$HOME/.local/share/banksman-opencode}
BIN=${BANKSMAN_BIN_DIR:-$HOME/.local/bin}
REPOSITORY=${BANKSMAN_REPOSITORY:-arodriguezvaz/banksman-opencode}

# A checkout runs from its own directory: the package has no dependency outside the standard
# library, so there is nothing to build.
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd) || SOURCE=
if [ -n "$SOURCE" ] && [ -f "$SOURCE/pyproject.toml" ] && [ -d "$SOURCE/src/banksman" ]; then
    ROOT=$SOURCE
else
    TMP=$(mktemp -d)
    trap 'rm -rf "$TMP"' EXIT INT TERM
    download() {
        if command -v curl >/dev/null 2>&1; then
            curl -fsSL "$1" -o "$TMP/source.tar.gz"
        elif command -v wget >/dev/null 2>&1; then
            wget -q "$1" -O "$TMP/source.tar.gz"
        else
            echo "install.sh: curl or wget is needed to download banksman-opencode" >&2
            exit 1
        fi
    }
    # A branch, a tag, or a commit: try each form that GitHub serves.
    FOUND=0
    for URL in \
        "https://github.com/$REPOSITORY/archive/refs/heads/$REF.tar.gz" \
        "https://github.com/$REPOSITORY/archive/refs/tags/$REF.tar.gz" \
        "https://github.com/$REPOSITORY/archive/$REF.tar.gz"
    do
        if download "$URL"; then
            FOUND=1
            break
        fi
    done
    if [ "$FOUND" -eq 0 ]; then
        echo "install.sh: cannot download $REF from $REPOSITORY" >&2
        exit 1
    fi
    # A branch tarball unpacks to banksman-opencode-<branch>, a tag tarball to
    # banksman-opencode-<tag without v>: take the one directory that it made.
    tar -xzf "$TMP/source.tar.gz" -C "$TMP"
    UNPACKED=$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n 1)
    if [ -z "$UNPACKED" ] || [ ! -d "$UNPACKED/src/banksman" ]; then
        echo "install.sh: the download does not hold the source tree" >&2
        exit 1
    fi
    mkdir -p "$DEST"
    # The managed copy holds no local change: replace the source and the launcher, so that a
    # file that the new version removed does not stay behind.
    rm -rf "$DEST/src" "$DEST/bin"
    cp -R "$UNPACKED/." "$DEST/"
    ROOT=$DEST
fi

mkdir -p "$BIN"
ln -sfn "$ROOT/bin/banksman" "$BIN/banksman"

if ! command -v python3 >/dev/null 2>&1; then
    echo "install.sh: python3 is needed (3.11 or newer)" >&2
    exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "install.sh: python3 3.11 or newer is needed" >&2
    exit 1
fi
exec "$ROOT/bin/banksman" admin install-opencode "$@"
