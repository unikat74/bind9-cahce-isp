#!/bin/sh
# Zgodność ze starszą nazwą instalatora.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec "$ROOT/installer/bootstrap-rpz.sh" "$@"
