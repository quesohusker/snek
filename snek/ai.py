import json
import os
from datetime import date
from pathlib import Path

import anthropic
import pandas as pd

from snek.connect import api_key, load_keys
from snek.settings import AI_MODELS as MODELS
from snek.settings import DEFAULT_AI_MODEL as DEFAULT_MODEL
from snek.engine import Engine
from snek.tools import CATEGORY_ORDER, TOOLS

REPAIR_ROUNDS = 2
MAX_FILES = 60
DATA_SUFFIXES = (".csv", ".tsv", ".txt", ".csv.gz", ".xlsx", ".xls", ".json", ".jsonl", ".ndjson", ".parquet")
SKIP_DIRS = {"output", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "workflows", "frontend", "packaging", "snek", "tests", "scripts"}

RULES = """You build data workflows for Snek, a desktop app where tools on a canvas pass pandas DataFrames to each other. The user describes what they want; you return the workflow as JSON that matches the response schema.

How to write the workflow:
- nodes: each has an id (short string such as "1"), a type (a tool type from the catalog), a short label (or ""), and config_json: a JSON object, written as a string, holding that tool's settings. Use only the field keys the catalog lists for that tool. Leave a key out to use its default.
- edges: each connects an output port of one node (source, source_port) to an input port of another (target, target_port). Port names come from the catalog. A tool with one output uses "out"; a tool with one input uses "in". An input port marked multi accepts several edges.
- Field values by kind: text, textarea, code, python and file take a string; number takes a number; bool takes true or false; select takes one of the listed option values; multi_select takes a list of option values; column takes one column name from the tool's input; columns takes a list of column names; list takes a list of objects with the listed item fields; select_fields takes a list of objects like {"name": "col", "keep": true, "rename": "", "dtype": ""}.
- A field with show_if only matters when its condition holds.
- Filter conditions and Formula expressions are pandas expressions with each column written as [Column Name]. pd, np and iif(condition, then, else) are available.
- Read data only from the files listed under "Files in this project", using their paths exactly as given, or from a catalog tool that downloads data when the user asks for that source. Never invent a file path. Use the column names given for each file; for columns that a tool creates, use the names its description gives.
- Keep the workflow as short as the task allows. Add Output Data only when the user asks to save results. End each branch with the tool whose result the user wants to see.
- summary: two or three plain sentences for the user: what the workflow does, and anything they must check or supply (an API key, an assumption about a column, a file they need to add).

The tool catalog follows. Each line is one tool as JSON."""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string", "enum": sorted(TOOLS)},
                    "label": {"type": "string"},
                    "config_json": {"type": "string"},
                },
                "required": ["id", "type", "label", "config_json"],
                "additionalProperties": False,
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"source": {"type": "string"}, "source_port": {"type": "string"}, "target": {"type": "string"}, "target_port": {"type": "string"}},
                "required": ["source", "source_port", "target", "target_port"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "nodes", "edges"],
    "additionalProperties": False,
}


class AIError(Exception):
    pass


def field_entry(f):
    entry = {"key": f["key"], "kind": f["kind"], "label": f["label"]}
    if f.get("default") not in (None, "", []):
        entry["default"] = f["default"]
    if f.get("options"):
        entry["options"] = [o["value"] for o in f["options"]]
    if f.get("dtypes"):
        entry["dtypes"] = [o["value"] for o in f["dtypes"]]
    if f.get("show_if"):
        entry["show_if"] = f["show_if"]
    if f.get("port"):
        entry["columns_from_port"] = f["port"]
    if f.get("fields"):
        entry["item_fields"] = [field_entry(sub) for sub in f["fields"]]
    if f.get("help"):
        entry["help"] = f["help"]
    return entry


def tool_catalog():
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    lines = []
    for tool in sorted(TOOLS.values(), key=lambda t: (order.get(t.category, 99), t.group, t.label)):
        entry = {
            "type": tool.type,
            "label": tool.label,
            "category": tool.category + (f" / {tool.group}" if tool.group else ""),
            "does": tool.description,
            "needs": tool.needs,
            "inputs": [{"port": p.name, **({"multi": True} if p.multi else {})} for p in tool.inputs],
            "outputs": [p.name for p in tool.outputs],
            "fields": [field_entry(f) for f in tool.fields],
        }
        lines.append(json.dumps(entry, separators=(",", ":"), default=str))
    return "\n".join(lines)


