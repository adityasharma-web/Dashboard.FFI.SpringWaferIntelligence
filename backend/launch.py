"""Launch Spring Wafer Intelligence (API + built frontend) in the default browser."""

from __future__ import annotations

import os
import socket
import threading
import webbrowser

import uvicorn

from app import app


def choose_port(preferred: int) -> int:
    """Return the preferred local port, or the next available port."""
    for port in range(preferred, preferred + 25):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No available local port was found in the scanned range.")


def main() -> None:
    preferred = int(os.environ.get("SPRING_WAFER_PORT", "8090"))
    port = choose_port(preferred)
    url = f"http://127.0.0.1:{port}"
    print(f"\nSpring Wafer Intelligence: {url}")
    print("Press Ctrl+C in this window to stop the application.\n")
    threading.Timer(1.2, lambda: webbrowser.open(url, new=2)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
