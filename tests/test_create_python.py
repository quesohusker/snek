import ast
import json
import subprocess
import sys

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from snek.codegen import export_notebook, export_script
from snek.engine import Engine
from snek.server import app
from tests.test_tools import GAMES, err, out, run, workflow

STEPS = [
    ("formula", {"formulas": [{"column": "margin", "expression": "[pts] - [opp_pts]", "dtype": ""}, {"column": "level", "expression": 'IF([margin] > 10, "big", "close")', "dtype": ""}]}),
    ("filter", {"column": "margin", "operator": ">", "value": "0"}),
    ("summarize", {"group_by": ["team"], "aggs": [{"column": "margin", "func": "mean", "name": "avg"}]}),
]


def build(tmp_path, fmt, title="", name="made"):
    result = tmp_path / "result.csv"
    nodes = [(1, "text_input", {"data": GAMES})]
    edges = []
    for i, (t, c) in enumerate(STEPS, start=2):
        nodes.append((i, t, c))
    nodes.append((5, "output", {"path": str(result)}))
    nodes.append((6, "create_python", {"path": str(tmp_path / name), "format": fmt, "title": title}))
    edges = [(1, "out", 2, "in"), (2, "out", 3, "in"), (3, "true", 4, "in"), (4, "out", 5, "in"), (4, "out", 6, "in")]
    return workflow(nodes, edges), result


