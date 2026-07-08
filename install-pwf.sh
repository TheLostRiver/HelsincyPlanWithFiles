#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN=python
fi

case "${1:-}" in
  install|uninstall)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/installer/pwf_install.py" "$@"
    ;;
  *)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/installer/pwf_install.py" install "$@"
    ;;
esac
