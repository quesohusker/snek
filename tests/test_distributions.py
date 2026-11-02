import json
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from snek import distributions
from snek.codegen import export_script
from snek.engine import Engine


def run(nodes, edges=()):
    wf = {"nodes": [{"id": str(i), "type": t, "config": c} for i, t, c in nodes], "edges": [{"source": str(s), "sourceHandle": sh, "target": str(t), "targetHandle": th} for s, sh, t, th in edges]}
    return Engine().evaluate(wf, run_side_effects=True)


def generate(dist, p, rows=60000, seed=5, name="x"):
    cols = [{"name": name, "dist": dist, "p1": p[0] if len(p) > 0 else "", "p2": p[1] if len(p) > 1 else "", "p3": p[2] if len(p) > 2 else "", "choices": ""}]
    ev = run([(1, "random_data", {"rows": rows, "seed": seed, "columns": cols})])
    assert ev.results["1"].status == "ok", ev.results["1"].error
    return ev.frames[("1", "out")]


MOMENTS = [
    ("normal", [10, 2], 10, 2),
    ("lognormal", [1, 0.5], np.exp(1 + 0.125), np.sqrt((np.exp(0.25) - 1) * np.exp(2 + 0.25))),
    ("exponential", [30], 30, 30),
    ("gamma", [3, 10], 30, np.sqrt(3) * 10),
    ("weibull", [2, 10], 10 * 0.886227, 10 * np.sqrt(1 - np.pi / 4)),
    ("uniform", [2, 8], 5, 6 / np.sqrt(12)),
    ("triangular", [0, 2, 10], 4, np.sqrt((0 + 4 + 100 - 0 - 0 - 20) / 18)),
    ("logistic", [5, 2], 5, 2 * np.pi / np.sqrt(3)),
    ("beta", [2, 5], 2 / 7, np.sqrt(10 / (49 * 8))),
    ("poisson", [4], 4, 2),
    ("geometric", [0.25], 4, np.sqrt(0.75) / 0.25),
    ("negative_binomial", [5, 0.5], 5, np.sqrt(10)),
    ("binomial", [20, 0.3], 6, np.sqrt(4.2)),
    ("integer_uniform", [1, 6], 3.5, np.sqrt(35 / 12)),
    ("constant", [7], 7, 0),
]


@pytest.mark.parametrize("dist,p,mean,sd", MOMENTS)
def test_each_distribution_has_the_right_mean_and_spread(dist, p, mean, sd):
    x = generate(dist, p)["x"]
    assert x.mean() == pytest.approx(mean, rel=0.03, abs=0.03)
    assert x.std() == pytest.approx(sd, rel=0.04, abs=0.03)


def test_same_seed_same_numbers_and_different_seed_differs():
    a, b, c = generate("normal", [0, 1], 100, 3), generate("normal", [0, 1], 100, 3), generate("normal", [0, 1], 100, 4)
    pd.testing.assert_frame_equal(a, b)
    assert not a.equals(c)


def test_choice_column_follows_the_weights():
    cols = [{"name": "size", "dist": "choice", "choices": "small:0.5, medium:0.3, large:0.2"}, {"name": "even", "dist": "choice", "choices": "a, b"}]
    ev = run([(1, "random_data", {"rows": 40000, "seed": 2, "columns": cols})])
    df = ev.frames[("1", "out")]
    shares = df["size"].value_counts(normalize=True)
    assert shares["small"] == pytest.approx(0.5, abs=0.02) and shares["large"] == pytest.approx(0.2, abs=0.02)
    assert df["even"].value_counts(normalize=True)["a"] == pytest.approx(0.5, abs=0.02)


