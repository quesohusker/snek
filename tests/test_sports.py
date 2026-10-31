import math
import subprocess
import sys

import pandas as pd
import pytest
from scipy.stats import norm

from snek.codegen import export_script
from snek.engine import Engine
from snek.tools import TOOLS


def wf(nodes, edges):
    return {
        "nodes": [{"id": str(i), "type": t, "config": c} for i, t, c in nodes],
        "edges": [{"source": str(s), "sourceHandle": sh, "target": str(t), "targetHandle": th} for s, sh, t, th in edges],
    }


def single(tool, cfg, data):
    return wf([(1, "text_input", {"data": data}), (2, tool, cfg)], [(1, "out", 2, "in")])


def paired(tool, cfg, ratings, games):
    return wf([(1, "text_input", {"data": ratings}), (2, "text_input", {"data": games}), (3, tool, cfg)], [(1, "out", 3, "ratings"), (2, "out", 3, "games")])


def run(w):
    return Engine().evaluate(w, run_side_effects=True)


def out(ev, node, port="out"):
    res = ev.results[str(node)]
    assert res.status == "ok", res.error
    return ev.frames[(str(node), port)]


def test_every_sports_tool_names_its_group_and_input():
    sports = [t for t in TOOLS.values() if t.category == "Sports"]
    assert {t.group for t in sports} == {"All sports", "Football", "Basketball", "Baseball", "Volleyball"}
    assert all(t.needs for t in sports)


def test_opponent_adjust_recovers_true_strengths():
    off, dfn = {"A": 30, "B": 20, "C": 10}, {"A": -5, "B": 0, "C": 5}
    rows = "\n".join(f"{t},{o},{off[t] + dfn[o]}" for t in off for o in off if t != o)
    ev = run(single("opponent_adjust", {"team": "team", "opp": "", "opponent": "opp", "stats": ["pts"], "alpha": 1e-9}, "team,opp,pts\n" + rows))
    adj = out(ev, 2, "adjusted").set_index("Team")
    assert adj["pts offense adj"].to_dict() == pytest.approx(off, abs=1e-6)
    assert adj["pts defense adj"].to_dict() == pytest.approx({"A": 15, "B": 20, "C": 25}, abs=1e-6)
    assert adj.loc["A", "pts offense"] == pytest.approx(32.5)


def test_spread_win_probability_and_line_grading():
    cfg = {"team": "team", "rating": "rating", "home": "home", "away": "away", "home_points": "hp", "away_points": "ap", "home_edge": 3, "sigma": 10, "line": "line"}
    ev = run(paired("spread_win_prob", cfg, "team,rating\nA,10\nB,0", "home,away,hp,ap,line\nA,B,20,10,-7\nB,A,24,21,3"))
    games, summary = out(ev, 3, "games"), out(ev, 3, "summary").set_index("Measure")["Value"]
    assert games["Predicted margin"].tolist() == [13, -7]
    assert games["Home win probability"].tolist() == pytest.approx([norm.cdf(1.3), norm.cdf(-0.7)])
    assert games["Edge"].tolist() == [6, -4]
    assert games["Pick vs line"].tolist() == ["A", "A"]
    assert games["Result vs line"].tolist() == ["Win", "Loss"]
    assert summary["Record vs line (W-L-P)"] == "1-1-0"
    assert summary["Straight-up correct %"] == "50.0"
    assert float(summary["Mean absolute error"]) == pytest.approx(6.5)
    assert float(summary["Brier score"]) == pytest.approx(round(((1 - norm.cdf(1.3)) ** 2 + (1 - norm.cdf(-0.7)) ** 2) / 2, 4))


def test_season_simulation_counts_played_and_simulated_games():
    cfg = {"team": "team", "rating": "rating", "home": "home", "away": "away", "home_points": "hp", "away_points": "ap", "sigma": 1, "target_wins": 2, "simulations": 2000}
    ev = run(paired("season_sim", cfg, "team,rating\nA,100\nB,0\nC,-100", "home,away,hp,ap\nA,B,30,20\nA,C,,\nB,C,,"))
    teams = out(ev, 3, "teams").set_index("Team")
    assert teams["Wins"].to_dict() == {"A": 1, "B": 0, "C": 0}
    assert teams["Projected wins"].to_dict() == pytest.approx({"A": 2, "B": 1, "C": 0})
    assert teams.loc["A", "Chance to win out"] == 1 and teams.loc["A", "Chance of 2+ wins"] == 1 and teams.loc["B", "Chance of 2+ wins"] == 0
    even = {**cfg, "simulations": 20000, "home_points": "", "away_points": ""}
    first = out(run(paired("season_sim", even, "team,rating\nA,0\nB,0", "home,away\nA,B")), 3, "teams").set_index("Team")
    assert first.loc["A", "Projected wins"] == pytest.approx(0.5, abs=0.015)
    again = out(run(paired("season_sim", even, "team,rating\nA,0\nB,0", "home,away\nA,B")), 3, "teams").set_index("Team")
    assert again.loc["A", "Projected wins"] == first.loc["A", "Projected wins"]


