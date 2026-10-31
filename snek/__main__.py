import argparse
import json
import os
import socket
import sys
import threading
import urllib.request
import webbrowser

import uvicorn

from snek.paths import snek_home


def running_snek(host, port):
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/project", timeout=1) as r:
            return "path" in json.loads(r.read())
    except (OSError, ValueError):
        return False


def free_port(host, preferred):
    with socket.socket() as s:
        if os.name != "nt":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, preferred))
            return preferred
        except OSError:
            s.bind((host, 0))
            return s.getsockname()[1]


def ensure_streams():
    if sys.stdout is not None and sys.stderr is not None:
        return
    log = snek_home() / "snek.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    stream = open(log, "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stdout or stream
    sys.stderr = sys.stderr or stream


def main():
    parser = argparse.ArgumentParser(prog="snek")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    ensure_streams()
    if running_snek(args.host, args.port):
        url = f"http://{args.host}:{args.port}"
        print(f"Snek is already running at {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return
    port = free_port(args.host, args.port)
    url = f"http://{args.host}:{port}"
    from snek.server import app

    if not args.no_browser:
        threading.Timer(1.2, webbrowser.open, [url]).start()
    print(f"Snek is running at {url}")
    print("Keep this window open while you use Snek. Close it, or choose File > Quit Snek, to stop.")
    uvicorn.run(app, host=args.host, port=port, log_level="warning", loop="asyncio", http="h11", ws="none", log_config=None)


if __name__ == "__main__":
    main()
