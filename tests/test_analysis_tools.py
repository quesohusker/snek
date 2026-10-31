import math
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from snek.codegen import export_script
from snek.engine import Engine

GAMES = "conf,result,pts,yds\nB1G,W,24,350\nB1G,L,17,280\nSEC,W,31,410\nSEC,W,28,390\nSEC,L,,300\nACC,W,21,330"
LINE = "x,y\n1,2.1\n2,3.9\n3,6.2\n4,7.8\n5,10.1\n6,12.2\n7,13.8\n8,16.1\n9,18.0\n10,20.2"


def chain(*steps, data=GAMES):
    nodes = [{"id": "1", "type": "text_input", "config": {"data": data}}]
    edges = []
    for i, (t, c) in enumerate(steps, start=2):
        nodes.append({"id": str(i), "type": t, "config": c})
        edges.append({"source": str(i - 1), "sourceHandle": "out", "target": str(i), "targetHandle": "in"})
    return {"nodes": nodes, "edges": edges}


def run(wf):
    return Engine().evaluate(wf, run_side_effects=True)


def out(ev, node, port="out"):
    res = ev.results[str(node)]
    assert res.status == "ok", res.error
    return ev.frames[(str(node), port)]


def err(ev, node):
    assert ev.results[str(node)].status == "error"
    return ev.results[str(node)].error


def t_pvalue_by_integration(t, dof):
    c = math.exp(math.lgamma((dof + 1) / 2) - math.lgamma(dof / 2)) / math.sqrt(dof * math.pi)
    x = np.linspace(abs(t), abs(t) + 400, 2_000_001)
    pdf = c * (1 + x**2 / dof) ** (-(dof + 1) / 2)
    return 2 * np.trapezoid(pdf, x)


def test_field_summary():
    df = out(run(chain(("field_summary", {}))), 2).set_index("Name")
    assert df.loc["pts", "Count"] == 5 and df.loc["pts", "Nulls"] == 1
    assert df.loc["pts", "Mean"] == pytest.approx(24.2)
    assert df.loc["conf", "Top"] == "SEC" and df.loc["conf", "Top Count"] == 3
    assert df.loc["conf", "Unique"] == 3


def test_frequency_table():
    df = out(run(chain(("frequency", {"columns": ["conf"]}))), 2)
    assert df["conf"].tolist()[0] == "SEC" and df["Count"].tolist()[0] == 3
    assert df["Percent"].sum() == pytest.approx(100)
    assert df["Cumulative %"].iloc[-1] == pytest.approx(100)
    by_value = out(run(chain(("frequency", {"columns": ["conf", "result"], "order": "value"}))), 2)
    assert by_value[["conf", "result"]].iloc[0].tolist() == ["ACC", "W"]
    nonull = out(run(chain(("frequency", {"columns": ["pts"], "nulls": False}))), 2)
    assert nonull["Count"].sum() == 5


def test_correlation():
    df = out(run(chain(("correlation", {}))), 2).set_index("Variable")
    assert df.columns.tolist() == ["pts", "yds"]
    assert df.loc["pts", "pts"] == pytest.approx(1)
    assert 0.9 < df.loc["pts", "yds"] <= 1
    assert "Not numeric" in err(run(chain(("correlation", {"columns": ["conf", "pts"]}))), 2)


def test_contingency_table():
    counts = out(run(chain(("contingency", {"rows": "conf", "columns": "result"}))), 2).set_index("conf")
    assert counts.loc["SEC", "W"] == 2 and counts.loc["Total", "Total"] == 6
    rows = out(run(chain(("contingency", {"rows": "conf", "columns": "result", "show": "index", "totals": False}))), 2).set_index("conf")
    assert (rows.sum(axis=1).round(6) == 100).all()


def test_linear_regression_matches_numpy():
    ev = run(chain(("linear_regression", {"target": "y", "predictors": ["x"]}), data=LINE))
    coef = out(ev, 2, "coef").set_index("Term")
    fit = out(ev, 2, "fit").set_index("Measure")["Value"]
    scored = out(ev, 2, "scored")
    data = pd.read_csv(pd.io.common.StringIO(LINE))
    slope, intercept = np.polyfit(data["x"], data["y"], 1)
    assert coef.loc["x", "Coefficient"] == pytest.approx(slope)
    assert coef.loc["(Intercept)", "Coefficient"] == pytest.approx(intercept)
    assert fit["R squared"] == pytest.approx(np.corrcoef(data["x"], data["y"])[0, 1] ** 2)
    assert fit["Rows used"] == 10
    assert scored["y_predicted"].iloc[0] == pytest.approx(intercept + slope)
    assert scored["y_residual"].iloc[0] == pytest.approx(2.1 - intercept - slope)
    for term in ("x", "(Intercept)"):
        t = coef.loc[term, "t"]
        assert coef.loc[term, "p-value"] == pytest.approx(t_pvalue_by_integration(t, 8), abs=1e-6)


def test_regression_p_value_matches_t_table():
    data = "x,y\n" + "\n".join(f"{i},{v}" for i, v in enumerate([3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0, 5.0, 3.0, 5.0, 8.0], start=1))
    coef = out(run(chain(("linear_regression", {"target": "y", "predictors": ["x"]}), data=data)), 2, "coef").set_index("Term")
    t = coef.loc["x", "t"]
    assert coef.loc["x", "p-value"] == pytest.approx(t_pvalue_by_integration(t, 10), abs=1e-6)


def test_regression_handles_nulls_and_bad_input():
    data = "x,z,y\n1,5,2\n2,3,4\n3,8,7\n4,1,8\n5,,11\n6,2,"
    ev = run(chain(("linear_regression", {"target": "y", "predictors": ["x", "z"]}), data=data))
    assert out(ev, 2, "fit").set_index("Measure")["Value"]["Rows used"] == 4
    assert pd.isna(out(ev, 2, "scored")["y_predicted"].iloc[4])
    assert "Not numeric" in err(run(chain(("linear_regression", {"target": "pts", "predictors": ["conf"]}))), 2)
    tiny = "x,y\n1,2\n2,4"
    assert "more complete rows" in err(run(chain(("linear_regression", {"target": "y", "predictors": ["x"]}), data=tiny)), 2)


def test_export_runs_analysis_tools(tmp_path):
    engine_out = tmp_path / "engine.csv"
    script_out = tmp_path / "script.csv"
    wf = {
        "nodes": [
            {"id": "1", "type": "text_input", "config": {"data": LINE}},
            {"id": "2", "type": "linear_regression", "config": {"target": "y", "predictors": ["x"]}},
            {"id": "3", "type": "field_summary", "config": {}},
            {"id": "4", "type": "output", "config": {"path": str(engine_out)}},
        ],
        "edges": [
            {"source": "1", "sourceHandle": "out", "target": "2", "targetHandle": "in"},
            {"source": "2", "sourceHandle": "scored", "target": "3", "targetHandle": "in"},
            {"source": "3", "sourceHandle": "out", "target": "4", "targetHandle": "in"},
        ],
    }
    ev = Engine().evaluate(wf, run_side_effects=True)
    assert all(r.status == "ok" for r in ev.results.values())
    code = export_script(ev, "analysis").replace(repr(str(engine_out)), repr(str(script_out)))
    script = tmp_path / "exported.py"
    script.write_text(code)
    subprocess.run([sys.executable, str(script)], check=True, cwd=tmp_path)
    pd.testing.assert_frame_equal(pd.read_csv(engine_out), pd.read_csv(script_out))
