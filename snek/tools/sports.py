from snek.tools.base import Port, Tool, ToolError, fld, opts, register, short

CATEGORY = "Sports"
GAMES_NEEDED = "One row per game with home team, away team, home points and away points columns. Optional: a true/false neutral-site column."


def game_fields(port="in", scores=True, optional_scores=False):
    tail = " (optional)" if optional_scores else ""
    score_help = {"help": "Played games need both scores. Games without scores are treated as not yet played."} if optional_scores else {}
    return [
        fld("home", "Home team column", "column", "", port=port),
        fld("away", "Away team column", "column", "", port=port),
        *([fld("home_points", f"Home points column{tail}", "column", "", port=port, **score_help), fld("away_points", f"Away points column{tail}", "column", "", port=port)] if scores else []),
        fld("neutral", "Neutral site column (optional)", "column", "", port=port, help="True/false. Leave blank if every game had a home team."),
    ]


def check_games(cfg, ctx, port="in", scores=True):
    keys = ("home", "away", "home_points", "away_points") if scores else ("home", "away")
    cols = [cfg[k] for k in keys]
    if not all(cols):
        raise ToolError("Pick the home team, away team, and both points columns" if scores else "Pick the home and away team columns")
    ctx.require_columns(cols + ([cfg["neutral"]] if cfg.get("neutral") else []), port)
    return [repr(c) for c in cols]


def optional_scores(cfg, ctx, port):
    if bool(cfg["home_points"]) != bool(cfg["away_points"]):
        raise ToolError("Pick both points columns, or neither")
    if not cfg["home_points"]:
        return []
    ctx.require_columns([cfg["home_points"], cfg["away_points"]], port)
    return [f"home_points={cfg['home_points']!r}", f"away_points={cfg['away_points']!r}"]


def rating_fields():
    return [
        fld("team", "Team column (ratings)", "column", "", port="ratings"),
        fld("rating", "Rating column (ratings)", "column", "", port="ratings", help="Points better than average, like Team Ratings' Rating column."),
    ]


def check_ratings(cfg, ctx):
    if not cfg["team"] or not cfg["rating"]:
        raise ToolError("Pick the team and rating columns from the ratings input")
    ctx.require_columns([cfg["team"], cfg["rating"]], "ratings")
    return [repr(cfg["team"]), repr(cfg["rating"])]


def number(cfg, key, default=0.0):
    value = cfg[key]
    return float(default if value in (None, "") else value)


def box_args(ctx, cfg, required, optional=()):
    missing = [label for key, label in required if not cfg[key]]
    if missing:
        raise ToolError(f"Pick the {', '.join(missing)} column{'s' if len(missing) > 1 else ''}")
    keys = [k for k, _ in required] + [k for k in optional if cfg[k]]
    group = list(cfg.get("group_by") or [])
    ctx.require_columns(group + [cfg[k] for k in keys])
    return [ctx.var(), repr(group)] + [f"{k}={cfg[k]!r}" for k in keys]


def group_field(label="Group by (player, team or season)"):
    return fld("group_by", label, "columns", [], help="Rows are added up within each group before rates are worked out. Leave empty for one overall line.")


@register
class TeamRatings(Tool):
    type = "team_ratings"
    label = "Team Ratings"
    category = CATEGORY
    group = "All sports"
    description = "Simple Rating System (SRS / Massey): points better than an average team, adjusted for schedule. Outputs: ratings, games with predicted margins, and fit with the home-field edge."
    needs = GAMES_NEEDED
    outputs = [Port("ratings", "ratings"), Port("games", "games"), Port("fit", "fit")]
    fields = game_fields() + [
        fld("home_field", "Estimate home-field advantage", "bool", True),
        fld("cap", "Cap each margin at (0 = no cap)", "number", 0, help="A cap like 28 stops blowouts from dominating."),
    ]

    def code(self, cfg, ctx):
        args = [ctx.var()] + check_games(cfg, ctx)
        if cfg["neutral"]:
            args.append(f"neutral={cfg['neutral']!r}")
        if not cfg["home_field"]:
            args.append("home_field=False")
        if cfg["cap"]:
            if float(cfg["cap"]) <= 0:
                raise ToolError("The cap must be above 0")
            args.append(f"cap={float(cfg['cap']):g}")
        outs = ", ".join(ctx.out(p) for p in ("ratings", "games", "fit"))
        return f"{outs} = team_ratings({', '.join(args)})"

    def summary(self, cfg):
        return short(f"{cfg['home']} vs {cfg['away']}" + (f", cap {cfg['cap']:g}" if cfg["cap"] else "")) if cfg["home"] else ""