def system_prompt():
    return RULES + "\n\n" + tool_catalog()


def read_columns(path):
    name = path.name.lower()
    if name.endswith((".csv", ".txt", ".csv.gz")):
        df = pd.read_csv(path, nrows=200)
    elif name.endswith(".tsv"):
        df = pd.read_csv(path, sep="\t", nrows=200)
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(path, nrows=200)
    elif name.endswith(".parquet"):
        import pyarrow.parquet as pq

        return [f"{f.name}:{f.type}" for f in pq.read_schema(path)]
    elif path.stat().st_size > 5_000_000:
        return []
    else:
        df = pd.read_json(path, lines=name.endswith((".jsonl", ".ndjson")))
    return [f"{c}:{t}" for c, t in df.dtypes.astype(str).items()]


def project_files(root):
    root = Path(root).resolve()
    found = []
    for folder, dirs, files in os.walk(root):
        depth = len(Path(folder).relative_to(root).parts)
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS and depth < 4)
        for name in sorted(files):
            if len(found) >= MAX_FILES:
                return found
            if name.lower().endswith(DATA_SUFFIXES):
                path = Path(folder) / name
                try:
                    cols = read_columns(path)
                except Exception:
                    cols = []
                found.append((path.relative_to(root).as_posix(), cols[:80]))
    return found


def context_message(request, root, project_name):
    today = date.today()
    season = today.year if today.month >= 8 else today.year - 1
    files = project_files(root)
    lines = [f"Project folder: {project_name}", "", "Files in this project (path | columns with types):"]
    lines += [f"- {path} | {', '.join(cols) if cols else 'columns unknown'}" for path, cols in files] or ["- none"]
    keys = sorted(load_keys())
    lines += ["", f"Saved API key names: {', '.join(keys) if keys else 'none'}. Today is {today.isoformat()}; the current college football season is {season}.", "", "What the user wants:", request.strip()]
    return "\n".join(lines)


def to_workflow(plan):
    problems, nodes, edges, ids, back = [], [], [], {}, {}
    for n in plan.get("nodes", []):
        tool = TOOLS.get(n.get("type"))
        if not tool:
            problems.append(f"Node {n.get('id')}: there is no tool type {n.get('type')!r}")
            continue
        try:
            raw = json.loads(n.get("config_json") or "{}")
        except ValueError:
            raw = None
        if not isinstance(raw, dict):
            problems.append(f"Node {n['id']}: config_json is not a JSON object")
            raw = {}
        unknown = sorted(set(raw) - {f["key"] for f in tool.fields})
        if unknown:
            problems.append(f"Node {n['id']} ({tool.label}) has no field {', '.join(unknown)}")
        nid = str(len(nodes) + 1)
        ids[n["id"]], back[nid] = nid, n["id"]
        nodes.append({"id": nid, "type": tool.type, "label": str(n.get("label") or "")[:60], "config": tool.config(raw)})
    types = {n["id"]: TOOLS[n["type"]] for n in nodes}
    for e in plan.get("edges", []):
        source, target = ids.get(e.get("source")), ids.get(e.get("target"))
        if not source or not target:
            problems.append(f"Edge {e.get('source')} -> {e.get('target')} points at a node that doesn't exist")
            continue
        outs = [p.name for p in types[source].outputs]
        ins = [p.name for p in types[target].inputs]
        sp = e.get("source_port") if e.get("source_port") in outs else (outs[0] if len(outs) == 1 else None)
        tp = e.get("target_port") if e.get("target_port") in ins else (ins[0] if len(ins) == 1 else None)
        if sp is None or tp is None:
            problems.append(f"Edge {e['source']} -> {e['target']}: ports must be one of {outs} and {ins}")
            continue
        edges.append({"id": f"e{source}.{sp}-{target}.{tp}", "source": source, "sourceHandle": sp, "target": target, "targetHandle": tp})
    layout(nodes, edges)
    return {"version": 1, "nodes": nodes, "edges": edges}, problems, back


