import numpy as np
import pandas as pd

from snek.modeling import is_true


def normal_cdf(x):
    from scipy.special import ndtr

    return ndtr(np.asarray(x, dtype=float))


def site_sign(series):
    if pd.api.types.is_bool_dtype(series):
        return np.where(series.fillna(False).astype(bool), 1.0, -1.0)
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce").fillna(0).clip(-1, 1).to_numpy(dtype=float)
    text = series.astype(str).str.strip().str.lower()
    home = text.isin(["home", "h", "true", "yes", "1"])
    away = text.isin(["away", "a", "@", "road", "visitor", "false", "no", "-1"])
    return np.select([home.to_numpy(), away.to_numpy()], [1.0, -1.0], 0.0)


def rating_lookup(ratings, team, rating):
    return dict(zip(ratings[team].astype(str), pd.to_numeric(ratings[rating], errors="coerce")))


def check_rated(lookup, teams):
    missing = sorted(set(teams) - set(lookup))
    if missing:
        more = f" and {len(missing) - 5} more" if len(missing) > 5 else ""
        raise ValueError(f"No rating for {', '.join(missing[:5])}{more}. Add them to the ratings or filter those games out")


def margin_spread(actual, predicted, teams=0):
    resid = (actual - predicted)[~(np.isnan(actual) | np.isnan(predicted))]
    dof = len(resid) - teams
    if dof < 10:
        raise ValueError("Set the spread of results: there are too few played games to estimate it")
    return float(np.sqrt(np.sum(resid**2) / dof))


def opponent_adjust(df, team, opponent, stats, location=None, weight=None, alpha=1.0):
    from sklearn.linear_model import Ridge

    cols = [team, opponent] + list(stats) + [c for c in (location, weight) if c]
    rows = df[list(dict.fromkeys(cols))].dropna(subset=[team, opponent]).copy()
    rows[team], rows[opponent] = rows[team].astype(str), rows[opponent].astype(str)
    teams = sorted(set(rows[team]) | set(rows[opponent]))
    n = len(teams)
    X = np.hstack([
        pd.get_dummies(pd.Categorical(rows[team], categories=teams), dtype=float).to_numpy(),
        pd.get_dummies(pd.Categorical(rows[opponent], categories=teams), dtype=float).to_numpy(),
    ])
    if location:
        X = np.column_stack([X, site_sign(rows[location])])
    w_all = pd.to_numeric(rows[weight], errors="coerce").fillna(0).to_numpy(dtype=float) if weight else np.ones(len(rows))
    table = pd.DataFrame({"Team": teams})
    table["Games"] = table["Team"].map(rows[team].value_counts()).fillna(0).astype(int)
    fit = []
    for stat in stats:
        y = pd.to_numeric(rows[stat], errors="coerce").to_numpy(dtype=float)
        ok = ~np.isnan(y) & (w_all > 0)
        if ok.sum() < 2:
            raise ValueError(f"{stat} has too few numeric values to adjust")
        model = Ridge(alpha=float(alpha)).fit(X[ok], y[ok], sample_weight=w_all[ok])
        off, dfn = model.coef_[:n], model.coef_[n : 2 * n]
        frame = pd.DataFrame({"t": rows[team].to_numpy()[ok], "o": rows[opponent].to_numpy()[ok], "y": y[ok], "w": w_all[ok]})
        frame["wy"] = frame["y"] * frame["w"]
        raw_off = frame.groupby("t")["wy"].sum() / frame.groupby("t")["w"].sum()
        raw_def = frame.groupby("o")["wy"].sum() / frame.groupby("o")["w"].sum()
        table[f"{stat} offense"] = table["Team"].map(raw_off)
        table[f"{stat} offense adj"] = model.intercept_ + off + dfn.mean()
        table[f"{stat} defense"] = table["Team"].map(raw_def)
        table[f"{stat} defense adj"] = model.intercept_ + dfn + off.mean()
        fit.append({"Stat": stat, "Rows used": int(ok.sum()), "Average": float(np.average(y[ok], weights=w_all[ok])), "Home effect": float(model.coef_[2 * n]) if location else np.nan, "Ridge alpha": float(alpha)})
    return table, pd.DataFrame(fit)