@register
class EloRatings(Tool):
    type = "elo"
    label = "Elo Ratings"
    category = CATEGORY
    group = "All sports"
    description = "Game-by-game Elo with home edge, margin of victory and season carry-over. Outputs: current ratings, and each game's pre-game ratings and win probability."
    needs = GAMES_NEEDED[:-1] + ", a date or week column to put games in order, and a season column for carry-over."
    outputs = [Port("ratings", "ratings"), Port("games", "games")]
    fields = game_fields() + [
        fld("order", "Order games by (date or week)", "column", ""),
        fld("season", "Season column (optional)", "column", "", help="When a team starts a new season its rating moves partway back toward average."),
        fld("k", "K factor", "number", 20),
        fld("home_advantage", "Home edge (Elo points)", "number", 55),
        fld("start", "Starting rating", "number", 1500),
        fld("margin", "Weight wins by margin of victory", "bool", True),
        fld("carryover", "Carry-over between seasons", "number", 0.75, show_if={}, help="0.75 keeps three quarters of a team's distance from average."),
    ]

    def code(self, cfg, ctx):
        args = [ctx.var()] + check_games(cfg, ctx)
        for key in ("order", "neutral", "season"):
            if cfg[key]:
                ctx.require_columns([cfg[key]])
                args.append(f"{key}={cfg[key]!r}")
        k = float(cfg["k"] or 0)
        if k <= 0:
            raise ToolError("K must be above 0")
        carry = float(cfg["carryover"] if cfg["carryover"] is not None else 0.75)
        if not 0 <= carry <= 1:
            raise ToolError("Carry-over must be between 0 and 1")
        args += [f"k={k:g}", f"home_advantage={float(cfg['home_advantage'] or 0):g}", f"start={float(cfg['start'] or 1500):g}"]
        if not cfg["margin"]:
            args.append("margin_of_victory=False")
        if cfg["season"]:
            args.append(f"carryover={carry:g}")
        return f"{ctx.out('ratings')}, {ctx.out('games')} = elo_ratings({', '.join(args)})"

    def summary(self, cfg):
        return short(f"K {cfg['k']:g}, home {cfg['home_advantage']:g}") if cfg["home"] else ""


