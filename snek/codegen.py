import inspect
import json
import os
import pprint
import re

from snek.distributions import FAMILIES
from snek.geo import CENSUS_BATCH, EARTH_RADIUS_KM, US_BASEMAP, WORLD_BASEMAP
from snek.runtime import EXTENSIONS, FORMATS, HELPERS, NAMESPACE, output_path
from snek.tools import TOOLS


def export_steps(ev, only=None):
    steps = []
    for nid in ev.graph.order:
        if only is not None and nid not in only:
            continue
        node = ev.graph.nodes[nid]
        res = ev.results.get(nid)
        tool = TOOLS.get(node.get("type"))
        if res is None or (tool is not None and not tool.exportable):
            continue
        label = node.get("label") or (tool.label if tool else node.get("type"))
        if res.code:
            code = res.code
        elif res.status != "ok":
            code = f"raise RuntimeError({f'Tool {nid} ({label}) is not ready: {res.error}'!r})"
        else:
            continue
        if code.strip():
            steps.append({"id": nid, "type": node.get("type"), "label": label, "description": tool.description if tool else "", "code": code})
    return steps


def script_text(steps, name="workflow"):
    body = "\n\n".join(step["code"] for step in steps)
    return prelude(body, name) + body + "\n"


def notebook_text(steps, name="workflow"):
    body = "\n\n".join(step["code"] for step in steps)
    cells = [
        markdown_cell(f"# {name}\n\nExported from Snek. Run the cells in order. Each section below is one tool from the workflow."),
        markdown_cell("## Setup\n\nImports and the helper functions the steps use."),
        code_cell(prelude(body, name).strip()),
    ]
    for i, step in enumerate(steps, start=1):
        title = f"## Step {i}: {step['label']}"
        cells.append(markdown_cell(f"{title}\n\n{step['description']}" if step["description"] else title))
        cells.append(code_cell(step["code"]))
    for n, cell in enumerate(cells, start=1):
        cell["id"] = f"snek-{n:03d}"
    notebook = {
        "cells": cells,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(notebook, indent=1, ensure_ascii=False) + "\n"


def markdown_cell(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code_cell(text):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": text.splitlines(keepends=True)}


def export_script(ev, name="workflow"):
    return script_text(export_steps(ev), name)


def export_notebook(ev, name="workflow"):
    return notebook_text(export_steps(ev), name)


def create_python(steps, path, fmt="py", title=""):
    target = output_path(path, fmt)
    name = title or os.path.splitext(os.path.basename(target))[0]
    text = notebook_text(steps, name) if fmt == "ipynb" else script_text(steps, name)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(text)
    return target


def prelude(body, name):
    constants = {"FORMATS": FORMATS, "EXTENSIONS": EXTENSIONS, "FAMILIES": FAMILIES, "EARTH_RADIUS_KM": EARTH_RADIUS_KM, "US_BASEMAP": US_BASEMAP, "WORLD_BASEMAP": WORLD_BASEMAP, "CENSUS_BATCH": CENSUS_BATCH}
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


NAMESPACE["create_python"] = create_python
