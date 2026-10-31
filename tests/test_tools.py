import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from snek.codegen import export_script
from snek.engine import Engine
from snek.expr import ExprError, translate

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples" / "data"

GAMES = "team,opp,pts,opp_pts,conf\nNebraska,Iowa,24,20,Big Ten\nIowa,Nebraska,20,24,Big Ten\n Ohio State ,Michigan,42,27,Big Ten\nBoise State,Utah State,,10,Mountain West\nNebraska,Akron,68,0,Big Ten"


def workflow(nodes, edges):
    return {
        "nodes": [{"id": str(i), "type": t, "config": c} for i, t, c in nodes],
        "edges": [{"source": str(s), "sourceHandle": sh, "target": str(t), "targetHandle": th} for s, sh, t, th in edges],
    }


def chain(*steps, data=GAMES):
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


def test_filter_basic_numeric():
    ev = run(chain(("filter", {"column": "pts", "operator": ">", "value": "21"})))
    assert out(ev, 2, "true")["team"].tolist() == ["Nebraska", " Ohio State ", "Nebraska"]
    assert len(out(ev, 2, "false")) == 2


def test_filter_null_goes_false():
    ev = run(chain(("filter", {"column": "pts", "operator": "<", "value": "100"})))
    assert "Boise State" in out(ev, 2, "false")["team"].tolist()


def test_filter_contains_case_insensitive_and_in_list():
    ev = run(chain(("filter", {"column": "team", "operator": "contains", "value": "ohio"})))
    assert out(ev, 2, "true")["team"].str.strip().tolist() == ["Ohio State"]
    ev = run(chain(("filter", {"column": "opp", "operator": "in", "value": "Iowa, Akron"})))
    assert out(ev, 2, "true")["opp"].tolist() == ["Iowa", "Akron"]


def test_filter_isna_and_expression():
    ev = run(chain(("filter", {"column": "pts", "operator": "isna"})))
    assert out(ev, 2, "true")["team"].tolist() == ["Boise State"]
    ev = run(chain(("filter", {"mode": "expression", "expression": "([pts] > [opp_pts]) & ([conf] == 'Big Ten')"})))
    assert len(out(ev, 2, "true")) == 3


def test_filter_bad_number_is_clear():
    ev = run(chain(("filter", {"column": "pts", "operator": ">", "value": "abc"})))
    assert "not a number" in err(ev, 2)


def test_formula_chain_iif_and_type():
    ev = run(chain(("formula", {"formulas": [
        {"column": "margin", "expression": "[pts] - [opp_pts]", "dtype": "Int64"},
        {"column": "result", "expression": "iif([margin] > 0, 'W', 'L')"},
        {"column": "Team Upper", "expression": "[team].str.strip().str.upper()"},
    ]})))
    df = out(ev, 2)
    assert df["margin"].dtype == "Int64"
    assert df["margin"].tolist()[:3] == [4, -4, 15]
    assert pd.isna(df["margin"].iloc[3])
    assert df["result"].tolist() == ["W", "L", "W", "L", "W"]
    assert df["Team Upper"].iloc[2] == "OHIO STATE"


def test_formula_unknown_column_suggests():
    ev = run(chain(("formula", {"formulas": [{"column": "x", "expression": "[point] + 1"}]})))
    assert "Unknown column [point]" in err(ev, 2)
    assert "[pts]" in err(ev, 2) or "[opp_pts]" in err(ev, 2)


def test_formula_does_not_mutate_upstream():
    engine = Engine()
    wf = chain(("formula", {"formulas": [{"column": "pts", "expression": "[pts] * 0"}]}))
    ev = run(wf, engine)
    assert out(ev, 1)["pts"].iloc[0] == 24
    assert out(ev, 2)["pts"].iloc[0] == 0


def test_python_tool_cannot_mutate_cache():
    engine = Engine()
    wf = workflow(
        [(1, "text_input", {"data": GAMES}), (2, "python", {"code": "df['pts'] = 0\ndf.loc[0, 'team'] = 'X'"}), (3, "sort", {"keys": [{"column": "team"}]})],
        [(1, "out", 2, "in"), (1, "out", 3, "in")],
    )
    ev = run(wf, engine)
    assert out(ev, 2)["pts"].eq(0).all()
    assert out(ev, 1)["pts"].iloc[0] == 24
    assert "X" not in out(ev, 3)["team"].tolist()