def game_predictions(ratings, games, team, rating, home, away, neutral=None, home_edge=0.0, sigma=0.0, home_points=None, away_points=None, line=None, line_negative_favorite=True):
    lookup = rating_lookup(ratings, team, rating)
    out = games.dropna(subset=[home, away]).copy()
    h, a = out[home].astype(str), out[away].astype(str)
    check_rated(lookup, set(h) | set(a))
    at_home = ~is_true(out[neutral]).to_numpy() if neutral else np.ones(len(out), dtype=bool)
    pred = h.map(lookup).to_numpy(dtype=float) - a.map(lookup).to_numpy(dtype=float) + float(home_edge) * at_home
    out["Predicted margin"] = pred
    actual = None
    if home_points and away_points:
        actual = (pd.to_numeric(out[home_points], errors="coerce") - pd.to_numeric(out[away_points], errors="coerce")).to_numpy(dtype=float)
        out["Actual margin"] = actual
    if not sigma:
        if actual is None:
            raise ValueError("Set the spread of results, or pick the points columns so Snek can estimate it from played games")
        rated = ~np.isnan(actual) & ~np.isnan(pred)
        sigma = margin_spread(actual, pred, len(set(h[rated]) | set(a[rated])))
    sigma = float(sigma)
    prob = normal_cdf(pred / sigma)
    out["Home win probability"] = prob
    out["Predicted winner"] = np.where(pred > 0, h, np.where(pred < 0, a, "Even"))
    rows = [("Games", len(out)), ("Spread of results (sd of margin)", round(sigma, 3)), ("Home-field edge", float(home_edge))]
    played = None
    if actual is not None:
        played = ~np.isnan(actual)
        decided = played & (actual != 0)
        won = actual[decided] > 0
        out["Correct pick"] = pd.array(np.where(played & (actual != 0) & (pred != 0), (pred > 0) == (actual > 0), pd.NA), dtype="boolean")
        rows += [
            ("Games played", int(played.sum())),
            ("Straight-up correct %", round(100 * float(np.mean((pred[decided] > 0) == won)), 1) if decided.any() else np.nan),
            ("Mean absolute error", round(float(np.mean(np.abs(actual[played] - pred[played]))), 3) if played.any() else np.nan),
            ("Brier score", round(float(np.mean((prob[decided] - won) ** 2)), 4) if decided.any() else np.nan),
        ]
    if line:
        raw = pd.to_numeric(out[line], errors="coerce").to_numpy(dtype=float)
        line_margin = -raw if line_negative_favorite else raw
        edge = pred - line_margin
        out["Line margin"] = line_margin
        out["Edge"] = edge
        out["Pick vs line"] = np.where(edge > 0, h, np.where(edge < 0, a, ""))
        if actual is not None:
            cover = actual - line_margin
            graded = ~np.isnan(cover) & ~np.isnan(edge) & (edge != 0)
            result = np.where(cover * edge > 0, "Win", np.where(cover * edge < 0, "Loss", "Push"))
            out["Result vs line"] = pd.array(np.where(graded, result, None), dtype="string")
            wins, losses, pushes = (int(np.sum(graded & (result == r))) for r in ("Win", "Loss", "Push"))
            both = played & ~np.isnan(line_margin)
            rows += [
                ("Record vs line (W-L-P)", f"{wins}-{losses}-{pushes}"),
                ("Win % vs line", round(100 * wins / (wins + losses), 1) if wins + losses else np.nan),
                ("Line mean absolute error", round(float(np.mean(np.abs(actual[both] - line_margin[both]))), 3) if both.any() else np.nan),
                ("Model mean absolute error, same games", round(float(np.mean(np.abs(actual[both] - pred[both]))), 3) if both.any() else np.nan),
            ]
    summary = pd.DataFrame({"Measure": [r[0] for r in rows], "Value": [str(r[1]) for r in rows]})
    return out.reset_index(drop=True), summary


