import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from snek.codegen import export_script
from snek.engine import Engine

ROOT = Path(__file__).resolve().parent.parent
PENGUINS = str(ROOT / "examples" / "data" / "penguins" / "penguins.csv")


def wf(nodes, edges):
    return {
        "nodes": [{"id": str(i), "type": t, "config": c} for i, t, c in nodes],
        "edges": [{"source": str(s), "sourceHandle": sh, "target": str(t), "targetHandle": th} for s, sh, t, th in edges],
    }


def run(w):
    return Engine().evaluate(w, run_side_effects=True)


def out(ev, node, port="out"):
    res = ev.results[str(node)]
    assert res.status == "ok", res.error
    return ev.frames[(str(node), port)]


def err(ev, node):
    assert ev.results[str(node)].status == "error"
    return ev.results[str(node)].error


def csv_text(df):
    return df.to_csv(index=False)


def logistic_data(n=300, seed=3):
    rng = np.random.default_rng(seed)
    x1, x2 = rng.normal(size=n), rng.normal(size=n)
    p = 1 / (1 + np.exp(-(0.5 + 1.5 * x1 - 1.0 * x2)))
    y = np.where(rng.random(n) < p, "W", "L")
    conf = rng.choice(["B1G", "SEC"], size=n)
    return pd.DataFrame({"x1": x1.round(4), "x2": x2.round(4), "conf": conf, "result": y})


def test_logistic_regression_matches_statsmodels():
    import statsmodels.api as sm

    data = logistic_data()
    ev = run(wf([(1, "text_input", {"data": csv_text(data)}), (2, "logistic_regression", {"target": "result", "predictors": ["x1", "x2"]})], [(1, "out", 2, "in")]))
    coef = out(ev, 2, "coef").set_index("Term")
    direct = sm.Logit((data["result"] == "W").astype(float), sm.add_constant(data[["x1", "x2"]])).fit(disp=0)
    assert coef.loc["x1", "Coefficient"] == pytest.approx(direct.params["x1"], rel=1e-6)
    assert coef.loc["(Intercept)", "p-value"] == pytest.approx(direct.pvalues["const"], rel=1e-6)
    assert coef.loc["x1", "Odds Ratio"] == pytest.approx(np.exp(direct.params["x1"]))
    fit = out(ev, 2, "fit").set_index("Measure")["Value"]
    assert fit["Positive class"] == "W" and fit["Rows used"] == "300"


def test_logistic_errors():
    three = "y,x\na,1\nb,2\nc,3\na,4"
    assert "exactly two" in err(run(wf([(1, "text_input", {"data": three}), (2, "logistic_regression", {"target": "y", "predictors": ["x"]})], [(1, "out", 2, "in")])), 2)
    separated = "y,x\nL,1\nL,2\nL,3\nW,10\nW,11\nW,12"
    assert "separate" in err(run(wf([(1, "text_input", {"data": separated}), (2, "logistic_regression", {"target": "y", "predictors": ["x"]})], [(1, "out", 2, "in")])), 2)


def test_score_logistic_and_categorical_predictors():
    data = logistic_data()
    new = pd.DataFrame({"x1": [2.0, -2.0, None], "x2": [-1.0, 1.0, 0.0], "conf": ["SEC", "B1G", "ACC"]})
    ev = run(wf(
        [(1, "text_input", {"data": csv_text(data)}), (2, "logistic_regression", {"target": "result", "predictors": ["x1", "x2", "conf"]}), (3, "text_input", {"data": csv_text(new)}), (4, "score", {})],
        [(1, "out", 2, "in"), (2, "model", 4, "model"), (3, "out", 4, "data")],
    ))
    assert "conf_SEC" in out(ev, 2, "coef")["Term"].tolist()
    scored = out(ev, 4)
    assert scored["result_predicted"].tolist()[:2] == ["W", "L"]
    assert 0.5 < scored["P_W"].iloc[0] <= 1 and 0 <= scored["P_W"].iloc[1] < 0.5
    assert pd.isna(scored["P_W"].iloc[2]) and pd.isna(scored["result_predicted"].iloc[2])


def penguin_pipeline(model_type, cfg):
    return wf(
        [
            (1, "input", {"path": PENGUINS}),
            (2, "create_samples", {"estimation": 70, "validation": 30, "seed": 7}),
            (3, model_type, cfg),
            (4, "model_comparison", {}),
            (5, "score", {}),
        ],
        [(1, "out", 2, "in"), (2, "estimation", 3, "in"), (3, "model", 4, "model"), (2, "validation", 4, "data"), (3, "model", 5, "model"), (2, "validation", 5, "data")],
    )


