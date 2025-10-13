#!/bin/bash

set -eu # deliberately no `-x` or `-v`
set -o pipefail

# Import common.bashrc and change to git repository directory
# shellcheck source-path=SCRIPTDIR  # to help shellcheck to find common.bashrc
source "$(dirname -- "${BASH_SOURCE[0]}")/common.bashrc"
cd "${REPO_DIR}"

#
# NOTE: If you want to ignore some files, please add them to `.flake8` file, but not here.
#
run flake8 --version
run flake8 --show-source "${DIRS_TO_CHECK[@]}"
