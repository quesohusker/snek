import math
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


def single(tool, cfg, data):
    return wf([(1, "text_input", {"data": data}), (2, tool, cfg)], [(1, "out", 2, "in")])


def run(w):
    return Engine().evaluate(w, run_side_effects=True)


def out(ev, node, port="out"):
    res = ev.results[str(node)]
    assert res.status == "ok", res.error
    return ev.frames[(str(node), port)]


def err(ev, node):
    assert ev.results[str(node)].status == "error"
    return ev.results[str(node)].error


def frame_text(df):
    return df.to_csv(index=False)


def regression_data(n=200, seed=4):
    rng = np.random.default_rng(seed)
    x1, x2, noise_col = rng.normal(size=n), rng.normal(size=n), rng.normal(size=n)
    y = 3 + 2 * x1 - 1.5 * x2 + rng.normal(scale=0.5, size=n)
    return pd.DataFrame({"x1": x1, "x2": x2, "junk": noise_col, "y": y}).round(5)


def test_regularized_regression():
    data = regression_data()
    ev = run(single("regularized", {"target": "y", "predictors": ["x1", "x2", "junk"], "method": "lasso", "alpha": 0.3}, frame_text(data)))
    coef = out(ev, 2, "coef").set_index("Term")
    assert not coef.loc["junk", "Kept"] and coef.loc["x1", "Kept"]
    model = out(ev, 2, "model").iloc[0]["Model"]
    X = data[["x1", "x2", "junk"]]
    manual = coef.loc["(Intercept)", "Coefficient"] + X.to_numpy() @ coef.loc[["x1", "x2", "junk"], "Coefficient"].to_numpy()
    np.testing.assert_allclose(model.predict(X), manual, rtol=1e-9)
    auto = run(single("regularized", {"target": "y", "predictors": ["x1", "x2"], "method": "ridge"}, frame_text(data)))
    fit = out(auto, 2, "fit").set_index("Measure")["Value"]
    assert float(fit["Training R squared"]) > 0.9 and float(fit["Alpha"]) > 0


def count_data(n=300, seed=6):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    group = rng.choice(["A", "B"], size=n)
    mu = np.exp(0.5 + 0.4 * x + 0.3 * (group == "B"))
    return pd.DataFrame({"x": x.round(5), "group": group, "tds": rng.poisson(mu), "yards": rng.gamma(2.0, mu * 10).round(3)})


def test_count_and_gamma_regression_match_statsmodels():
    import statsmodels.api as sm

    data = count_data()
    ev = run(single("count_regression", {"target": "tds", "predictors": ["x", "group"], "family": "poisson"}, frame_text(data)))
    coef = out(ev, 2, "coef").set_index("Term")
    X = sm.add_constant(pd.get_dummies(data[["x", "group"]], drop_first=True, dtype=float))
    direct = sm.GLM(data["tds"], X, family=sm.families.Poisson()).fit()
    assert coef.loc["x", "Coefficient"] == pytest.approx(direct.params["x"], rel=1e-6)
    assert coef.loc["group_B", "Ratio"] == pytest.approx(math.exp(direct.params["group_B"]), rel=1e-6)
    nb = out(run(single("count_regression", {"target": "tds", "predictors": ["x"], "family": "negbin"}, frame_text(data))), 2, "fit").set_index("Measure")["Value"]
    assert float(nb["Dispersion (alpha)"]) >= 0
    gamma = out(run(single("gamma_regression", {"target": "yards", "predictors": ["x", "group"]}, frame_text(data))), 2, "coef").set_index("Term")
    gdirect = sm.GLM(data["yards"], X, family=sm.families.Gamma(sm.families.links.Log())).fit()
    assert gamma.loc["x", "Coefficient"] == pytest.approx(gdirect.params["x"], rel=1e-5)
    neg = "y,x\n-1,1\n2,2\n3,3"
    assert "0 or more" in err(run(single("count_regression", {"target": "y", "predictors": ["x"]}, neg)), 2)
    assert "above 0" in err(run(single("gamma_regression", {"target": "y", "predictors": ["x"]}, neg)), 2)


