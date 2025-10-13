# shellcheck shell=bash

# ================================================================
# This file is meant to be sourced, not executed directly
# ================================================================
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "ERROR: This script should be sourced, not executed directly."
    exit 1
fi

# ================================================================
# Common definitions
# ================================================================
REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &>/dev/null && pwd)"

DIRS_TO_CHECK=(
    "memorylake"
    "cicd"
)

# ================================================================
# Common functions
# ================================================================
function run() {
    echo "[$(pwd)] $*"
    "$@"
}
