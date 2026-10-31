from snek.tools.base import Tool, ToolError, fld, is_numeric, lit, opts, register, short

CATEGORY = "Data Investigation"


@register
class FieldSummary(Tool):
    type = "field_summary"
    label = "Field Summary"
    category = CATEGORY
    description = "One row per column: count, nulls, distinct values, min, max, mean, median, standard deviation, and the most common value."
    fields = []

    def code(self, cfg, ctx):
        return f"{ctx.out()} = field_summary({ctx.var()})"


@register
class FrequencyTable(Tool):
    type = "frequency"
    label = "Frequency Table"
    category = CATEGORY
    description = "Count how often each value, or each combination of values, appears, with percents."
    fields = [
        fld("columns", "Columns", "columns", []),
        fld("nulls", "Count nulls as a value", "bool", True),
        fld("order", "Order", "select", "count", options=opts(("count", "Most common first"), ("value", "By value"))),
    ]

    def code(self, cfg, ctx):
        cols = cfg["columns"] or []
        ctx.require(cols, "Pick at least one column")
        ctx.require_columns(cols)
        out = ctx.out()
        lines = [f"{out} = {ctx.var()}.value_counts(subset={lit(cols)}, dropna={not cfg['nulls']}).reset_index(name='Count')"]
        if cfg["order"] == "value":
            lines.append(f"{out} = {out}.sort_values({lit(cols)}, na_position='last').reset_index(drop=True)")
        lines += [
            f"{out}['Percent'] = 100 * {out}['Count'] / {out}['Count'].sum()",
            f"{out}['Cumulative %'] = {out}['Percent'].cumsum()",
        ]
        return "\n".join(lines)

    def summary(self, cfg):
        return short(", ".join(cfg["columns"] or []))


@register
class Correlation(Tool):
    type = "correlation"
    label = "Correlation"
    category = CATEGORY
    description = "Correlation matrix for numeric columns: Pearson for straight-line relationships, Spearman for rank order."
    fields = [
        fld("columns", "Columns", "columns", [], help="Blank uses every numeric column."),
        fld("method", "Method", "select", "pearson", options=opts(("pearson", "Pearson"), ("spearman", "Spearman"), ("kendall", "Kendall"))),
    ]

    def code(self, cfg, ctx):
        cols = cfg["columns"] or [c for c in ctx.columns() if is_numeric(ctx.dtype(c))]
        ctx.require_columns(cols)
        if len(cols) < 2:
            raise ToolError("Pick at least two numeric columns")
        bad = [c for c in cols if not is_numeric(ctx.dtype(c))]
        if bad:
            raise ToolError(f"Not numeric: {', '.join(bad)}. Use Auto Field or Select to convert them.")
        return f"{ctx.out()} = {ctx.var()}[{lit(cols)}].corr(method={cfg['method']!r}).reset_index(names='Variable')"

    def summary(self, cfg):
        return cfg["method"].capitalize()


@register
class ContingencyTable(Tool):
    type = "contingency"
    label = "Contingency Table"
    category = CATEGORY
    description = "Cross-count two columns, such as conference by win or loss, as counts or percents."
    fields = [
        fld("rows", "Rows", "column", ""),
        fld("columns", "Columns", "column", ""),
        fld("show", "Show", "select", "count", options=opts(("count", "Counts"), ("all", "Percent of total"), ("index", "Percent of each row"), ("columns", "Percent of each column"))),
        fld("totals", "Add totals", "bool", True),
    ]

    def code(self, cfg, ctx):
        r, c = cfg["rows"], cfg["columns"]
        ctx.require(r, "Pick the row column")
        ctx.require(c, "Pick the column column")
        ctx.require_columns([r, c])
        inp = ctx.var()
        out = ctx.out()
        norm = "False" if cfg["show"] == "count" else repr(cfg["show"])
        expr = f"pd.crosstab({inp}[{r!r}], {inp}[{c!r}], normalize={norm}, margins={bool(cfg['totals'])}, margins_name='Total')"
        if cfg["show"] != "count":
            expr = f"({expr} * 100)"
        return "\n".join([
            f"{out} = {expr}.reset_index()",
            f"{out}.columns = [str(col) for col in {out}.columns]",
        ])

    def summary(self, cfg):
        return short(f"{cfg['rows']} × {cfg['columns']}") if cfg["rows"] else ""
