"""Entry point so `python -m agent.mcp_server` and the installed
console-script `discovery-inception-mcp` both work.
"""
from __future__ import annotations

import asyncio

from agent.mcp_server.server import run


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