def test_select_drop_rename_reorder_type():
    ev = run(chain(("select", {"fields": [
        {"name": "pts", "keep": True, "rename": "points", "dtype": "float64"},
        {"name": "team", "keep": True, "rename": "", "dtype": ""},
        {"name": "conf", "keep": False},
    ], "keep_new": True})))
    df = out(ev, 2)
    assert df.columns.tolist() == ["points", "team", "opp", "opp_pts"]
    assert df["points"].dtype == "float64"
    ev = run(chain(("select", {"fields": [{"name": "team", "keep": True}], "keep_new": False})))
    assert out(ev, 2).columns.tolist() == ["team"]


def test_sort_multi_key_nulls_last():
    ev = run(chain(("sort", {"keys": [{"column": "conf", "order": "desc"}, {"column": "pts", "order": "asc"}]})))
    df = out(ev, 2)
    assert df["conf"].iloc[0] == "Mountain West"
    assert df["pts"].tolist()[1:] == [20, 24, 42, 68]


def test_sample_modes():
    assert len(out(run(chain(("sample", {"mode": "first", "n": 2}))), 2)) == 2
    assert out(run(chain(("sample", {"mode": "last", "n": 1}))), 2)["opp"].tolist() == ["Akron"]
    first_per = out(run(chain(("sample", {"mode": "first", "n": 1, "group_by": ["conf"]}))), 2)
    assert first_per["team"].tolist() == ["Nebraska", "Boise State"]
    rnd = out(run(chain(("sample", {"mode": "random_n", "n": 3, "seed": 7}))), 2)
    assert len(rnd) == 3
    assert out(run(chain(("sample", {"mode": "nth", "n": 2}))), 2)["opp"].tolist() == ["Iowa", "Michigan", "Akron"]


def test_unique_split():
    ev = run(chain(("unique", {"columns": ["team"]})))
    assert len(out(ev, 2, "unique")) == 4
    assert out(ev, 2, "dupes")["opp"].tolist() == ["Akron"]


def test_record_id_and_clash():
    df = out(run(chain(("record_id", {"column": "rid", "start": 10}))), 2)
    assert df.columns[0] == "rid"
    assert df["rid"].tolist() == [10, 11, 12, 13, 14]
    assert "already exists" in err(run(chain(("record_id", {"column": "team"}))), 2)


def test_cleanse_trim_case_fill():
    df = out(run(chain(("cleanse", {"trim": True, "case": "upper", "fill_numbers": True}))), 2)
    assert df["team"].iloc[2] == "OHIO STATE"
    assert df["pts"].iloc[3] == 0


def test_find_replace_case_insensitive():
    df = out(run(chain(("replace", {"columns": ["conf"], "find": "big ten", "replace": "B1G", "case": False}))), 2)
    assert df["conf"].tolist()[:3] == ["B1G", "B1G", "B1G"]


def test_text_to_columns_and_rows():
    data = "id,tags\n1,a; b;c\n2,d"
    cols = out(run(chain(("split", {"column": "tags", "delimiter": ";"}), data=data)), 2)
    assert cols[["tags_1", "tags_2", "tags_3"]].iloc[0].tolist() == ["a", "b", "c"]
    assert pd.isna(cols["tags_2"].iloc[1])
    rows = out(run(chain(("split", {"column": "tags", "delimiter": ";", "mode": "rows"}), data=data)), 2)
    assert rows["tags"].tolist() == ["a", "b", "c", "d"]
    assert rows["id"].tolist() == [1, 1, 1, 2]


def test_explode_unnest_nested_json(tmp_path):
    path = tmp_path / "nested.json"
    path.write_text('[{"id": 1, "teams": [{"team": "A", "stats": [{"category": "pts", "stat": "7"}]}, {"team": "B", "stats": []}]}, {"id": 2, "teams": []}]')
    wf = workflow(
        [(1, "input", {"path": str(path)}), (2, "explode", {"column": "teams"}), (3, "unnest", {"column": "teams", "prefix": False}), (4, "explode", {"column": "stats"}), (5, "unnest", {"column": "stats"})],
        [(1, "out", 2, "in"), (2, "out", 3, "in"), (3, "out", 4, "in"), (4, "out", 5, "in")],
    )
    df = out(run(wf), 5)
    assert df.columns.tolist() == ["id", "team", "stats.category", "stats.stat"]
    assert df["team"].tolist()[:2] == ["A", "B"]
    assert df["stats.stat"].iloc[0] == "7"
    assert len(df) == 3


