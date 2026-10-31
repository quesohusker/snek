import itertools
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "examples" / "data" / "demo_sports"
TEAMS = ["Prairie Dogs", "Ridge Hawks", "Lake Pike", "Canyon Wrens", "Iron Owls", "Delta Herons", "Mesa Foxes", "Harbor Seals", "Timber Wolves", "Salt Flats"]


def round_robin(teams):
    teams = list(teams)
    rounds = []
    for r in range(len(teams) - 1):
        pairs = [(teams[i], teams[-1 - i]) for i in range(len(teams) // 2)]
        rounds.append([(a, b) if (r + i) % 2 else (b, a) for i, (a, b) in enumerate(pairs)])
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    return rounds


def football(rng):
    off = dict(zip(TEAMS, rng.normal(0, 1, len(TEAMS))))
    dfn = dict(zip(TEAMS, rng.normal(0, 1, len(TEAMS))))
    plays, games = [], []
    game_id = 100
    for week, pairs in enumerate(round_robin(TEAMS), start=1):
        for home, away in pairs:
            game_id += 1
            line = -round(2 * (1.2 * (off[home] - dfn[home] - off[away] + dfn[away]) * 3 + 2.5 + rng.normal(0, 2))) / 2
            if week > 6:
                games.append((game_id, week, home, away, None, None, line))
                continue
            score = {home: 0, away: 0}
            ball, ytg, down, dist = away, 75, 1, 10
            for n in range(124):
                o = ball
                d = home if o == away else away
                period = min(4, n // 31 + 1)
                kind = "Pass" if rng.random() < 0.55 else "Rush"
                need = (0.5 if down == 1 else 0.7 if down == 2 else 1.0) * dist
                mean = 4.6 + 1.3 * (off[o] - dfn[d]) + (1.5 if kind == "Pass" else 0)
                yards = int(round(rng.normal(mean, 9 if kind == "Pass" else 4.5)))
                if kind == "Pass" and rng.random() < 0.36:
                    yards = 0
                yards = max(-10, min(ytg, yards))
                turnover = rng.random() < 0.022
                td = yards == ytg and not turnover
                havoc = turnover or yards < 0
                epa = 0.12 * (yards - need) + (2.0 if td else 0) - (4.0 if turnover else 0) + rng.normal(0, 0.2)
                plays.append((game_id, week, period, o, d, home, away, score[o], score[d], down, dist, ytg, yards, kind, round(epa, 3), havoc))
                if td:
                    score[o] += 7
                    ball, ytg, down, dist = d, 75, 1, 10
                elif turnover:
                    ball, ytg, down, dist = d, max(5, min(95, 100 - (ytg - yards))), 1, 10
                elif yards >= dist:
                    ytg -= yards
                    down, dist = 1, min(10, ytg)
                else:
                    ytg, down, dist = ytg - yards, down + 1, dist - yards
                    if down == 4 and dist > 2:
                        if ytg <= 35 and rng.random() < 0.75:
                            score[o] += 3
                            ball, ytg = d, 75
                        else:
                            ball, ytg = d, max(20, min(95, 100 - max(ytg - 40, 5)))
                        down, dist = 1, 10
                    elif down > 4:
                        ball, ytg, down, dist = d, max(5, min(95, 100 - ytg)), 1, 10
            if score[home] == score[away]:
                score[home] += 3
            games.append((game_id, week, home, away, score[home], score[away], line))
    pcols = ["game_id", "week", "period", "offense", "defense", "home", "away", "offense_score", "defense_score", "down", "distance", "yards_to_goal", "yards_gained", "play_type", "epa", "havoc"]
    gcols = ["game_id", "week", "home", "away", "home_points", "away_points", "spread"]
    return pd.DataFrame(plays, columns=pcols), pd.DataFrame(games, columns=gcols).astype({"home_points": "Int64", "away_points": "Int64"})


def basketball(rng):
    teams = TEAMS[:8]
    skill = dict(zip(teams, rng.normal(0, 0.03, len(teams))))
    rows = []
    game_id = 500
    for leg in range(2):
        for week, pairs in enumerate(round_robin(teams), start=1 + leg * 7):
            for a, b in pairs:
                game_id += 1
                poss = rng.normal(69, 4)
                box = {}
                for t, opp in ((a, b), (b, a)):
                    tov = int(round(poss * rng.normal(0.17, 0.02)))
                    fga = int(round((poss - tov) * rng.normal(0.9, 0.03)))
                    fg3a = int(round(fga * rng.normal(0.38, 0.04)))
                    fg3m = rng.binomial(fg3a, 0.34 + skill[t] - skill[opp] / 2)
                    fg2m = rng.binomial(fga - fg3a, 0.5 + skill[t] - skill[opp] / 2)
                    fta = int(round(fga * rng.normal(0.3, 0.05)))
                    ftm = rng.binomial(fta, 0.72)
                    box[t] = dict(fga=fga, fgm=fg2m + fg3m, fg3a=fg3a, fg3m=fg3m, fta=fta, ftm=ftm, tov=tov, pts=2 * fg2m + 3 * fg3m + ftm)
                for t, opp in ((a, b), (b, a)):
                    box[t]["orb"] = rng.binomial(box[t]["fga"] - box[t]["fgm"], 0.29)
                for t, opp in ((a, b), (b, a)):
                    box[t]["drb"] = box[opp]["fga"] - box[opp]["fgm"] - box[opp]["orb"]
                if box[a]["pts"] == box[b]["pts"]:
                    box[a]["fta"] += 2
                    box[a]["ftm"] += 2
                    box[a]["pts"] += 2
                for t in (a, b):
                    rows.append({"game_id": game_id, "week": week, "team": t, **box[t], "minutes": 200})
    return pd.DataFrame(rows)


def baseball(rng):
    clubs = ["Prairie Dogs", "Ridge Hawks", "Lake Pike"]
    bat, pit = [], []
    first = ["Al", "Benny", "Cal", "Dez", "Eli", "Finn", "Gus", "Hal", "Ike", "Jory"]
    for c, club in enumerate(clubs):
        for i, name in enumerate(first):
            pa = int(rng.integers(250, 660))
            bb, hbp, sf = rng.binomial(pa, 0.085), rng.binomial(pa, 0.01), rng.binomial(pa, 0.008)
            ab = pa - bb - hbp - sf
            so = rng.binomial(ab, 0.24)
            h = rng.binomial(ab - so, 0.33)
            hr = rng.binomial(h, 0.12)
            triples = rng.binomial(h - hr, 0.02)
            doubles = rng.binomial(h - hr - triples, 0.22)
            bat.append({"player": f"{name} {club.split()[0]}", "team": club, "PA": pa, "AB": ab, "H": h, "2B": doubles, "3B": triples, "HR": hr, "BB": bb, "IBB": rng.binomial(bb, 0.05), "HBP": hbp, "SF": sf, "SO": so})
        for i, name in enumerate(first[:5]):
            outs = int(rng.integers(150, 600))
            bf = int(outs * rng.normal(1.42, 0.06))
            so, bb, hbp = rng.binomial(bf, 0.23), rng.binomial(bf, 0.08), rng.binomial(bf, 0.01)
            h = rng.binomial(bf - so - bb - hbp, 0.3)
            hr = rng.binomial(h, 0.12)
            er = int(round((h + bb) * rng.normal(0.36, 0.05) + hr * 0.6))
            pit.append({"pitcher": f"{name} {club.split()[0]}", "team": club, "IP": float(f"{outs // 3}.{outs % 3}"), "BF": bf, "H": h, "ER": er, "HR": hr, "BB": bb, "HBP": hbp, "SO": so})
    return pd.DataFrame(bat), pd.DataFrame(pit)


def volleyball(rng):
    teams = TEAMS[:6]
    skill = dict(zip(teams, rng.normal(0, 0.05, len(teams))))
    rallies, box = [], []
    for match_id, (home, away) in enumerate(itertools.permutations(teams, 2), start=900):
        if rng.random() < 0.5:
            continue
        sets_won, set_no, serve = {home: 0, away: 0}, 0, home
        while max(sets_won.values()) < 3:
            set_no += 1
            target = 15 if set_no == 5 else 25
            pts, rally = {home: 0, away: 0}, 0
            while not (max(pts.values()) >= target and abs(pts[home] - pts[away]) >= 2):
                rally += 1
                recv = away if serve == home else home
                p_sideout = 0.6 + skill[recv] - skill[serve]
                winner = recv if rng.random() < p_sideout else serve
                event = rng.choice(["Kill", "Attack error", "Ace", "Service error", "Block"], p=[0.55, 0.15, 0.06, 0.12, 0.12])
                rallies.append((match_id, home, away, set_no, rally, serve, recv, winner, event, pts[home], pts[away]))
                pts[winner] += 1
                serve = winner
            sets_won[max(pts, key=pts.get)] += 1
        for t in (home, away):
            for pos, share in (("OH", 0.3), ("OH", 0.25), ("MB", 0.15), ("MB", 0.12), ("OPP", 0.18), ("S", 0.0), ("L", 0.0)):
                ta = int(rng.poisson(40 * set_no / 4 * share)) if share else int(rng.poisson(1))
                kills = rng.binomial(ta, 0.4 + skill[t])
                errors = rng.binomial(ta - kills, 0.25)
                bs, ba = (rng.poisson(0.3 * set_no), rng.poisson(1.0 * set_no)) if pos == "MB" else (rng.poisson(0.05 * set_no), rng.poisson(0.3 * set_no))
                box.append({"match_id": match_id, "team": t, "opponent": away if t == home else home, "position": pos, "sets": set_no, "kills": kills, "errors": errors, "total_attacks": ta,
                            "assists": rng.poisson(11 * set_no) if pos == "S" else rng.poisson(0.3 * set_no), "aces": rng.poisson(0.35 * set_no), "service_errors": rng.poisson(0.5 * set_no),
                            "digs": rng.poisson(4 * set_no) if pos == "L" else rng.poisson(1.8 * set_no), "block_solos": bs, "block_assists": ba})
    box_df = pd.DataFrame(box)
    box_df.insert(2, "player", box_df["team"].str.split().str[0] + " " + box_df["position"] + box_df.groupby(["match_id", "team", "position"]).cumcount().add(1).astype(str))
    rcols = ["match_id", "home_team", "away_team", "set_no", "rally_no", "serve_team", "recv_team", "winner", "end_event", "score_home", "score_away"]
    return box_df, pd.DataFrame(rallies, columns=rcols)


def main():
    rng = np.random.default_rng(2026)
    OUT.mkdir(parents=True, exist_ok=True)
    plays, games = football(rng)
    plays.to_csv(OUT / "football_plays.csv", index=False)
    games.to_csv(OUT / "football_games.csv", index=False)
    basketball(rng).to_csv(OUT / "basketball_box.csv", index=False)
    bat, pit = baseball(rng)
    bat.to_csv(OUT / "baseball_batting.csv", index=False)
    pit.to_csv(OUT / "baseball_pitching.csv", index=False)
    box, rallies = volleyball(rng)
    box.to_csv(OUT / "volleyball_box.csv", index=False)
    rallies.to_csv(OUT / "volleyball_rallies.csv", index=False)
    for f in sorted(OUT.glob("*.csv")):
        print(f.name, f.stat().st_size, len(pd.read_csv(f)))


if __name__ == "__main__":
    main()
