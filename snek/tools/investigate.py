from snek.tools.base import Port, Tool, ToolError, fld, is_numeric, lit, opts, register, short

CATEGORY = "Data Investigation"


@register
class FieldSummary(Tool):
    type = "field_summary"
    label = "Field Summary"
    category = CATEGORY
    description = "One row per column: count, nulls, distinct values, min, max, mean, median, standard deviation, and the most common value."
    needs = "Any table."
    fields = []

    def code(self, cfg, ctx):
        return f"{ctx.out()} = field_summary({ctx.var()})"


@register
class FrequencyTable(Tool):
    type = "frequency"
    label = "Frequency Table"
    category = CATEGORY
    description = "Count how often each value, or each combination of values, appears, with percents."
    needs = "Any table, plus one or more columns to count."
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
    needs = "A table with two or more numeric columns."
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
    needs = "A table with two category columns, such as conference and result."
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


@register
class TestOfMeans(Tool):
    type = "test_of_means"
    label = "Test of Means"
    category = CATEGORY
    description = "Is the difference in averages real? Two groups: t-test. Three or more: one-way ANOVA. S = stats per group, T = the test."
    needs = "One row per observation with a numeric value column and a group column with two or more groups."
    outputs = [Port("summary", "S"), Port("test", "T")]
    fields = [
        fld("value", "Numeric column", "column", ""),
        fld("group", "Group column", "column", ""),
        fld("equal_var", "Assume equal variances (Student t-test)", "bool", False, help="Off uses Welch's t-test, which is safer."),
    ]

    def code(self, cfg, ctx):
        value, group = cfg["value"], cfg["group"]
        ctx.require(value, "Pick the numeric column")
        ctx.require(group, "Pick the group column")
        ctx.require_columns([value, group])
        if not is_numeric(ctx.dtype(value)):
            raise ToolError(f"{value} is not numeric")
        eq = ", equal_var=True" if cfg["equal_var"] else ""
        return f"{ctx.out('summary')}, {ctx.out('test')} = test_of_means({ctx.var()}, {value!r}, {group!r}{eq})"

    def summary(self, cfg):
        return short(f"{cfg['value']} by {cfg['group']}") if cfg["value"] else ""


@register
class ChiSquareTest(Tool):
    type = "chi_square"
    label = "Chi-Square Test"
    category = CATEGORY
    description = "Are two category columns related, such as conference and bowl eligibility? T = test result with Cramér's V, E = observed vs expected counts."
    needs = "One row per observation with two category columns."
    outputs = [Port("test", "T"), Port("expected", "E")]
    fields = [fld("rows", "First column", "column", ""), fld("columns", "Second column", "column", "")]

    def code(self, cfg, ctx):
        r, c = cfg["rows"], cfg["columns"]
        ctx.require(r, "Pick the first column")
        ctx.require(c, "Pick the second column")
        ctx.require_columns([r, c])
        return f"{ctx.out('test')}, {ctx.out('expected')} = chi_square_test({ctx.var()}, {r!r}, {c!r})"

    def summary(self, cfg):
        return short(f"{cfg['rows']} × {cfg['columns']}") if cfg["rows"] else ""


@register
class Chart(Tool):
    type = "chart"
    label = "Chart"
    category = CATEGORY
    description = "Bar, line, scatter, area, histogram, box plot or heat map. The chart shows in the results panel; connect Output Data with an .html path to save it."
    needs = "Any table with the columns to plot. Charts embed up to the row limit, so summarize large data first."
    fields = [
        fld("kind", "Chart type", "select", "bar", options=opts(("bar", "Bar"), ("line", "Line"), ("scatter", "Scatter"), ("area", "Area"), ("histogram", "Histogram"), ("box", "Box plot"), ("heatmap", "Heat map"))),
        fld("x", "X axis", "column", ""),
        fld("y", "Y axis", "column", "", help="Leave blank to count rows. Histograms use only X; box plots use Y for the values and X for groups."),
        fld("agg", "Combine Y values by", "select", "sum", options=opts(("none", "Don't combine"), ("sum", "Sum"), ("mean", "Average"), ("median", "Median"), ("min", "Minimum"), ("max", "Maximum"), ("count", "Count")), show_if={"kind": ["bar", "line", "area", "heatmap"]}),
        fld("color", "Color by (optional)", "column", "", help="For a heat map, the value that sets each cell's color."),
        fld("facet", "Small multiples by (optional)", "column", ""),
        fld("bins", "Number of bins", "number", 20, show_if={"kind": ["histogram"]}),
        fld("title", "Title (optional)", "text", ""),
        fld("max_rows", "Plot at most this many rows", "number", 5000),
    ]

    def code(self, cfg, ctx):
        if not cfg["x"]:
            raise ToolError("Pick the column for the X axis")
        if cfg["kind"] in ("scatter", "heatmap") and not cfg["y"]:
            raise ToolError("Pick the column for the Y axis")
        cols = [c for c in (cfg["x"], cfg["y"], cfg["color"], cfg["facet"]) if c]
        ctx.require_columns(cols)
        numeric = {"histogram": cfg["x"], "scatter": cfg["y"], "box": cfg["y"] or cfg["x"]}.get(cfg["kind"])
        if numeric and not is_numeric(ctx.dtype(numeric)):
            raise ToolError(f"{numeric} must be numeric for this chart")
        args = [ctx.var(), repr(cfg["kind"]), repr(cfg["x"])]
        if cfg["y"] and cfg["kind"] != "histogram":
            args.append(f"y={cfg['y']!r}")
        if cfg["kind"] in ("bar", "line", "area", "heatmap") and cfg["agg"] != "none" and (cfg["y"] or cfg["kind"] == "heatmap"):
            args.append(f"agg={cfg['agg']!r}")
        for key in ("color", "facet"):
            if cfg[key]:
                args.append(f"{key}={cfg[key]!r}")
        if cfg["kind"] == "histogram":
            args.append(f"bins={int(cfg['bins'] or 20)}")
        if cfg["title"]:
            args.append(f"title={cfg['title']!r}")
        limit = int(cfg["max_rows"] or 5000)
        if not 1 <= limit <= 100000:
            raise ToolError("Plot between 1 and 100,000 rows")
        if limit != 5000:
            args.append(f"max_rows={limit}")
        return f"{ctx.out()} = make_chart({', '.join(args)})"

    def summary(self, cfg):
        return short(f"{cfg['kind']}: {cfg['y'] or 'count'} by {cfg['x']}") if cfg["x"] else ""
