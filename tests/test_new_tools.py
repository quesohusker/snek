import json
import subprocess
import sys

import pandas as pd
import pytest

from snek.codegen import export_script
from snek.engine import Engine

SCORES = "team,week,pts\nNebraska,1,20\nNebraska,2,34\nNebraska,3,27\nIowa,1,10\nIowa,2,31\nIowa,3,"


def workflow(nodes, edges):
    return {
        "nodes": [{"id": str(i), "type": t, "config": c} for i, t, c in nodes],
        "edges": [{"source": str(s), "sourceHandle": sh, "target": str(t), "targetHandle": th} for s, sh, t, th in edges],
    }


def chain(*steps, data=SCORES):
    nodes = [(1, "text_input", {"data": data})]
    edges = []
    for i, (t, c) in enumerate(steps, start=2):
        nodes.append((i, t, c))
        edges.append((i - 1, "out", i, "in"))
    return workflow(nodes, edges)


def run(wf, engine=None):
    return (engine or Engine()).evaluate(wf, run_side_effects=True)


def out(ev, node, port="out"):
    res = ev.results[str(node)]
    assert res.status == "ok", res.error
    return ev.frames[(str(node), port)]


def err(ev, node):
    res = ev.results[str(node)]
    assert res.status == "error"
    return res.error


def json_input(tmp_path, records, name="data.json"):
    path = tmp_path / name
    path.write_text(json.dumps(records))
    return (1, "input", {"path": str(path)})


def test_multirow_prior_value_by_group():
    df = out(run(chain(("multirow", {"column": "change", "expression": "[pts] - [Row-1:pts]", "group_by": ["team"]}))), 2)
    assert df["change"].tolist()[:3] == [pytest.approx(float("nan"), nan_ok=True), 14, -7]
    assert pd.isna(df["change"].iloc[3])
    assert df["change"].iloc[4] == 21
    nxt = out(run(chain(("multirow", {"column": "next_pts", "expression": "[Row+1:pts]", "outside": "zero"}))), 2)
    assert nxt["next_pts"].iloc[-1] == 0
    assert nxt["next_pts"].iloc[0] == 34


def test_multirow_unknown_column():
    assert "not in the input" in err(run(chain(("multirow", {"column": "x", "expression": "[Row-1:points]"}))), 2)


def test_running_total_and_rank():
    rt = out(run(chain(("running_total", {"columns": ["pts"], "group_by": ["team"]}))), 2)
    assert rt["RunTot_pts"].tolist()[:3] == [20, 54, 81]
    assert rt["RunTot_pts"].iloc[4] == 41
    rk = out(run(chain(("rank", {"column": "pts", "order": "desc", "method": "min", "group_by": ["team"]}))), 2)
    assert rk["Rank"].tolist()[:3] == [3, 1, 2]
    assert pd.isna(rk["Rank"].iloc[5])
    dense = out(run(chain(("rank", {"column": "week", "order": "asc", "method": "dense"}))), 2)
    assert dense["Rank"].tolist() == [1, 2, 3, 1, 2, 3]


def test_tile_quantiles_and_manual():
    q = out(run(chain(("tile", {"column": "pts", "mode": "count", "tiles": 2}))), 2)
    assert q["Tile"].tolist()[:5] == [1, 2, 1, 1, 2]
    manual = out(run(chain(("tile", {"column": "pts", "mode": "manual", "breaks": "20, 30"}))), 2)
    assert manual["Tile"].tolist()[:5] == [1, 3, 2, 1, 3]
    assert "numbers" in err(run(chain(("tile", {"column": "pts", "mode": "manual", "breaks": "a, b"}))), 2)


def test_select_records():
    df = out(run(chain(("select_records", {"ranges": "1-2, 5+"}))), 2)
    assert df["week"].tolist() == [1, 2, 2, 3]
    assert "Can't read" in err(run(chain(("select_records", {"ranges": "1-x"}))), 2)


def test_generate_rows():
    nums = out(run(workflow([(1, "generate_rows", {"mode": "number", "name": "week", "start": "1", "end": "5", "step": 2})], [])), 1)
    assert nums["week"].tolist() == [1, 3, 5]
    dates = out(run(workflow([(1, "generate_rows", {"mode": "date", "name": "day", "start": "2025-08-30", "end": "2025-09-01", "freq": "D"})], [])), 1)
    assert len(dates) == 3 and str(dates["day"].dtype).startswith("datetime64")
    halves = out(run(workflow([(1, "generate_rows", {"mode": "number", "start": "0", "end": "1", "step": 0.5})], [])), 1)
    assert halves["Value"].tolist() == [0.0, 0.5, 1.0]