@register
class OpponentAdjust(Tool):
    type = "opponent_adjust"
    label = "Opponent Adjust"
    category = CATEGORY
    group = "All sports"
    description = "Adjusts per-game stats for opponent strength (ridge regression on team and opponent). Outputs: adjusted offense and defense per team, and fit."
    needs = "One row per team per game: a team column, an opponent column, and one or more numeric stat columns (points, yards per play, EPA per play...). Optional: home/away column and a weight column such as plays."
    outputs = [Port("adjusted", "adjusted"), Port("fit", "fit")]
    fields = [
        fld("team", "Team column", "column", ""),
        fld("opponent", "Opponent column", "column", ""),
        fld("stats", "Stats to adjust", "columns", [], help="Offense columns are what the team did; defense columns are what its opponents did against it."),
        fld("location", "Home/away column (optional)", "column", "", help="home/away/neutral, 1/-1/0, or true for home."),
        fld("weight", "Weight column (optional)", "column", "", help="For per-play averages, weight each game by its plays."),
        fld("alpha", "Ridge strength", "number", 1, help="Higher pulls every team toward average. Raise it when there are few games per team."),
    ]

    def code(self, cfg, ctx):
        if not cfg["team"] or not cfg["opponent"] or not cfg["stats"]:
            raise ToolError("Pick the team and opponent columns and at least one stat")
        ctx.require_columns([cfg["team"], cfg["opponent"]] + list(cfg["stats"]) + [cfg[k] for k in ("location", "weight") if cfg[k]])
        alpha = number(cfg, "alpha", 1)
        if alpha < 0:
            raise ToolError("Ridge strength can't be negative")
        args = [ctx.var(), repr(cfg["team"]), repr(cfg["opponent"]), repr(list(cfg["stats"]))]
        args += [f"{k}={cfg[k]!r}" for k in ("location", "weight") if cfg[k]]
        args.append(f"alpha={alpha:g}")
        return f"{ctx.out('adjusted')}, {ctx.out('fit')} = opponent_adjust({', '.join(args)})"

    def summary(self, cfg):
        return short(", ".join(cfg["stats"])) if cfg["stats"] else ""


@register
class SpreadWinProbability(Tool):
    type = "spread_win_prob"
    label = "Spread & Win Probability"
    category = CATEGORY
    group = "All sports"
    description = "Turns team ratings into a predicted margin and win probability for each game, and grades picks against betting lines. Outputs: games and a summary."
    needs = "ratings input: one row per team with a rating (connect Team Ratings' ratings output). games input: one row per game with home and away team columns. Optional: scores to grade the picks, and a betting line column."
    inputs = [Port("ratings", "ratings"), Port("games", "games")]
    outputs = [Port("games", "games"), Port("summary", "summary")]
    fields = rating_fields() + game_fields("games", optional_scores=True) + [
        fld("home_edge", "Home-field edge (points)", "number", 0, help="Use the home-field value from Team Ratings' fit output."),
        fld("sigma", "Spread of results (0 = estimate)", "number", 0, help="Standard deviation of real margins around the prediction. 0 estimates it from the played games, allowing for the ratings having been fit to them."),
        fld("line", "Betting line column (optional)", "column", "", port="games"),
        fld("line_sign", "Line convention", "select", "negative", options=opts(("negative", "Home favorite is negative (-7)"), ("positive", "Home favorite is positive (+7)"))),
    ]

    def code(self, cfg, ctx):
        args = [ctx.var("ratings"), ctx.var("games")] + check_ratings(cfg, ctx) + check_games(cfg, ctx, "games", scores=False)
        args += optional_scores(cfg, ctx, "games")
        if cfg["neutral"]:
            args.append(f"neutral={cfg['neutral']!r}")
        sigma = number(cfg, "sigma")
        if sigma < 0:
            raise ToolError("The spread of results can't be negative")
        args += [f"home_edge={number(cfg, 'home_edge'):g}", f"sigma={sigma:g}"]
        if cfg["line"]:
            ctx.require_columns([cfg["line"]], "games")
            args.append(f"line={cfg['line']!r}")
            if cfg["line_sign"] == "positive":
                args.append("line_negative_favorite=False")
        return f"{ctx.out('games')}, {ctx.out('summary')} = game_predictions({', '.join(args)})"

    def summary(self, cfg):
        return "vs line" if cfg["line"] else ""


