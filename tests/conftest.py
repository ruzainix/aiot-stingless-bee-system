"""Shared pytest configuration.

Makes the source modules importable without packaging by adding their
directories to ``sys.path``.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for module_dir in ("ml_prediction", "raspberry_pi_gateway"):
    path = str(ROOT / module_dir)
    if path not in sys.path:
        sys.path.insert(0, path)
