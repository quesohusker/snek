import hashlib
import json
import threading
import time
import traceback
import warnings
from collections import OrderedDict
from dataclasses import asdict, dataclass, field

import pandas as pd

from snek.runtime import NAMESPACE, output_path
from snek.tools import TOOLS, Ctx, ToolError, output_var


@dataclass
class NodeResult:
    status: str = "ok"
    error: str = ""
    message: str = ""
    warnings: list = field(default_factory=list)
    code: str = ""
    elapsed_ms: float = 0.0
    cached: bool = False
    executed: bool = False
    inputs: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)


def describe(df):
    return {"rows": int(len(df)), "columns": [{"name": str(c), "dtype": str(t)} for c, t in df.dtypes.items()]}


def merged_columns(frames):
    seen = {}
    for df in frames:
        for c, t in df.dtypes.items():
            seen.setdefault(str(c), str(t))
    return [{"name": k, "dtype": v} for k, v in seen.items()]


class Graph:
    def __init__(self, workflow):
        self.nodes = {str(n["id"]): n for n in workflow.get("nodes", [])}
        self.inbound = {nid: {} for nid in self.nodes}
        for e in workflow.get("edges", []):
            src, tgt = str(e.get("source")), str(e.get("target"))
            if src in self.nodes and tgt in self.nodes:
                self.inbound[tgt].setdefault(e.get("targetHandle") or "in", []).append((src, e.get("sourceHandle") or "out"))
        self.order, self.cyclic = self.topo()

    def parents(self, nid):
        return {src for links in self.inbound[nid].values() for src, _ in links}

    def topo(self):
        pending = {nid: set(self.parents(nid)) for nid in self.nodes}
        order = []
        ready = sorted((n for n, p in pending.items() if not p), key=sort_key)
        while ready:
            nid = ready.pop(0)
            order.append(nid)
            for child, parents in pending.items():
                if nid in parents:
                    parents.discard(nid)
                    if not parents and child not in order and child not in ready:
                        ready.append(child)
                        ready.sort(key=sort_key)
        cyclic = set(self.nodes) - set(order)
        return order + sorted(cyclic, key=sort_key), cyclic

    def ancestors(self, nid):
        found = set()
        stack = list(self.parents(nid))
        while stack:
            cur = stack.pop()
            if cur not in found:
                found.add(cur)
                stack.extend(self.parents(cur))
        return found


def sort_key(nid):
    return (0, int(nid), "") if nid.isdigit() else (1, 0, nid)


@dataclass
class Evaluation:
    graph: Graph
    results: dict
    frames: dict
    input_frames: dict
    elapsed_ms: float = 0.0

    def to_json(self):
        return {"results": {k: asdict(v) for k, v in self.results.items()}, "elapsed_ms": self.elapsed_ms}