def test_script_file_runs_and_matches_the_canvas(tmp_path):
    wf, result = build(tmp_path, "py", title="Margins")
    ev = run(wf)
    assert ev.results["6"].status == "ok", ev.results["6"].error
    assert ev.results["6"].message.endswith("made.py")
    script = tmp_path / "made.py"
    text = script.read_text()
    assert text.startswith('"""Exported from Snek workflow: Margins')
    assert "def IF(" in text and "write_any" not in text and "create_python" not in text
    ast.parse(text)
    proc = subprocess.run([sys.executable, "-I", str(script)], capture_output=True, text=True, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr


def test_script_returns_the_same_table_as_the_canvas(tmp_path):
    wf, _ = build(tmp_path, "py")
    ev = run(wf)
    script = tmp_path / "made.py"
    ns = {}
    exec(compile(script.read_text(), str(script), "exec"), ns)
    pd.testing.assert_frame_equal(ns["summarize_4"], out(ev, 4))


def test_notebook_has_one_section_per_tool(tmp_path):
    wf, _ = build(tmp_path, "ipynb", title="Margins")
    ev = run(wf)
    assert ev.results["6"].status == "ok", ev.results["6"].error
    nb = json.loads((tmp_path / "made.ipynb").read_text())
    assert nb["nbformat"] == 4 and nb["nbformat_minor"] == 5
    assert nb["metadata"]["kernelspec"]["name"] == "python3"
    cells = nb["cells"]
    assert [c["cell_type"] for c in cells] == ["markdown", "markdown", "code"] + ["markdown", "code"] * 4
    assert len({c["id"] for c in cells}) == len(cells)
    assert "".join(cells[0]["source"]).startswith("# Margins")
    heads = ["".join(c["source"]).splitlines()[0] for c in cells if c["cell_type"] == "markdown"][2:]
    assert [h.split(": ", 1)[1] for h in heads] == ["Type or Paste Data", "Calculate", "Keep Rows", "Group and Total"]
    for c in cells:
        if c["cell_type"] == "code":
            assert c["outputs"] == [] and c["execution_count"] is None
            ast.parse("".join(c["source"]))


def test_notebook_cells_run_in_order_and_match_the_canvas(tmp_path):
    wf, _ = build(tmp_path, "ipynb")
    ev = run(wf)
    nb = json.loads((tmp_path / "made.ipynb").read_text())
    ns = {}
    for c in nb["cells"]:
        if c["cell_type"] == "code":
            exec(compile("".join(c["source"]), "<cell>", "exec"), ns)
    pd.testing.assert_frame_equal(ns["summarize_4"], out(ev, 4))


def test_several_branches_and_a_label_in_the_notebook(tmp_path):
    nodes = [
        (1, "text_input", {"data": GAMES}),
        (2, "filter", {"column": "pts", "operator": ">", "value": "30"}),
        (3, "sort", {"keys": [{"column": "pts", "order": "desc"}]}),
        (4, "create_python", {"path": str(tmp_path / "both.ipynb"), "format": "ipynb"}),
    ]
    wf = workflow(nodes, [(1, "out", 2, "in"), (2, "true", 3, "in"), (2, "false", 4, "in"), (3, "out", 4, "in")])
    wf["nodes"][2]["label"] = "Biggest first"
    ev = run(wf)
    assert ev.results["4"].status == "ok", ev.results["4"].error
    nb = json.loads((tmp_path / "both.ipynb").read_text())
    titles = ["".join(c["source"]).splitlines()[0] for c in nb["cells"] if c["cell_type"] == "markdown"]
    assert titles[2:] == ["## Step 1: Type or Paste Data", "## Step 2: Keep Rows", "## Step 3: Biggest first"]


def test_only_upstream_tools_are_included(tmp_path):
    nodes = [
        (1, "text_input", {"data": GAMES}),
        (2, "filter", {"column": "pts", "operator": ">", "value": "30"}),
        (3, "sort", {"keys": [{"column": "pts", "order": "desc"}]}),
        (4, "create_python", {"path": str(tmp_path / "part.py"), "format": "py"}),
    ]
    run(workflow(nodes, [(1, "out", 2, "in"), (2, "true", 3, "in"), (2, "true", 4, "in")]))
    text = (tmp_path / "part.py").read_text()
    assert "filter_2" in text and "sort_3" not in text


def test_extension_comes_from_the_format(tmp_path):
    nodes = [(1, "text_input", {"data": GAMES}), (2, "filter", {"column": "pts", "operator": ">", "value": "30"}), (3, "create_python", {"path": str(tmp_path / "plain"), "format": "ipynb"})]
    ev = run(workflow(nodes, [(1, "out", 2, "in"), (2, "true", 3, "in")]))
    assert (tmp_path / "plain.ipynb").exists()
    assert ev.results["3"].message == f"Wrote {tmp_path / 'plain.ipynb'}"


def test_nothing_is_written_until_run(tmp_path):
    wf, _ = build(tmp_path, "py")
    Engine().evaluate(wf, run_side_effects=False)
    assert not (tmp_path / "made.py").exists()


def test_errors_are_plain(tmp_path):
    nodes = [(1, "text_input", {"data": GAMES}), (2, "create_python", {"path": "", "format": "py"})]
    assert "Pick an output file" in err(run(workflow(nodes, [(1, "out", 2, "in")])), 2)
    nodes = [(1, "text_input", {"data": GAMES}), (2, "create_python", {"path": str(tmp_path / "x"), "format": "py"})]
    assert err(run(workflow(nodes, [])), 2).startswith("Connect")


def test_export_leaves_the_tool_out(tmp_path):
    wf, _ = build(tmp_path, "py")
    ev = run(wf)
    assert "create_python" not in export_script(ev, "w")
    assert "create_python" not in export_notebook(ev, "w")


def test_failed_steps_become_raises_in_both_formats(tmp_path):
    nodes = [(1, "text_input", {"data": GAMES}), (2, "filter", {"column": "nope", "operator": "==", "value": "1"})]
    ev = run(workflow(nodes, [(1, "out", 2, "in")]))
    assert "is not ready" in export_script(ev, "w")
    assert "is not ready" in export_notebook(ev, "w")


def test_export_api_gives_script_or_notebook():
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    wf = workflow([(1, "text_input", {"data": GAMES}), (2, "filter", {"column": "pts", "operator": ">", "value": "30"})], [(1, "out", 2, "in")])
    script = client.post("/api/export", json={"workflow": wf, "name": "demo"}).json()["code"]
    assert script.startswith('"""Exported from Snek workflow: demo')
    nb = json.loads(client.post("/api/export", json={"workflow": wf, "name": "demo", "fmt": "ipynb"}).json()["code"])
    assert nb["cells"][0]["cell_type"] == "markdown" and "# demo" in "".join(nb["cells"][0]["source"])