def layout(nodes, edges):
    depth = {n["id"]: 0 for n in nodes}
    for _ in range(len(nodes)):
        for e in edges:
            depth[e["target"]] = max(depth[e["target"]], depth[e["source"]] + 1)
    rows = {}
    for n in nodes:
        d = depth[n["id"]]
        n["position"] = {"x": 60 + d * 190, "y": 60 + rows.get(d, 0) * 130}
        rows[d] = rows.get(d, 0) + 1


def check(workflow, engine):
    ev = engine.evaluate(workflow, run_side_effects=False)
    errors = {nid: res.error.strip().splitlines()[0] for nid, res in ev.results.items() if res.status == "error"}
    columns = {}
    for (nid, port), df in ev.frames.items():
        columns[(nid, port)] = [f"{c}:{t}" for c, t in list(df.dtypes.astype(str).items())[:60]]
    return errors, columns


def repair_message(workflow, problems, errors, columns, back):
    label = {n["id"]: TOOLS[n["type"]].label for n in workflow["nodes"]}
    lines = ["I built and ran that workflow."]
    if problems:
        lines += ["", "Problems in the JSON:"] + [f"- {p}" for p in problems]
    if errors:
        lines += ["", "These tools failed:"] + [f"- node {back[nid]} ({label[nid]}): {msg}" for nid, msg in errors.items()]
    lines += ["", "Columns each tool produced:"] + [f"- node {back[nid]} ({label[nid]}) port {port}: {', '.join(cols)}" for (nid, port), cols in columns.items()]
    lines += ["", "Fix the problems and return the complete corrected workflow."]
    return "\n".join(lines)


def make_client():
    key = api_key("anthropic")
    try:
        return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    except anthropic.AnthropicError:
        raise AIError("Add your Anthropic API key in Edit ▸ Settings ▸ AI. Get one at console.anthropic.com.") from None


def ask(client, model, messages):
    request = {
        "model": model,
        "max_tokens": 64000,
        "system": [{"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}],
        "messages": messages,
        "output_config": {"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
    }
    if model != "claude-haiku-5-5":
        request.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    try:
        with client.beta.messages.stream(**request) as stream:
            response = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise AIError("Anthropic rejected the API key. Check it in Edit ▸ Settings ▸ AI.") from None
    except anthropic.PermissionDeniedError as e:
        raise AIError(f"The API key can't use {model}: {e.message}") from None
    except anthropic.RateLimitError:
        raise AIError("Anthropic's rate limit was reached. Wait a minute and try again.") from None
    except anthropic.APIStatusError as e:
        raise AIError(f"Anthropic returned an error ({e.status_code}): {e.message}") from None
    except anthropic.APIConnectionError:
        raise AIError("Could not reach Anthropic. Check your internet connection.") from None
    except anthropic.AnthropicError as e:
        raise AIError(str(e)) from None
    if response.stop_reason == "refusal":
        raise AIError("Claude declined this request. Try describing the workflow differently.")
    if response.stop_reason == "max_tokens":
        raise AIError("The answer ran too long. Describe a smaller workflow, or split it in two.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return response, json.loads(text)
    except ValueError:
        raise AIError("Claude's answer was not a valid workflow. Try again.") from None


def create_workflow(request, root, project_name, model=DEFAULT_MODEL, engine=None, client=None):
    if not request.strip():
        raise AIError("Describe the workflow you want")
    if model not in MODELS:
        raise AIError(f"Unknown model {model}")
    engine = engine or Engine()
    client = client or make_client()
    messages = [{"role": "user", "content": context_message(request, root, project_name)}]
    usage = {"input": 0, "output": 0, "cache_read": 0}
    for attempt in range(REPAIR_ROUNDS + 1):
        response, plan = ask(client, model, messages)
        for key, attr in (("input", "input_tokens"), ("output", "output_tokens"), ("cache_read", "cache_read_input_tokens")):
            usage[key] += getattr(response.usage, attr, 0) or 0
        workflow, problems, back = to_workflow(plan)
        errors, columns = check(workflow, engine) if workflow["nodes"] else ({}, {})
        if not (problems or errors) or attempt == REPAIR_ROUNDS:
            break
        messages += [{"role": "assistant", "content": response.content}, {"role": "user", "content": repair_message(workflow, problems, errors, columns, back)}]
    return {"workflow": workflow, "summary": plan.get("summary", ""), "errors": errors, "problems": problems, "rounds": attempt + 1, "model": response.model, "usage": usage}
