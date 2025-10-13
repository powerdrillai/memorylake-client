#!/bin/bash

set -eu
set -o pipefail

# Import common.bashrc and change to git repository directory
# shellcheck source-path=SCRIPTDIR  # to help shellcheck to find common.bashrc
source "$(dirname -- "${BASH_SOURCE[0]}")/common.bashrc"
cd "${REPO_DIR}"

# Do formats
run autopep8 "${DIRS_TO_CHECK[@]}"
run isort "${DIRS_TO_CHECK[@]}"
