#!/bin/sh
# The installer is a command of banksman now: `banksman admin install-opencode`.
#
# This file keeps the earlier invocation working from a checkout:
#     ./scripts/install-opencode.sh --dry-run
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec "$ROOT/bin/banksman" admin install-opencode "$@"
