#!/usr/bin/env bash
# Regenerate the CI/release lockfiles in requirements/.
#
# These pin what *our automation* installs. They do NOT pin what users get: the ranges in
# `pyproject.toml` stay permissive on purpose, because pinning a library's dependencies pushes
# a resolution problem onto every application that depends on it. Reproducible CI and a
# permissive published package are different questions (audit 2026-08-27-01, T18/GA-#28).
#
# --python-version 3.10 IS LOAD-BEARING. Without it `uv pip compile --universal` resolves
# against the interpreter you happen to be running - it does not take the floor from
# `requires-python` in pyproject.toml - and quietly emits a lock that cannot install on our
# oldest supported Python. Measured: it pinned `rpds-py==2026.6.3` (requires >=3.11), which
# installs on four of the five matrix legs and fails the fifth.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/"; exit 1; }

FLOOR=3.14

# --upgrade re-resolves everything to the newest compatible versions. Without it, compiling an
# unchanged input reproduces the existing pins, so a plain run is a no-op and safe to repeat.
UPGRADE=""
[ "${1:-}" = "--upgrade" ] && UPGRADE="--upgrade"

compile() { uv pip compile --universal --generate-hashes --python-version "$FLOOR" \
              --no-header --quiet $UPGRADE "$@"; }

# The dev closure: lint, type-check and the five-Python test matrix.
compile --extra dev pyproject.toml -o requirements/dev.txt

# The release toolchain that turns the tree into an sdist + wheel.
compile requirements/build.in -o requirements/build.txt

# uv itself, so CI can regenerate these without trusting an unpinned download.
compile requirements/uv.in -o requirements/uv.txt

# The build BACKEND, applied through PIP_CONSTRAINT. `python -m build` creates its own
# isolated venv and installs `build-system.requires` into it from PyPI, so pinning `build`
# itself in the outer environment does not reach the code that actually writes the artifact.
compile requirements/build-backend.in -o requirements/build-backend.txt

echo "Regenerated. Review the diff, then run: pytest -q tests/test_lockfiles.py"