def test_glm_scores_like_statsmodels():
    data = count_data()
    ev = run(wf(
        [(1, "text_input", {"data": frame_text(data)}), (2, "count_regression", {"target": "tds", "predictors": ["x", "group"]}), (3, "score", {})],
        [(1, "out", 2, "in"), (2, "model", 3, "model"), (1, "out", 3, "data")],
    ))
    res = out(ev, 2, "model").iloc[0]["Model"]
    np.testing.assert_allclose(out(ev, 3)["tds_predicted"], res.predict(), rtol=1e-9)


def species_pipeline(tool, cfg):
    return wf(
        [(1, "input", {"path": PENGUINS}), (2, "create_samples", {"estimation": 70, "validation": 30, "seed": 11}), (3, tool, cfg), (4, "model_comparison", {}), (5, "score", {})],
        [(1, "out", 2, "in"), (2, "estimation", 3, "in"), (3, "model", 4, "model"), (2, "validation", 4, "data"), (3, "model", 5, "model"), (2, "validation", 5, "data")],
    )


@pytest.mark.parametrize("tool,cfg,floor", [
    ("naive_bayes", {}, 0.85),
    ("knn", {"k": 5}, 0.9),
    ("svm", {"kernel": "rbf"}, 0.9),
    ("neural_network", {"hidden": "32"}, 0.9),
])
def test_classifiers_on_penguins(tool, cfg, floor):
    feats = ["bill_length_mm", "bill_depth_mm", "flipper_length_mm", "body_mass_g"]
    ev = run(species_pipeline(tool, {"target": "species", "predictors": feats, **cfg}))
    assert out(ev, 4, "metrics").iloc[0]["Accuracy"] > floor
    assert set(out(ev, 3, "importance")["Feature"]) == set(feats)
    assert "P_Adelie" in out(ev, 5).columns


def test_knn_regression_and_naive_bayes_guard():
    ev = run(species_pipeline("knn", {"target": "body_mass_g", "predictors": ["flipper_length_mm", "bill_depth_mm"], "task": "regression", "k": 7}))
    assert out(ev, 4, "metrics").iloc[0]["R squared"] > 0.6
    bad = run(species_pipeline("naive_bayes", {"target": "body_mass_g", "predictors": ["flipper_length_mm"], "task": "regression"}))
    assert "only predicts categories" in err(bad, 3)


def test_cross_validation_matches_manual_folds():
    data = regression_data(120)
    ev = run(wf(
        [(1, "text_input", {"data": frame_text(data)}), (2, "linear_regression", {"target": "y", "predictors": ["x1", "x2"]}), (3, "cross_validation", {"folds": 4, "seed": 9})],
        [(1, "out", 2, "in"), (2, "model", 3, "model"), (1, "out", 3, "data")],
    ))
    summary, folds = out(ev, 3, "summary"), out(ev, 3, "folds")
    assert len(folds) == 4
    assignment = np.random.default_rng(9).permutation(len(data)) % 4
    scores = []
    for f in range(4):
        train, test = data[assignment != f], data[assignment == f]
        X = np.column_stack([np.ones(len(train)), train[["x1", "x2"]]])
        beta, *_ = np.linalg.lstsq(X, train["y"], rcond=None)
        pred = beta[0] + test[["x1", "x2"]].to_numpy() @ beta[1:]
        scores.append(1 - ((test["y"] - pred) ** 2).sum() / ((test["y"] - test["y"].mean()) ** 2).sum())
    assert summary["R squared (mean)"].iloc[0] == pytest.approx(np.mean(scores))
    assert folds["R squared"].tolist() == pytest.approx(scores)