def test_pythagorean_and_fitted_exponent():
    games = "home,away,hp,ap\nA,B,20,10\nB,A,10,10"
    cfg = {"home": "home", "away": "away", "home_points": "hp", "away_points": "ap", "exponent": 2}
    teams = out(run(single("pythagorean", cfg, games)), 2, "teams").set_index("Team")
    assert teams.loc["A", "Expected win %"] == pytest.approx(900 / 1300)
    assert teams.loc["A", "Luck"] == pytest.approx(1.5 - 2 * 900 / 1300)
    assert teams.loc["B", "Win %"] == 0.25
    fit = out(run(single("pythagorean", {**cfg, "fit_exponent": True}, games)), 2, "fit").set_index("Measure")["Value"]
    assert float(fit["Exponent"]) == pytest.approx(math.log(3) / math.log(1.5), abs=1e-3)


def test_garbage_time_thresholds():
    plays = "id,period,off,def\n1,1,50,0\n2,2,39,0\n3,2,38,0\n4,3,0,29\n5,4,22,0\n6,4,23,0\n7,5,40,0"
    ev = run(single("garbage_time", {"period": "period", "score_a": "off", "score_b": "def"}, plays))
    assert out(ev, 2, "kept")["id"].tolist() == [1, 3, 5, 7]
    assert out(ev, 2, "garbage")["id"].tolist() == [2, 4, 6]


def test_success_rate_by_down():
    plays = "down,dist,gain\n1,10,5\n1,10,4\n2,10,7\n2,10,6\n3,3,3\n4,2,1"
    result = out(run(single("success_rate", {"down": "down", "distance": "dist", "yards": "gain"}, plays)), 2)
    assert result["Success"].tolist() == [True, False, True, False, True, False]


def test_football_efficiency_offense_and_defense():
    plays = "off,def,epa,ok,havoc,yds\nA,B,1,true,false,8\nA,B,-0.5,false,true,-2\nA,B,2,true,false,12\nB,A,0.5,true,false,5\nB,A,-1,false,false,0"
    cfg = {"offense": "off", "defense": "def", "success": "ok", "epa": "epa", "havoc": "havoc", "yards": "yds"}
    t = out(run(single("football_efficiency", cfg, plays)), 2).set_index("Team")
    assert t.loc["A", "Off plays"] == 3 and t.loc["A", "Off yards/play"] == 6
    assert t.loc["A", "Off success rate"] == pytest.approx(2 / 3)
    assert t.loc["A", "Off EPA/play"] == pytest.approx(2.5 / 3)
    assert t.loc["A", "Off explosiveness"] == pytest.approx(1.5)
    assert t.loc["A", "Off havoc rate"] == pytest.approx(1 / 3)
    assert t.loc["A", "Def EPA/play"] == pytest.approx(-0.25)
    assert t.loc["A", "Net EPA/play"] == pytest.approx(2.5 / 3 + 0.25)


def test_four_factors_hand_calculation():
    box = "g,team,pts,fgm,fga,tpm,ftm,fta,orb,drb,tov,min\n1,X,100,38,85,10,14,20,10,30,12,240\n1,Y,90,35,88,8,12,16,12,33,14,240"
    cfg = {"game": "g", "team": "team", "pts": "pts", "fgm": "fgm", "fga": "fga", "fg3m": "tpm", "ftm": "ftm", "fta": "fta", "orb": "orb", "drb": "drb", "tov": "tov", "minutes": "min"}
    t = out(run(single("four_factors", cfg, box)), 2, "teams").set_index("Team")
    poss = ((85 - 10 + 12 + 0.44 * 20) + (88 - 12 + 14 + 0.44 * 16)) / 2
    x = t.loc["X"]
    assert x["Possessions/game"] == pytest.approx(poss) and x["Pace"] == pytest.approx(poss)
    assert x["Off rating"] == pytest.approx(100 * 100 / poss) and x["Def rating"] == pytest.approx(100 * 90 / poss)
    assert x["Off eFG%"] == pytest.approx(43 / 85) and x["Off TOV%"] == pytest.approx(12 / (85 + 8.8 + 12))
    assert x["Off ORB%"] == pytest.approx(10 / 43) and x["Off FT/FGA"] == pytest.approx(14 / 85)
    assert x["Def eFG%"] == pytest.approx(39 / 88) and x["Def ORB%"] == pytest.approx(12 / 42)
    assert x["Wins"] == 1 and t.loc["Y", "Losses"] == 1


def test_shooting_efficiency():
    row = out(run(single("shooting", {"pts": "pts", "fga": "fga", "fta": "fta", "fgm": "fgm", "fg3m": "tpm", "fg3a": "tpa"}, "pts,fga,fta,fgm,tpm,tpa\n30,20,10,11,2,6")), 2).iloc[0]
    assert row["TS%"] == pytest.approx(30 / 48.8) and row["eFG%"] == pytest.approx(0.6)
    assert row["3PA rate"] == pytest.approx(0.3) and row["FTA rate"] == pytest.approx(0.5) and row["Points per shot"] == pytest.approx(1.5)


