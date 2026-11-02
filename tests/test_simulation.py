import math
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from snek.codegen import export_script
from snek.engine import Engine
from snek.simulation import simulate_process


def station(name, servers=1, capacity=None, dist="constant", p=(1,), next="", block=False, scale_by=""):
    spec = {"name": name, "servers": servers, "dist": dist, "next": next, "block": block, "scale_by": scale_by}
    for key, value in zip(("p1", "p2", "p3"), p):
        spec[key] = value
    if capacity is not None:
        spec["capacity"] = capacity
    return spec


def arrivals(times, **attrs):
    return pd.DataFrame({"arrival_time": times, **attrs})


def summary(result, metric, where="system"):
    s = result[3]
    return s[(s["metric"] == metric) & (s["station"] == where)].iloc[0]


def test_blocking_tandem_matches_a_hand_calculation():
    ent, vis, sta, _, log = simulate_process(arrivals([0, 1, 2]), [station("A", p=(2,), next="B", block=True), station("B", capacity=0, p=(5,))], keep_log=True)
    assert ent["exit_time"].tolist() == [7, 12, 17] and ent["time_in_system"].tolist() == [7, 11, 15]
    assert ent["total_wait"].tolist() == [0, 1, 5] and ent["total_blocked"].tolist() == [0, 3, 3]
    assert ent["outcome"].tolist() == ["served"] * 3
    a = sta.set_index("station")
    assert a.loc["A", "utilization"] == pytest.approx(6 / 17) and a.loc["A", "blocked_share"] == pytest.approx(6 / 17)
    assert a.loc["B", "utilization"] == pytest.approx(15 / 17) and a.loc["A", "max_queue"] == 2
    assert {"arrive", "start service", "end service", "blocked", "depart"} <= set(log["event"])
    b = vis[vis["station"] == "B"].sort_values("entity_id")
    assert b["start"].tolist() == [2, 7, 12]


def test_without_blocking_an_entity_is_lost_when_the_next_station_is_full():
    ent, *_ = simulate_process(arrivals([0, 1, 2]), [station("A", p=(2,), next="B"), station("B", capacity=0, p=(5,))])
    assert ent["outcome"].tolist() == ["served", "lost at B", "lost at B"]
    assert ent["exit_time"].tolist() == [7, 4, 6]


def test_a_full_entry_queue_loses_arrivals():
    ent, _, sta, *_ = simulate_process(arrivals([0, 0, 0, 0]), [station("A", capacity=1, p=(10,))])
    assert ent["outcome"].tolist() == ["served", "served", "lost at A", "lost at A"]
    assert sta.loc[0, "lost"] == 2 and sta.loc[0, "max_queue"] == 1


def test_a_schedule_changes_the_number_of_servers():
    schedule = pd.DataFrame({"station": ["A"], "time": [5], "servers": [4]})
    _, vis, *_ = simulate_process(arrivals([0, 0, 0, 0]), [station("A", p=(10,))], schedule=schedule)
    assert sorted(vis["start"].tolist()) == [0, 5, 5, 5]


def test_service_time_scales_with_an_attribute():
    _, vis, *_ = simulate_process(arrivals([0, 100, 200], size=[1, 2, 3]), [station("A", p=(10,), scale_by="size")])
    assert vis["service"].tolist() == [10, 20, 30]


def test_routing_weights_split_the_flow():
    ent, vis, *_ = simulate_process(arrivals(list(range(0, 4000, 2))), [station("A", servers=5, p=(1,), next="B:0.7, C:0.3, Exit:0"), station("B", servers=5), station("C", servers=5)], seed=3)
    counts = vis["station"].value_counts()
    assert counts["B"] / len(ent) == pytest.approx(0.7, abs=0.04) and counts["C"] / len(ent) == pytest.approx(0.3, abs=0.04)