def simulate_season(ratings, games, team, rating, home, away, home_points=None, away_points=None, neutral=None, home_edge=0.0, sigma=0.0, simulations=10000, seed=1, target_wins=6):
    lookup = rating_lookup(ratings, team, rating)
    g = games.dropna(subset=[home, away]).copy()
    h, a = g[home].astype(str).to_numpy(), g[away].astype(str).to_numpy()
    at_home = ~is_true(g[neutral]).to_numpy() if neutral else np.ones(len(g), dtype=bool)
    if home_points and away_points:
        actual = (pd.to_numeric(g[home_points], errors="coerce") - pd.to_numeric(g[away_points], errors="coerce")).to_numpy(dtype=float)
    else:
        actual = np.full(len(g), np.nan)
    played = ~np.isnan(actual)
    check_rated(lookup, set(h[~played]) | set(a[~played]))
    teams = sorted(set(h) | set(a))
    index = {t: i for i, t in enumerate(teams)}
    hi, ai = np.array([index[t] for t in h], dtype=int), np.array([index[t] for t in a], dtype=int)
    rate = np.array([lookup.get(t, np.nan) for t in teams])
    pred = rate[hi] - rate[ai] + float(home_edge) * at_home
    if not sigma:
        rated = played & ~np.isnan(pred)
        sigma = margin_spread(actual[rated], pred[rated], len(set(h[rated]) | set(a[rated])))
    sigma = float(sigma)
    wins = np.zeros(len(teams))
    losses = np.zeros(len(teams))
    np.add.at(wins, hi[played & (actual > 0)], 1)
    np.add.at(wins, ai[played & (actual < 0)], 1)
    np.add.at(losses, ai[played & (actual > 0)], 1)
    np.add.at(losses, hi[played & (actual < 0)], 1)
    left = ~played
    remaining = np.zeros(len(teams))
    np.add.at(remaining, hi[left], 1)
    np.add.at(remaining, ai[left], 1)
    p = normal_cdf(pred[left] / sigma)
    rng = np.random.default_rng(int(seed))
    home_won = rng.random((int(simulations), int(left.sum()))) < p
    onehot_h = np.zeros((int(left.sum()), len(teams)))
    onehot_a = np.zeros((int(left.sum()), len(teams)))
    onehot_h[np.arange(left.sum()), hi[left]] = 1
    onehot_a[np.arange(left.sum()), ai[left]] = 1
    sim_wins = home_won @ onehot_h + (~home_won) @ onehot_a
    total = wins + sim_wins
    target = int(target_wins)
    table = pd.DataFrame({
        "Team": teams,
        "Rating": rate,
        "Wins": wins.astype(int),
        "Losses": losses.astype(int),
        "Games left": remaining.astype(int),
        "Projected wins": total.mean(axis=0),
        "Projected losses": losses + remaining - sim_wins.mean(axis=0),
        "Wins, 10th percentile": np.percentile(total, 10, axis=0),
        "Wins, 90th percentile": np.percentile(total, 90, axis=0),
        f"Chance of {target}+ wins": (total >= target).mean(axis=0),
        "Chance to win out": (sim_wins == remaining).mean(axis=0),
    }).sort_values("Projected wins", ascending=False, ignore_index=True)
    counts = [(t, int(w), float(c) / simulations) for i, t in enumerate(teams) for w, c in zip(*np.unique(total[:, i], return_counts=True))]
    dist = pd.DataFrame(counts, columns=["Team", "Wins", "Chance"])
    return table, dist


def pythagorean(df, home, away, home_points, away_points, exponent=2.37, fit_exponent=False):
    games = df[[home, away, home_points, away_points]].dropna()
    hp, ap = pd.to_numeric(games[home_points]).astype(float), pd.to_numeric(games[away_points]).astype(float)
    long = pd.concat([
        pd.DataFrame({"Team": games[home].astype(str).to_numpy(), "For": hp.to_numpy(), "Against": ap.to_numpy()}),
        pd.DataFrame({"Team": games[away].astype(str).to_numpy(), "For": ap.to_numpy(), "Against": hp.to_numpy()}),
    ])
    long["Win"], long["Loss"], long["Tie"] = (long["For"] > long["Against"]), (long["For"] < long["Against"]), (long["For"] == long["Against"])
    t = long.groupby("Team").agg(Games=("For", "size"), Wins=("Win", "sum"), Losses=("Loss", "sum"), Ties=("Tie", "sum"), **{"Points for": ("For", "sum"), "Points against": ("Against", "sum")}).reset_index()
    pct = (t["Wins"] + 0.5 * t["Ties"]) / t["Games"]

    def expected(x):
        ratio = t["Points against"] / t["Points for"].where(t["Points for"] > 0)
        return (1 / (1 + ratio**x)).fillna((t["Points against"] == 0) * 0.5)

    if fit_exponent:
        from scipy.optimize import minimize_scalar

        exponent = float(minimize_scalar(lambda x: float(((pct - expected(x)) ** 2).sum()), bounds=(0.5, 30), method="bounded").x)
    t["Win %"] = pct
    t["Expected win %"] = expected(float(exponent))
    t["Expected wins"] = t["Expected win %"] * t["Games"]
    t["Luck"] = t["Wins"] + 0.5 * t["Ties"] - t["Expected wins"]
    t = t.sort_values("Expected win %", ascending=False, ignore_index=True)
    fit = pd.DataFrame({"Measure": ["Exponent", "Fitted", "RMSE of win %"], "Value": [f"{float(exponent):.3f}", "yes" if fit_exponent else "no", f"{float(np.sqrt(((t['Win %'] - t['Expected win %']) ** 2).mean())):.4f}"]})
    return t, fit


