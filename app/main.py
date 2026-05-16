"""
main.py — starts the Catering Multi-Agent API server.

Usage (Terminal 1):
    python -m app.main

Then open Terminal 2 and run:
    python -m app.chat
"""

import os

import uvicorn
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    from app.platform.config import platform_status_banner

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    print(f"\n[Catering Agent Runtime] Starting on http://{host}:{port}")
    print(f"  Platform: {platform_status_banner()}")
    print("  Docs: http://127.0.0.1:8000/docs")
    print("  In another terminal run:  python -m app.chat\n")
    uvicorn.run("app.runtime.api:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    main()