def test_cross_validation_several_model_types():
    nodes = [
        (1, "input", {"path": PENGUINS}),
        (2, "decision_tree", {"target": "species", "predictors": ["bill_length_mm", "flipper_length_mm"], "max_depth": 3}),
        (3, "random_forest", {"target": "species", "predictors": ["bill_length_mm", "flipper_length_mm"], "trees": 30}),
        (4, "logistic_regression", {"target": "sex", "predictors": ["body_mass_g", "bill_depth_mm"]}),
        (5, "cross_validation", {"folds": 3}),
    ]
    edges = [(1, "out", n, "in") for n in (2, 3, 4)] + [(n, "model", 5, "model") for n in (2, 3, 4)] + [(1, "out", 5, "data")]
    summary = out(run(wf(nodes, edges)), 5, "summary")
    assert summary["Model"].tolist() == ["tree (species)", "forest (species)", "logistic (sex)"]
    assert summary["Accuracy (mean)"].between(0.6, 1).all()


def test_vif_matches_statsmodels():
    import statsmodels.api as sm
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    rng = np.random.default_rng(1)
    x1 = rng.normal(size=100)
    data = pd.DataFrame({"x1": x1, "x2": 2 * x1 + rng.normal(scale=0.1, size=100), "x3": rng.normal(size=100)}).round(6)
    table = out(run(single("vif", {"predictors": ["x1", "x2", "x3"]}, frame_text(data))), 2).set_index("Predictor")
    X = sm.add_constant(data)
    assert table.loc["x2", "VIF"] == pytest.approx(variance_inflation_factor(X.to_numpy(), 2), rel=1e-6)
    assert table.loc["x1", "Concern"] == "high" and table.loc["x3", "Concern"] == "low"


def test_test_of_means_matches_scipy():
    from scipy import stats

    rng = np.random.default_rng(2)
    data = pd.DataFrame({"pts": np.concatenate([rng.normal(30, 7, 40), rng.normal(24, 9, 35), rng.normal(27, 8, 30)]).round(2), "conf": ["SEC"] * 40 + ["B1G"] * 35 + ["ACC"] * 30})
    two = data[data["conf"] != "ACC"]
    t = out(run(single("test_of_means", {"value": "pts", "group": "conf"}, frame_text(two))), 2, "test").set_index("Measure")["Value"]
    direct = stats.ttest_ind(two[two["conf"] == "B1G"]["pts"], two[two["conf"] == "SEC"]["pts"], equal_var=False)
    assert t["Test"] == "Welch t-test" and float(t["p-value"]) == pytest.approx(direct.pvalue, rel=1e-4)
    f = out(run(single("test_of_means", {"value": "pts", "group": "conf"}, frame_text(data))), 2, "test").set_index("Measure")["Value"]
    fdirect = stats.f_oneway(*[g["pts"] for _, g in data.groupby("conf")])
    assert f["Test"] == "One-way ANOVA" and float(f["Statistic (F)"]) == pytest.approx(fdirect.statistic, rel=1e-4)


def test_chi_square_matches_scipy():
    from scipy import stats

    data = pd.DataFrame({"conf": ["SEC"] * 30 + ["B1G"] * 30, "bowl": ["Y"] * 22 + ["N"] * 8 + ["Y"] * 14 + ["N"] * 16})
    ev = run(single("chi_square", {"rows": "conf", "columns": "bowl"}, frame_text(data)))
    t = out(ev, 2, "test").set_index("Measure")["Value"]
    chi2, p, dof, _ = stats.chi2_contingency(pd.crosstab(data["conf"], data["bowl"]))
    assert float(t["Chi-square"]) == pytest.approx(chi2, rel=1e-4) and float(t["p-value"]) == pytest.approx(p, rel=1e-4)
    assert float(t["Cramér's V"]) == pytest.approx(math.sqrt(chi2 / 60), rel=1e-3)
    assert out(ev, 2, "expected")["Observed"].sum() == 60