def football_efficiency(df, offense, defense, success=None, epa=None, yards=None, havoc=None, split=None):
    d = df.copy()
    keys = [split] if split else []
    if success:
        d["_success"] = is_true(d[success]).astype(float)
    if havoc:
        d["_havoc"] = is_true(d[havoc]).astype(float)
    for col in (epa, yards):
        if col:
            d[col] = pd.to_numeric(d[col], errors="coerce")

    def side(team_col, prefix):
        g = d.groupby([team_col] + keys)
        res = g.size().rename(f"{prefix} plays").to_frame()
        if yards:
            res[f"{prefix} yards/play"] = g[yards].mean()
        if success:
            res[f"{prefix} success rate"] = g["_success"].mean()
        if epa:
            res[f"{prefix} EPA/play"] = g[epa].mean()
            if success:
                res[f"{prefix} explosiveness"] = d[d["_success"] == 1].groupby([team_col] + keys)[epa].mean()
        if havoc:
            res[f"{prefix} havoc rate"] = g["_havoc"].mean()
        return res.rename_axis(["Team"] + keys)

    table = side(offense, "Off").join(side(defense, "Def"), how="outer").reset_index()
    if epa:
        table["Net EPA/play"] = table["Off EPA/play"] - table["Def EPA/play"]
    return table


def four_factors(df, game, team, pts, fgm, fga, fg3m, ftm, fta, orb, drb, tov, minutes=None, ft_factor=0.44, game_minutes=48):
    stats = {"PTS": pts, "FGM": fgm, "FGA": fga, "3PM": fg3m, "FTM": ftm, "FTA": fta, "ORB": orb, "DRB": drb, "TOV": tov}
    if minutes:
        stats["MIN"] = minutes
    box = df[[game, team] + list(stats.values())].dropna(subset=[game, team]).copy()
    box.columns = ["Game", "Team"] + list(stats)
    box["Team"] = box["Team"].astype(str)
    for col in stats:
        box[col] = pd.to_numeric(box[col], errors="coerce")
    sizes = box.groupby("Game")["Team"].transform("size")
    if (sizes != 2).any():
        bad = box.loc[sizes != 2, "Game"].iloc[0]
        raise ValueError(f"Each game needs exactly two team rows; game {bad} has {int(sizes[sizes != 2].iloc[0])}")
    opp = box.merge(box, on="Game", suffixes=("", " opp"))
    opp = opp[opp["Team"] != opp["Team opp"]].reset_index(drop=True)

    def rates(t):
        o = pd.DataFrame(index=t.index)
        poss = t["FGA"] - t["ORB"] + t["TOV"] + ft_factor * t["FTA"]
        opp_poss = t["FGA opp"] - t["ORB opp"] + t["TOV opp"] + ft_factor * t["FTA opp"]
        o["Possessions"] = (poss + opp_poss) / 2
        if minutes:
            o["Pace"] = game_minutes * o["Possessions"] / (t["MIN"] / 5)
        o["Off rating"] = 100 * t["PTS"] / o["Possessions"]
        o["Def rating"] = 100 * t["PTS opp"] / o["Possessions"]
        o["Net rating"] = o["Off rating"] - o["Def rating"]
        for side, s in (("Off", ""), ("Def", " opp")):
            other = " opp" if s == "" else ""
            o[f"{side} eFG%"] = (t["FGM" + s] + 0.5 * t["3PM" + s]) / t["FGA" + s]
            o[f"{side} TOV%"] = t["TOV" + s] / (t["FGA" + s] + ft_factor * t["FTA" + s] + t["TOV" + s])
            o[f"{side} ORB%"] = t["ORB" + s] / (t["ORB" + s] + t["DRB" + other])
            o[f"{side} FT/FGA"] = t["FTM" + s] / t["FGA" + s]
        return o

    by_game = pd.concat([opp[["Game", "Team", "Team opp", "PTS", "PTS opp"]].rename(columns={"Team opp": "Opponent", "PTS opp": "Opp PTS"}), rates(opp)], axis=1)
    totals = opp.drop(columns=["Game", "Team opp"]).groupby("Team").sum(numeric_only=True)
    games_played = opp.groupby("Team").size()
    season = rates(totals)
    season["Possessions"] = season["Possessions"] / games_played
    season.insert(0, "Games", games_played)
    season.insert(1, "Wins", (opp["PTS"] > opp["PTS opp"]).groupby(opp["Team"]).sum())
    season.insert(2, "Losses", (opp["PTS"] < opp["PTS opp"]).groupby(opp["Team"]).sum())
    season = season.rename(columns={"Possessions": "Possessions/game"}).reset_index().sort_values("Net rating", ascending=False, ignore_index=True)
    return season, by_game


