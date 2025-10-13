#!/bin/bash

set -eu # deliberately no `-x` or `-v`
set -o pipefail

# Import common.bashrc and change to git repository directory
# shellcheck source-path=SCRIPTDIR  # to help shellcheck to find common.bashrc
source "$(dirname -- "${BASH_SOURCE[0]}")/common.bashrc"
cd "${REPO_DIR}"

# pytest-xdist will force pytest stdout/stderr capture (aka. disables -s/--capture=no),
# which is inconvenient for local development.
# We disable pytest-xdist by default, and only use it in CICD pipeline.
#
# Also, before running, we ensure .coverage file does not exist
rm -f ./.coverage

TEST_SCOPE="${1:-memorylake}"
python3 -m pytest -n logical --cov=. --cov-append --cov-report="" "${TEST_SCOPE}"

# Generate coverage.xml, and print to console too
coverage xml -o coverage.xml
coverage report
