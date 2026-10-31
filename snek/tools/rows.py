import re

from snek.expr import ExprError, translate
from snek.tools.base import DTYPE_OPTIONS, Tool, ToolError, convert_line, fld, lit, opts, register, short

ROW_REF = re.compile(r"\[Row([+-]\d+):([^\]]+)\]")
RANGE_TOKEN = re.compile(r"^(\d+|\d+\+|-\d+|\d+-\d+)$")


def grouped(frame, group_by, column):
    if group_by:
        return f"{frame}.groupby({lit(group_by)}, dropna=False, sort=False)[{column!r}]"
    return f"{frame}[{column!r}]"


@register
class MultiRowFormula(Tool):
    type = "multirow"
    label = "Multi-Row Formula"
    category = "Preparation"
    description = "Use values from earlier or later rows, such as last week's score or the change since the prior game."
    needs = "Rows in order, such as one row per team per game. Optional: group columns so each team stays separate."
    fields = [
        fld("column", "Output column", "text", "", placeholder="new or existing column"),
        fld("expression", "Expression", "code", "", help="Refer to other rows as [Row-1:column] or [Row+1:column], and to this row as [column]. Sort first; rows are used in their current order."),
        fld("group_by", "Restart for each group", "columns", []),
        fld("outside", "Rows that don't exist", "select", "null", options=opts(("null", "Null"), ("zero", "0"))),
        fld("dtype", "Type", "select", "", options=[{"value": v, "label": l} for v, l in DTYPE_OPTIONS]),
    ]

    def code(self, cfg, ctx):
        inp = ctx.var()
        out = ctx.out()
        col = cfg["column"]
        expr = cfg["expression"] or ""
        ctx.require(col, "Name the output column")
        ctx.require(expr, "Enter an expression")
        gb = cfg["group_by"] or []
        ctx.require_columns(gb)
        cols = ctx.columns()
        lines = [f"{out} = {inp}.copy()"]
        names = {}
        for offset, ref in ROW_REF.findall(expr):
            if ref not in cols:
                raise ToolError(f"[Row{offset}:{ref}] refers to a column that is not in the input")
            key = (int(offset), ref)
            if key not in names:
                n = -int(offset)
                tag = f"{'prev' if n > 0 else 'next'}{abs(n)}"
                safe = re.sub(r"\W", "_", ref)
                name = f"{safe}_{tag}_{ctx.node_id}"
                fill = ", fill_value=0" if cfg["outside"] == "zero" else ""
                lines.append(f"{name} = {grouped(out, gb, ref)}.shift({n}{fill})")
                names[key] = name
        body = ROW_REF.sub(lambda m: names[(int(m.group(1)), m.group(2))], expr)
        try:
            body = translate(body, out, cols)
        except ExprError as e:
            raise ToolError(str(e)) from None
        lines.append(f"{out}[{col!r}] = {body}")
        if cfg["dtype"]:
            lines.append(convert_line(out, col, cfg["dtype"]))
        return "\n".join(lines)

    def summary(self, cfg):
        return short(f"{cfg['column']} = {cfg['expression']}") if cfg["column"] else ""


@register
class RunningTotal(Tool):
    type = "running_total"
    label = "Running Total"
    category = "Transform"
    description = "Add cumulative sums, optionally restarting for each group."
    needs = "Rows in order with numeric columns to add up. Optional: group columns."
    fields = [
        fld("columns", "Columns to total", "columns", []),
        fld("group_by", "Restart for each group", "columns", []),
        fld("prefix", "New column prefix", "text", "RunTot_"),
    ]

    def code(self, cfg, ctx):
        cols = cfg["columns"] or []
        gb = cfg["group_by"] or []
        ctx.require(cols, "Pick at least one column")
        ctx.require_columns(cols + gb)
        out = ctx.out()
        lines = [f"{out} = {ctx.var()}.copy()"]
        for c in cols:
            lines.append(f"{out}[{(cfg['prefix'] or '') + c!r}] = {grouped(out, gb, c)}.cumsum()")
        return "\n".join(lines)

    def summary(self, cfg):
        return short(", ".join(cfg["columns"] or []))


@register
class Rank(Tool):
    type = "rank"
    label = "Rank"
    category = "Preparation"
    description = "Rank rows by a column, overall or within groups."
    needs = "A table with a numeric or sortable column. Optional: group columns."
    fields = [
        fld("column", "Rank by", "column", ""),
        fld("order", "Order", "select", "desc", options=opts(("desc", "Highest is 1"), ("asc", "Lowest is 1"))),
        fld("method", "Ties", "select", "min", options=opts(("min", "Share the best rank (1, 2, 2, 4)"), ("dense", "Share, no gaps (1, 2, 2, 3)"), ("first", "Break by row order (1, 2, 3, 4)"), ("average", "Average (1, 2.5, 2.5, 4)"))),
        fld("group_by", "Rank within each group", "columns", []),
        fld("name", "Output column", "text", "Rank"),
    ]

    def code(self, cfg, ctx):
        col = cfg["column"]
        gb = cfg["group_by"] or []
        ctx.require(col, "Pick a column to rank by")
        ctx.require_columns([col] + gb)
        out = ctx.out()
        name = cfg["name"] or "Rank"
        expr = f"{grouped(out, gb, col)}.rank(method={cfg['method']!r}, ascending={cfg['order'] == 'asc'})"
        if cfg["method"] != "average":
            expr += ".astype('Int64')"
        return f"{out} = {ctx.var()}.copy()\n{out}[{name!r}] = {expr}"

    def summary(self, cfg):
        return short(f"{cfg['column']} {'↓' if cfg['order'] == 'desc' else '↑'}") if cfg["column"] else ""


