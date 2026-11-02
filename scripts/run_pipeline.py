#!/usr/bin/env python3
"""Collect ICLR submissions and reviews, then search for matching papers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from neurips26_ethics.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
