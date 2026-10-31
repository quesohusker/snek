import re

from snek.expr import ExprError, translate
from snek.tools.base import DTYPE_OPTIONS, Tool, ToolError, convert_line, fld, is_numeric, is_text, lit, opts, register, short
from snek.tools.prep import typed_literal

CURRENT = "[_CurrentField_]"
SENTINEL = "__snek_current__"
TYPE_GROUPS = opts(("numeric", "Numbers"), ("text", "Text"), ("datetime", "Dates"), ("bool", "True/False"), ("other", "Other (lists, objects)"))


def kind(dtype):
    if is_numeric(dtype):
        return "numeric"
    if is_text(dtype):
        return "text"
    if dtype.startswith("datetime"):
        return "datetime"
    if dtype in ("bool", "boolean"):
        return "bool"
    return "other"


def snake(name):
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_").lower()


@register
class AutoField(Tool):
    type = "autofield"
    label = "Auto Field"
    category = "Preparation"
    description = "Turn text columns that hold numbers, dates or true/false values into real types."
    fields = [fld("columns", "Columns", "columns", [], help="Blank checks every text column. Codes with a leading zero and four or more digits, like ZIP codes, stay text.")]

    def code(self, cfg, ctx):
        cols = cfg["columns"] or []
        ctx.require_columns(cols)
        arg = f", {lit(cols)}" if cols else ""
        return f"{ctx.out()} = auto_type({ctx.var()}{arg})"

    def summary(self, cfg):
        return short(", ".join(cfg["columns"] or []) or "all text columns")


@register
class MultiFieldFormula(Tool):
    type = "multifield"
    label = "Multi-Field Formula"
    category = "Preparation"
    description = "Apply one expression to many columns. Write the column being changed as [_CurrentField_]."
    fields = [
        fld("columns", "Columns", "columns", []),
        fld("expression", "Expression", "code", "", placeholder="[_CurrentField_].round(1)", help="[_CurrentField_] stands for each picked column in turn. Other columns work as usual."),
        fld("output", "Write results to", "select", "replace", options=opts(("replace", "The same columns"), ("new", "New columns"))),
        fld("prefix", "New column prefix", "text", "", show_if={"output": ["new"]}),
        fld("suffix", "New column suffix", "text", "_new", show_if={"output": ["new"]}),
        fld("dtype", "Type", "select", "", options=[{"value": v, "label": l} for v, l in DTYPE_OPTIONS]),
    ]

    def code(self, cfg, ctx):
        cols = cfg["columns"] or []
        expr = cfg["expression"] or ""
        ctx.require(cols, "Pick at least one column")
        ctx.require(expr, "Enter an expression")
        ctx.require_columns(cols)
        out = ctx.out()
        try:
            body = translate(expr.replace(CURRENT, SENTINEL), out, ctx.columns())
        except ExprError as e:
            raise ToolError(str(e)) from None
        body = body.replace(SENTINEL, f"{out}[col]")
        target = "col" if cfg["output"] == "replace" else f"f{(cfg['prefix'] or '') + '{col}' + (cfg['suffix'] or '')!r}"
        lines = [f"{out} = {ctx.var()}.copy()", f"for col in {lit(cols)}:", f"    {out}[{target}] = {body}"]
        if cfg["dtype"]:
            lines.append("    " + convert_line(out, "__placeholder__", cfg["dtype"]).replace("'__placeholder__'", target))
        return "\n".join(lines)

    def summary(self, cfg):
        return short(cfg["expression"] or "")


@register
class Imputation(Tool):
    type = "impute"
    label = "Imputation"
    category = "Preparation"
    description = "Fill nulls with the mean, median, most common value, a fixed value, or the nearest row."
    fields = [
        fld("columns", "Columns", "columns", []),
        fld("method", "Fill with", "select", "mean", options=opts(("mean", "Average"), ("median", "Median"), ("mode", "Most common value"), ("value", "A value"), ("ffill", "Previous row's value"), ("bfill", "Next row's value"))),
        fld("value", "Value", "text", "", show_if={"method": ["value"]}),
        fld("group_by", "Within each group", "columns", [], show_if={"method": ["mean", "median", "mode", "ffill", "bfill"]}),
        fld("flag", "Add a column that marks filled rows", "bool", False),
    ]

    def code(self, cfg, ctx):
        cols = cfg["columns"] or []
        method = cfg["method"]
        gb = (cfg["group_by"] or []) if method != "value" else []
        ctx.require(cols, "Pick at least one column")
        ctx.require_columns(cols + gb)
        if method in ("mean", "median"):
            not_num = [c for c in cols if not is_numeric(ctx.dtype(c))]
            if not_num:
                raise ToolError(f"{method.capitalize()} needs numeric columns: {', '.join(not_num)}")
        out = ctx.out()
        lines = [f"{out} = {ctx.var()}.copy()"]
        for c in cols:
            ref = f"{out}[{c!r}]"
            if cfg["flag"]:
                lines.append(f"{out}[{'Imputed_' + c!r}] = {ref}.isna()")
            src = f"{out}.groupby({lit(gb)}, dropna=False, sort=False)[{c!r}]" if gb else ref
            if method in ("mean", "median"):
                fill = f"{src}.transform({method!r})" if gb else f"{ref}.{method}()"
                lines.append(f"{ref} = {ref}.fillna({fill})")
            elif method == "mode":
                if gb:
                    lines.append(f"{ref} = {ref}.fillna({src}.transform(lambda s: s.mode().iloc[0] if s.notna().any() else s.iloc[0]))")
                else:
                    lines.append(f"{ref} = {ref}.fillna({ref}.mode().iloc[0]) if {ref}.notna().any() else {ref}")
            elif method == "value":
                ctx.require(cfg["value"], "Enter the fill value")
                lines.append(f"{ref} = {ref}.fillna({typed_literal(cfg['value'], ctx.dtype(c))})")
            else:
                lines.append(f"{ref} = {src}.{method}()")
        return "\n".join(lines)

    def summary(self, cfg):
        label = {o["value"]: o["label"] for o in self.fields[1]["options"]}[cfg["method"]]
        return short(f"{label}: {', '.join(cfg['columns'] or [])}") if cfg["columns"] else ""