def test_autofield_types(tmp_path):
    records = [
        {"yards": "350", "ypp": "5.2", "won": "true", "date": "2025-09-06", "zip": "02134", "pen": "2-25", "wk": "01"},
        {"yards": "412", "ypp": "6.1", "won": "false", "date": "2025-09-13", "zip": "68508", "pen": "5-40", "wk": "02"},
        {"yards": None, "ypp": "", "won": "true", "date": "2025-09-20", "zip": "10001", "pen": "3-30", "wk": "10"},
    ]
    wf = workflow([json_input(tmp_path, records), (2, "autofield", {})], [(1, "out", 2, "in")])
    df = out(run(wf), 2)
    assert str(df["yards"].dtype) == "Int64" and df["yards"].iloc[1] == 412
    assert df["ypp"].dtype == "float64" and pd.isna(df["ypp"].iloc[2])
    assert str(df["won"].dtype) == "boolean"
    assert str(df["date"].dtype).startswith("datetime64")
    assert not pd.api.types.is_numeric_dtype(df["zip"])
    assert not pd.api.types.is_numeric_dtype(df["pen"])
    assert df["wk"].tolist() == [1, 2, 10]


def test_multifield_formula():
    data = "a,b,c\n1.234,2.345,x\n3.456,4.567,y"
    df = out(run(chain(("multifield", {"columns": ["a", "b"], "expression": "[_CurrentField_].round(1)"}), data=data)), 2)
    assert df["a"].tolist() == [1.2, 3.5] and df["b"].tolist() == [2.3, 4.6]
    new = out(run(chain(("multifield", {"columns": ["a", "b"], "expression": "[_CurrentField_] * 10", "output": "new", "suffix": "_x10", "dtype": "Int64"}), data=data)), 2)
    assert new.columns.tolist() == ["a", "b", "c", "a_x10", "b_x10"]
    assert new["a_x10"].tolist() == [12, 35]


def test_imputation():
    data = "team,pts\nA,10\nA,\nB,30\nB,\nB,40"
    mean = out(run(chain(("impute", {"columns": ["pts"], "method": "mean", "flag": True}), data=data)), 2)
    assert mean["pts"].tolist() == [10, 80 / 3, 30, 80 / 3, 40]
    assert mean["Imputed_pts"].tolist() == [False, True, False, True, False]
    grouped = out(run(chain(("impute", {"columns": ["pts"], "method": "median", "group_by": ["team"]}), data=data)), 2)
    assert grouped["pts"].tolist() == [10, 10, 30, 35, 40]
    ff = out(run(chain(("impute", {"columns": ["pts"], "method": "ffill"}), data=data)), 2)
    assert ff["pts"].tolist() == [10, 10, 30, 30, 40]
    val = out(run(chain(("impute", {"columns": ["pts"], "method": "value", "value": "0"}), data=data)), 2)
    assert val["pts"].tolist() == [10, 0, 30, 0, 40]
    assert "numeric" in err(run(chain(("impute", {"columns": ["team"], "method": "mean"}), data=data)), 2)


def test_dynamic_rename():
    first = out(run(chain(("dynamic_rename", {"mode": "first_row"}), data="c1,c2\nTeam,Points\nNU,24")), 2)
    assert first.columns.tolist() == ["Team", "Points"] and first["Team"].tolist() == ["NU"]
    pre = out(run(chain(("dynamic_rename", {"mode": "prefix", "text": "home_", "columns": ["team", "pts"]}))), 2)
    assert pre.columns.tolist() == ["home_team", "week", "home_pts"]
    snake = out(run(chain(("dynamic_rename", {"mode": "case", "case": "snake"}), data="homeTeam,Away Points\nA,1")), 2)
    assert snake.columns.tolist() == ["home_team", "away_points"]
    assert "duplicate" in err(run(chain(("dynamic_rename", {"mode": "replace", "find": ".*", "replace": "x"}))), 2)


def test_dynamic_select_and_field_info():
    nums = out(run(chain(("dynamic_select", {"mode": "type", "types": ["numeric"]}))), 2)
    assert nums.columns.tolist() == ["week", "pts"]
    dropped = out(run(chain(("dynamic_select", {"mode": "pattern", "pattern": "^w", "action": "drop"}))), 2)
    assert dropped.columns.tolist() == ["team", "pts"]
    info = out(run(chain(("field_info", {}))), 2)
    assert info["Name"].tolist() == ["team", "week", "pts"]
    assert info["Nulls"].tolist() == [0, 0, 1]


def test_datetime_tool():
    data = "game,day\nA,09/06/2025\nB,11/29/2025"
    parsed = out(run(chain(("datetime", {"mode": "parse", "column": "day", "format": "%m/%d/%Y"}), data=data)), 2)
    assert parsed["day"].iloc[1] == pd.Timestamp("2025-11-29")
    name = out(run(chain(("datetime", {"mode": "extract", "column": "day", "part": "day_name"}), data=data)), 2)
    assert name["day_day_name"].tolist() == ["Saturday", "Saturday"]
    text = out(run(chain(("datetime", {"mode": "format", "column": "day", "format": "%Y-%m-%d", "name": "iso"}), data=data)), 2)
    assert text["iso"].tolist() == ["2025-09-06", "2025-11-29"]