@pytest.mark.parametrize("col,message", [
    ({"name": "x", "dist": "normal", "p1": 0, "p2": -1}, "not valid"),
    ({"name": "x", "dist": "normal", "p1": 0}, "Number 2"),
    ({"name": "", "dist": "normal", "p1": 0, "p2": 1}, "needs a name"),
    ({"name": "x", "dist": "choice", "choices": ""}, "Enter the choices"),
    ({"name": "x", "dist": "triangular", "p1": 5, "p2": 1, "p3": 9}, "not valid"),
    ({"name": "x", "dist": "geometric", "p1": 1.5}, "not valid"),
])
def test_bad_settings_give_plain_messages(col, message):
    res = run([(1, "random_data", {"rows": 10, "columns": [col]})]).results["1"]
    assert res.status == "error" and message in res.error


FITS = [
    ("gamma", [3, 10], "gamma"),
    ("lognormal", [1, 0.6], "lognormal"),
    ("weibull", [2.5, 10], "weibull"),
    ("exponential", [30], "exponential"),
    ("normal", [50, 8], "normal"),
    ("uniform", [2, 8], "uniform"),
    ("beta", [2, 5], "beta"),
    ("poisson", [4], "poisson"),
    ("geometric", [0.25], "geometric"),
    ("negative_binomial", [5, 0.3], "negative_binomial"),
]


@pytest.mark.parametrize("dist,p,expected", FITS)
def test_the_true_family_ranks_first(dist, p, expected):
    df = generate(dist, p, rows=8000)
    fits, chart = distributions.fit_distribution(df, "x")
    if dist == "exponential":
        close = fits[fits["distribution"] == "exponential"].iloc[0]
        assert close["delta_aic"] < 4 and fits.loc[0, "distribution"] in ("exponential", "gamma", "weibull")
        assert close["p1"] == pytest.approx(30, rel=0.05)
    else:
        assert fits.loc[0, "distribution"] == expected and fits.loc[0, "rank"] == 1
    assert fits["akaike_weight"].sum() == pytest.approx(1.0)
    usable = fits[fits["note"] == ""]
    assert usable["aic"].is_monotonic_increasing and usable["delta_aic"].iloc[0] == 0


@pytest.mark.parametrize("dist,p", [("gamma", [3, 10]), ("lognormal", [1, 0.6]), ("weibull", [2.5, 10]), ("normal", [50, 8]), ("beta", [2, 5]), ("poisson", [4])])
def test_fitted_numbers_come_back_close_to_the_true_ones(dist, p):
    fits, _ = distributions.fit_distribution(generate(dist, p, rows=20000), "x")
    row = fits[fits["distribution"] == dist].iloc[0]
    assert row["p1"] == pytest.approx(p[0], rel=0.05)
    if len(p) > 1:
        assert row["p2"] == pytest.approx(p[1], rel=0.05)


def test_triangular_and_logistic_are_in_the_running():
    for dist, p in [("triangular", [0, 2, 10]), ("logistic", [5, 2])]:
        fits, _ = distributions.fit_distribution(generate(dist, p, rows=8000), "x")
        assert dist in fits["distribution"].head(2).tolist()


def test_goodness_of_fit_says_the_right_one_is_plausible():
    fits, _ = distributions.fit_distribution(generate("gamma", [3, 10], rows=3000), "x")
    best, worst = fits.iloc[0], fits[fits["note"] == ""].iloc[-1]
    assert best["ks_p"] > 0.01 and worst["ks_p"] < 1e-6 and best["ks_stat"] < worst["ks_stat"]


def test_families_that_cannot_fit_are_listed_with_a_reason():
    df = pd.DataFrame({"x": np.random.default_rng(1).normal(0, 1, 500)})
    fits, _ = distributions.fit_distribution(df, "x")
    skipped = fits[fits["note"] != ""].set_index("distribution")["note"]
    assert "above 0" in skipped["lognormal"] and "above 0" in skipped["gamma"] and "0 or more" in skipped["exponential"] and "0 to 1" in skipped["beta"]
    assert fits[fits["note"] != ""]["rank"].isna().all()