def test_warmup_entities_are_flagged_and_left_out_of_the_statistics():
    ent, _, sta, summ, _ = simulate_process(arrivals([0, 10, 20, 30]), [station("A", p=(1,))], warmup=15)
    assert ent["warmup"].tolist() == [True, True, False, False]
    assert sta.loc[0, "arrivals"] == 2 and summary((None, None, None, summ), "arrivals")["mean"] == 2


def test_entities_still_inside_at_the_end_are_unfinished():
    ent, *_ = simulate_process(arrivals([0, 1]), [station("A", p=(10,))], until=5)
    assert ent["outcome"].tolist() == ["unfinished", "unfinished"] and ent["time_in_system"].isna().all()


def test_generated_arrivals_and_ids():
    ent, *_ = simulate_process(None, [station("A", p=(1,))], gap={"dist": "constant", "params": [10]}, until=100)
    assert ent["arrival_time"].tolist() == list(np.arange(10, 101, 10)) and ent["entity_id"].tolist() == list(range(1, 11))
    custom = arrivals([5, 1], tag=["late", "early"], car=["b", "a"])
    ent, *_ = simulate_process(custom, [station("A", p=(1,))], id_column="car")
    assert ent["entity_id"].tolist() == ["a", "b"] and ent["tag"].tolist() == ["early", "late"]


def test_same_seed_gives_the_same_run_and_replications_differ():
    run = lambda seed: simulate_process(None, [station("A", dist="exponential", p=(5,))], gap={"dist": "exponential", "params": [8]}, until=2000, replications=3, seed=seed)
    a, b, c = run(4), run(4), run(5)
    pd.testing.assert_frame_equal(a[0], b[0])
    pd.testing.assert_frame_equal(a[3], b[3])
    assert not a[3]["mean"].equals(c[3]["mean"])
    per = a[2].groupby("replication")["avg_wait"].first()
    assert per.nunique() == 3


def within(result, metric, where, expected):
    row = summary(result, metric, where)
    assert row["ci_low"] <= expected <= row["ci_high"], (metric, expected, row["mean"], row["ci_low"], row["ci_high"])
    return row["mean"]


def test_mm1_queue_matches_theory():
    lam, mu = 1 / 10, 1 / 5
    rho = lam / mu
    result = simulate_process(None, [station("A", dist="exponential", p=(1 / mu,))], gap={"dist": "exponential", "params": [1 / lam]}, until=60000, warmup=3000, replications=20, seed=11)
    within(result, "avg_wait", "A", rho / (mu - lam))
    within(result, "avg_queue", "A", rho**2 / (1 - rho))
    within(result, "utilization", "A", rho)


def test_mm2_queue_matches_erlang_c():
    lam, mu, c = 0.15, 0.1, 2
    a = lam / mu
    top = a**c / math.factorial(c) * (1 / (1 - a / c))
    wait_chance = top / (sum(a**k / math.factorial(k) for k in range(c)) + top)
    result = simulate_process(None, [station("A", servers=c, dist="exponential", p=(1 / mu,))], gap={"dist": "exponential", "params": [1 / lam]}, until=60000, warmup=3000, replications=20, seed=12)
    within(result, "avg_wait", "A", wait_chance / (c * mu - lam))
    within(result, "utilization", "A", a / c)


def test_mm1k_loss_rate_matches_theory():
    lam, mu, k = 0.1, 1 / 8, 5
    rho = lam / mu
    loss = (1 - rho) * rho**k / (1 - rho ** (k + 1))
    result = simulate_process(None, [station("A", capacity=k - 1, dist="exponential", p=(1 / mu,))], gap={"dist": "exponential", "params": [1 / lam]}, until=60000, warmup=3000, replications=20, seed=13)
    within(result, "loss_rate", "system", loss)


def test_time_varying_rates():
    rates = pd.DataFrame({"start": [0, 5000], "mean_gap": [10, 2]})
    ent, *_ = simulate_process(None, [station("A", servers=50, p=(1,))], rates=rates, until=10000, seed=2)
    early, late = (ent["arrival_time"] < 5000).sum(), (ent["arrival_time"] >= 5000).sum()
    assert early == pytest.approx(500, rel=0.12) and late == pytest.approx(2500, rel=0.06)


