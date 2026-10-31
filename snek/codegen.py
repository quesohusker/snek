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
    constants = {"FORMATS": FORMATS, "EXTENSIONS": EXTENSIONS}
    used = [h for h in HELPERS if re.search(rf"\b{h}\(", body)]
    imports = {"io"} if "io.StringIO" in body else set()
    needed_constants, functions, packages = [], [], []
    for h in used:
        fns, imps, consts, *extra = HELPERS[h]
        imports |= set(imps)
        needed_constants += [c for c in consts if c not in needed_constants]
        functions += [fn for fn in fns if fn not in functions]
        packages += [p for p in (extra[0] if extra else []) if p not in packages]
    doc = f"Exported from Snek workflow: {name}"
    if packages:
        doc += f"\n\nRequires pandas, numpy, {', '.join(packages)}."
    parts = ['"""' + doc + '"""', ""]
    parts += [f"import {m}" for m in sorted(imports)] + ([""] if imports else [])
    parts += ["import numpy as np", "import pandas as pd"]
    for c in needed_constants:
        parts += ["", f"{c} = " + pprint.pformat(constants[c], sort_dicts=False)]
    for fn in functions:
        parts += ["", "", inspect.getsource(fn).rstrip()]
    return "\n".join(parts).rstrip() + "\n\n\n"