def test_decision_tree_classifies_species():
    ev = run(penguin_pipeline("decision_tree", {"target": "species", "predictors": ["bill_length_mm", "bill_depth_mm", "flipper_length_mm", "island"], "max_depth": 4}))
    metrics = out(ev, 4, "metrics").iloc[0]
    assert metrics["Accuracy"] > 0.9
    assert len(out(ev, 3, "rules")) > 3
    assert out(ev, 3, "importance")["Importance"].sum() == pytest.approx(1)
    confusion = out(ev, 4, "confusion")
    assert confusion["Count"].sum() == metrics["Rows"]
    scored = out(ev, 5)
    assert {"species_predicted", "P_Adelie", "P_Gentoo", "P_Chinstrap"} <= set(scored.columns)


def test_random_forest_regression_and_boosted_classification():
    forest = run(penguin_pipeline("random_forest", {"target": "body_mass_g", "predictors": ["flipper_length_mm", "bill_length_mm", "bill_depth_mm", "species", "sex"], "trees": 100}))
    m = out(forest, 4, "metrics").iloc[0]
    assert m["R squared"] > 0.75 and m["RMSE"] > 0
    boosted = run(penguin_pipeline("boosted_model", {"target": "sex", "predictors": ["body_mass_g", "bill_depth_mm", "bill_length_mm", "species"], "trees": 100}))
    b = out(boosted, 4, "metrics").iloc[0]
    assert b["Accuracy"] > 0.8 and 0.5 < b["AUC"] <= 1


def test_create_samples_split():
    data = "\n".join(["i"] + [str(i) for i in range(100)])
    ev = run(wf([(1, "text_input", {"data": data}), (2, "create_samples", {"estimation": 60, "validation": 25, "seed": 3})], [(1, "out", 2, "in")]))
    e, v, h = (out(ev, 2, p)["i"].tolist() for p in ("estimation", "validation", "holdout"))
    assert (len(e), len(v), len(h)) == (60, 25, 15)
    assert sorted(e + v + h) == list(range(100)) and e == sorted(e)
    again = run(wf([(1, "text_input", {"data": data}), (2, "create_samples", {"estimation": 60, "validation": 25, "seed": 3})], [(1, "out", 2, "in")]))
    assert out(again, 2, "estimation")["i"].tolist() == e
    assert "add up" in err(run(wf([(1, "text_input", {"data": data}), (2, "create_samples", {"estimation": 80, "validation": 30})], [(1, "out", 2, "in")])), 2)


def test_linear_model_scores_like_its_own_output():
    line = "x,y\n1,2.1\n2,3.9\n3,6.2\n4,7.8\n5,10.1"
    ev = run(wf([(1, "text_input", {"data": line}), (2, "linear_regression", {"target": "y", "predictors": ["x"]}), (3, "score", {})], [(1, "out", 2, "in"), (2, "model", 3, "model"), (1, "out", 3, "data")]))
    np.testing.assert_allclose(out(ev, 3)["y_predicted"], out(ev, 2, "scored")["y_predicted"])


def test_model_comparison_ranks_two_models():
    nodes = [
        (1, "input", {"path": PENGUINS}),
        (2, "create_samples", {"estimation": 70, "validation": 30, "seed": 2}),
        (3, "decision_tree", {"target": "species", "predictors": ["bill_length_mm"], "max_depth": 2}),
        (4, "random_forest", {"target": "species", "predictors": ["bill_length_mm", "bill_depth_mm", "flipper_length_mm"], "trees": 50}),
        (5, "model_comparison", {}),
    ]
    edges = [(1, "out", 2, "in"), (2, "estimation", 3, "in"), (2, "estimation", 4, "in"), (3, "model", 5, "model"), (4, "model", 5, "model"), (2, "validation", 5, "data")]
    metrics = out(run(wf(nodes, edges)), 5, "metrics")
    assert metrics["Model"].tolist() == ["tree (species)", "forest (species)"]
    assert metrics["Accuracy"].iloc[1] > metrics["Accuracy"].iloc[0]


def blobs():
    rng = np.random.default_rng(0)
    centers = [(0, 0), (10, 10), (0, 10)]
    rows = [(c[0] + rng.normal(scale=0.5), c[1] + rng.normal(scale=0.5), i) for i, c in enumerate(centers) for _ in range(30)]
    return pd.DataFrame(rows, columns=["a", "b", "truth"])