def test_regex_tool():
    data = "team,pen\nNU,2-25\nIA,5-40\nOSU,"
    parsed = out(run(chain(("regex", {"column": "pen", "pattern": r"(\d+)-(\d+)", "mode": "parse"}), data=data)), 2)
    assert parsed[["pen_1", "pen_2"]].iloc[0].tolist() == ["2", "25"]
    named = out(run(chain(("regex", {"column": "pen", "pattern": r"(?P<count>\d+)-(?P<yards>\d+)", "mode": "parse"}), data=data)), 2)
    assert named["yards"].tolist()[:2] == ["25", "40"]
    match = out(run(chain(("regex", {"column": "team", "pattern": "nu|ia", "mode": "match", "case": False}), data=data)), 2)
    assert match["team_match"].tolist() == [True, True, False]
    rep = out(run(chain(("regex", {"column": "pen", "pattern": r"(\d+)-(\d+)", "mode": "replace", "replacement": r"\2 yds"}), data=data)), 2)
    assert rep["pen"].tolist()[:2] == ["25 yds", "40 yds"]
    rows = out(run(chain(("regex", {"column": "pen", "pattern": r"\d+", "mode": "tokenize", "into": "rows"}), data=data)), 2)
    assert rows["pen"].tolist()[:4] == ["2", "25", "5", "40"]
    cols = out(run(chain(("regex", {"column": "pen", "pattern": r"\d+", "mode": "tokenize", "into": "columns"}), data=data)), 2)
    assert cols["pen_2"].tolist()[:2] == ["25", "40"]
    assert "capture group" in err(run(chain(("regex", {"column": "pen", "pattern": r"\d+", "mode": "parse"}), data=data)), 2)
    assert "Bad regular expression" in err(run(chain(("regex", {"column": "pen", "pattern": "(", "mode": "match"}), data=data)), 2)


def test_json_parse(tmp_path):
    records = [{"id": 1, "raw": '{"plays": 77, "ppa": 0.15}'}, {"id": 2, "raw": "not json"}, {"id": 3, "raw": None}]
    wf = workflow([json_input(tmp_path, records), (2, "json_parse", {"column": "raw"})], [(1, "out", 2, "in")])
    df = out(run(wf), 2)
    assert df.columns.tolist() == ["id", "raw.plays", "raw.ppa"]
    assert df["raw.plays"].iloc[0] == 77 and pd.isna(df["raw.plays"].iloc[1])
    strict = workflow([json_input(tmp_path, records), (2, "json_parse", {"column": "raw", "strict": True})], [(1, "out", 2, "in")])
    assert "JSONDecodeError" in err(run(strict), 2)


def lookup_wf(cfg, data="team,pts\nNU,24\nia,20\nUSC,17", lookup="abbr,name,conf\nNU,Nebraska,Big Ten\nIA,Iowa,Big Ten"):
    return workflow(
        [(1, "text_input", {"data": data}), (2, "text_input", {"data": lookup}), (3, "find_replace", cfg)],
        [(1, "out", 3, "find"), (2, "out", 3, "lookup")],
    )


def test_find_replace_lookup():
    rep = out(run(lookup_wf({"column": "team", "key": "abbr", "mode": "replace", "value": "name"})), 3)
    assert rep["team"].tolist() == ["Nebraska", "ia", "USC"]
    nocase = out(run(lookup_wf({"column": "team", "key": "abbr", "mode": "replace", "value": "name", "case": False})), 3)
    assert nocase["team"].tolist() == ["Nebraska", "Iowa", "USC"]
    app = out(run(lookup_wf({"column": "team", "key": "abbr", "mode": "append", "append": ["conf"]})), 3)
    assert app.columns.tolist() == ["team", "pts", "conf"]
    assert app["conf"].tolist()[0] == "Big Ten" and pd.isna(app["conf"].iloc[1])
    app2 = out(run(lookup_wf({"column": "team", "key": "abbr", "mode": "append", "append": ["conf"], "case": False})), 3)
    assert app2["conf"].tolist()[:2] == ["Big Ten", "Big Ten"]


