#!/usr/bin/env python
"""Bring the whole network up: 7 MCP servers, 7 agents, 1 gateway.

Fifteen uvicorn servers, each on its own port, in one asyncio process. The
traffic between them is real HTTP over real A2A and MCP -- only the process
supervision is collapsed, so the demo runs with one command.

To run a single service the way production would, use its own entrypoint:

    python -m refundry.agents.tracer
    python -m refundry.servers.orders        (via scripts/run_one.py)
"""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

from refundry.agents import AGENTS  # noqa: E402
from refundry.agents import build as build_agent
from refundry.config import HOST, PORTS, settings  # noqa: E402
from refundry.gateway import build as build_gateway  # noqa: E402
from refundry.jev import jev  # noqa: E402
from refundry.servers import SERVERS  # noqa: E402
from refundry.servers import build as build_server


def _server(app, port: int) -> uvicorn.Server:
    return uvicorn.Server(uvicorn.Config(app, host=HOST, port=port,
                                         log_level="warning", access_log=False))


async def main() -> None:
    servers: list[tuple[str, uvicorn.Server]] = []

    for key in SERVERS:
        servers.append((f"mcp:{key}", _server(build_server(key), PORTS[key])))
    for key in AGENTS:
        servers.append((f"a2a:{key}", _server(build_agent(key), PORTS[key])))
    servers.append(("gateway", _server(build_gateway(), PORTS["gateway"])))

    print("\n  Refundry")
    print("  " + "-" * 66)
    print(f"  reasoning   {settings.reasoning}")
    aside = ("  (local System One stand-in, not Jev)" if jev.backend == "local"
             else "  (typesafe_sdk)")
    print(f"  jev         {jev.backend}{aside}")
    print(f"  approval    ${settings.auto_approval_limit:,.2f}"
          f"   confidence floor {settings.confidence_floor}")
    print("  " + "-" * 66)
    for key in SERVERS:
        print(f"  mcp    {key:<14} http://{HOST}:{PORTS[key]}/mcp")
    for key in AGENTS:
        print(f"  agent  {key:<14} http://{HOST}:{PORTS[key]}/.well-known/agent-card.json")
    print(f"\n  gateway               http://{HOST}:{PORTS['gateway']}{'/docs':<6}"
          f"  <- open this")
    print("  " + "-" * 66)
    print("  ctrl-c to stop\n")

    tasks = [asyncio.create_task(s.serve(), name=n) for n, s in servers]

    stop = asyncio.Event()

    def _bye(*_):
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, _bye)
        except NotImplementedError:  # pragma: no cover - Windows
            signal.signal(sig, _bye)

    await stop.wait()
    print("\n  stopping ...")
    for _, s in servers:
        s.should_exit = True
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
