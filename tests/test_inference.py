import math
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from snek.codegen import export_script
from snek.engine import Engine
from snek.inference import inference_summary

DATA = "g,x,tag\na,2,u\na,4,u\na,4,v\na,4,v\nb,5,u\nb,5,u\nb,7,v\nb,9,v\nb,,v\n"


def run(cfg, data=DATA):
    wf = {
        "nodes": [{"id": "1", "type": "text_input", "config": {"data": data}}, {"id": "2", "type": "inference", "config": cfg}],
        "edges": [{"source": "1", "sourceHandle": "out", "target": "2", "targetHandle": "in"}],
    }
    return Engine().evaluate(wf, run_side_effects=True)


def numeric(ev):
    return ev.frames[("2", "numeric")]


def test_mean_interval_and_t_test_match_scipy_for_each_group():
    ev = run({"columns": ["x"], "group_by": ["g"], "mu": 4})
    df = numeric(ev).set_index("g")
    for name, values in {"a": [2, 4, 4, 4], "b": [5, 5, 7, 9]}.items():
        x = np.array(values, dtype=float)
        low, high = stats.t.interval(0.95, len(x) - 1, loc=x.mean(), scale=stats.sem(x))
        row = df.loc[name]
        assert row["n"] == len(x) and row["mean"] == pytest.approx(x.mean()) and row["sd"] == pytest.approx(x.std(ddof=1))
        assert row["std_error"] == pytest.approx(stats.sem(x))
        assert (row["mean_ci_low"], row["mean_ci_high"]) == (pytest.approx(low), pytest.approx(high))
        test = stats.ttest_1samp(x, 4)
        assert row["t"] == pytest.approx(test.statistic) and row["p_value"] == pytest.approx(test.pvalue) and row["df"] == len(x) - 1
        assert row["cohens_d"] == pytest.approx((x.mean() - 4) / x.std(ddof=1))
        assert row["normality_test"] == "Shapiro-Wilk" and row["normality_p"] == pytest.approx(stats.shapiro(x).pvalue)


def test_missing_values_are_counted_and_skipped():
    row = numeric(run({"columns": ["x"], "group_by": ["g"]})).set_index("g").loc["b"]
    assert row["n"] == 4 and row["missing"] == 1


def test_sd_interval_uses_chi_square():
    x = np.array([5, 5, 7, 9], dtype=float)
    sd = x.std(ddof=1)
    row = numeric(run({"columns": ["x"], "group_by": ["g"]})).set_index("g").loc["b"]
    assert row["sd_ci_low"] == pytest.approx(math.sqrt(3 * sd**2 / stats.chi2.ppf(0.975, 3)))
    assert row["sd_ci_high"] == pytest.approx(math.sqrt(3 * sd**2 / stats.chi2.ppf(0.025, 3)))


def test_confidence_level_and_test_direction():
    wide = numeric(run({"columns": ["x"], "group_by": ["g"], "confidence": 99})).set_index("g").loc["a"]
    narrow = numeric(run({"columns": ["x"], "group_by": ["g"], "confidence": 80})).set_index("g").loc["a"]
    assert wide["mean_ci_high"] - wide["mean_ci_low"] > narrow["mean_ci_high"] - narrow["mean_ci_low"]
    two = numeric(run({"columns": ["x"], "group_by": ["g"], "mu": 0})).set_index("g").loc["b"]
    greater = numeric(run({"columns": ["x"], "group_by": ["g"], "mu": 0, "alternative": "greater"})).set_index("g").loc["b"]
    less = numeric(run({"columns": ["x"], "group_by": ["g"], "mu": 0, "alternative": "less"})).set_index("g").loc["b"]
    assert greater["p_value"] == pytest.approx(two["p_value"] / 2) and less["p_value"] == pytest.approx(1 - two["p_value"] / 2)


def test_category_shares_use_wilson_intervals():
    ev = run({"columns": ["tag"], "group_by": ["g"]})
    cats = ev.frames[("2", "categories")]
    row = cats[(cats["g"] == "a") & (cats["level"] == "u")].iloc[0]
    n, k, z = 4, 2, stats.norm.ppf(0.975)
    p = k / n
    centre = (p + z**2 / (2 * n)) / (1 + z**2 / n)
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / (1 + z**2 / n)
    assert row["share"] == 0.5 and row["ci_low"] == pytest.approx(centre - half) and row["ci_high"] == pytest.approx(centre + half)
    assert row["p_equal_shares"] == pytest.approx(1.0)
    assert len(numeric(ev)) == 0


def test_whole_table_default_and_id_columns_are_skipped():
    data = "id,x,kind\n" + "\n".join(f"{i},{i * 1.5},{'a' if i % 2 else 'b'}" for i in range(30))
    ev = run({"columns": [], "group_by": [], "max_levels": 5}, data)
    assert numeric(ev)["column"].tolist() == ["id", "x"]
    assert ev.frames[("2", "categories")]["column"].unique().tolist() == ["kind"]


def test_tiny_and_constant_columns_do_not_crash():
    ev = run({"columns": [], "group_by": []}, "a,b,c\n1,5,x\n,5,y\n,5,y\n")
    df = numeric(ev).set_index("column")
    assert df.loc["a", "n"] == 1 and math.isnan(df.loc["a", "sd"]) and df.loc["a", "mean"] == 1
    assert df.loc["b", "sd"] == 0 and math.isnan(df.loc["b", "p_value"]) and df.loc["b", "normality_test"] == ""


def test_large_columns_switch_to_the_dagostino_test():
    rng = np.random.default_rng(1)
    frame = pd.DataFrame({"x": rng.normal(size=6000)})
    result, _ = inference_summary(frame, ["x"])
    assert result.loc[0, "normality_test"] == "D'Agostino" and 0 <= result.loc[0, "normality_p"] <= 1


def test_tool_checks_its_settings():
    assert run({"columns": ["nope"]}).results["2"].status == "error"
    res = run({"columns": ["x"], "confidence": 100}).results["2"]
    assert res.status == "error" and "Confidence level" in res.error


def test_export_runs_and_matches(tmp_path):
    wf = {
        "nodes": [
            {"id": "1", "type": "text_input", "config": {"data": DATA}},
            {"id": "2", "type": "inference", "config": {"columns": ["x"], "group_by": ["g"], "mu": 4}},
            {"id": "3", "type": "output", "config": {"path": str(tmp_path / "out.csv")}},
        ],
        "edges": [
            {"source": "1", "sourceHandle": "out", "target": "2", "targetHandle": "in"},
            {"source": "2", "sourceHandle": "numeric", "target": "3", "targetHandle": "in"},
        ],
    }
    ev = Engine().evaluate(wf, run_side_effects=True)
    engine_df = pd.read_csv(tmp_path / "out.csv")
    script = export_script(ev)
    assert "inference_summary(" in script and "scipy" in script
    (tmp_path / "flow.py").write_text(script, encoding="utf-8")
    (tmp_path / "out.csv").unlink()
    subprocess.run([sys.executable, str(tmp_path / "flow.py")], check=True, cwd=tmp_path)
    pd.testing.assert_frame_equal(pd.read_csv(tmp_path / "out.csv"), engine_df)