def test_unnest_clash_is_clear(tmp_path):
    path = tmp_path / "clash.json"
    path.write_text('[{"id": 1, "obj": {"id": 9}}]')
    wf = workflow([(1, "input", {"path": str(path)}), (2, "unnest", {"column": "obj", "prefix": False})], [(1, "out", 2, "in")])
    assert "prefix" in err(run(wf), 2)


def join_wf(keys, left=GAMES, right="name,mascot\nNebraska,Huskers\nIowa,Hawkeyes\nIowa,Herky\nTexas,Longhorns"):
    return workflow(
        [(1, "text_input", {"data": left}), (2, "text_input", {"data": right}), (3, "join", {"keys": keys})],
        [(1, "out", 3, "left"), (2, "out", 3, "right")],
    )


def test_join_lrj():
    ev = run(join_wf([{"left": "team", "right": "name"}]))
    j = out(ev, 3, "join")
    assert len(j) == 4
    assert sorted(j["mascot"].tolist()) == ["Hawkeyes", "Herky", "Huskers", "Huskers"]
    assert out(ev, 3, "left")["team"].tolist() == [" Ohio State ", "Boise State"]
    assert out(ev, 3, "right")["name"].tolist() == ["Texas"]
    assert out(ev, 3, "left").columns.tolist() == ["team", "opp", "pts", "opp_pts", "conf"]


def test_join_same_name_suffix():
    ev = run(join_wf([{"left": "team", "right": "team"}], right="team,conf\nNebraska,B1G"))
    j = out(ev, 3, "join")
    assert "conf_right" in j.columns
    assert j["team"].tolist() == ["Nebraska", "Nebraska"]


def test_join_type_mismatch_errors():
    ev = run(join_wf([{"left": "pts", "right": "name"}]))
    assert "merge" in err(ev, 3).lower()


def test_join_missing_input():
    wf = workflow([(1, "text_input", {"data": GAMES}), (2, "join", {"keys": [{"left": "team", "right": "team"}]})], [(1, "out", 2, "left")])
    assert "Connect the R input" in err(run(wf), 2)


def test_union_modes_and_order():
    a = "x,y\n1,a"
    b = "y,z\nb,2"
    nodes = [(1, "text_input", {"data": a}), (2, "text_input", {"data": b}), (3, "union", {"mode": "name"}), (4, "union", {"mode": "common"}), (5, "union", {"mode": "position"})]
    edges = [(1, "out", n, "in") for n in (3, 4, 5)] + [(2, "out", n, "in") for n in (3, 4, 5)]
    ev = run(workflow(nodes, edges))
    assert out(ev, 3).columns.tolist() == ["x", "y", "z"]
    assert out(ev, 4).columns.tolist() == ["y"]
    assert out(ev, 5)["x"].tolist() == [1, "b"]
    rev = workflow(nodes[:3], [(2, "out", 3, "in"), (1, "out", 3, "in")])
    assert out(run(rev), 3)["y"].tolist() == ["b", "a"]


def test_append_cross():
    wf = workflow([(1, "text_input", {"data": "a\n1\n2"}), (2, "text_input", {"data": "b\nx\ny\nz"}), (3, "append", {})], [(1, "out", 3, "target"), (2, "out", 3, "source")])
    assert len(out(run(wf), 3)) == 6


def test_summarize_group_and_total():
    ev = run(chain(("summarize", {"group_by": ["conf"], "aggs": [
        {"column": "pts", "func": "sum", "name": "total"},
        {"column": "pts", "func": "count"},
        {"column": "team", "func": "size", "name": "rows"},
        {"column": "opp", "func": "concat", "name": "opps"},
    ]})))
    df = out(ev, 2)
    big = df[df["conf"] == "Big Ten"].iloc[0]
    assert big["total"] == 154
    assert big["Count_pts"] == 4
    assert big["rows"] == 4
    assert big["opps"] == "Iowa, Nebraska, Michigan, Akron"
    total = out(run(chain(("summarize", {"aggs": [{"column": "pts", "func": "max", "name": "best"}]}))), 2)
    assert total["best"].tolist() == [68]


def test_summarize_keeps_null_groups():
    df = out(run(chain(("summarize", {"group_by": ["pts"], "aggs": [{"column": "team", "func": "size", "name": "n"}]}))), 2)
    assert df["pts"].isna().sum() == 1


