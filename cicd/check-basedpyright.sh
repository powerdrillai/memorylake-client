#!/bin/bash

set -eu # deliberately no `-x` or `-v`
set -o pipefail

# Import common.bashrc and change to git repository directory
# shellcheck source-path=SCRIPTDIR  # to help shellcheck to find common.bashrc
source "$(dirname -- "${BASH_SOURCE[0]}")/common.bashrc"
cd "${REPO_DIR}"

#
# Run basedpyright
#
# Decide the actual python version we are running on, and use this version for basedpyright
PYTHON_VERSION="$(python3 -c "from sys import version_info as v; print(f'{v[0]}.{v[1]}')")"

run basedpyright --pythonversion "${PYTHON_VERSION}" --warnings --threads --stats