@register
class SeasonSimulation(Tool):
    type = "season_sim"
    label = "Season Simulation"
    category = CATEGORY
    group = "All sports"
    description = "Monte Carlo season: plays out every unplayed game thousands of times from team ratings. Outputs: projected wins and odds per team, and the win distribution."
    needs = "ratings input: one row per team with a rating (connect Team Ratings' ratings output). games input: the full schedule, one row per game with home and away teams. Played games keep their scores; games with blank scores are simulated."
    inputs = [Port("ratings", "ratings"), Port("games", "games")]
    outputs = [Port("teams", "teams"), Port("dist", "distribution")]
    fields = rating_fields() + game_fields("games", optional_scores=True) + [
        fld("home_edge", "Home-field edge (points)", "number", 0, help="Use the home-field value from Team Ratings' fit output."),
        fld("sigma", "Spread of results (0 = estimate)", "number", 0, help="Standard deviation of real margins around the prediction. 0 estimates it from the played games, allowing for the ratings having been fit to them."),
        fld("simulations", "Simulations", "number", 10000),
        fld("target_wins", "Show the chance of at least this many wins", "number", 6),
        fld("seed", "Random seed", "number", 1, help="The same seed gives the same results every run."),
    ]

    def code(self, cfg, ctx):
        args = [ctx.var("ratings"), ctx.var("games")] + check_ratings(cfg, ctx) + check_games(cfg, ctx, "games", scores=False)
        args += optional_scores(cfg, ctx, "games")
        if cfg["neutral"]:
            args.append(f"neutral={cfg['neutral']!r}")
        sims = int(number(cfg, "simulations", 10000))
        if not 100 <= sims <= 200000:
            raise ToolError("Simulations must be between 100 and 200,000")
        sigma = number(cfg, "sigma")
        if sigma < 0:
            raise ToolError("The spread of results can't be negative")
        args += [f"home_edge={number(cfg, 'home_edge'):g}", f"sigma={sigma:g}", f"simulations={sims}", f"seed={int(number(cfg, 'seed', 1))}", f"target_wins={int(number(cfg, 'target_wins', 6))}"]
        return f"{ctx.out('teams')}, {ctx.out('dist')} = simulate_season({', '.join(args)})"

    def summary(self, cfg):
        return f"{int(number(cfg, 'simulations', 10000)):,} seasons"


@register
class Pythagorean(Tool):
    type = "pythagorean"
    label = "Pythagorean Expectation"
    category = CATEGORY
    group = "All sports"
    description = "Expected win % from points scored and allowed, and luck: actual wins minus expected wins. Outputs: teams, and the exponent and fit."
    needs = "One row per game with home team, away team, home points and away points columns."
    outputs = [Port("teams", "teams"), Port("fit", "fit")]
    fields = [f for f in game_fields() if f["key"] != "neutral"] + [
        fld("exponent", "Exponent", "number", 2.37, help="Common choices: 1.83 baseball, 2.37 pro football, about 14 pro basketball."),
        fld("fit_exponent", "Fit the exponent to this data", "bool", False, help="Finds the exponent that best matches these teams' records."),
    ]

    def code(self, cfg, ctx):
        args = [ctx.var()] + check_games(cfg, ctx)
        exponent = number(cfg, "exponent", 2.37)
        if exponent <= 0:
            raise ToolError("The exponent must be above 0")
        args.append(f"exponent={exponent:g}")
        if cfg["fit_exponent"]:
            args.append("fit_exponent=True")
        return f"{ctx.out('teams')}, {ctx.out('fit')} = pythagorean({', '.join(args)})"

    def summary(self, cfg):
        return "fitted exponent" if cfg["fit_exponent"] else f"exponent {number(cfg, 'exponent', 2.37):g}"