def test_event_log_cap_warns():
    with pytest.warns(UserWarning, match="event log stopped"):
        *_, log = simulate_process(arrivals(list(range(50))), [station("A", p=(0.5,))], keep_log=True, max_log=20)
    assert len(log) == 20


@pytest.mark.parametrize("kwargs,message", [
    ({"stations": [station("A", next="Zed")]}, "not in the list"),
    ({"stations": [station("A"), station("a")]}, "same name"),
    ({"stations": [station("A:B")]}, "colon"),
    ({"stations": []}, "at least one station"),
    ({"stations": [station("A", next="A")]}, "more than 1000 stations"),
    ({"stations": [station("A")], "schedule": pd.DataFrame({"station": ["Q"], "time": [1], "servers": [2]})}, "schedule names a station"),
    ({"stations": [station("A")], "schedule": pd.DataFrame({"station": ["A"]})}, "needs a column"),
    ({"stations": [station("A", scale_by="nope")]}, "no column named nope"),
    ({"stations": [station("A")], "arrivals": pd.DataFrame({"when": [1]})}, "needs a column named arrival_time"),
    ({"stations": [station("A")], "arrivals": None, "gap": None}, "Connect an arrivals table"),
    ({"stations": [station("A")], "arrivals": None, "gap": {"dist": "constant", "params": [1]}}, "Set the run length"),
    ({"stations": [station("A")], "warmup": 50, "until": 10}, "shorter than the run length"),
])
def test_bad_models_give_plain_messages(kwargs, message):
    args = {"arrivals": arrivals([0, 1]), **kwargs}
    with pytest.raises(ValueError, match=message):
        simulate_process(args.pop("arrivals"), args.pop("stations"), **args)


def run_tool(cfg, extra_nodes=(), edges=()):
    nodes = [{"id": "9", "type": "simulate_process", "config": cfg}, *extra_nodes]
    wf = {"nodes": nodes, "edges": [{"source": s, "sourceHandle": sh, "target": t, "targetHandle": th} for s, sh, t, th in edges]}
    ev = Engine().evaluate(wf, run_side_effects=True)
    return ev, ev.results["9"]


def test_tool_runs_without_any_input_and_checks_its_settings():
    base = {"stations": [{"name": "Order", "servers": 1, "dist": "exponential", "p1": 20}], "gap_dist": "exponential", "gap_p1": 30, "until": 1000}
    ev, res = run_tool(base)
    assert res.status == "ok", res.error
    assert len(ev.frames[("9", "entities")]) > 10 and set(ev.frames[("9", "summary")]["metric"]) >= {"avg_wait", "utilization", "loss_rate"}
    for change, message in [
        ({"stations": [{"name": "A", "dist": "normal", "p1": 5}]}, "Number 2"),
        ({"stations": [{"name": "A", "dist": "normal", "p1": 5, "p2": -1}]}, "not valid"),
        ({"stations": [{"name": "A", "dist": "constant", "p1": 5, "next": "Q"}]}, "not in the list"),
        ({"until": ""}, "Set the run length"),
        ({"warmup": 5000}, "Warm-up"),
        ({"replications": 0}, "Replications"),
        ({"gap_p1": ""}, "Time between arrivals"),
    ]:
        assert message in run_tool({**base, **change})[1].error