def test_stl_components_add_up():
    t = np.arange(48)
    data = pd.DataFrame({"m": pd.date_range("2020-01-01", periods=48, freq="MS").strftime("%Y-%m-%d"), "v": (50 + t + 8 * np.sin(2 * np.pi * t / 12)).round(4)})
    df = out(run(single("stl", {"date": "m", "value": "v", "freq": "M", "period": 12}, frame_text(data))), 2)
    np.testing.assert_allclose(df["Trend"] + df["Seasonal"] + df["Remainder"], df["v"], atol=1e-8)
    assert df["Seasonal"].abs().max() > 5


def test_ts_compare_metrics():
    forecast = "date,Forecast,Lower,Upper\n2025-01-01,10,8,12\n2025-01-02,20,15,25\n2025-01-03,30,29,31"
    actual = "day,value\n2025-01-01,12\n2025-01-02,18\n2025-01-03,33\n2025-01-04,40"
    ev = run(wf(
        [(1, "text_input", {"data": forecast}), (2, "text_input", {"data": actual}), (3, "ts_compare", {"date": "date", "actual_date": "day", "actual_value": "value"})],
        [(1, "out", 3, "forecast"), (2, "out", 3, "actual")],
    ))
    m = out(ev, 3, "metrics").iloc[0]
    assert m["Rows"] == 3 and m["MAE"] == pytest.approx(7 / 3)
    assert m["RMSE"] == pytest.approx(math.sqrt((4 + 4 + 9) / 3))
    assert m["Bias"] == pytest.approx(-1)
    assert m["Inside interval %"] == pytest.approx(200 / 3)
    assert m["MAPE %"] == pytest.approx((2 / 12 + 2 / 18 + 3 / 33) / 3 * 100)


def blobs():
    rng = np.random.default_rng(0)
    rows = [(cx + rng.normal(scale=0.4), cy + rng.normal(scale=0.4), f"{name}{i}") for name, (cx, cy) in {"a": (0, 0), "b": (8, 8), "c": (0, 8)}.items() for i in range(20)]
    return pd.DataFrame(rows, columns=["x", "y", "id"])


def test_cluster_diagnostics_hierarchical_and_neighbors():
    data = blobs()
    diag = out(run(single("cluster_diagnostics", {"features": ["x", "y"], "k_min": 2, "k_max": 6}, frame_text(data))), 2)
    assert diag.loc[diag["Best by silhouette"], "K"].tolist() == [3]
    ev = run(single("hierarchical", {"features": ["x", "y"], "k": 3}, frame_text(data)))
    clustered = out(ev, 2, "data")
    assert clustered.groupby(clustered["id"].str[0])["Cluster"].nunique().eq(1).all()
    assert out(ev, 2, "summary")["Rows"].tolist() == [20, 20, 20]
    points = "team,x,y\nA,0,0\nB,1,0\nC,10,10\nD,10,11"
    nn = out(run(single("nearest_neighbors", {"id": "team", "features": ["x", "y"], "k": 1, "standardize": False}, points)), 2)
    assert dict(zip(nn["team"], nn["Neighbor"])) == {"A": "B", "B": "A", "C": "D", "D": "C"}