@register
class GarbageTime(Tool):
    type = "garbage_time"
    label = "Garbage-Time Filter"
    category = CATEGORY
    group = "Football"
    description = "Splits plays into competitive (K) and garbage time (G) by quarter and score margin."
    needs = "Play-by-play: one row per play with a quarter (period) column and both teams' scores at the time of the play."
    outputs = [Port("kept", "competitive"), Port("garbage", "garbage")]
    fields = [
        fld("period", "Quarter column", "column", ""),
        fld("score_a", "Offense score column", "column", ""),
        fld("score_b", "Defense score column", "column", ""),
        fld("q1", "Garbage in Q1 when the margin is over (0 = never)", "number", 0),
        fld("q2", "Q2 margin over", "number", 38),
        fld("q3", "Q3 margin over", "number", 28),
        fld("q4", "Q4 margin over", "number", 22, help="Overtime is never garbage time. These defaults are a common college definition; adjust them for your league."),
    ]

    def code(self, cfg, ctx):
        cols = [cfg["period"], cfg["score_a"], cfg["score_b"]]
        if not all(cols):
            raise ToolError("Pick the quarter column and both score columns")
        ctx.require_columns(cols)
        src = ctx.var()
        limits = {q: number(cfg, f"q{q}") for q in range(1, 5)}
        limits = {q: v for q, v in limits.items() if v > 0}
        margin, flag = ctx.tmp("margin"), ctx.tmp("garbage")
        return "\n".join([
            f"{margin} = (pd.to_numeric({src}[{cfg['score_a']!r}], errors='coerce') - pd.to_numeric({src}[{cfg['score_b']!r}], errors='coerce')).abs()",
            f"{flag} = {margin} > pd.to_numeric({src}[{cfg['period']!r}], errors='coerce').map({ {q: float(v) for q, v in limits.items()} })",
            f"{ctx.out('kept')} = {src}[~{flag}].reset_index(drop=True)",
            f"{ctx.out('garbage')} = {src}[{flag}].reset_index(drop=True)",
        ])

    def summary(self, cfg):
        return short(" / ".join(f"{number(cfg, f'q{q}'):g}" for q in range(1, 5)))


@register
class SuccessRate(Tool):
    type = "success_rate"
    label = "Success Rate"
    category = CATEGORY
    group = "Football"
    description = "Marks each play a success or not: enough yards for the down. Adds a true/false column."
    needs = "Play-by-play: one row per play with down, distance (yards to go) and yards gained columns."
    fields = [
        fld("down", "Down column", "column", ""),
        fld("distance", "Distance (yards to go) column", "column", ""),
        fld("yards", "Yards gained column", "column", ""),
        fld("first", "1st down: share of distance needed", "number", 0.5),
        fld("second", "2nd down: share needed", "number", 0.7),
        fld("later", "3rd and 4th down: share needed", "number", 1.0),
        fld("name", "New column name", "text", "Success"),
    ]

    def code(self, cfg, ctx):
        cols = [cfg["down"], cfg["distance"], cfg["yards"]]
        if not all(cols):
            raise ToolError("Pick the down, distance and yards gained columns")
        ctx.require_columns(cols)
        src, out = ctx.var(), ctx.out()
        down = f"pd.to_numeric({out}[{cfg['down']!r}], errors='coerce')"
        share = f"np.select([{down} == 1, {down} == 2, {down} >= 3], [{number(cfg, 'first', 0.5):g}, {number(cfg, 'second', 0.7):g}, {number(cfg, 'later', 1.0):g}], np.nan)"
        return "\n".join([
            f"{out} = {src}.copy()",
            f"{out}[{(cfg['name'] or 'Success')!r}] = pd.to_numeric({out}[{cfg['yards']!r}], errors='coerce') >= {share} * pd.to_numeric({out}[{cfg['distance']!r}], errors='coerce')",
        ])

    def summary(self, cfg):
        return f"{number(cfg, 'first', 0.5):g} / {number(cfg, 'second', 0.7):g} / {number(cfg, 'later', 1.0):g}"


