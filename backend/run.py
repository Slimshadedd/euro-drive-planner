"""Start the Euro Drive Planner server: python run.py [--port 8000]"""
import asyncio
import os
import sys

import uvicorn

if sys.platform == "win32":
    # Playwright launches the browser as a subprocess, which needs the Proactor event loop.
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.getcwd())
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8000
    config = uvicorn.Config("app.main:app", host="127.0.0.1", port=port, loop="none")
    asyncio.run(uvicorn.Server(config).serve())