def test_kind_and_size_checks():
    df = pd.DataFrame({"x": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]})
    with pytest.raises(ValueError, match="whole numbers"):
        distributions.fit_distribution(df, "x", kind="discrete")
    with pytest.raises(ValueError, match="at least 8"):
        distributions.fit_distribution(df.head(5), "x")
    wide = distributions.fit_distribution(pd.DataFrame({"x": list(range(1, 400))}), "x")[0]
    assert wide.loc[0, "kind"] == "continuous"
    counts = distributions.fit_distribution(pd.DataFrame({"x": [0, 1, 1, 2, 2, 2, 3, 3, 4, 5] * 5}), "x")[0]
    assert counts.loc[0, "kind"] == "discrete"


def test_chart_output_is_a_vega_lite_layer_spec():
    for dist, p in [("gamma", [3, 10]), ("poisson", [4])]:
        _, chart = distributions.fit_distribution(generate(dist, p, rows=2000), "x", top=2)
        spec = json.loads(chart.loc[0, "Vega-Lite"])
        assert len(spec["layer"]) == 2 and spec["layer"][1]["encoding"]["color"]["field"] == "fit"
        assert len({row["fit"] for row in spec["layer"][1]["data"]["values"]}) == 2


def test_connecting_a_fit_makes_random_data_from_the_best_fit():
    ev = run(
        [(1, "random_data", {"rows": 20000, "seed": 1, "columns": [{"name": "t", "dist": "gamma", "p1": 3, "p2": 10}]}), (2, "fit_distribution", {"column": "t"}), (3, "random_data", {"rows": 20000, "seed": 9, "fit_name": "again"})],
        [(1, "out", 2, "in"), (2, "fits", 3, "fit")],
    )
    assert all(r.status == "ok" for r in ev.results.values()), [r.error for r in ev.results.values()]
    first, again = ev.frames[("1", "out")]["t"], ev.frames[("3", "out")]["again"]
    assert again.mean() == pytest.approx(first.mean(), rel=0.03) and again.std() == pytest.approx(first.std(), rel=0.05)
    bad = run([(1, "random_data", {"rows": 20000, "columns": [{"name": "t", "dist": "gamma", "p1": 3, "p2": 10}]}), (2, "fit_distribution", {"column": "t"}), (3, "random_data", {"rows": 5, "fit_rank": 40})], [(1, "out", 2, "in"), (2, "fits", 3, "fit")])
    assert "Rank 40" in bad.results["3"].error


def test_fit_tool_checks_its_column():
    ev = run([(1, "text_input", {"data": "a,b\nx,1\n"}), (2, "fit_distribution", {"column": "a"})], [(1, "out", 2, "in")])
    assert ev.results["2"].status == "error" and "not numeric" in ev.results["2"].error


def test_export_runs_and_matches(tmp_path):
    out = tmp_path / "fits.csv"
    nodes = [
        (1, "random_data", {"rows": 3000, "seed": 4, "columns": [{"name": "t", "dist": "weibull", "p1": 2, "p2": 5}]}),
        (2, "fit_distribution", {"column": "t"}),
        (3, "random_data", {"rows": 50, "seed": 8, "fit_name": "again"}),
        (4, "output", {"path": str(out)}),
    ]
    ev = run(nodes, [(1, "out", 2, "in"), (2, "fits", 3, "fit"), (3, "out", 4, "in")])
    assert all(r.status == "ok" for r in ev.results.values()), [r.error for r in ev.results.values()]
    engine_df = pd.read_csv(out)
    script = export_script(ev)
    assert "def fit_distribution(" in script and "FAMILIES = " in script and "Requires pandas, numpy, scipy" in script
    (tmp_path / "flow.py").write_text(script, encoding="utf-8")
    out.unlink()
    subprocess.run([sys.executable, str(tmp_path / "flow.py")], check=True, cwd=tmp_path)
    pd.testing.assert_frame_equal(pd.read_csv(out), engine_df)
