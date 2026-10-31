from snek.tools.base import Port, Tool, ToolError, fld, is_numeric, lit, opts, register, short

CATEGORY = "Time Series"
FREQS = opts(("D", "Daily"), ("W", "Weekly"), ("M", "Monthly"), ("Q", "Quarterly"), ("Y", "Yearly"))


def series_fields():
    return [
        fld("date", "Date column", "column", ""),
        fld("value", "Value column", "column", ""),
        fld("freq", "Period", "select", "M", options=FREQS),
        fld("periods", "Periods to forecast", "number", 12),
        fld("confidence", "Interval confidence %", "number", 95),
        fld("group_by", "One series per group", "columns", [], help="Forecast each team or product separately."),
    ]


def check_series(cfg, ctx):
    date, value = cfg["date"], cfg["value"]
    ctx.require(date, "Pick the date column")
    ctx.require(value, "Pick the value column")
    gb = cfg["group_by"] or []
    ctx.require_columns([date, value] + gb)
    if not is_numeric(ctx.dtype(value)):
        raise ToolError(f"{value} is not numeric")
    periods = int(cfg["periods"] or 0)
    if periods < 1:
        raise ToolError("Forecast at least 1 period")
    conf = float(cfg["confidence"] or 95)
    if not 50 <= conf < 100:
        raise ToolError("Confidence must be between 50 and 99.9")
    return date, value, gb, periods, conf


@register
class TSFiller(Tool):
    type = "ts_filler"
    label = "TS Filler"
    category = CATEGORY
    description = "Add rows for missing dates so every period appears once, such as a week with no game. A Filled column marks the new rows."
    fields = [
        fld("date", "Date column", "column", ""),
        fld("freq", "Period", "select", "D", options=FREQS),
        fld("group_by", "Fill each group separately", "columns", []),
        fld("method", "New rows get", "select", "none", options=opts(("none", "Nulls"), ("previous", "The previous period's values"), ("zero", "0 for numbers"))),
    ]

    def code(self, cfg, ctx):
        date = cfg["date"]
        ctx.require(date, "Pick the date column")
        gb = cfg["group_by"] or []
        ctx.require_columns([date] + gb)
        group = f", group_by={lit(gb)}" if gb else ""
        return f"{ctx.out()} = fill_periods({ctx.var()}, {date!r}, freq={cfg['freq']!r}{group}, method={cfg['method']!r})"

    def summary(self, cfg):
        return short(f"{cfg['date']} by {cfg['freq']}") if cfg["date"] else ""


@register
class RollingWindow(Tool):
    type = "rolling"
    label = "Rolling Window"
    category = CATEGORY
    description = "Moving averages and totals over the last N rows, such as a team's average over its last three games."
    fields = [
        fld("columns", "Columns", "columns", []),
        fld("window", "Window (rows)", "number", 3),
        fld("func", "Calculate", "select", "mean", options=opts(("mean", "Average"), ("sum", "Sum"), ("median", "Median"), ("min", "Min"), ("max", "Max"), ("std", "Std dev"))),
        fld("group_by", "Restart for each group", "columns", []),
        fld("exclude_current", "Use only earlier rows", "bool", False, help="Leaves the current row out, so a prediction never sees its own result."),
        fld("min_periods", "Minimum rows needed", "number", 1),
    ]

    def code(self, cfg, ctx):
        cols = cfg["columns"] or []
        gb = cfg["group_by"] or []
        ctx.require(cols, "Pick at least one column")
        ctx.require_columns(cols + gb)
        w = int(cfg["window"] or 0)
        if w < 1:
            raise ToolError("The window must be at least 1 row")
        minp = max(1, min(int(cfg["min_periods"] or 1), w))
        func = cfg["func"]
        out = ctx.out()
        roll = f"{'s.shift(1)' if cfg['exclude_current'] else 's'}.rolling({w}, min_periods={minp}).{func}()"
        lines = [f"{out} = {ctx.var()}.copy()"]
        for c in cols:
            name = f"{c}_{'prior' if cfg['exclude_current'] else 'last'}{w}_{func}"
            if gb:
                lines.append(f"{out}[{name!r}] = {out}.groupby({lit(gb)}, dropna=False, sort=False)[{c!r}].transform(lambda s: {roll})")
            else:
                lines.append(f"{out}[{name!r}] = (lambda s: {roll})({out}[{c!r}])")
        return "\n".join(lines)

    def summary(self, cfg):
        return short(f"{cfg['func']} of last {cfg['window']}: {', '.join(cfg['columns'] or [])}") if cfg["columns"] else ""