def test_tool_reads_arrivals_schedule_and_rates_tables():
    stations = [{"name": "Order", "servers": 1, "dist": "constant", "p1": 10}]
    nodes = [
        {"id": "1", "type": "text_input", "config": {"data": "when,size\n0,1\n0,2\n0,3\n"}},
        {"id": "2", "type": "text_input", "config": {"data": "station,time,servers\nOrder,5,3\n"}},
    ]
    edges = [("1", "out", "9", "arrivals"), ("2", "out", "9", "schedule")]
    ev, res = run_tool({"stations": stations, "time_column": "when", "id_column": "", "until": ""}, nodes, edges)
    assert res.status == "ok", res.error
    assert sorted(ev.frames[("9", "visits")]["start"]) == [0, 5, 5]
    assert "time_column" in res.code or "when" in res.code
    _, res = run_tool({"stations": stations, "time_column": "nope"}, nodes, edges)
    assert res.status == "error" and "nope" in res.error
    bad = [{"id": "3", "type": "text_input", "config": {"data": "a,b\n1,2\n"}}]
    _, res = run_tool({"stations": stations, "until": 100}, bad, [("3", "out", "9", "schedule")])
    assert res.status == "error" and "station, time and servers" in res.error
    _, res = run_tool({"stations": stations, "until": 100}, bad, [("3", "out", "9", "rates")])
    assert res.status == "error" and "start and mean_gap" in res.error


def test_make_arrivals_tool_with_rates_and_attributes():
    nodes = [
        {"id": "1", "type": "text_input", "config": {"data": "start,mean_gap\n0,10\n1000,5\n"}},
        {"id": "2", "type": "make_arrivals", "config": {"until": 2000, "seed": 3, "attributes": [{"name": "size", "dist": "choice", "choices": "S:0.5, L:0.5"}]}},
    ]
    ev = Engine().evaluate({"nodes": nodes, "edges": [{"source": "1", "sourceHandle": "out", "target": "2", "targetHandle": "rates"}]}, run_side_effects=True)
    assert ev.results["2"].status == "ok", ev.results["2"].error
    df = ev.frames[("2", "out")]
    assert list(df.columns) == ["entity_id", "arrival_time", "size"] and df["arrival_time"].is_monotonic_increasing
    assert (df["arrival_time"] < 1000).sum() == pytest.approx(100, rel=0.3) and (df["arrival_time"] >= 1000).sum() == pytest.approx(200, rel=0.25)
    bad = Engine().evaluate({"nodes": [{"id": "1", "type": "make_arrivals", "config": {"until": 0}}], "edges": []}, run_side_effects=True)
    assert "above 0" in bad.results["1"].error


def test_export_runs_headless_and_gives_the_same_numbers(tmp_path):
    out = tmp_path / "summary.csv"
    wf = {
        "nodes": [
            {"id": "1", "type": "make_arrivals", "config": {"until": 1500, "gap_dist": "exponential", "gap_p1": 30, "seed": 5, "attributes": [{"name": "items", "dist": "poisson", "p1": 3}]}},
            {"id": "2", "type": "simulate_process", "config": {"until": 1500, "warmup": 100, "replications": 3, "seed": 6, "stations": [
                {"name": "Order", "servers": 1, "capacity": 4, "dist": "triangular", "p1": 10, "p2": 20, "p3": 40, "block": True, "next": "Window"},
                {"name": "Window", "servers": 1, "dist": "gamma", "p1": 4, "p2": 5, "scale_by": "items"}]}},
            {"id": "3", "type": "output", "config": {"path": str(out)}},
        ],
        "edges": [
            {"source": "1", "sourceHandle": "out", "target": "2", "targetHandle": "arrivals"},
            {"source": "2", "sourceHandle": "summary", "target": "3", "targetHandle": "in"},
        ],
    }
    ev = Engine().evaluate(wf, run_side_effects=True)
    assert all(r.status == "ok" for r in ev.results.values()), [r.error for r in ev.results.values()]
    engine_df = pd.read_csv(out)
    script = export_script(ev)
    assert "class Sim" in script and "def simulate_process(" in script and "import heapq" in script
    (tmp_path / "flow.py").write_text(script, encoding="utf-8")
    out.unlink()
    subprocess.run([sys.executable, str(tmp_path / "flow.py")], check=True, cwd=tmp_path)
    pd.testing.assert_frame_equal(pd.read_csv(out), engine_df)
