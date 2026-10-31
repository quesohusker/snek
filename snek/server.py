import json
import os
import re
import subprocess
import sys
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers

from snek.codegen import export_script
from snek.engine import Engine
from snek.paths import DIST, snek_home
from snek.preview import preview
from snek.projects import Projects
from snek.runtime import output_path
from snek import ai, connect
from snek import settings as user_settings
from snek import updates
from snek.tools import CATEGORY_ORDER, TOOLS

NAME_RE = re.compile(r"^[\w\- .(),'&+#]{1,80}$")

engine = Engine()
projects = Projects()


@asynccontextmanager
async def lifespan(app):
    projects.load()
    yield


app = FastAPI(title="Snek", lifespan=lifespan)

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def host_name(value):
    value = (value or "").strip().lower()
    if value.startswith("["):
        return value.split("]", 1)[0] + "]"
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def local_request(headers, path):
    if host_name(headers.get("host")) not in ALLOWED_HOSTS:
        return False
    if not path.startswith("/api/"):
        return True
    origin = headers.get("origin")
    if origin and host_name(urlsplit(origin).netloc) not in ALLOWED_HOSTS:
        return False
    return headers.get("sec-fetch-site") != "cross-site"


class LocalOnly:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not local_request(Headers(scope=scope), scope["path"]):
            response = JSONResponse(status_code=403, content={"detail": "Snek answers only its own browser tab on this computer"})
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


app.add_middleware(LocalOnly)


@app.get("/api/project")
def project_info():
    return projects.info()


