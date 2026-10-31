import json
import subprocess
import sys
from pathlib import Path

from snek.codegen import export_script
from snek.engine import Engine

ROOT = Path(__file__).resolve().parent.parent
PENGUINS = str(ROOT / "examples" / "data" / "penguins" / "penguins.csv")


def chart(cfg, data=None):
    source = {"id": "1", "type": "text_input", "config": {"data": data}} if data else {"id": "1", "type": "input", "config": {"path": PENGUINS}}
    ev = Engine().evaluate({"nodes": [source, {"id": "2", "type": "chart", "config": cfg}], "edges": [{"source": "1", "sourceHandle": "out", "target": "2", "targetHandle": "in"}]}, run_side_effects=False)
    return ev, ev.results["2"]


def spec_of(ev):
    return json.loads(ev.frames[("2", "out")].loc[0, "Vega-Lite"])


def test_chart_kinds_build_vega_lite():
    ev, res = chart({"kind": "bar", "x": "species", "y": "body_mass_g", "agg": "mean"})
    s = spec_of(ev)
    assert res.status == "ok" and s["mark"]["type"] == "bar" and s["encoding"]["y"]["aggregate"] == "mean" and s["encoding"]["x"]["sort"] == "-y"
    assert len(s["data"]["values"]) == 344 and s["$schema"].endswith("v6.json")
    ev, _ = chart({"kind": "histogram", "x": "body_mass_g", "bins": 12})
    assert spec_of(ev)["encoding"]["x"]["bin"] == {"maxbins": 12}
    ev, _ = chart({"kind": "box", "x": "species", "y": "bill_length_mm"})
    assert spec_of(ev)["mark"]["type"] == "boxplot"
    ev, _ = chart({"kind": "line", "x": "year", "y": "body_mass_g", "agg": "mean", "facet": "island"})
    s = spec_of(ev)
    assert s["encoding"]["x"]["axis"] == {"format": "d"} and s["encoding"]["facet"]["field"] == "island" and s["width"] == 220
    ev, _ = chart({"kind": "scatter", "x": "flipper_length_mm", "y": "body_mass_g", "max_rows": 50})
    assert len(spec_of(ev)["data"]["values"]) == 50 and ev.frames[("2", "out")].loc[0, "Rows in data"] == 344
    _, res = chart({"kind": "scatter", "x": "species", "y": "island"})
    assert res.status == "error" and "numeric" in res.error


def test_html_output_and_export_match(tmp_path):
    out = tmp_path / "chart"
    wf = {
        "nodes": [
            {"id": "1", "type": "text_input", "config": {"data": "team,wins\nNebraska,7\nIowa </script>,8"}},
            {"id": "2", "type": "chart", "config": {"kind": "bar", "x": "team", "y": "wins", "title": "Wins"}},
            {"id": "3", "type": "output", "config": {"path": str(out), "format": "html"}},
        ],
        "edges": [{"source": "1", "sourceHandle": "out", "target": "2", "targetHandle": "in"}, {"source": "2", "sourceHandle": "out", "target": "3", "targetHandle": "in"}],
    }
    ev = Engine().evaluate(wf, run_side_effects=True)
    page = (tmp_path / "chart.html").read_text(encoding="utf-8")
    assert "vegaEmbed('#chart0'" in page and "vega-lite@6.5.0/build/vega-lite.min.js" in page and "</script>,8" not in page
    assert page.count('integrity="sha384-') == 3 and page.count('crossorigin="anonymous"') == 3
    assert '"source": false, "compiled": false, "editor": false' in page
    script = tmp_path / "flow.py"
    script.write_text(export_script(ev), encoding="utf-8")
    (tmp_path / "chart.html").unlink()
    subprocess.run([sys.executable, str(script)], check=True, cwd=tmp_path)
    assert (tmp_path / "chart.html").read_text(encoding="utf-8") == page