@register
class Tile(Tool):
    type = "tile"
    label = "Tile"
    category = "Preparation"
    description = "Assign each row to a bucket: quantiles, equal-width bins, or your own break points."
    needs = "A table with a numeric column. Optional: group columns."
    fields = [
        fld("column", "Column", "column", ""),
        fld("mode", "Method", "select", "count", options=opts(("count", "Equal counts (quantiles)"), ("width", "Equal width"), ("manual", "My break points"))),
        fld("tiles", "Number of tiles", "number", 4, show_if={"mode": ["count", "width"]}),
        fld("breaks", "Break points", "text", "", show_if={"mode": ["manual"]}, help="Comma-separated, e.g. 0, 10, 20. Values below the first or above the last get their own tile."),
        fld("group_by", "Tile within each group", "columns", [], show_if={"mode": ["count"]}),
        fld("name", "Output column", "text", "Tile"),
    ]

    def code(self, cfg, ctx):
        col = cfg["column"]
        ctx.require(col, "Pick a column")
        gb = (cfg["group_by"] or []) if cfg["mode"] == "count" else []
        ctx.require_columns([col] + gb)
        out = ctx.out()
        name = cfg["name"] or "Tile"
        n = int(cfg["tiles"] or 0)
        if cfg["mode"] == "manual":
            try:
                breaks = sorted(float(b) for b in (cfg["breaks"] or "").split(",") if b.strip())
            except ValueError:
                raise ToolError("Break points must be numbers separated by commas") from None
            ctx.require(breaks, "Enter at least one break point")
            expr = f"pd.cut({out}[{col!r}], bins=[-np.inf, {', '.join(repr(b) for b in breaks)}, np.inf], labels=False) + 1"
        else:
            if n < 2:
                raise ToolError("Use at least 2 tiles")
            fn = "qcut" if cfg["mode"] == "count" else "cut"
            arg = "q" if cfg["mode"] == "count" else "bins"
            drop = ", duplicates='drop'" if cfg["mode"] == "count" else ""
            if gb:
                expr = f"{grouped(out, gb, col)}.transform(lambda s: pd.{fn}(s, {arg}={n}, labels=False{drop}) + 1)"
            else:
                expr = f"pd.{fn}({out}[{col!r}], {arg}={n}, labels=False{drop}) + 1"
        return f"{out} = {ctx.var()}.copy()\n{out}[{name!r}] = ({expr}).astype('Int64')"

    def summary(self, cfg):
        if not cfg["column"]:
            return ""
        return short(f"{cfg['column']}: {cfg['tiles']} tiles" if cfg["mode"] != "manual" else f"{cfg['column']}: {cfg['breaks']}")


@register
class SelectRecords(Tool):
    type = "select_records"
    label = "Select Records"
    category = "Preparation"
    description = "Keep rows by position, such as 1-10, 25, 100+."
    needs = "Any table."
    fields = [fld("ranges", "Rows to keep", "textarea", "1-10", help="Comma or line separated. 5 = row 5; 1-10 = rows 1 to 10; -3 = the first 3; 100+ = row 100 to the end.")]

    def code(self, cfg, ctx):
        tokens = [t.strip() for t in (cfg["ranges"] or "").replace("\n", ",").split(",") if t.strip()]
        ctx.require(tokens, "Enter the rows to keep")
        bad = [t for t in tokens if not RANGE_TOKEN.match(t)]
        if bad:
            raise ToolError(f"Can't read {', '.join(bad)}. Use forms like 5, 1-10, -3 or 100+.")
        return f"{ctx.out()} = select_rows({ctx.var()}, {', '.join(tokens)!r})"

    def summary(self, cfg):
        return short((cfg["ranges"] or "").replace("\n", ", "))


@register
class GenerateRows(Tool):
    type = "generate_rows"
    label = "Generate Rows"
    category = "Preparation"
    description = "Create a sequence of numbers or dates, such as weeks 1 to 15 or every day of a season."
    needs = "No input."
    inputs = []
    fields = [
        fld("mode", "Generate", "select", "number", options=opts(("number", "Numbers"), ("date", "Dates"))),
        fld("name", "Column name", "text", "Value"),
        fld("start", "Start", "text", "1", help="A number, or a date like 2025-08-23."),
        fld("end", "End", "text", "15"),
        fld("step", "Step", "number", 1, show_if={"mode": ["number"]}),
        fld("freq", "Every", "select", "D", show_if={"mode": ["date"]}, options=opts(("D", "Day"), ("7D", "7 days"), ("MS", "Month (first day)"), ("ME", "Month (last day)"), ("YS", "Year"))),
    ]

    def code(self, cfg, ctx):
        name = cfg["name"] or "Value"
        start, end = str(cfg["start"] or "").strip(), str(cfg["end"] or "").strip()
        ctx.require(start, "Enter a start")
        ctx.require(end, "Enter an end")
        out = ctx.out()
        if cfg["mode"] == "date":
            return f"{out} = pd.DataFrame({{{name!r}: pd.date_range({start!r}, {end!r}, freq={cfg['freq']!r})}})"
        try:
            a, b, step = float(start), float(end), float(cfg["step"] or 1)
        except ValueError:
            raise ToolError("Start, end and step must be numbers") from None
        if step == 0 or (b - a) * step < 0:
            raise ToolError("The step must move from start toward end")
        if all(x.is_integer() for x in (a, b, step)):
            stop = int(b) + (1 if step > 0 else -1)
            return f"{out} = pd.DataFrame({{{name!r}: range({int(a)}, {stop}, {int(step)})}})"
        return f"{out} = pd.DataFrame({{{name!r}: np.arange({a!r}, {b + step / 2!r}, {step!r})}})"

    def summary(self, cfg):
        return short(f"{cfg['name']}: {cfg['start']} → {cfg['end']}")
