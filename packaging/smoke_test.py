import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PORT = 8797


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main(executable):
    home = tempfile.mkdtemp(prefix="snek-smoke-")
    env = dict(os.environ, SNEK_HOME=home)
    proc = subprocess.Popen([executable, "--no-browser", "--port", str(PORT)], env=env)
    try:
        for _ in range(120):
            try:
                call("/api/tools")
                break
            except OSError:
                time.sleep(1)
        else:
            raise SystemExit("Snek did not start")
        tools = call("/api/tools")["tools"]
        project = call("/api/project")
        print("tools:", len(tools), "project:", project["name"], project["path"])
        if len(tools) < int(os.environ.get("SNEK_MIN_TOOLS", "96")):
            raise SystemExit(f"Only {len(tools)} tools are bundled")
        names = [w["name"] for w in call("/api/workflows")["workflows"]]
        print("workflows:", names)
        for name in ["Penguins - body mass by species", "Flights - fleets from nested JSON", "Flights - Q1 delays by airline", "Flights - daily delay trend", "Penguins - predict body mass", "Penguins - classify species", "Flights - forecast daily departures", "Demo - league ratings (made-up teams)", "Penguins - model bake-off", "Flights - forecast accuracy check", "Sports - football play-by-play kit (made-up league)", "Sports - season projection (made-up league)", "Sports - basketball four factors (made-up league)", "Sports - baseball batting and pitching (made-up players)", "Sports - volleyball box and side-out (made-up matches)", "Penguins - charts"]:
            wf = json.loads((Path(project["path"]) / "workflows" / f"{name}.snek").read_text(encoding="utf-8"))
            results = call("/api/run", {"workflow": wf})["results"]
            bad = {k: v["error"] for k, v in results.items() if v["status"] != "ok"}
            print(name, "->", "ok" if not bad else bad)
            if bad:
                raise SystemExit(1)
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=10) as r:
            page = r.read().decode()
        assert "<title>Snek</title>" in page, "UI not served"
        print("ui: ok")
        call("/api/shutdown", {})
        proc.wait(timeout=15)
        print("shutdown: ok")
    finally:
        if proc.poll() is None:
            proc.kill()


if __name__ == "__main__":
    main(sys.argv[1])
