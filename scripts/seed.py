#!/usr/bin/env python
"""Reset the database. The seed JSON is read at runtime, so this only clears
the tables the network writes to."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from refundry import store  # noqa: E402
from refundry.config import settings  # noqa: E402

if __name__ == "__main__":
    store.reset()
    print(f"reset {settings.db_path}")