def test_join_multiple():
    a, b, c = "id,x\n1,a\n2,b", "id,y\n1,c\n3,d", "id,z\n1,e\n2,f"
    nodes = [(1, "text_input", {"data": a}), (2, "text_input", {"data": b}), (3, "text_input", {"data": c}), (4, "join_multiple", {"keys": ["id"], "how": "inner"}), (5, "join_multiple", {"keys": ["id"], "how": "outer"})]
    edges = [(n, "out", t, "in") for t in (4, 5) for n in (1, 2, 3)]
    ev = run(workflow(nodes, edges))
    assert out(ev, 4).values.tolist() == [[1, "a", "c", "e"]]
    assert sorted(out(ev, 5)["id"].tolist()) == [1, 2, 3]


def test_directory_and_dynamic_input(tmp_path):
    (tmp_path / "w1.csv").write_text("a\n1\n")
    (tmp_path / "w2.csv").write_text("a\n2\n3\n")
    (tmp_path / "notes.txt").write_text("x")
    engine = Engine()
    wf = workflow([(1, "directory", {"folder": str(tmp_path), "pattern": "*.csv"}), (2, "dynamic_input", {"column": "path"})], [(1, "out", 2, "in")])
    ev = run(wf, engine)
    assert out(ev, 1)["name"].tolist() == ["w1.csv", "w2.csv"]
    stacked = out(ev, 2)
    assert stacked["FileName"].tolist() == ["w1.csv", "w2.csv", "w2.csv"]
    (tmp_path / "w3.csv").write_text("a\n4\n")
    again = run(wf, engine)
    assert not again.results["1"].cached
    assert len(out(again, 2)) == 4


def test_date_time_now_is_never_cached():
    engine = Engine()
    wf = workflow([(1, "now", {})], [])
    run(wf, engine)
    second = run(wf, engine)
    assert second.results["1"].executed and not second.results["1"].cached
    assert len(out(second, 1)) == 1


def test_weighted_average_and_count():
    data = "team,ypp,plays\nA,5,10\nA,8,30\nB,4,\nB,6,20"
    wa = out(run(chain(("weighted_avg", {"value": "ypp", "weight": "plays", "group_by": ["team"], "name": "wypp"}), data=data)), 2)
    assert wa.set_index("team")["wypp"].to_dict() == {"A": 7.25, "B": 6.0}
    total = out(run(chain(("weighted_avg", {"value": "ypp", "weight": "plays"}), data=data)), 2)
    assert total["WeightedAverage"].iloc[0] == pytest.approx((50 + 240 + 120) / 60)
    assert out(run(chain(("count_records", {}), data=data)), 2)["Count"].tolist() == [4]


def test_export_runs_new_tools_standalone(tmp_path):
    (tmp_path / "games").mkdir()
    for i, rows in enumerate([[("NU", "2-25", '{"plays": 70}', "24"), ("IA", "5-40", '{"plays": 60}', "")], [("NU", "1-5", '{"plays": 65}', "31")]], start=1):
        (tmp_path / "games" / f"w{i}.csv").write_text("team,pen,adv,pts\n" + "\n".join(f'{t},{p},"{a.replace(chr(34), chr(34) * 2)}",{s}' for t, p, a, s in rows))
    engine_out = tmp_path / "engine.csv"
    script_out = tmp_path / "script.csv"
    nodes = [
        (1, "directory", {"folder": str(tmp_path / "games"), "pattern": "*.csv"}),
        (2, "dynamic_input", {"column": "path"}),
        (3, "regex", {"column": "pen", "pattern": r"(?P<pen_count>\d+)-(?P<pen_yards>\d+)", "mode": "parse"}),
        (4, "autofield", {}),
        (5, "json_parse", {"column": "adv", "prefix": False}),
        (6, "impute", {"columns": ["pts"], "method": "value", "value": "0"}),
        (7, "multirow", {"column": "prev_pts", "expression": "[Row-1:pts]", "group_by": ["team"], "outside": "zero"}),
        (8, "running_total", {"columns": ["pen_yards"], "group_by": ["team"]}),
        (9, "rank", {"column": "pts", "order": "desc"}),
        (10, "weighted_avg", {"value": "pen_yards", "weight": "plays", "group_by": ["team"]}),
        (11, "output", {"path": str(engine_out)}),
    ]
    edges = [(i, "out", i + 1, "in") for i in range(1, 10)] + [(10, "out", 11, "in")]
    ev = Engine().evaluate(workflow(nodes, edges), run_side_effects=True)
    problems = {k: r.error for k, r in ev.results.items() if r.status != "ok"}
    assert not problems, problems
    code = export_script(ev, "new tools").replace(repr(str(engine_out)), repr(str(script_out)))
    for helper in ("def list_files", "def read_many", "def auto_type", "def parse_json", "def weighted_average", "import json"):
        assert helper in code, helper
    script = tmp_path / "exported.py"
    script.write_text(code)
    subprocess.run([sys.executable, str(script)], check=True, cwd=tmp_path)
    pd.testing.assert_frame_equal(pd.read_csv(engine_out), pd.read_csv(script_out))
