@echo off
REM One-time setup after cloning: makes Jupyter notebooks merge cleanly.
REM Run from the repository root:  setup_git_notebooks.bat

pip install nbstripout nbdime
nbstripout --install --keep-id --extra-keys "cell.metadata.ExecuteTime cell.metadata.execution" --attributes .git/info/attributes
nbdime config-git --enable --global
git config filter.nbstripout.clean "nbstripout --keep-id --extra-keys \"cell.metadata.ExecuteTime cell.metadata.execution\""

echo.
echo Done. Check with:  git config --get filter.nbstripout.clean