def test_crosstab_and_transpose():
    data = "team,stat,val\nA,pts,7\nA,yds,300\nB,pts,3"
    ct = out(run(chain(("crosstab", {"group_by": ["team"], "header": "stat", "value": "val", "func": "sum"}), data=data)), 2)
    assert ct.columns.tolist() == ["team", "pts", "yds"]
    assert ct.set_index("team").loc["A", "yds"] == 300
    assert pd.isna(ct.set_index("team").loc["B", "yds"])
    long = out(run(chain(("transpose", {"keys": ["team"], "data": ["pts", "opp_pts"]}))), 2)
    assert len(long) == 10
    assert long.columns.tolist() == ["team", "Name", "Value"]


def test_python_tool_two_inputs():
    wf = workflow(
        [(1, "text_input", {"data": "a\n1\n2"}), (2, "text_input", {"data": "a\n3"}), (3, "python", {"code": "df = pd.concat(dfs)\ndf['b'] = df['a'] * 10"})],
        [(1, "out", 3, "in"), (2, "out", 3, "in")],
    )
    assert out(run(wf), 3)["b"].tolist() == [10, 20, 30]


def test_python_tool_error_shows_line():
    wf = chain(("python", {"code": "x = 1\ndf = df['nope']"}))
    message = err(run(wf), 2)
    assert "KeyError" in message and "df['nope']" in message


def test_unconnected_tool_asks_for_input():
    wf = workflow([(1, "sort", {"keys": [{"column": ""}]})], [])
    assert err(run(wf), 1) == "Connect the input"


def test_cycle_detected():
    wf = workflow([(1, "sort", {"keys": [{"column": "a"}]}), (2, "sort", {"keys": [{"column": "a"}]})], [(1, "out", 2, "in"), (2, "out", 1, "in")])
    ev = run(wf)
    assert "loop" in err(ev, 1)