def test_kmeans_recovers_blobs_and_scores_new_rows():
    data = blobs()
    new = pd.DataFrame({"a": [10.2, -0.1], "b": [9.8, 0.2]})
    ev = run(wf(
        [(1, "text_input", {"data": csv_text(data)}), (2, "kmeans", {"features": ["a", "b"], "k": 3}), (3, "text_input", {"data": csv_text(new)}), (4, "score", {})],
        [(1, "out", 2, "in"), (2, "model", 4, "model"), (3, "out", 4, "data")],
    ))
    clustered = out(ev, 2, "data")
    assert clustered.groupby("truth")["Cluster"].nunique().eq(1).all()
    assert clustered["Cluster"].nunique() == 3
    centers = out(ev, 2, "centers")
    assert centers["Rows"].tolist() == [30, 30, 30]
    assert sorted(centers["a"].round().tolist()) == [0, 0, 10]
    scored = out(ev, 4)
    label_of = clustered.groupby("truth")["Cluster"].first()
    assert scored["Cluster"].tolist() == [label_of[1], label_of[0]]


def test_pca():
    ev = run(wf([(1, "input", {"path": PENGUINS}), (2, "pca", {"features": ["bill_length_mm", "bill_depth_mm", "flipper_length_mm", "body_mass_g"], "components": 2})], [(1, "out", 2, "in")]))
    var = out(ev, 2, "variance")
    assert var["Explained variance %"].iloc[0] > 60 and var["Cumulative %"].iloc[-1] <= 100
    assert out(ev, 2, "loadings").shape == (4, 3)
    data = out(ev, 2, "data")
    assert data["PC1"].notna().sum() == 342 and data["PC2"].isna().sum() == 2


def test_ts_filler():
    data = "team,week,pts\nNU,2025-09-01,20\nNU,2025-09-15,34\nIA,2025-09-01,10\nIA,2025-09-08,31"
    ev = run(wf([(1, "text_input", {"data": data}), (2, "ts_filler", {"date": "week", "freq": "W", "group_by": ["team"], "method": "previous"})], [(1, "out", 2, "in")]))
    df = out(ev, 2)
    nu = df[df["team"] == "NU"]
    assert len(nu) == 3 and nu["Filled"].tolist() == [False, True, False]
    assert nu["pts"].tolist() == [20, 20, 34]
    assert len(df[df["team"] == "IA"]) == 2
    dupes = "d,v\n2025-01-01,1\n2025-01-01,2"
    assert "more than one row" in err(run(wf([(1, "text_input", {"data": dupes}), (2, "ts_filler", {"date": "d", "freq": "D"})], [(1, "out", 2, "in")])), 2)


def test_rolling_window():
    data = "team,pts\nNU,10\nNU,20\nNU,30\nNU,40\nIA,7\nIA,9"
    df = out(run(wf([(1, "text_input", {"data": data}), (2, "rolling", {"columns": ["pts"], "window": 3, "group_by": ["team"]})], [(1, "out", 2, "in")])), 2)
    assert df["pts_last3_mean"].tolist() == [10, 15, 20, 30, 7, 8]
    prior = out(run(wf([(1, "text_input", {"data": data}), (2, "rolling", {"columns": ["pts"], "window": 2, "group_by": ["team"], "exclude_current": True, "func": "sum"})], [(1, "out", 2, "in")])), 2)
    assert prior["pts_prior2_sum"].tolist()[:4] == [pytest.approx(float("nan"), nan_ok=True), 10, 30, 50]


def monthly(n=48, seasonal=True):
    t = np.arange(n)
    values = 100 + 2 * t + (10 * np.sin(2 * np.pi * t / 12) if seasonal else 0) + np.random.default_rng(1).normal(scale=1, size=n)
    return pd.DataFrame({"month": pd.date_range("2020-01-01", periods=n, freq="MS").strftime("%Y-%m-%d"), "sales": values.round(3)})