@register
class ETS(Tool):
    type = "ets"
    label = "ETS Forecast"
    category = CATEGORY
    description = "Exponential smoothing forecast with optional trend and seasonality. F = forecast with intervals, H = history with fitted values."
    outputs = [Port("forecast", "F"), Port("history", "H")]
    fields = series_fields() + [
        fld("trend", "Trend", "select", "", options=opts(("", "None"), ("add", "Additive"), ("mul", "Multiplicative"))),
        fld("damped", "Damp the trend", "bool", False, show_if={"trend": ["add", "mul"]}),
        fld("seasonal", "Seasonality", "select", "", options=opts(("", "None"), ("add", "Additive"), ("mul", "Multiplicative"))),
        fld("seasonal_periods", "Periods per season", "number", 12, show_if={"seasonal": ["add", "mul"]}, help="12 for monthly data with a yearly pattern."),
    ]

    def code(self, cfg, ctx):
        date, value, gb, periods, conf = check_series(cfg, ctx)
        args = [ctx.var(), repr(date), repr(value), f"freq={cfg['freq']!r}", f"periods={periods}"]
        if cfg["trend"]:
            args.append(f"trend={cfg['trend']!r}")
            if cfg["damped"]:
                args.append("damped=True")
        if cfg["seasonal"]:
            sp = int(cfg["seasonal_periods"] or 0)
            if sp < 2:
                raise ToolError("Periods per season must be at least 2")
            args += [f"seasonal={cfg['seasonal']!r}", f"seasonal_periods={sp}"]
        args.append(f"confidence={conf:g}")
        if gb:
            args.append(f"group_by={lit(gb)}")
        return f"{ctx.out('forecast')}, {ctx.out('history')} = ets_forecast({', '.join(args)})"

    def summary(self, cfg):
        return short(f"{cfg['value']}: {cfg['periods']} ahead") if cfg["value"] else ""


@register
class Arima(Tool):
    type = "arima"
    label = "ARIMA Forecast"
    category = CATEGORY
    description = "ARIMA forecast. Auto picks the order with the lowest AIC. F = forecast with intervals, H = history with fitted values, S = model summary."
    outputs = [Port("forecast", "F"), Port("history", "H"), Port("summary", "S")]
    fields = series_fields() + [
        fld("order_mode", "Order", "select", "auto", options=opts(("auto", "Choose automatically"), ("manual", "Set p, d, q"))),
        fld("p", "p (autoregressive terms)", "number", 1, show_if={"order_mode": ["manual"]}),
        fld("d", "d (differences)", "number", 1, show_if={"order_mode": ["manual"]}),
        fld("q", "q (moving average terms)", "number", 1, show_if={"order_mode": ["manual"]}),
        fld("seasonal", "Seasonal", "bool", False),
        fld("season_length", "Periods per season", "number", 12, show_if={"seasonal": ["true"]}),
    ]

    def code(self, cfg, ctx):
        date, value, gb, periods, conf = check_series(cfg, ctx)
        args = [ctx.var(), repr(date), repr(value), f"freq={cfg['freq']!r}", f"periods={periods}"]
        if cfg["order_mode"] == "manual":
            order = tuple(int(cfg[k] or 0) for k in ("p", "d", "q"))
            if any(v < 0 for v in order):
                raise ToolError("p, d and q must be 0 or more")
            args.append(f"order={order!r}")
        if cfg["seasonal"]:
            s = int(cfg["season_length"] or 0)
            if s < 2:
                raise ToolError("Periods per season must be at least 2")
            args.append(f"seasonal_order=(1, 1, 0, {s})")
        args.append(f"confidence={conf:g}")
        if gb:
            args.append(f"group_by={lit(gb)}")
        outs = ", ".join(ctx.out(p) for p in ("forecast", "history", "summary"))
        return f"{outs} = arima_forecast({', '.join(args)})"

    def summary(self, cfg):
        return short(f"{cfg['value']}: {cfg['periods']} ahead") if cfg["value"] else ""
