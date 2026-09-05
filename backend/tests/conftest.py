from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

import pytest


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
