import argparse
import threading
import webbrowser

import uvicorn


def main():
    parser = argparse.ArgumentParser(prog="snek")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not args.no_browser:
        threading.Timer(1.2, webbrowser.open, [f"http://{args.host}:{args.port}"]).start()
    uvicorn.run("snek.server:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