def test_cache_hits_and_file_change(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("a\n1\n")
    engine = Engine()
    wf = workflow([(1, "input", {"path": str(path)}), (2, "sort", {"keys": [{"column": "a"}]})], [(1, "out", 2, "in")])
    run(wf, engine)
    again = run(wf, engine)
    assert again.results["1"].cached and again.results["2"].cached
    path.write_text("a\n1\n2\n")
    os.utime(path, (1, 2))
    changed = run(wf, engine)
    assert not changed.results["1"].cached
    assert len(out(changed, 2)) == 2


def test_output_formats_round_trip(tmp_path):
    for ext in ("csv", "xlsx", "parquet", "json"):
        target = tmp_path / f"out.{ext}"
        wf = workflow([(1, "text_input", {"data": GAMES}), (2, "output", {"path": str(target)}), (3, "input", {"path": str(target)})], [(1, "out", 2, "in")])
        run(wf)
        back = out(run(workflow([(3, "input", {"path": str(target)})], [])), 3)
        assert back.shape == (5, 5), ext


def test_output_bare_name_gets_extension_and_full_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ev = run(workflow([(1, "text_input", {"data": GAMES}), (2, "output", {"path": "nebraska games"})], [(1, "out", 2, "in")]))
    target = tmp_path / "nebraska games.csv"
    assert target.exists()
    assert not (tmp_path / "nebraska games").exists()
    assert ev.results["2"].message == f"Wrote 5 rows to {target}"


def test_output_extension_follows_format(tmp_path):
    run(workflow([(1, "text_input", {"data": GAMES}), (2, "output", {"path": str(tmp_path / "book"), "format": "excel"})], [(1, "out", 2, "in")]))
    assert (tmp_path / "book.xlsx").exists()


def test_output_writes_nested_values_as_json(tmp_path):
    import json

    src = tmp_path / "nested.json"
    src.write_text('[{"id": 1, "offense": {"plays": 77, "ppa": 0.15}, "tags": ["a", "b"]}, {"id": 2, "offense": null, "tags": []}]')
    target = tmp_path / "out.csv"
    run(workflow([(1, "input", {"path": str(src)}), (2, "output", {"path": str(target)})], [(1, "out", 2, "in")]))
    back = pd.read_csv(target)
    assert json.loads(back["offense"].iloc[0]) == {"plays": 77, "ppa": 0.15}
    assert json.loads(back["tags"].iloc[0]) == ["a", "b"]
    assert pd.isna(back["offense"].iloc[1])


def test_glob_input_adds_filename(tmp_path):
    (tmp_path / "w1.csv").write_text("a\n1\n")
    (tmp_path / "w2.csv").write_text("a\n2\n3\n")
    df = out(run(workflow([(1, "input", {"path": str(tmp_path / "w*.csv"), "filename_col": "src"})], [])), 1)
    assert df["src"].tolist() == ["w1.csv", "w2.csv", "w2.csv"]


def test_preview_side_effect_free(tmp_path):
    target = tmp_path / "never.csv"
    wf = workflow([(1, "text_input", {"data": GAMES}), (2, "output", {"path": str(target)})], [(1, "out", 2, "in")])
    Engine().evaluate(wf, targets=["2"], run_side_effects=False)
    assert not target.exists()


def test_export_matches_engine(tmp_path):
    engine_out = tmp_path / "engine.csv"
    script_out = tmp_path / "script.csv"
    steps = [
        ("formula", {"formulas": [{"column": "margin", "expression": "[pts] - [opp_pts]"}]}),
        ("filter", {"column": "margin", "operator": ">", "value": "0"}),
        ("summarize", {"group_by": ["team"], "aggs": [{"column": "margin", "func": "mean", "name": "avg"}]}),
        ("sort", {"keys": [{"column": "avg", "order": "desc"}]}),
    ]
    nodes = [(1, "text_input", {"data": GAMES})] + [(i, t, c) for i, (t, c) in enumerate(steps, start=2)] + [(6, "output", {"path": str(engine_out)})]
    edges = [(1, "out", 2, "in"), (2, "out", 3, "in"), (3, "true", 4, "in"), (4, "out", 5, "in"), (5, "out", 6, "in")]
    wf = workflow(nodes, edges)
    engine = Engine()
    ev = engine.evaluate(wf, run_side_effects=True)
    assert all(r.status == "ok" for r in ev.results.values())
    code = export_script(ev, "test").replace(str(engine_out), str(script_out))
    script = tmp_path / "exported.py"
    script.write_text(code)
    subprocess.run([sys.executable, str(script)], check=True, cwd=tmp_path)
    pd.testing.assert_frame_equal(pd.read_csv(engine_out), pd.read_csv(script_out))


def test_translate_rules():
    cols = ["a", "Home Team", "b"]
    assert translate("[a] + [b]", "df", cols) == "df['a'] + df['b']"
    assert translate("[Home Team].str.upper()", "df", cols) == "df['Home Team'].str.upper()"
    assert translate("'[a]' + [a]", "df", cols) == "'[a]' + df['a']"
    assert translate("[a].isin([1, 2])", "df", cols) == "df['a'].isin([1, 2])"
    assert translate("x[a]", "df", cols) == "x[a]"
    with pytest.raises(ExprError):
        translate("[Home Teams]", "df", cols)


def test_bundled_flights_glob_gz():
    df = out(run(workflow([(1, "input", {"path": str(EXAMPLES / "nycflights13" / "flights_2013_*.csv.gz"), "filename_col": "file"})], [])), 1)
    assert len(df) == 80789
    assert df["file"].nunique() == 3
    assert df["dep_time"].isna().sum() > 0


def test_bundled_carriers_json_explode_unnest():
    wf = workflow(
        [(1, "input", {"path": str(EXAMPLES / "nycflights13" / "carriers.json")}), (2, "explode", {"column": "fleet"}), (3, "unnest", {"column": "fleet", "prefix": False})],
        [(1, "out", 2, "in"), (2, "out", 3, "in")],
    )
    df = out(run(wf), 3)
    assert {"carrier", "name", "tailnum", "seats"} <= set(df.columns)
    assert df["tailnum"].notna().sum() == 2931


def test_bundled_sample_workflows_run(monkeypatch):
    import json

    monkeypatch.chdir(ROOT)
    names = ["Penguins - body mass by species", "Penguins - clean the raw file", "Flights - Q1 delays by airline", "Flights - weather at departure", "Flights - fleets from nested JSON", "Demo - no files needed"]
    engine = Engine()
    for name in names:
        wf = json.loads((ROOT / "workflows" / f"{name}.flow.json").read_text())
        ev = engine.evaluate(wf, run_side_effects=False)
        problems = {k: r.error for k, r in ev.results.items() if r.status != "ok"}
        assert not problems, f"{name}: {problems}"
