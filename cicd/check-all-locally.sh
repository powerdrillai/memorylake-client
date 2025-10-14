#!/bin/bash

set -eu # deliberately no `-x` or `-v`
set -o pipefail

# Import common.bashrc and change to git repository directory
# shellcheck source-path=SCRIPTDIR  # to help shellcheck to find common.bashrc
source "$(dirname -- "${BASH_SOURCE[0]}")/common.bashrc"
cd "${REPO_DIR}"

COLOR_GREEN='\033[32;1m'
COLOR_RESET='\033[0m'

function invoke() {
    echo -e "${COLOR_GREEN}>>>> Check with $*${COLOR_RESET}"
    "$@"
    echo
}

# invoke ./cicd/check-python-import.py
invoke ./cicd/check-python-code.py
invoke ./cicd/check-flake8.sh
invoke ./cicd/check-isort.sh
invoke ./cicd/check-basedpyright.sh
invoke ./cicd/check-codespell.sh
invoke ./cicd/check-shell.sh
