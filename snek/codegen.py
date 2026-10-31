import inspect
import pprint
import re

from snek.runtime import EXTENSIONS, FORMATS, HELPERS


def export_script(ev, name="workflow"):
    blocks = []
    for nid in ev.graph.order:
        node = ev.graph.nodes[nid]
        res = ev.results.get(nid)
        label = node.get("label") or node.get("type")
        if res is None:
            continue
        if res.code:
            blocks.append(res.code)
        elif res.status != "ok":
            blocks.append(f"raise RuntimeError({f'Tool {nid} ({label}) is not ready: {res.error}'!r})")
    body = "\n\n".join(b for b in blocks if b.strip())
    return prelude(body, name) + body + "\n"


def prelude(body, name):
    used = [h for h in HELPERS if re.search(rf"\b{h}\(", body)]
    imports = []
    if "read_any" in used:
        imports.append("import glob")
    if "read_any" in used or "write_any" in used:
        imports.append("import json")
    if "io.StringIO" in body:
        imports.append("import io")
    if "read_any" in used or "write_any" in used:
        imports.append("import os")
    imports = sorted(set(imports))
    parts = ['"""' + f"Exported from Snek workflow: {name}" + '"""', ""]
    parts += imports + ([""] if imports else [])
    parts += ["import numpy as np", "import pandas as pd", ""]
    if "read_any" in used or "write_any" in used:
        parts += ["FORMATS = " + pprint.pformat(FORMATS, sort_dicts=False)]
    if "write_any" in used:
        parts += ["", "EXTENSIONS = " + pprint.pformat(EXTENSIONS, sort_dicts=False)]
    seen = set()
    for h in used:
        for fn in HELPERS[h]:
            if fn.__name__ not in seen:
                seen.add(fn.__name__)
                parts += ["", "", inspect.getsource(fn).rstrip()]
    return "\n".join(parts).rstrip() + "\n\n\n"