def test_team_ratings_exact_solutions():
    neutral = "home,away,hp,ap,neutral\nA,B,20,10,true\nB,C,24,14,true\nA,C,30,10,true"
    ratings = out(run(single("team_ratings", {"home": "home", "away": "away", "home_points": "hp", "away_points": "ap", "neutral": "neutral"}, neutral)), 2, "ratings").set_index("Team")
    assert ratings["Rating"].to_dict() == pytest.approx({"A": 10, "B": 0, "C": -10})
    assert ratings.loc["A", "Rank"] == 1 and ratings.loc["C", "Schedule strength"] == pytest.approx(5)
    home = "home,away,hp,ap\nA,B,27,20\nB,A,21,20"
    ev = run(single("team_ratings", {"home": "home", "away": "away", "home_points": "hp", "away_points": "ap"}, home))
    r = out(ev, 2, "ratings").set_index("Team")["Rating"]
    assert r["A"] == pytest.approx(1.5) and r["B"] == pytest.approx(-1.5)
    assert out(ev, 2, "fit").set_index("Measure")["Value"]["Home-field advantage"] == "4.000"
    capped = out(run(single("team_ratings", {"home": "home", "away": "away", "home_points": "hp", "away_points": "ap", "neutral": "neutral", "cap": 15}, neutral)), 2, "games")
    assert capped["Margin used"].tolist() == [10, 10, 15]


def test_elo_hand_calculation():
    games = "wk,home,away,hp,ap\n1,A,B,24,17\n2,B,C,30,0"
    plain = run(single("elo", {"home": "home", "away": "away", "home_points": "hp", "away_points": "ap", "order": "wk", "margin": False}, games))
    expected = 1 / (1 + 10 ** (-55 / 400))
    detail = out(plain, 2, "games")
    assert detail["Home win probability"].iloc[0] == pytest.approx(expected)
    assert detail["Home Elo after"].iloc[0] == pytest.approx(1500 + 20 * (1 - expected))
    ratings = out(plain, 2, "ratings").set_index("Team")
    assert ratings.loc["A", "Elo"] == pytest.approx(1500 + 20 * (1 - expected))
    mov = out(run(single("elo", {"home": "home", "away": "away", "home_points": "hp", "away_points": "ap", "order": "wk"}, games)), 2, "games")
    mult = math.log(8) * (2.2 / (55 * 0.001 + 2.2))
    assert mov["Home Elo after"].iloc[0] == pytest.approx(1500 + 20 * mult * (1 - expected))
    seasons = "season,wk,home,away,hp,ap\n2024,1,A,B,40,0\n2025,1,A,B,10,7"
    sdetail = out(run(single("elo", {"home": "home", "away": "away", "home_points": "hp", "away_points": "ap", "order": "wk", "season": "season", "carryover": 0.5}, seasons)), 2, "games")
    end_2024 = sdetail["Home Elo after"].iloc[0]
    assert sdetail["Home Elo before"].iloc[1] == pytest.approx(1500 + 0.5 * (end_2024 - 1500))


def test_export_runs_wave2_standalone(tmp_path):
    engine_out, script_out = tmp_path / "engine.csv", tmp_path / "script.csv"
    games = "wk,home,away,hp,ap\n1,A,B,24,17\n1,C,D,14,21\n2,A,C,31,10\n2,B,D,28,27\n3,D,A,20,23\n3,B,C,17,14"
    nodes = [
        (1, "text_input", {"data": games}),
        (2, "team_ratings", {"home": "home", "away": "away", "home_points": "hp", "away_points": "ap"}),
        (3, "elo", {"home": "home", "away": "away", "home_points": "hp", "away_points": "ap", "order": "wk"}),
        (4, "join", {"keys": [{"left": "Team", "right": "Team"}]}),
        (5, "output", {"path": str(engine_out)}),
    ]
    edges = [(1, "out", 2, "in"), (1, "out", 3, "in"), (2, "ratings", 4, "left"), (3, "ratings", 4, "right"), (4, "join", 5, "in")]
    ev = Engine().evaluate(wf(nodes, edges), run_side_effects=True)
    assert all(r.status == "ok" for r in ev.results.values()), {k: r.error for k, r in ev.results.items()}
    code = export_script(ev, "ratings").replace(repr(str(engine_out)), repr(str(script_out)))
    script = tmp_path / "exported.py"
    script.write_text(code)
    subprocess.run([sys.executable, str(script)], check=True, cwd=tmp_path)
    pd.testing.assert_frame_equal(pd.read_csv(engine_out), pd.read_csv(script_out))
