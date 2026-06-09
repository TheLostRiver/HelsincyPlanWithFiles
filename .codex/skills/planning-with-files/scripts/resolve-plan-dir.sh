#!/bin/sh
# planning-with-files: deprecated compatibility resolver.
#
# The authoritative resolver lives in .codex/hooks/planning_state.py and is
# exposed through plan.py status. Keep this wrapper thin so session bindings,
# PLAN_ID precedence, and workspace fallback do not drift across implementations.

set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/../../../.." && pwd)"
PLAN_CLI="${ROOT_DIR}/.codex/skills/planning-with-files/scripts/plan.py"

PWF_LANG= python "${PLAN_CLI}" --root "${ROOT_DIR}" status 2>/dev/null \
    | sed -n 's/^path: //p' \
    | head -n 1

exit 0
