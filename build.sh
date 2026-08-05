#!/bin/sh
# Package the module as a source tarball.
#
# This is a pure-Python module, so it uploads with `--platform any`: pip resolves
# the right wheels on the target machine when setup.sh runs there. That avoids
# cross-compiling a PyInstaller binary for every board architecture.
cd "$(dirname "$0")" || exit 1

rm -rf dist
mkdir -p dist

tar -czf dist/archive.tar.gz \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    meta.json requirements.txt setup.sh run.sh src

echo "built dist/archive.tar.gz:"
tar -tzf dist/archive.tar.gz
