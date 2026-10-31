from snek.tools.base import Port, Tool, ToolError, fld, register, short

CATEGORY = "Sports"


def game_fields():
    return [
        fld("home", "Home team column", "column", ""),
        fld("away", "Away team column", "column", ""),
        fld("home_points", "Home points column", "column", ""),
        fld("away_points", "Away points column", "column", ""),
        fld("neutral", "Neutral site column (optional)", "column", "", help="True/false. Leave blank if every game had a home team."),
    ]


def check_games(cfg, ctx):
    cols = [cfg[k] for k in ("home", "away", "home_points", "away_points")]
    if not all(cols):
        raise ToolError("Pick the home team, away team, and both points columns")
    ctx.require_columns(cols + ([cfg["neutral"]] if cfg["neutral"] else []))
    return [repr(c) for c in cols]


@register
class TeamRatings(Tool):
    type = "team_ratings"
    label = "Team Ratings"
    category = CATEGORY
    description = "Simple Rating System (SRS / Massey): points better than an average team, adjusted for schedule. R = ratings, G = games with predicted margins, F = fit and home-field edge."
    outputs = [Port("ratings", "R"), Port("games", "G"), Port("fit", "F")]
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
    description = "Game-by-game Elo with home edge, margin of victory and season carry-over. R = current ratings, G = each game's pre-game ratings and win probability."
    outputs = [Port("ratings", "R"), Port("games", "G")]
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
