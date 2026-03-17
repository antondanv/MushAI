from __future__ import annotations

import asyncio

from mushai.channels.cli import run_cli

def main() -> None:
    asyncio.run(run_cli())

if __name__ == "__main__":
    main()