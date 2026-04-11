"""Async streaming — `barflow.aio.atrack` over an async iterable.

Demonstrates the asyncio wrapper: the progress bar ticks once per yielded
item, with an unknown total so you get a pulsing indeterminate bar.

Run from any cwd:
    python examples/async_stream.py
"""

import asyncio
import sys
from pathlib import Path

_REPO_SRC = Path(__file__).resolve().parent.parent / "src"
if _REPO_SRC.is_dir() and str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

import barflow
from barflow.aio import atrack


async def fake_stream(n, delay=0.02):
    for i in range(n):
        await asyncio.sleep(delay)
        yield i


async def known_total():
    # Total is known upfront — standard bar.
    async for _ in atrack(fake_stream(200), total=200, desc="known  "):
        pass


async def unknown_total():
    # No total — pulses via the spinner preset.
    async for _ in atrack(fake_stream(150), desc="stream ", total=0):
        pass


async def main():
    await known_total()
    await unknown_total()
    sys.stderr.write("\n\x1b[1;92mAsync streams drained.\x1b[0m\n")


if __name__ == "__main__":
    asyncio.run(main())
