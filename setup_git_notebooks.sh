#!/usr/bin/env sh
# One-time setup after cloning: makes Jupyter notebooks merge cleanly.
# Run from the repository root:  sh setup_git_notebooks.sh

pip install nbstripout nbdime
nbstripout --install --keep-id --extra-keys "cell.metadata.ExecuteTime cell.metadata.execution" --attributes .git/info/attributes
nbdime config-git --enable --global
git config filter.nbstripout.clean 'nbstripout --keep-id --extra-keys "cell.metadata.ExecuteTime cell.metadata.execution"'

echo "Done. Check with:  git config --get filter.nbstripout.clean"