def test_ets_forecast_matches_statsmodels():
    from statsmodels.tsa.exponential_smoothing.ets import ETSModel

    data = monthly()
    ev = run(wf([(1, "text_input", {"data": csv_text(data)}), (2, "ets", {"date": "month", "value": "sales", "freq": "M", "periods": 6, "trend": "add", "seasonal": "add", "seasonal_periods": 12})], [(1, "out", 2, "in")]))
    fc = out(ev, 2, "forecast")
    assert len(fc) == 6 and (fc["Lower"] < fc["Forecast"]).all() and (fc["Forecast"] < fc["Upper"]).all()
    assert str(fc["month"].iloc[0])[:7] == "2024-01"
    y = pd.Series(data["sales"].to_numpy(), index=pd.period_range("2020-01", periods=48, freq="M"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        direct = ETSModel(y, error="add", trend="add", seasonal="add", seasonal_periods=12).fit(disp=False).forecast(6)
    np.testing.assert_allclose(fc["Forecast"], direct.to_numpy(), rtol=1e-6)
    assert len(out(ev, 2, "history")) == 48
    short = run(wf([(1, "text_input", {"data": csv_text(monthly(18))}), (2, "ets", {"date": "month", "value": "sales", "freq": "M", "seasonal": "add", "seasonal_periods": 12})], [(1, "out", 2, "in")]))
    assert "two full seasons" in err(short, 2)


def test_arima_manual_matches_statsmodels_and_auto_runs():
    from statsmodels.tsa.arima.model import ARIMA

    data = monthly(seasonal=False)
    ev = run(wf([(1, "text_input", {"data": csv_text(data)}), (2, "arima", {"date": "month", "value": "sales", "freq": "M", "periods": 3, "order_mode": "manual", "p": 1, "d": 1, "q": 0})], [(1, "out", 2, "in")]))
    y = pd.Series(data["sales"].to_numpy(), index=pd.period_range("2020-01", periods=48, freq="M"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        direct = ARIMA(y, order=(1, 1, 0)).fit().forecast(3)
    np.testing.assert_allclose(out(ev, 2, "forecast")["Forecast"], direct.to_numpy(), rtol=1e-6)
    auto = run(wf([(1, "text_input", {"data": csv_text(data)}), (2, "arima", {"date": "month", "value": "sales", "freq": "M", "periods": 3})], [(1, "out", 2, "in")]))
    summary = out(auto, 2, "summary").set_index("Measure")["Value"]
    assert summary["Order (p, d, q)"].startswith("(") and float(summary["AIC"]) > 0
    gappy = data.drop(index=[5]).reset_index(drop=True)
    assert "Fill Missing Dates" in err(run(wf([(1, "text_input", {"data": csv_text(gappy)}), (2, "arima", {"date": "month", "value": "sales", "freq": "M"})], [(1, "out", 2, "in")])), 2)


def test_grouped_forecast():
    a, b = monthly(36, False).assign(team="A"), monthly(36, False).assign(team="B", sales=lambda d: d["sales"] * 2)
    data = pd.concat([a, b])
    fc = out(run(wf([(1, "text_input", {"data": csv_text(data)}), (2, "ets", {"date": "month", "value": "sales", "freq": "M", "periods": 2, "trend": "add", "group_by": ["team"]})], [(1, "out", 2, "in")])), 2, "forecast")
    assert fc["team"].tolist() == ["A", "A", "B", "B"]
    assert fc[fc["team"] == "B"]["Forecast"].iloc[0] > fc[fc["team"] == "A"]["Forecast"].iloc[0]


def test_export_runs_models_standalone(tmp_path):
    engine_out, script_out = tmp_path / "engine.csv", tmp_path / "script.csv"
    nodes = [
        (1, "input", {"path": PENGUINS}),
        (2, "create_samples", {"estimation": 70, "validation": 30, "seed": 5}),
        (3, "random_forest", {"target": "species", "predictors": ["bill_length_mm", "bill_depth_mm", "flipper_length_mm"], "trees": 30, "seed": 4}),
        (4, "score", {}),
        (5, "output", {"path": str(engine_out)}),
    ]
    edges = [(1, "out", 2, "in"), (2, "estimation", 3, "in"), (3, "model", 4, "model"), (2, "validation", 4, "data"), (4, "out", 5, "in")]
    ev = Engine().evaluate(wf(nodes, edges), run_side_effects=True)
    assert all(r.status == "ok" for r in ev.results.values()), {k: r.error for k, r in ev.results.items()}
    code = export_script(ev, "models").replace(repr(str(engine_out)), repr(str(script_out)))
    assert "Requires pandas, numpy, scikit-learn" in code
    script = tmp_path / "exported.py"
    script.write_text(code)
    subprocess.run([sys.executable, str(script)], check=True, cwd=tmp_path)
    pd.testing.assert_frame_equal(pd.read_csv(engine_out), pd.read_csv(script_out))