@app.post("/api/project/open")
def open_project(path: str = Body(..., embed=True)):
    try:
        projects.open(path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    engine.clear()
    return projects.info()


@app.post("/api/project/new")
def new_project(parent: str = Body(...), name: str = Body(...)):
    try:
        projects.create(parent, name)
    except (ValueError, OSError) as e:
        raise HTTPException(400, str(e))
    engine.clear()
    return projects.info()


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


COPY_LIMIT = 100_000


@app.post("/api/table")
def table_text(workflow: dict = Body(...), node: str = Body(...), port: str | None = Body(None)):
    ev = engine.evaluate(workflow, targets=[node], include_targets=True, run_side_effects=False)
    res = ev.results.get(node)
    if res is None or res.status != "ok":
        raise HTTPException(400, res.error if res else "No such tool")
    tool = TOOLS[ev.graph.nodes[node]["type"]]
    if tool.outputs:
        df = ev.frames.get((node, port if port in res.outputs else tool.outputs[0].name))
    else:
        frames = ev.input_frames.get(node, {}).get("in") or []
        df = frames[0] if frames else None
    if df is None:
        raise HTTPException(400, "Nothing to copy")
    return {"text": df.head(COPY_LIMIT).to_csv(sep="\t", index=False, lineterminator="\n"), "rows": int(min(len(df), COPY_LIMIT)), "total": int(len(df))}


@app.post("/api/chart")
def chart_specs(workflow: dict = Body(...), node: str = Body(...), port: str | None = Body(None)):
    ev = engine.evaluate(workflow, targets=[node], include_targets=True, run_side_effects=False)
    res = ev.results.get(node)
    if res is None or res.status != "ok":
        raise HTTPException(400, res.error if res else "No such tool")
    tool = TOOLS[ev.graph.nodes[node]["type"]]
    if tool.outputs:
        df = ev.frames.get((node, port if port in res.outputs else tool.outputs[0].name))
    else:
        frames = ev.input_frames.get(node, {}).get("in") or []
        df = frames[0] if frames else None
    if df is None or "Vega-Lite" not in df.columns:
        raise HTTPException(400, "No chart here")
    return {"specs": [json.loads(s) for s in df["Vega-Lite"].head(20)]}


@app.post("/api/export")
def export(workflow: dict = Body(...), name: str = Body("workflow")):
    ev = engine.evaluate(workflow, run_side_effects=False)
    return {"code": export_script(ev, name)}


@app.get("/api/update")
def update_check(force: bool = False):
    return updates.check(force=force)


@app.post("/api/update/settings")
def update_settings(enabled: bool = Body(..., embed=True)):
    return updates.set_enabled(enabled)


@app.post("/api/shutdown")
def shutdown():
    threading.Timer(0.3, os._exit, [0]).start()
    return {"ok": True}


@app.post("/api/cache/clear")
def clear_cache():
    engine.clear()
    return {"ok": True}


EXT = ".snek"
LEGACY_EXT = ".flow.json"


def workflow_name(path):
    name = path.name
    return name[: -len(EXT)] if name.endswith(EXT) else name[: -len(LEGACY_EXT)] if name.endswith(LEGACY_EXT) else path.stem


def read_workflow(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise HTTPException(400, f"Could not read {path}: {e}")
    if not isinstance(data, dict) or "nodes" not in data:
        raise HTTPException(400, f"{Path(path).name} is not a Snek workflow")
    for n in data["nodes"] if isinstance(data["nodes"], list) else []:
        tool = TOOLS.get(n.get("type")) if isinstance(n, dict) else None
        if tool and tool.needs_trust:
            n["trusted"] = False
    return data


def write_workflow(path, workflow, name):
    path.parent.mkdir(parents=True, exist_ok=True)
    nodes = [{k: v for k, v in n.items() if k != "trusted"} if isinstance(n, dict) else n for n in workflow.get("nodes", [])]
    data = {"format": "snek", **workflow, "nodes": nodes, "name": name}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@app.get("/api/workflows")
def list_workflows():
    folder = projects.workflows
    found = {}
    if folder.is_dir():
        for p in list(folder.glob(f"*{LEGACY_EXT}")) + list(folder.glob(f"*{EXT}")):
            found[workflow_name(p)] = p
    items = sorted(found.items(), key=lambda kv: kv[1].stat().st_mtime, reverse=True)
    return {"workflows": [{"name": n, "path": str(p), "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")} for n, p in items], "folder": str(folder)}


@app.get("/api/workflows/{name}")
def load_workflow(name: str):
    path = workflow_path(name)
    legacy = path.with_name(f"{name}{LEGACY_EXT}")
    if not path.exists() and legacy.exists():
        path = legacy
    if not path.exists():
        raise HTTPException(404, f"No workflow named {name}")
    return read_workflow(path)


@app.put("/api/workflows/{name}")
def save_workflow(name: str, workflow: dict = Body(...)):
    path = workflow_path(name)
    legacy = path.with_name(f"{name}{LEGACY_EXT}")
    write_workflow(path, workflow, name)
    if legacy.exists():
        legacy.unlink()
    return {"ok": True, "path": str(path)}


def workflow_path(name):
    if not NAME_RE.match(name) or name.startswith("."):
        raise HTTPException(400, "Use letters, numbers, spaces and . - _ ( ) , ' & + # in workflow names")
    return projects.workflows / f"{name}{EXT}"


@app.get("/api/settings")
def get_settings():
    return {**user_settings.load(), "autosave_folder": str(user_settings.autosave_folder())}


@app.put("/api/settings")
def put_settings(changes: dict = Body(...)):
    try:
        saved = user_settings.save(changes)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    return {**saved, "autosave_folder": str(user_settings.autosave_folder())}


@app.get("/api/ai")
def ai_info():
    keys = {k["name"]: k for k in connect.list_keys()}
    anthropic_key = keys.get("anthropic", {"saved": False, "hint": "", "from_env": False})
    return {"models": [{"value": k, "label": v} for k, v in user_settings.AI_MODELS.items()], "model": user_settings.load()["ai_model"], "key_saved": anthropic_key["saved"], "key_hint": anthropic_key["hint"], "key_from_env": bool(connect.api_key("anthropic")) and not anthropic_key["saved"]}


@app.post("/api/ai/context")
def ai_context(request: str = Body("", embed=True)):
    info = projects.info()
    return {"text": ai.context_message(request or "(your description)", projects.current, info["name"]), "catalog_chars": len(ai.tool_catalog())}


@app.post("/api/ai/workflow")
def ai_workflow(request: str = Body(...), model: str | None = Body(None)):
    info = projects.info()
    try:
        return ai.create_workflow(request, projects.current, info["name"], model or user_settings.load()["ai_model"], engine=engine)
    except ai.AIError as e:
        raise HTTPException(400, str(e))


@app.get("/api/connections")
def get_connections():
    return {"keys": connect.list_keys(), "file": str(connect.connections_path())}


@app.put("/api/connections")
def put_connection(name: str = Body(...), key: str = Body(...)):
    try:
        connect.set_key(name.strip().lower(), key)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return get_connections()


@app.delete("/api/connections/{name}")
def delete_connection(name: str):
    connect.delete_key(name)
    return get_connections()


@app.post("/api/autosave")
def autosave(workflow: dict = Body(...), name: str = Body(...)):
    safe = re.sub(r"[^\w\- .(),'&+#]", "_", name).strip(" .")[:80] or "Untitled"
    target = user_settings.autosave_folder() / f"{safe}{EXT}"
    write_workflow(target, workflow, safe)
    return {"ok": True, "path": str(target)}


@app.post("/api/file/open")
def open_file(path: str = Body(..., embed=True)):
    target = Path(os.path.expanduser(path)).resolve()
    if not target.is_file():
        raise HTTPException(404, f"No file at {target}")
    return {"workflow": read_workflow(target), "path": str(target), "name": workflow_name(target)}


@app.post("/api/file/save")
def save_file(path: str = Body(...), workflow: dict = Body(...)):
    target = Path(os.path.expanduser(path)).resolve()
    if target.name.endswith(LEGACY_EXT):
        target = target.with_name(target.name[: -len(LEGACY_EXT)] + EXT)
    elif target.suffix.lower() != EXT:
        target = target.with_name(target.name + EXT)
    write_workflow(target, workflow, workflow_name(target))
    return {"ok": True, "path": str(target), "name": workflow_name(target)}


DATA_SUFFIXES = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json", ".jsonl", ".ndjson", ".parquet", ".gz")


@app.post("/api/upload")
async def upload(request: Request, name: str):
    safe = Path(name).name
    if not safe or safe.startswith(".") or not safe.lower().endswith(DATA_SUFFIXES):
        raise HTTPException(400, "Drop a CSV, TSV, Excel, JSON, JSON Lines or Parquet file")
    body = await request.body()
    folder = snek_home() / "uploads" if projects.info()["is_examples"] else Path(projects.current) / "data"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / safe
    stem, suffix = safe.split(".", 1)[0], safe[len(safe.split(".", 1)[0]):]
    n = 2
    while target.exists() and target.read_bytes() != body:
        target = folder / f"{stem} ({n}){suffix}"
        n += 1
    if not target.exists():
        target.write_bytes(body)
    return {"path": str(target), "name": target.name}


@app.get("/api/fs")
def list_dir(path: str = ""):
    target = Path(os.path.expanduser(path)).resolve() if path else projects.current
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
    return {"path": str(target), "parent": str(target.parent), "entries": entries, "places": projects.places()}


@app.get("/api/resolve")
def resolve(path: str, fmt: str = "auto"):
    target = output_path(path, fmt)
    return {"path": target, "exists": os.path.isfile(target), "folder_exists": os.path.isdir(os.path.dirname(target))}


@app.post("/api/reveal")
def reveal(path: str = Body(..., embed=True)):
    target = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(target):
        raise HTTPException(404, f"Not found: {target}")
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", target], check=False)
    elif sys.platform.startswith("win"):
        subprocess.run(["explorer", f"/select,{target}"], check=False)
    else:
        subprocess.run(["xdg-open", os.path.dirname(target)], check=False)
    return {"ok": True, "path": target}


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