@register
class FootballEfficiency(Tool):
    type = "football_efficiency"
    label = "Football Efficiency"
    category = CATEGORY
    group = "Football"
    description = "Per-team offense and defense: plays, yards per play, success rate, EPA per play, explosiveness (EPA on successful plays) and havoc rate."
    needs = "Play-by-play: one row per play with offense and defense team columns. Add any of: a success column (from Success Rate), an EPA or PPA column, yards gained, a true/false havoc column."
    fields = [
        fld("offense", "Offense team column", "column", ""),
        fld("defense", "Defense team column", "column", ""),
        fld("success", "Success column (optional)", "column", "", help="True/false, for example from the Success Rate tool."),
        fld("epa", "EPA or PPA column (optional)", "column", ""),
        fld("yards", "Yards gained column (optional)", "column", ""),
        fld("havoc", "Havoc column (optional)", "column", "", help="True/false: tackles for loss, sacks, forced fumbles, interceptions, pass breakups."),
        fld("split", "Split by (optional)", "column", "", help="For example rush/pass, or down."),
    ]

    def code(self, cfg, ctx):
        if not cfg["offense"] or not cfg["defense"]:
            raise ToolError("Pick the offense and defense columns")
        optional = [k for k in ("success", "epa", "yards", "havoc", "split") if cfg[k]]
        if not any(cfg[k] for k in ("success", "epa", "yards", "havoc")):
            raise ToolError("Pick at least one of success, EPA, yards or havoc")
        ctx.require_columns([cfg["offense"], cfg["defense"]] + [cfg[k] for k in optional])
        args = [ctx.var(), repr(cfg["offense"]), repr(cfg["defense"])] + [f"{k}={cfg[k]!r}" for k in optional]
        return f"{ctx.out()} = football_efficiency({', '.join(args)})"

    def summary(self, cfg):
        return short(", ".join(k for k in ("success", "epa", "yards", "havoc") if cfg[k]))


BASKETBALL_BOX = [("pts", "Points"), ("fgm", "Field goals made"), ("fga", "Field goal attempts"), ("fg3m", "3-pointers made"), ("ftm", "Free throws made"), ("fta", "Free throw attempts"), ("orb", "Offensive rebounds"), ("drb", "Defensive rebounds"), ("tov", "Turnovers")]


@register
class FourFactors(Tool):
    type = "four_factors"
    label = "Four Factors"
    category = CATEGORY
    group = "Basketball"
    description = "Possessions, offensive, defensive and net rating per 100 possessions, and Dean Oliver's four factors for offense and defense. Outputs: teams, and each game."
    needs = "Team box scores: two rows per game (one per team) with a game ID, team, and points, FGM, FGA, 3PM, FTM, FTA, offensive rebounds, defensive rebounds and turnovers."
    outputs = [Port("teams", "teams"), Port("games", "games")]
    fields = [fld("game", "Game ID column", "column", ""), fld("team", "Team column", "column", "")] + [fld(k, f"{label} column", "column", "") for k, label in BASKETBALL_BOX] + [
        fld("minutes", "Team minutes column (optional)", "column", "", help="Total player minutes, like 240 for a 48-minute game. Adds pace."),
        fld("game_minutes", "Minutes in a regulation game", "number", 48, help="48 for the NBA, 40 for college and FIBA."),
        fld("ft_factor", "Free-throw possession factor", "number", 0.44),
    ]

    def code(self, cfg, ctx):
        required = [("game", "game ID"), ("team", "team")] + BASKETBALL_BOX
        missing = [label.lower() for key, label in required if not cfg[key]]
        if missing:
            raise ToolError(f"Pick the {', '.join(missing)} column{'s' if len(missing) > 1 else ''}")
        ctx.require_columns([cfg[k] for k, _ in required] + ([cfg["minutes"]] if cfg["minutes"] else []))
        args = [ctx.var()] + [repr(cfg[k]) for k, _ in required]
        if cfg["minutes"]:
            args += [f"minutes={cfg['minutes']!r}", f"game_minutes={number(cfg, 'game_minutes', 48):g}"]
        args.append(f"ft_factor={number(cfg, 'ft_factor', 0.44):g}")
        return f"{ctx.out('teams')}, {ctx.out('games')} = four_factors({', '.join(args)})"


