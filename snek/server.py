import json
import os
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from snek.codegen import export_script
from snek.engine import Engine
from snek.preview import preview
from snek.tools import CATEGORY_ORDER, TOOLS

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = Path(os.environ.get("SNEK_WORKFLOWS", ROOT / "workflows"))
DIST = ROOT / "frontend" / "dist"
NAME_RE = re.compile(r"^[\w\- .]{1,80}$")
EXAMPLES = ROOT / "examples" / "data"
PLACES = [
    ("Home", "~"),
    ("Examples", str(EXAMPLES)),
    ("Workflows", str(WORKFLOWS)),
    ("Output", str(ROOT / "output")),
] + [tuple(p.split("=", 1)) for p in os.environ.get("SNEK_PLACES", "").split(";") if "=" in p]

app = FastAPI(title="Snek")
engine = Engine()


@app.get("/api/tools")
def tools():
    specs = sorted((t.spec() for t in TOOLS.values()), key=lambda s: CATEGORY_ORDER.index(s["category"]))
    return {"tools": specs, "categories": CATEGORY_ORDER}


@app.post("/api/run")
def run(workflow: dict = Body(..., embed=True)):
    return engine.evaluate(workflow, run_side_effects=True).to_json()


@app.post("/api/summaries")
def summaries(workflow: dict = Body(..., embed=True)):
    out = {}
    for n in workflow.get("nodes", []):
        tool = TOOLS.get(n.get("type"))
        try:
            out[str(n["id"])] = tool.summary(tool.config(n.get("config"))) if tool else ""
        except Exception:
            out[str(n["id"])] = ""
    return {"summaries": out}


@app.post("/api/schema")
def schema(workflow: dict = Body(...), node: str = Body(...)):
    ev = engine.evaluate(workflow, targets=[node], dry=True)
    res = ev.results.get(node)
    if res is None:
        raise HTTPException(404, "No such tool")
    return {"result": asdict(res), "upstream": {k: v.status for k, v in ev.results.items()}}


@app.post("/api/preview")
def preview_node(
    workflow: dict = Body(...),
    node: str = Body(...),
    port: str | None = Body(None),
    offset: int = Body(0),
    limit: int = Body(100),
    profile: bool = Body(False),
):
    ev = engine.evaluate(workflow, targets=[node], include_targets=True, run_side_effects=False)
    res = ev.results.get(node)
    if res is None:
        raise HTTPException(404, "No such tool")
    payload = {"result": asdict(res), "upstream": {k: v.status for k, v in ev.results.items()}}
    df = None
    if res.status == "ok":
        tool = TOOLS[ev.graph.nodes[node]["type"]]
        if tool.outputs:
            port = port if port in res.outputs else tool.outputs[0].name
            df = ev.frames.get((node, port))
        else:
            frames = ev.input_frames.get(node, {}).get("in") or []
            df = frames[0] if frames else None
    payload["port"] = port
    payload["data"] = preview(df, offset, limit, profile) if df is not None else None
    return payload


@app.post("/api/export")
def export(workflow: dict = Body(...), name: str = Body("workflow")):
    ev = engine.evaluate(workflow, run_side_effects=False)
    return {"code": export_script(ev, name)}


@app.post("/api/cache/clear")
def clear_cache():
    engine.clear()
    return {"ok": True}


@app.get("/api/workflows")
def list_workflows():
    WORKFLOWS.mkdir(parents=True, exist_ok=True)
    items = []
    for p in sorted(WORKFLOWS.glob("*.flow.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        items.append({"name": p.name[: -len(".flow.json")], "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")})
    return {"workflows": items, "folder": str(WORKFLOWS)}


@app.get("/api/workflows/{name}")
def load_workflow(name: str):
    path = workflow_path(name)
    if not path.exists():
        raise HTTPException(404, f"No workflow named {name}")
    return json.loads(path.read_text())


@app.put("/api/workflows/{name}")
def save_workflow(name: str, workflow: dict = Body(...)):
    path = workflow_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    workflow["name"] = name
    path.write_text(json.dumps(workflow, indent=2))
    return {"ok": True, "path": str(path)}


def workflow_path(name):
    if not NAME_RE.match(name) or name.startswith("."):
        raise HTTPException(400, "Use letters, numbers, spaces, dots, dashes or underscores")
    return WORKFLOWS / f"{name}.flow.json"


@app.get("/api/fs")
def list_dir(path: str = ""):
    target = Path(os.path.expanduser(path)) if path else EXAMPLES
    if target.is_file():
        target = target.parent
    while not target.exists() and target != target.parent:
        target = target.parent
    entries = []
    try:
        children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        children = []
    for p in children:
        if p.name.startswith("."):
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        entries.append({"name": p.name, "path": str(p), "dir": p.is_dir(), "size": st.st_size, "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes")})
    places = [{"label": l, "path": os.path.expanduser(p)} for l, p in PLACES if Path(os.path.expanduser(p)).exists()]
    return {"path": str(target), "parent": str(target.parent), "entries": entries, "places": places}


@app.exception_handler(Exception)
def unhandled(request, exc):
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        candidate = DIST / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