def box_totals(df, group_by, stats):
    cols = {name: col for name, col in stats.items() if col}
    box = df[list(group_by) + list(cols.values())].copy()
    for name, col in cols.items():
        box[col] = pd.to_numeric(box[col], errors="coerce")
    box = box.rename(columns={col: name for name, col in cols.items()})
    if group_by:
        return box.groupby(list(group_by), dropna=False)[list(cols)].sum(min_count=1).reset_index()
    return box[list(cols)].sum(min_count=1).to_frame().T


def safe_div(num, den):
    den = den.astype(float)
    return num / den.where(den != 0)


def shooting_stats(df, group_by, pts, fga, fta, fgm=None, fg3m=None, fg3a=None, ft_factor=0.44):
    t = box_totals(df, group_by, {"PTS": pts, "FGM": fgm, "FGA": fga, "3PM": fg3m, "3PA": fg3a, "FTA": fta})
    t["TS%"] = safe_div(t["PTS"], 2 * (t["FGA"] + ft_factor * t["FTA"]))
    if fgm and fg3m:
        t["eFG%"] = safe_div(t["FGM"] + 0.5 * t["3PM"], t["FGA"])
    if fgm:
        t["FG%"] = safe_div(t["FGM"], t["FGA"])
    if fg3m and fg3a:
        t["3P%"] = safe_div(t["3PM"], t["3PA"])
    if fg3a:
        t["3PA rate"] = safe_div(t["3PA"], t["FGA"])
    t["FTA rate"] = safe_div(t["FTA"], t["FGA"])
    t["Points per shot"] = safe_div(t["PTS"], t["FGA"])
    return t


def batting_stats(df, group_by, ab, h, doubles, triples, hr, bb, hbp, sf, so, ibb=None, sh=None, pa=None, weights=(0.72, 0.75, 0.90, 1.24, 1.56, 1.95)):
    t = box_totals(df, group_by, {"AB": ab, "H": h, "2B": doubles, "3B": triples, "HR": hr, "BB": bb, "HBP": hbp, "SF": sf, "SO": so, "IBB": ibb, "SH": sh, "PA": pa})
    if not pa:
        t["PA"] = t["AB"] + t["BB"] + t["HBP"] + t["SF"] + (t["SH"] if sh else 0)
    t["1B"] = t["H"] - t["2B"] - t["3B"] - t["HR"]
    nibb = t["BB"] - (t["IBB"] if ibb else 0)
    t["AVG"] = safe_div(t["H"], t["AB"])
    t["OBP"] = safe_div(t["H"] + t["BB"] + t["HBP"], t["AB"] + t["BB"] + t["HBP"] + t["SF"])
    t["SLG"] = safe_div(t["1B"] + 2 * t["2B"] + 3 * t["3B"] + 4 * t["HR"], t["AB"])
    t["OPS"] = t["OBP"] + t["SLG"]
    t["ISO"] = t["SLG"] - t["AVG"]
    t["BABIP"] = safe_div(t["H"] - t["HR"], t["AB"] - t["SO"] - t["HR"] + t["SF"])
    t["K%"] = safe_div(t["SO"], t["PA"])
    t["BB%"] = safe_div(t["BB"], t["PA"])
    w_bb, w_hbp, w_1b, w_2b, w_3b, w_hr = weights
    t["wOBA"] = safe_div(w_bb * nibb + w_hbp * t["HBP"] + w_1b * t["1B"] + w_2b * t["2B"] + w_3b * t["3B"] + w_hr * t["HR"], t["AB"] + nibb + t["SF"] + t["HBP"])
    return t


def innings(series, outs_notation=True):
    ip = pd.to_numeric(series, errors="coerce").astype(float)
    if not outs_notation:
        return ip
    whole = np.floor(ip)
    return whole + np.round((ip - whole) * 10) / 3