@register
class ShootingEfficiency(Tool):
    type = "shooting"
    label = "Shooting Efficiency"
    category = CATEGORY
    group = "Basketball"
    description = "True shooting %, effective FG %, 3-point and free-throw attempt rates, and points per shot, for players or teams."
    needs = "Box score rows (player or team) with points, field goal attempts and free throw attempts. Optional: FGM, 3PM, 3PA."
    fields = [group_field("Group by (player or team)"), fld("pts", "Points column", "column", ""), fld("fga", "Field goal attempts column", "column", ""), fld("fta", "Free throw attempts column", "column", ""),
              fld("fgm", "Field goals made column (optional)", "column", ""), fld("fg3m", "3-pointers made column (optional)", "column", ""), fld("fg3a", "3-point attempts column (optional)", "column", ""),
              fld("ft_factor", "Free-throw factor", "number", 0.44)]

    def code(self, cfg, ctx):
        args = box_args(ctx, cfg, [("pts", "points"), ("fga", "FGA"), ("fta", "FTA")], ("fgm", "fg3m", "fg3a"))
        return f"{ctx.out()} = shooting_stats({', '.join(args)}, ft_factor={number(cfg, 'ft_factor', 0.44):g})"


BATTING = [("ab", "At bats"), ("h", "Hits"), ("doubles", "Doubles"), ("triples", "Triples"), ("hr", "Home runs"), ("bb", "Walks"), ("hbp", "Hit by pitch"), ("sf", "Sacrifice flies"), ("so", "Strikeouts")]


@register
class BattingStats(Tool):
    type = "batting"
    label = "Batting Stats"
    category = CATEGORY
    group = "Baseball"
    description = "AVG, OBP, SLG, OPS, ISO, BABIP, strikeout and walk rates, and wOBA, for players or teams."
    needs = "Batting lines (per game or season) with AB, H, 2B, 3B, HR, BB, HBP, SF and SO columns. Optional: IBB, SH, PA."
    fields = [group_field()] + [fld(k, f"{label} column", "column", "") for k, label in BATTING] + [
        fld("ibb", "Intentional walks column (optional)", "column", ""),
        fld("sh", "Sacrifice bunts column (optional)", "column", ""),
        fld("pa", "Plate appearances column (optional)", "column", "", help="Leave blank to count AB + BB + HBP + SF + SH."),
        fld("weights", "wOBA weights: BB, HBP, 1B, 2B, 3B, HR", "text", "0.72, 0.75, 0.90, 1.24, 1.56, 1.95", help="Defaults are the original weights from The Book. Use your season's weights for precise work."),
    ]

    def code(self, cfg, ctx):
        args = box_args(ctx, cfg, [(k, label.lower()) for k, label in BATTING], ("ibb", "sh", "pa"))
        try:
            weights = tuple(float(w) for w in str(cfg["weights"]).split(","))
        except ValueError:
            raise ToolError("wOBA weights must be six numbers separated by commas")
        if len(weights) != 6:
            raise ToolError("wOBA weights must be six numbers separated by commas")
        return f"{ctx.out()} = batting_stats({', '.join(args)}, weights={weights!r})"


@register
class PitchingStats(Tool):
    type = "pitching"
    label = "Pitching Stats"
    category = CATEGORY
    group = "Baseball"
    description = "ERA, WHIP, per-nine rates, K/BB, strikeout and walk rates, and FIP, for pitchers or staffs."
    needs = "Pitching lines (per game or season) with innings pitched, earned runs, hits, walks, strikeouts and home runs. Optional: HBP and batters faced."
    fields = [group_field("Group by (pitcher, team or season)"), fld("ip", "Innings pitched column", "column", ""), fld("er", "Earned runs column", "column", ""), fld("h", "Hits allowed column", "column", ""),
              fld("bb", "Walks column", "column", ""), fld("so", "Strikeouts column", "column", ""), fld("hr", "Home runs allowed column", "column", ""),
              fld("hbp", "Hit batters column (optional)", "column", ""), fld("bf", "Batters faced column (optional)", "column", ""),
              fld("outs_notation", "Innings use baseball notation (6.1 = 6⅓)", "bool", True),
              fld("fip_constant", "FIP constant", "number", 3.10, help="Puts FIP on the ERA scale. It changes by league and season.")]

    def code(self, cfg, ctx):
        args = box_args(ctx, cfg, [("ip", "innings"), ("er", "earned runs"), ("h", "hits"), ("bb", "walks"), ("so", "strikeouts"), ("hr", "home runs")], ("hbp", "bf"))
        if not cfg["outs_notation"]:
            args.append("outs_notation=False")
        return f"{ctx.out()} = pitching_stats({', '.join(args)}, fip_constant={number(cfg, 'fip_constant', 3.10):g})"


