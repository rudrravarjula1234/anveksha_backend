"""Windows-safe dev launcher for the backend.

psycopg v3 async refuses to run under Windows' default ProactorEventLoop.
Two things conspire to put us on a Proactor loop otherwise:
  1. uvicorn creates its event loop before importing app.main (where the
     Selector policy is set), and
  2. uvicorn's own asyncio loop setup can force a Proactor loop on Windows.

So we don't let uvicorn manage the loop at all: build a SelectorEventLoop
explicitly, then run the server inside it with loop="none" (uvicorn leaves
the running loop untouched).

Run:  .\.venv\Scripts\python.exe run_dev.py
"""

import asyncio
import selectors
import sys

import uvicorn

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)

    config = uvicorn.Config("app.main:app", host="0.0.0.0", port=8000, loop="none")
    server = uvicorn.Server(config)
    loop.run_until_complete(server.serve())
