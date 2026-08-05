#!/bin/sh
# Entry point for running this module as a *local* module during development:
# runs straight from source, so edits take effect on a module restart with no
# PyInstaller rebuild. The registry build uses dist/main instead (see meta.json).
cd "$(dirname "$0")" || exit 1

if [ ! -f venv/bin/python ]; then
    ./setup.sh || exit 1
fi

exec venv/bin/python src/main.py "$@"
