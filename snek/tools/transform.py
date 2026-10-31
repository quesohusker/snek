from snek.tools.base import Port, Tool, ToolError, fld, lit, opts, register, short

AGG_FUNCS = opts(
    ("sum", "Sum"),
    ("mean", "Average"),
    ("median", "Median"),
    ("min", "Min"),
    ("max", "Max"),
    ("count", "Count non-null"),
    ("size", "Count rows"),
    ("nunique", "Count distinct"),
    ("first", "First"),
    ("last", "Last"),
    ("std", "Std dev"),
    ("var", "Variance"),
    ("concat", "Concatenate"),
)

CONCAT = "lambda s: ', '.join(s.dropna().astype(str))"


def agg_expr(func):
    return CONCAT if func == "concat" else lit(func)


@register
class Summarize(Tool):
    type = "summarize"
    label = "Summarize"
    category = "Transform"
    description = "Group by columns and aggregate."
    fields = [
        fld("group_by", "Group by", "columns", []),
        fld("aggs", "Aggregations", "list", [{"column": "", "func": "sum", "name": ""}], fields=[
            fld("column", "Column", "column", ""),
            fld("func", "Action", "select", "sum", options=AGG_FUNCS),
            fld("name", "Output name", "text", "", placeholder="auto"),
        ]),
    ]

    def code(self, cfg, ctx):
        inp = ctx.var()
        out = ctx.out()
        gb = cfg["group_by"] or []
        aggs = [a for a in cfg["aggs"] or [] if a.get("column")]
        ctx.require_columns(gb + [a["column"] for a in aggs])
        if not gb and not aggs:
            raise ToolError("Pick a group-by column or an aggregation")
        if not aggs:
            return f"{out} = {inp}.groupby({lit(gb)}, dropna=False).size().reset_index(name='Count')"
        named = {}
        for a in aggs:
            name = a.get("name") or f"{a['func'].capitalize()}_{a['column']}"
            if name in named:
                raise ToolError(f"Duplicate output name {name!r}")
            named[name] = f"({a['column']!r}, {agg_expr(a['func'])})"
        body = ", ".join(f"{k!r}: {v}" for k, v in named.items())
        if gb:
            return f"{out} = {inp}.groupby({lit(gb)}, dropna=False).agg(**{{{body}}}).reset_index()"
        return f"{out} = {inp}.assign(_all=0).groupby('_all').agg(**{{{body}}}).reset_index(drop=True)"

    def summary(self, cfg):
        gb = cfg["group_by"] or []
        n = len([a for a in cfg["aggs"] or [] if a.get("column")])
        return short(f"by {', '.join(gb)}" if gb else "") + (f" · {n} agg" if n else "")


@register
class CrossTab(Tool):
    type = "crosstab"
    label = "Cross Tab"
    category = "Transform"
    description = "Pivot: turn the values of one column into new column headers."
    fields = [
        fld("group_by", "Group by (rows)", "columns", []),
        fld("header", "New column headers from", "column", ""),
        fld("value", "Values from", "column", ""),
        fld("func", "Method", "select", "sum", options=[o for o in AGG_FUNCS if o["value"] != "size"]),
    ]

    def code(self, cfg, ctx):
        gb = cfg["group_by"] or []
        ctx.require(gb, "Pick at least one group-by column")
        ctx.require(cfg["header"], "Pick the header column")
        ctx.require(cfg["value"], "Pick the value column")
        ctx.require_columns(gb + [cfg["header"], cfg["value"]])
        out = ctx.out()
        hdr = cfg["header"]
        return "\n".join([
            f"{out} = {ctx.var()}.groupby({lit(gb + [hdr])}, dropna=False)[{cfg['value']!r}].agg({agg_expr(cfg['func'])}).unstack({hdr!r}).reset_index()",
            f"{out}.columns = [str(c) for c in {out}.columns]",
        ])

    def summary(self, cfg):
        return short(f"{cfg['header']} × {cfg['value']}") if cfg["header"] else ""


@register
class Transpose(Tool):
    type = "transpose"
    label = "Transpose"
    category = "Transform"
    description = "Unpivot: turn columns into Name/Value rows."
    fields = [
        fld("keys", "Key columns (kept)", "columns", []),
        fld("data", "Data columns (blank = all others)", "columns", []),
        fld("name_col", "Name column", "text", "Name"),
        fld("value_col", "Value column", "text", "Value"),
    ]

    def code(self, cfg, ctx):
        keys = cfg["keys"] or []
        data = cfg["data"] or []
        ctx.require_columns(keys + data)
        value_vars = f", value_vars={lit(data)}" if data else ""
        return f"{ctx.out()} = {ctx.var()}.melt(id_vars={lit(keys)}{value_vars}, var_name={lit(cfg['name_col'] or 'Name')}, value_name={lit(cfg['value_col'] or 'Value')})"

    def summary(self, cfg):
        return short(f"keep {', '.join(cfg['keys'] or [])}") if cfg["keys"] else ""


@register
class Python(Tool):
    type = "python"
    label = "Python"
    category = "Developer"
    description = "Run your own pandas code. Inputs arrive as df (first) and dfs (all). Assign the result to df."
    inputs = [Port("in", "", multi=True)]
    fields = [fld("code", "Code", "python", "df = df.copy()\n")]

    def code(self, cfg, ctx):
        names = ctx.vars()
        fn = ctx.tmp("python_fn")
        body = (cfg["code"] or "").rstrip() or "pass"
        indented = "\n".join(("    " + line) if line.strip() else "" for line in body.splitlines())
        return "\n".join([
            f"def {fn}(dfs):",
            "    df = dfs[0]",
            indented,
            "    return df",
            "",
            "",
            f"{ctx.out()} = {fn}([{', '.join(names)}])",
        ])

    def summary(self, cfg):
        lines = [l for l in (cfg["code"] or "").splitlines() if l.strip()]
        return short(lines[0]) if lines else ""


@register
class WeightedAverage(Tool):
    type = "weighted_avg"
    label = "Weighted Average"
    category = "Transform"
    description = "Average a column weighted by another, such as yards per play weighted by plays. Rows with a null value or weight are skipped."
    fields = [
        fld("value", "Value", "column", ""),
        fld("weight", "Weight", "column", ""),
        fld("group_by", "Group by", "columns", []),
        fld("name", "Output column", "text", "WeightedAverage"),
    ]

    def code(self, cfg, ctx):
        ctx.require(cfg["value"], "Pick the value column")
        ctx.require(cfg["weight"], "Pick the weight column")
        gb = cfg["group_by"] or []
        ctx.require_columns([cfg["value"], cfg["weight"]] + gb)
        args = [ctx.var(), lit(cfg["value"]), lit(cfg["weight"])]
        if gb:
            args.append(lit(gb))
        args.append(f"name={lit(cfg['name'] or 'WeightedAverage')}")
        return f"{ctx.out()} = weighted_average({', '.join(args)})"

    def summary(self, cfg):
        return short(f"{cfg['value']} by {cfg['weight']}") if cfg["value"] else ""


@register
class CountRecords(Tool):
    type = "count_records"
    label = "Count Records"
    category = "Transform"
    description = "One row holding the number of input rows."
    fields = [fld("name", "Column name", "text", "Count")]

    def code(self, cfg, ctx):
        inp = ctx.var()
        return f"{ctx.out()} = pd.DataFrame({{{(cfg['name'] or 'Count')!r}: [len({inp})]}})"
