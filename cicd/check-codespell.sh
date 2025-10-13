#!/bin/bash

set -eu # deliberately no `-x` or `-v`
set -o pipefail

# Import common.bashrc and change to git repository directory
# shellcheck source-path=SCRIPTDIR  # to help shellcheck to find common.bashrc
source "$(dirname -- "${BASH_SOURCE[0]}")/common.bashrc"
cd "${REPO_DIR}"

run codespell --version
run codespell \
    --skip ".git,venv,.venv,.mypy_cache,.pytest_cache,__pycache__,.idea,third_party" \
    --builtin clear,rare,en-GB_to_en-US \
    --ignore-words ./cicd/codespell-ignore-words.txt \
    --dictionary ./cicd/codespell-custom-dictionary.txt \
    --check-filenames \
    --check-hidden \
    --context 0