def pitching_stats(df, group_by, ip, er, h, bb, so, hr, hbp=None, bf=None, outs_notation=True, fip_constant=3.10):
    d = df.copy()
    d["_IP"] = innings(d[ip], outs_notation)
    t = box_totals(d, group_by, {"IP": "_IP", "ER": er, "H": h, "BB": bb, "SO": so, "HR": hr, "HBP": hbp, "BF": bf})
    hbp_total = t["HBP"] if hbp else 0
    t["ERA"] = safe_div(9 * t["ER"], t["IP"])
    t["WHIP"] = safe_div(t["BB"] + t["H"], t["IP"])
    for col, name in (("H", "H/9"), ("HR", "HR/9"), ("BB", "BB/9"), ("SO", "K/9")):
        t[name] = safe_div(9 * t[col], t["IP"])
    t["K/BB"] = safe_div(t["SO"], t["BB"])
    if bf:
        t["K%"] = safe_div(t["SO"], t["BF"])
        t["BB%"] = safe_div(t["BB"], t["BF"])
        t["K-BB%"] = t["K%"] - t["BB%"]
    t["FIP"] = safe_div(13 * t["HR"] + 3 * (t["BB"] + hbp_total) - 2 * t["SO"], t["IP"]) + float(fip_constant)
    return t


def volleyball_stats(df, group_by, sets, kills, errors, attempts, assists=None, aces=None, service_errors=None, digs=None, block_solos=None, block_assists=None, reception_errors=None, team_rows=False):
    t = box_totals(df, group_by, {"Sets": sets, "Kills": kills, "Errors": errors, "Attempts": attempts, "Assists": assists, "Aces": aces, "Service errors": service_errors, "Digs": digs, "Block solos": block_solos, "Block assists": block_assists, "Reception errors": reception_errors})
    t["Hitting %"] = safe_div(t["Kills"] - t["Errors"], t["Attempts"])
    t["Kill %"] = safe_div(t["Kills"], t["Attempts"])
    solos = t["Block solos"] if block_solos else 0
    helps = t["Block assists"] if block_assists else 0
    if block_solos or block_assists:
        t["Blocks"] = solos + (0.5 if team_rows else 1.0) * helps
    t["Points"] = t["Kills"] + (t["Aces"] if aces else 0) + solos + 0.5 * helps
    for name in ("Kills", "Assists", "Aces", "Digs", "Blocks", "Points"):
        if name in t:
            t[f"{name}/set"] = safe_div(t[name], t["Sets"])
    return t


def sideout_stats(df, serving, winner, receiving=None, rally_set=(), group_by=()):
    keys = list(group_by)
    d = df.dropna(subset=[serving, winner]).copy()
    d["_serve"], d["_win"] = d[serving].astype(str), d[winner].astype(str)
    if receiving:
        d["_recv"] = d[receiving].astype(str)
    else:
        if not rally_set:
            raise ValueError("Pick the receiving team column, or the columns that identify each set")
        both = pd.concat([d[list(rally_set) + [c]].rename(columns={c: "_team"}) for c in ("_serve", "_win")])
        d = d.join(both.groupby(list(rally_set))["_team"].agg(lambda s: sorted(set(s))).rename("_teams"), on=list(rally_set))
        d["_recv"] = [next((t for t in ts if t != s), None) for ts, s in zip(d["_teams"], d["_serve"])]
    d["_point_on_serve"] = d["_win"] == d["_serve"]
    serve = d.groupby(["_serve"] + keys).agg(**{"Serve rallies": ("_point_on_serve", "size"), "Points on serve": ("_point_on_serve", "sum")})
    recv = d.dropna(subset=["_recv"]).groupby(["_recv"] + keys).agg(**{"Receive rallies": ("_point_on_serve", "size"), "Side-outs": ("_point_on_serve", lambda s: int((~s).sum()))})
    t = serve.rename_axis(["Team"] + keys).join(recv.rename_axis(["Team"] + keys), how="outer").fillna(0).reset_index()
    for col in ("Serve rallies", "Points on serve", "Receive rallies", "Side-outs"):
        t[col] = t[col].astype(int)
    t["Point-scoring %"] = safe_div(t["Points on serve"], t["Serve rallies"])
    t["Side-out %"] = safe_div(t["Side-outs"], t["Receive rallies"])
    t["Rally win %"] = safe_div(t["Points on serve"] + t["Side-outs"], t["Serve rallies"] + t["Receive rallies"])
    return t
