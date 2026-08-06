"""Run a single intraday signal tick for RELIANCE."""

import asyncio

from quantmind.agent.tools import run_intraday_signal


async def main():
    result = await run_intraday_signal("RELIANCE", fast=5, slow=10)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
