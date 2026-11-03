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
        export_flow = {
            "nodes": [
                {"id": "1", "type": "text_input", "config": {"data": "name,sales,day\n  Ann Lee ,120.456,2024-03-05\nbob,80,2024-12-31"}},
                {"id": "2", "type": "formula", "config": {"formulas": [{"column": "tidy", "expression": "PROPER(TRIM([name]))", "dtype": ""}, {"column": "level", "expression": 'IF([sales] > 100, "high", "low")', "dtype": ""}, {"column": "flag", "expression": "iif([sales] > 100, 1, 0)", "dtype": ""}, {"column": "p", "expression": "NORM.DIST([sales], 100, 20, TRUE)", "dtype": ""}, {"column": "tot", "expression": "SUMIF([name], [name], [sales])", "dtype": ""}, {"column": "pay", "expression": "PMT(0.05 / 12, 12, [sales])", "dtype": ""}]}},
            ],
            "edges": [{"source": "1", "sourceHandle": "out", "target": "2", "targetHandle": "in"}],
        }
        script = call("/api/export", {"workflow": export_flow, "name": "smoke"})["code"]
        assert "def PROPER" in script and "def IF" in script and "def iif" in script, "Export Python did not include the helper functions"
        assert "def NORM_DIST" in script and "def SUMIF" in script and "scipy" in script.split('"""')[1], "Export Python lost the statistics functions"
        ran = call("/api/run", {"workflow": export_flow})["results"]["2"]
        assert ran["status"] == "ok", ran["error"]
        notebook = json.loads(call("/api/export", {"workflow": export_flow, "name": "smoke", "fmt": "ipynb"})["code"])
        assert notebook["nbformat"] == 4 and len(notebook["cells"]) == 7, "Notebook export is wrong"
        print("export: ok")
        import shapefile

        shapes = Path(home) / "zones"
        with shapefile.Writer(str(shapes), shapeType=shapefile.POLYGON) as w:
            w.field("NAME", "C", size=20)
            w.poly([[[-98, 40], [-98, 43], [-94, 43], [-94, 40], [-98, 40]]])
            w.record("Zone A")
        maps_flow = {
            "nodes": [
                {"id": "1", "type": "read_map", "config": {"path": str(shapes) + ".shp"}},
                {"id": "2", "type": "text_input", "config": {"data": "store,lat,lon\nA,41.0,-96.0\nB,39.5,-95.0\n"}},
                {"id": "3", "type": "find_region", "config": {"lat": "lat", "lon": "lon"}},
                {"id": "4", "type": "text_input", "config": {"data": "city,lat,lon\nOmaha,41.2565,-95.9345\nKansas City,39.0997,-94.5786\n"}},
                {"id": "5", "type": "find_nearest", "config": {"lat": "lat", "lon": "lon", "place_lat": "lat", "place_lon": "lon", "count": 1, "columns": ["city"]}},
                {"id": "6", "type": "map_chart", "config": {"kind": "points", "lat": "lat", "lon": "lon", "color": "distance"}},
                {"id": "7", "type": "map_chart", "config": {"kind": "regions", "geometry": "geometry"}},
            ],
            "edges": [
                {"source": "2", "sourceHandle": "out", "target": "3", "targetHandle": "in"},
                {"source": "1", "sourceHandle": "out", "target": "3", "targetHandle": "regions"},
                {"source": "2", "sourceHandle": "out", "target": "5", "targetHandle": "in"},
                {"source": "4", "sourceHandle": "out", "target": "5", "targetHandle": "places"},
                {"source": "5", "sourceHandle": "out", "target": "6", "targetHandle": "in"},
                {"source": "1", "sourceHandle": "out", "target": "7", "targetHandle": "in"},
            ],
        }
        mapped = call("/api/run", {"workflow": maps_flow})["results"]
        bad = {k: v["error"] for k, v in mapped.items() if v["status"] != "ok"}
        assert not bad, f"Maps tools failed: {bad}"
        mapped_script = call("/api/export", {"workflow": maps_flow, "name": "maps"})["code"]
        assert "def find_region" in mapped_script and "def find_nearest" in mapped_script and "def map_chart" in mapped_script, "Export Python lost the map helpers"
        print("maps: ok")
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
