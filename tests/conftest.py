"""Pytest bootstrap: make the ``src`` layout importable without installing.

``python -m unittest discover -s tests`` does not import this file, so
``tests/__init__.py`` performs the same path fix for the standard library test
runner.  Both entry points therefore work with a plain checkout.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