@register
class VolleyballStats(Tool):
    type = "volleyball_stats"
    label = "Volleyball Box Stats"
    category = CATEGORY
    group = "Volleyball"
    description = "Hitting %, kill %, points (kills + aces + solo blocks + half of block assists), blocks, and per-set rates for players or teams."
    needs = "Box score rows (player or team) with sets played, kills, attack errors and total attacks. Optional: assists, aces, service errors, digs, block solos, block assists, reception errors."
    fields = [group_field("Group by (player, team or match)"), fld("sets", "Sets played column", "column", ""), fld("kills", "Kills column", "column", ""), fld("errors", "Attack errors column", "column", ""), fld("attempts", "Total attacks column", "column", "")] + [
        fld(k, f"{label} column (optional)", "column", "") for k, label in (("assists", "Assists"), ("aces", "Aces"), ("service_errors", "Service errors"), ("digs", "Digs"), ("block_solos", "Block solos"), ("block_assists", "Block assists"), ("reception_errors", "Reception errors"))
    ] + [fld("team_rows", "Rows are team totals", "bool", False, help="Team blocks count each block assist as half; player blocks count it as one.")]

    def code(self, cfg, ctx):
        args = box_args(ctx, cfg, [("sets", "sets"), ("kills", "kills"), ("errors", "attack errors"), ("attempts", "total attacks")], ("assists", "aces", "service_errors", "digs", "block_solos", "block_assists", "reception_errors"))
        if cfg["team_rows"]:
            args.append("team_rows=True")
        return f"{ctx.out()} = volleyball_stats({', '.join(args)})"


@register
class SideOut(Tool):
    type = "sideout"
    label = "Side-Out & Serve"
    category = CATEGORY
    group = "Volleyball"
    description = "From rally-by-rally data: side-out %, point-scoring % on serve, and rally win % per team."
    needs = "Play-by-play: one row per rally with the serving team and the team that won the point. Also the receiving team, or the columns that identify each set (match and set number)."
    fields = [
        fld("serving", "Serving team column", "column", ""),
        fld("winner", "Point winner column", "column", ""),
        fld("receiving", "Receiving team column", "column", "", help="Leave blank to work it out from the two teams in each set."),
        fld("rally_set", "Columns that identify a set", "columns", [], help="For example date, home team and set number. Only needed without a receiving column."),
        fld("group_by", "Group results by (optional)", "columns", [], help="Leave empty for one line per team."),
    ]

    def code(self, cfg, ctx):
        if not cfg["serving"] or not cfg["winner"]:
            raise ToolError("Pick the serving team and point winner columns")
        if not cfg["receiving"] and not cfg["rally_set"]:
            raise ToolError("Pick the receiving team column, or the columns that identify each set")
        ctx.require_columns([cfg["serving"], cfg["winner"]] + ([cfg["receiving"]] if cfg["receiving"] else []) + list(cfg["rally_set"]) + list(cfg["group_by"]))
        args = [ctx.var(), repr(cfg["serving"]), repr(cfg["winner"])]
        if cfg["receiving"]:
            args.append(f"receiving={cfg['receiving']!r}")
        else:
            args.append(f"rally_set={list(cfg['rally_set'])!r}")
        if cfg["group_by"]:
            args.append(f"group_by={list(cfg['group_by'])!r}")
        return f"{ctx.out()} = sideout_stats({', '.join(args)})"
