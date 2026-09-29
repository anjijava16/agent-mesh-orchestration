#!/usr/bin/env python
"""Run exactly one service, the way a production deployment would.

    python scripts/run_one.py mcp orders
    python scripts/run_one.py agent tracer
    python scripts/run_one.py gateway
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

from refundry.agents import build as build_agent  # noqa: E402
from refundry.config import HOST, PORTS  # noqa: E402
from refundry.gateway import build as build_gateway  # noqa: E402
from refundry.servers import build as build_server  # noqa: E402

if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else "gateway"
    key = sys.argv[2] if len(sys.argv) > 2 else "gateway"
    app = {"mcp": build_server, "agent": build_agent}.get(kind)
    app = app(key) if app else build_gateway()
    port = PORTS[key if kind != "gateway" else "gateway"]
    print(f"{kind}:{key} on http://{HOST}:{port}")
    uvicorn.run(app, host=HOST, port=port, log_level="info")
