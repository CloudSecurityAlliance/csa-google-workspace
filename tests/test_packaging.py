"""Packaging guards.

The library advertises a typed public surface (README). Under PEP 561 that promise is
only real if a `py.typed` marker ships inside the package, so downstream mypy/pyright
consume the inline hints from the installed wheel. This test fails if the marker is
dropped from the package directory (e.g. a package-data regression).
"""
import os

import csa_google_workspace


def test_py_typed_marker_present():
    pkg_dir = os.path.dirname(csa_google_workspace.__file__)
    assert os.path.isfile(os.path.join(pkg_dir, "py.typed")), (
        "PEP 561 marker missing; downstream type-checkers won't see our type hints"
    )