class Engine:
    def __init__(self, max_bytes=3 * 1024**3):
        self.cache = OrderedDict()
        self.sizes = {}
        self.max_bytes = max_bytes
        self.lock = threading.RLock()

    def evaluate(self, workflow, targets=None, include_targets=True, run_side_effects=False, dry=False):
        with self.lock:
            start = time.perf_counter()
            graph = Graph(workflow)
            if targets is None:
                needed = set(graph.order)
            else:
                needed = set()
                for t in targets:
                    if t in graph.nodes:
                        needed |= graph.ancestors(t)
                        if include_targets:
                            needed.add(t)
            ev = Evaluation(graph, {}, {}, {})
            fingerprints = {}
            for nid in graph.order:
                if nid in needed:
                    execute = not (dry and targets and nid in targets)
                    ev.results[nid] = self.run_node(graph, nid, ev, fingerprints, run_side_effects, execute)
            ev.elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            return ev

    def inputs_for(self, graph, nid, tool, ev, fingerprints):
        names, frames, schema, fps = {}, {}, {}, []
        for port in tool.inputs:
            links = graph.inbound[nid].get(port.name, [])
            if not port.multi:
                links = links[-1:]
            if not links:
                name = port.label or ("" if port.name == "in" else port.name)
                raise ToolError(f"Connect the {name + ' ' if name else ''}input")
            port_names, port_frames = [], []
            for src, sport in links:
                upstream = ev.results.get(src)
                if upstream is None or upstream.status != "ok":
                    return None
                df = ev.frames.get((src, sport))
                if df is None:
                    raise ToolError(f"Tool {src} has no '{sport}' output")
                src_tool = TOOLS[graph.nodes[src]["type"]]
                port_names.append(output_var(src_tool.type, src, sport, src_tool.outputs))
                port_frames.append(df)
                fps.append(f"{fingerprints[src]}:{sport}")
            names[port.name] = port_names
            frames[port.name] = port_frames
            schema[port.name] = merged_columns(port_frames)
        return names, frames, schema, fps

    def run_node(self, graph, nid, ev, fingerprints, run_side_effects, execute=True):
        node = graph.nodes[nid]
        tool = TOOLS.get(node.get("type"))
        res = NodeResult()
        if tool is None:
            return NodeResult(status="error", error=f"Unknown tool type {node.get('type')!r}")
        if nid in graph.cyclic:
            return NodeResult(status="error", error="This tool is part of a loop")
        cfg = tool.config(node.get("config"))
        try:
            gathered = self.inputs_for(graph, nid, tool, ev, fingerprints)
            if gathered is None:
                return NodeResult(status="skipped", error="An upstream tool failed")
            names, frames, schema, input_fps = gathered
            ev.input_frames[nid] = frames
            res.inputs = {p: {"rows": sum(len(f) for f in frames[p]), "columns": schema[p], "count": len(frames[p])} for p in frames}
            res.code = tool.code(cfg, Ctx(nid, tool, names, schema))
        except ToolError as e:
            res.status, res.error = "error", str(e)
            return res
        stamp = tool.stamp(cfg, frames)
        if tool.volatile:
            stamp += f"|{time.time_ns()}"
        fp = hashlib.sha256(json.dumps([tool.type, res.code, input_fps, stamp]).encode()).hexdigest()
        fingerprints[nid] = fp
        if not execute:
            return res
        if tool.side_effect and not run_side_effects:
            res.message = "Writes when you run the workflow"
            return res
        outputs = None if tool.side_effect or tool.volatile else self.cache_get(fp)
        if outputs is not None:
            res.cached = True
        else:
            started = time.perf_counter()
            try:
                outputs, res.warnings = self.execute(nid, tool, res.code, names, frames)
            except Exception as e:
                res.status, res.error = "error", explain(e, res.code, nid)
                return res
            res.elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            res.executed = True
            if not tool.side_effect and not tool.volatile:
                self.cache_put(fp, outputs)
        for port, df in outputs.items():
            ev.frames[(nid, port)] = df
        res.outputs = {p: describe(df) for p, df in outputs.items()}
        res.message = self.message(tool, cfg, res)
        return res

    def execute(self, nid, tool, code, names, frames):
        ns = dict(NAMESPACE)
        for port, port_names in names.items():
            for name, df in zip(port_names, frames[port]):
                ns[name] = df.copy(deep=False)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            exec(compile(code, f"<tool {nid}>", "exec"), ns)
        outputs = {}
        for port in tool.outputs:
            var = output_var(tool.type, nid, port.name, tool.outputs)
            value = ns.get(var)
            if isinstance(value, pd.Series):
                value = value.to_frame()
            if not isinstance(value, pd.DataFrame):
                raise TypeError(f"Output '{port.name}' must be a DataFrame, got {type(value).__name__}")
            outputs[port.name] = value
        notes = sorted({f"{w.category.__name__}: {w.message}" for w in caught})
        return outputs, notes

    def message(self, tool, cfg, res):
        if tool.type == "output":
            return f"Wrote {res.inputs['in']['rows']:,} rows to {output_path(cfg['path'], cfg['format'])}"
        if not tool.outputs:
            return f"{res.inputs.get('in', {}).get('rows', 0):,} rows"
        return ", ".join(f"{p}: {o['rows']:,}" if len(res.outputs) > 1 else f"{o['rows']:,} rows" for p, o in res.outputs.items())

    def cache_get(self, fp):
        if fp in self.cache:
            self.cache.move_to_end(fp)
            return self.cache[fp]
        return None

    def cache_put(self, fp, outputs):
        size = sum(int(df.memory_usage(index=False, deep=False).sum()) for df in outputs.values())
        self.cache[fp] = outputs
        self.sizes[fp] = size
        while sum(self.sizes.values()) > self.max_bytes and len(self.cache) > 1:
            old, _ = self.cache.popitem(last=False)
            self.sizes.pop(old, None)

    def clear(self):
        with self.lock:
            self.cache.clear()
            self.sizes.clear()


def explain(exc, code, nid):
    msg = f"{type(exc).__name__}: {exc}"
    tb = traceback.extract_tb(exc.__traceback__)
    lines = code.splitlines()
    for frame in reversed(tb):
        if frame.filename == f"<tool {nid}>" and frame.lineno and frame.lineno <= len(lines):
            return f"{msg}\n  at: {lines[frame.lineno - 1].strip()}"
    return msg
