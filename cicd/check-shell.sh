#!/bin/bash

set -eu # deliberately no `-x` or `-v`
set -o pipefail

# Import common.bashrc and change to git repository directory
# shellcheck source-path=SCRIPTDIR  # to help shellcheck to find common.bashrc
source "$(dirname -- "${BASH_SOURCE[0]}")/common.bashrc"
cd "${REPO_DIR}"

#
# Run shfmt
#
run shfmt --version

# Instead of mapfile (requires bash 4.0+), use a while read loop
files_to_check=()
while IFS=$'\n' read -r file; do
    files_to_check+=("${file}")
done < <(git ls-files "${DIRS_TO_CHECK[@]}" --exclude='*.bash' --exclude='*.bashrc' --exclude='*.sh' --ignored -c)

if [ ${#files_to_check[@]} -gt 0 ]; then
    run shfmt -i 4 -bn -d "${files_to_check[@]}"
fi

#
# Run shellcheck
#
run shellcheck --version

# Instead of mapfile (requires bash 4.0+), use a while read loop
files_to_check=()
while IFS=$'\n' read -r file; do
    files_to_check+=("${file}")
done < <(git ls-files "${DIRS_TO_CHECK[@]}" --exclude='*.bash' --exclude='*.sh' --ignored -c) # no *.bashrc

if [ ${#files_to_check[@]} -gt 0 ]; then
    run shellcheck "${files_to_check[@]}"
fi
