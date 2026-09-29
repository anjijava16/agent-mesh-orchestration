"""Seed data, loaded once per process."""

from __future__ import annotations

import functools
import json

from refundry.config import SEED


@functools.cache
def load(name: str) -> dict:
    return json.loads((SEED / f"{name}.json").read_text())
