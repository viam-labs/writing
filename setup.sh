#!/bin/sh
cd "$(dirname "$0")" || exit 1

# Create a virtual environment to run our code
VENV_NAME="venv"
PYTHON="$VENV_NAME/bin/python"
ENV_ERROR="This module requires Python >=3.10, pip, and virtualenv to be installed."

# viam-sdk needs Python >=3.10, but `python3` is still 3.9 on Raspberry Pi OS
# Bullseye and on stock macOS. Pick the first interpreter that's new enough, so
# an old default fails here with a clear message instead of halfway through pip
# with "no matching distribution found".
find_python() {
    for candidate in python3 python3.13 python3.12 python3.11 python3.10; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c \
            'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null
        then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

SYS_PYTHON=$(find_python)
if [ -z "$SYS_PYTHON" ]; then
    echo "No Python >=3.10 found on PATH (python3 is $(python3 -V 2>&1))." >&2
    if command -v apt-get >/dev/null; then
        echo "On Debian/Ubuntu: sudo apt install python3.11 python3.11-venv" >&2
    fi
    echo "$ENV_ERROR" >&2
    exit 1
fi
echo "Using $SYS_PYTHON ($($SYS_PYTHON -V 2>&1))"

if ! $SYS_PYTHON -m venv $VENV_NAME >/dev/null 2>&1; then
    echo "Failed to create virtualenv."
    if command -v apt-get >/dev/null; then
        echo "Detected Debian/Ubuntu, attempting to install python3-venv automatically."
        SUDO="sudo"
        if ! command -v $SUDO >/dev/null; then
            SUDO=""
        fi
		if ! apt info python3-venv >/dev/null 2>&1; then
			echo "Package info not found, trying apt update"
			$SUDO apt -qq update >/dev/null
		fi
        $SUDO apt install -qqy python3-venv >/dev/null 2>&1
        if ! $SYS_PYTHON -m venv $VENV_NAME >/dev/null 2>&1; then
            echo $ENV_ERROR >&2
            exit 1
        fi
    else
        echo $ENV_ERROR >&2
        exit 1
    fi
fi

# remove -U if viam-sdk should not be upgraded whenever possible
# -qq suppresses extraneous output from pip
# The marker is invalidated when requirements.txt changes, so editing deps and
# restarting the module actually reinstalls them.
if [ ! -f .installed ] || [ requirements.txt -nt .installed ]; then
    echo "Installing/upgrading Python packages..."
    if ! $PYTHON -m pip install -r requirements.txt -Uqq; then
        exit 1
    fi
    touch .installed
fi
