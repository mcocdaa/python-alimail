"""Test package for the alimail SDK.

The package is not installed in CI: make ``import alimail`` work by prepending
the repository's ``src`` directory to ``sys.path``.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