def test_batting_stats_hand_calculation():
    cfg = {k: k for k in ("ab", "h", "hr", "bb", "hbp", "sf", "so", "ibb")} | {"doubles": "2b", "triples": "3b"}
    row = out(run(single("batting", cfg, "ab,h,2b,3b,hr,bb,hbp,sf,so,ibb\n300,90,20,3,15,35,3,3,60,3\n200,60,10,2,10,25,2,2,40,2")), 2).iloc[0]
    assert row["AVG"] == pytest.approx(0.3) and row["OBP"] == pytest.approx(215 / 570) and row["SLG"] == pytest.approx(0.53)
    assert row["ISO"] == pytest.approx(0.23) and row["BABIP"] == pytest.approx(125 / 380) and row["K%"] == pytest.approx(100 / 570)
    assert row["wOBA"] == pytest.approx(218.1 / 565)


def test_pitching_stats_with_baseball_innings():
    cfg = {k: k for k in ("ip", "er", "h", "bb", "so", "hr", "hbp")}
    row = out(run(single("pitching", cfg, "ip,er,h,bb,so,hr,hbp\n6.1,3,7,2,8,1,1\n5.2,2,5,1,6,0,0")), 2).iloc[0]
    assert row["IP"] == pytest.approx(12) and row["ERA"] == pytest.approx(3.75) and row["WHIP"] == pytest.approx(1.25)
    assert row["K/9"] == pytest.approx(10.5) and row["FIP"] == pytest.approx(2.85)


def test_volleyball_box_matches_ncaa_points():
    box = "player,s,k,e,ta,a,sa,se,d,bs,ba\nThigpen,3,7,2,19,0,0,1,8,0,1\nDeLeye,3,12,2,31,2,1,3,6,0,1"
    cfg = {"group_by": ["player"], "sets": "s", "kills": "k", "errors": "e", "attempts": "ta", "assists": "a", "aces": "sa", "service_errors": "se", "digs": "d", "block_solos": "bs", "block_assists": "ba"}
    t = out(run(single("volleyball_stats", cfg, box)), 2).set_index("player")
    assert t["Points"].to_dict() == {"Thigpen": 7.5, "DeLeye": 13.5}
    assert t.loc["Thigpen", "Hitting %"] == pytest.approx(5 / 19) and t.loc["Thigpen", "Blocks"] == 1
    team = out(run(single("volleyball_stats", {**cfg, "group_by": [], "team_rows": True}, box)), 2).iloc[0]
    assert team["Blocks"] == 1 and team["Kills/set"] == pytest.approx(19 / 6)


def test_sideout_with_and_without_receiving_column():
    rallies = "set,serve,recv,won\n1,A,B,A\n1,A,B,B\n1,B,A,B\n1,B,A,A\n1,A,B,A"
    expected = {"A": (3, 2, 2, 1), "B": (2, 1, 3, 1)}
    for cfg in ({"serving": "serve", "winner": "won", "receiving": "recv"}, {"serving": "serve", "winner": "won", "rally_set": ["set"]}):
        t = out(run(single("sideout", cfg, rallies)), 2).set_index("Team")
        got = {team: tuple(int(t.loc[team, c]) for c in ("Serve rallies", "Points on serve", "Receive rallies", "Side-outs")) for team in "AB"}
        assert got == expected
        assert t.loc["A", "Side-out %"] == 0.5 and t.loc["B", "Point-scoring %"] == 0.5


def test_sports_export_runs_standalone(tmp_path):
    games = "home,away,hp,ap\nA,B,24,17\nC,D,14,21\nA,C,31,10\nB,D,28,27\nD,A,,\nB,C,,"
    nodes = [
        (1, "text_input", {"data": games}),
        (2, "team_ratings", {"home": "home", "away": "away", "home_points": "hp", "away_points": "ap"}),
        (3, "season_sim", {"team": "Team", "rating": "Rating", "home": "home", "away": "away", "home_points": "hp", "away_points": "ap", "sigma": 12, "simulations": 500}),
        (4, "pythagorean", {"home": "home", "away": "away", "home_points": "hp", "away_points": "ap"}),
        (5, "output", {"path": str(tmp_path / "sim.csv")}),
        (6, "output", {"path": str(tmp_path / "pyth.csv")}),
    ]
    edges = [(1, "out", 2, "in"), (2, "ratings", 3, "ratings"), (1, "out", 3, "games"), (1, "out", 4, "in"), (3, "teams", 5, "in"), (4, "teams", 6, "in")]
    w = wf(nodes, edges)
    ev = run(w)
    engine_sim, engine_pyth = pd.read_csv(tmp_path / "sim.csv"), pd.read_csv(tmp_path / "pyth.csv")
    script = tmp_path / "flow.py"
    script.write_text(export_script(ev), encoding="utf-8")
    (tmp_path / "sim.csv").unlink()
    subprocess.run([sys.executable, str(script)], check=True, cwd=tmp_path)
    pd.testing.assert_frame_equal(pd.read_csv(tmp_path / "sim.csv"), engine_sim)
    pd.testing.assert_frame_equal(pd.read_csv(tmp_path / "pyth.csv"), engine_pyth)