@register
class DynamicRename(Tool):
    type = "dynamic_rename"
    label = "Dynamic Rename"
    category = "Developer"
    description = "Rename many columns at once: use the first row as headers, add a prefix or suffix, change case, or find and replace in names."
    fields = [
        fld("mode", "Rename by", "select", "first_row", options=opts(("first_row", "First row of data"), ("prefix", "Add prefix"), ("suffix", "Add suffix"), ("case", "Change case"), ("replace", "Find and replace in names"))),
        fld("columns", "Columns", "columns", [], show_if={"mode": ["prefix", "suffix", "case", "replace"]}, help="Blank renames every column."),
        fld("text", "Text", "text", "", show_if={"mode": ["prefix", "suffix"]}),
        fld("case", "Case", "select", "snake", show_if={"mode": ["case"]}, options=opts(("snake", "snake_case"), ("lower", "lower"), ("upper", "UPPER"), ("title", "Title Case"))),
        fld("find", "Find (regular expression)", "text", "", show_if={"mode": ["replace"]}),
        fld("replace", "Replace with", "text", "", show_if={"mode": ["replace"]}),
    ]

    def code(self, cfg, ctx):
        inp = ctx.var()
        out = ctx.out()
        mode = cfg["mode"]
        if mode == "first_row":
            return f"{out} = {inp}.iloc[1:].reset_index(drop=True)\n{out}.columns = [str(v) for v in {inp}.iloc[0]]"
        cols = cfg["columns"] or ctx.columns()
        ctx.require_columns(cols)
        if mode == "prefix":
            mapping = {c: f"{cfg['text'] or ''}{c}" for c in cols}
        elif mode == "suffix":
            mapping = {c: f"{c}{cfg['text'] or ''}" for c in cols}
        elif mode == "case":
            fn = {"snake": snake, "lower": str.lower, "upper": str.upper, "title": str.title}[cfg["case"]]
            mapping = {c: fn(c) for c in cols}
        else:
            ctx.require(cfg["find"], "Enter text to find")
            try:
                pattern = re.compile(cfg["find"])
            except re.error as e:
                raise ToolError(f"Bad regular expression: {e}") from None
            mapping = {c: pattern.sub(cfg["replace"] or "", c) for c in cols}
        mapping = {k: v for k, v in mapping.items() if k != v}
        new_names = [mapping.get(c, c) for c in ctx.columns()]
        dupes = sorted({n for n in new_names if new_names.count(n) > 1})
        if dupes:
            raise ToolError(f"Renaming would duplicate {', '.join(dupes)}")
        return f"{out} = {inp}.rename(columns={lit(mapping)})"

    def summary(self, cfg):
        return {"first_row": "first row as headers", "prefix": f"prefix {cfg['text']}", "suffix": f"suffix {cfg['text']}", "case": cfg["case"], "replace": short(f"{cfg['find']} → {cfg['replace']}")}[cfg["mode"]]


@register
class DynamicSelect(Tool):
    type = "dynamic_select"
    label = "Dynamic Select"
    category = "Developer"
    description = "Keep or drop columns by type or by a pattern in their names."
    fields = [
        fld("mode", "Select by", "select", "type", options=opts(("type", "Column type"), ("pattern", "Name pattern"))),
        fld("types", "Types", "multi_select", ["numeric"], show_if={"mode": ["type"]}, options=TYPE_GROUPS),
        fld("pattern", "Name pattern (regular expression)", "text", "", show_if={"mode": ["pattern"]}, help="Example: ^home or Yards$"),
        fld("action", "Matching columns", "select", "keep", options=opts(("keep", "Keep them"), ("drop", "Drop them"))),
    ]

    def code(self, cfg, ctx):
        cols = ctx.columns()
        if cfg["mode"] == "type":
            wanted = set(cfg["types"] or [])
            ctx.require(wanted, "Pick at least one type")
            match = [c for c in cols if kind(ctx.dtype(c)) in wanted]
        else:
            ctx.require(cfg["pattern"], "Enter a pattern")
            try:
                rx = re.compile(cfg["pattern"])
            except re.error as e:
                raise ToolError(f"Bad regular expression: {e}") from None
            match = [c for c in cols if rx.search(c)]
        keep = match if cfg["action"] == "keep" else [c for c in cols if c not in match]
        if not keep:
            raise ToolError("No columns would remain")
        return f"{ctx.out()} = {ctx.var()}[{lit(keep)}]"

    def summary(self, cfg):
        what = ", ".join(cfg["types"] or []) if cfg["mode"] == "type" else cfg["pattern"]
        return short(f"{cfg['action']} {what}")


@register
class FieldInfo(Tool):
    type = "field_info"
    label = "Field Info"
    category = "Developer"
    description = "Turn the column list into rows: name, type, position, and how many nulls."
    fields = []

    def code(self, cfg, ctx):
        inp = ctx.var()
        return (
            f"{ctx.out()} = pd.DataFrame({{'Name': [str(c) for c in {inp}.columns], 'Type': {inp}.dtypes.astype(str).tolist(), "
            f"'Position': range(1, {inp}.shape[1] + 1), 'Nulls': {inp}.isna().sum().tolist(), 'Rows': len({inp})}})"
        )
