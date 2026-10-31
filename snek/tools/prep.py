from snek.expr import ExprError, translate
from snek.tools.base import (
    DTYPE_OPTIONS,
    Port,
    Tool,
    ToolError,
    convert_line,
    fld,
    is_numeric,
    is_text,
    lit,
    opts,
    register,
    short,
)

OPERATORS = opts(
    ("==", "equals"),
    ("!=", "does not equal"),
    (">", ">"),
    (">=", ">="),
    ("<", "<"),
    ("<=", "<="),
    ("contains", "contains"),
    ("not_contains", "does not contain"),
    ("startswith", "starts with"),
    ("endswith", "ends with"),
    ("in", "is in list"),
    ("isna", "is null"),
    ("notna", "is not null"),
)


def expr_or_error(expr, frame, columns):
    try:
        return translate(expr, frame, columns)
    except ExprError as e:
        raise ToolError(str(e)) from None


def typed_literal(value, dtype):
    text = str(value).strip()
    if is_numeric(dtype):
        try:
            num = float(text)
        except ValueError:
            raise ToolError(f"{text!r} is not a number") from None
        return repr(int(num)) if num.is_integer() and "int" in dtype.lower() else repr(num)
    if dtype in ("bool", "boolean"):
        return "True" if text.lower() in ("true", "1", "yes", "y", "t") else "False"
    if dtype and dtype.startswith("datetime64"):
        tz = dtype.split(", ", 1)[1].rstrip("]") if ", " in dtype else None
        return f"pd.Timestamp({text!r}, tz={tz!r})" if tz else f"pd.Timestamp({text!r})"
    return repr(str(value))


@register
class Select(Tool):
    type = "select"
    label = "Select"
    category = "Preparation"
    description = "Keep, drop, reorder, rename and change the type of columns."
    needs = "Any table."
    fields = [
        fld("fields", "Columns", "select_fields", [], dtypes=[{"value": v, "label": l} for v, l in DTYPE_OPTIONS]),
        fld("keep_new", "Keep columns not listed here", "bool", True, help="Columns that appear upstream later."),
    ]

    def code(self, cfg, ctx):
        inp = ctx.var()
        out = ctx.out()
        cols = ctx.columns()
        listed = {f["name"]: f for f in cfg["fields"] or [] if f.get("name") in cols}
        order = [f["name"] for f in cfg["fields"] or [] if f.get("name") in cols]
        order += [c for c in cols if c not in listed]
        keep = [c for c in order if (listed[c].get("keep", True) if c in listed else cfg["keep_new"])]
        if not keep:
            raise ToolError("No columns selected")
        lines = [f"{out} = {inp}" if keep == cols else f"{out} = {inp}[{lit(keep)}]"]
        renames = {c: listed[c]["rename"] for c in keep if c in listed and listed[c].get("rename") and listed[c]["rename"] != c}
        conversions = [(renames.get(c, c), listed[c]["dtype"]) for c in keep if c in listed and listed[c].get("dtype")]
        if renames:
            lines.append(f"{out} = {out}.rename(columns={lit(renames)})")
        if conversions and lines[0] == f"{out} = {inp}":
            lines[0] = f"{out} = {inp}.copy()"
        lines += [convert_line(out, c, d) for c, d in conversions]
        return "\n".join(lines)

    def summary(self, cfg):
        fields = cfg["fields"] or []
        dropped = sum(1 for f in fields if not f.get("keep", True))
        renamed = sum(1 for f in fields if f.get("rename"))
        parts = [f"drop {dropped}" if dropped else "", f"rename {renamed}" if renamed else ""]
        return ", ".join(p for p in parts if p)


@register
class Filter(Tool):
    type = "filter"
    label = "Filter"
    category = "Preparation"
    description = "Split rows into True and False streams."
    needs = "Any table. You write a condition using its columns."
    outputs = [Port("true", "T"), Port("false", "F")]
    fields = [
        fld("mode", "Mode", "select", "basic", options=opts(("basic", "Basic"), ("expression", "Expression"))),
        fld("column", "Column", "column", "", show_if={"mode": ["basic"]}),
        fld("operator", "Operator", "select", "==", options=OPERATORS, show_if={"mode": ["basic"]}),
        fld("value", "Value", "text", "", show_if={"mode": ["basic"], "operator": ["==", "!=", ">", ">=", "<", "<=", "contains", "not_contains", "startswith", "endswith", "in"]}, help="For 'is in list', separate values with commas."),
        fld("case", "Case sensitive", "bool", False, show_if={"mode": ["basic"], "operator": ["contains", "not_contains", "startswith", "endswith"]}),
        fld("expression", "Expression", "code", "", show_if={"mode": ["expression"]}, help="Pandas expression. Refer to columns as [Column Name]. Example: ([homePoints] > 30) & [conferenceGame]"),
    ]

    def mask(self, cfg, ctx, inp):
        if cfg["mode"] == "expression":
            ctx.require(cfg["expression"], "Enter an expression")
            expr = expr_or_error(cfg["expression"], inp, ctx.columns())
            return f"pd.Series({expr}, index={inp}.index).fillna(False).astype(bool)"
        col = cfg["column"]
        ctx.require(col, "Pick a column")
        ctx.require_columns([col])
        op = cfg["operator"]
        s = f"{inp}[{col!r}]"
        dtype = ctx.dtype(col)
        value = cfg["value"] or ""
        if op == "isna":
            return f"{s}.isna()"
        if op == "notna":
            return f"{s}.notna()"
        if op == "in":
            items = [typed_literal(v.strip(), dtype) for v in value.split(",") if v.strip()]
            return f"{s}.isin([{', '.join(items)}])"
        if op in ("contains", "not_contains"):
            expr = f"{s}.astype('string').str.contains({value!r}, case={bool(cfg['case'])}, regex=False)"
            return f"(~{expr}).fillna(False)" if op == "not_contains" else f"{expr}.fillna(False)"
        if op in ("startswith", "endswith"):
            if cfg["case"]:
                return f"{s}.astype('string').str.{op}({value!r}).fillna(False)"
            return f"{s}.astype('string').str.lower().str.{op}({value.lower()!r}).fillna(False)"
        return f"({s} {op} {typed_literal(value, dtype)}).fillna(False)"

    def code(self, cfg, ctx):
        inp = ctx.var()
        m = ctx.tmp("mask")
        return "\n".join([
            f"{m} = {self.mask(cfg, ctx, inp)}",
            f"{ctx.out('true')} = {inp}[{m}].reset_index(drop=True)",
            f"{ctx.out('false')} = {inp}[~{m}].reset_index(drop=True)",
        ])

    def summary(self, cfg):
        if cfg["mode"] == "expression":
            return short(cfg["expression"] or "")
        label = {o["value"]: o["label"] for o in OPERATORS}.get(cfg["operator"], cfg["operator"])
        if not cfg["column"]:
            return ""
        return short(f"[{cfg['column']}] {label} {cfg['value'] if cfg['operator'] not in ('isna', 'notna') else ''}")


@register
class Formula(Tool):
    type = "formula"
    label = "Formula"
    category = "Preparation"
    description = "Create or update columns with pandas expressions."
    needs = "Any table. New columns are built from its existing columns."
    fields = [
        fld("formulas", "Formulas", "list", [{"column": "", "expression": "", "dtype": ""}], fields=[
            fld("column", "Output column", "text", "", placeholder="new or existing column"),
            fld("expression", "Expression", "code", "", help="Refer to columns as [Column Name]. Use np, pd, and iif(condition, then, else)."),
            fld("dtype", "Type", "select", "", options=[{"value": v, "label": l} for v, l in DTYPE_OPTIONS]),
        ]),
    ]

    def code(self, cfg, ctx):
        inp = ctx.var()
        out = ctx.out()
        formulas = [f for f in cfg["formulas"] or [] if f.get("column") or f.get("expression")]
        if not formulas:
            raise ToolError("Add a formula")
        cols = list(ctx.columns())
        lines = [f"{out} = {inp}.copy()"]
        for f in formulas:
            ctx.require(f.get("column"), "Every formula needs an output column")
            ctx.require(f.get("expression"), f"Enter an expression for {f['column']}")
            expr = expr_or_error(f["expression"], out, cols)
            lines.append(f"{out}[{f['column']!r}] = {expr}")
            if f.get("dtype"):
                lines.append(convert_line(out, f["column"], f["dtype"]))
            if f["column"] not in cols:
                cols.append(f["column"])
        return "\n".join(lines)

    def summary(self, cfg):
        formulas = [f for f in cfg["formulas"] or [] if f.get("column")]
        if len(formulas) == 1:
            return short(f"{formulas[0]['column']} = {formulas[0].get('expression', '')}")
        return f"{len(formulas)} formulas" if formulas else ""


@register
class Sort(Tool):
    type = "sort"
    label = "Sort"
    category = "Preparation"
    description = "Sort rows by one or more columns."
    needs = "Any table, plus the columns to sort by."
    fields = [
        fld("keys", "Sort by", "list", [{"column": "", "order": "asc"}], fields=[
            fld("column", "Column", "column", ""),
            fld("order", "Order", "select", "asc", options=opts(("asc", "Ascending"), ("desc", "Descending"))),
        ]),
        fld("nulls", "Nulls", "select", "last", options=opts(("last", "Last"), ("first", "First"))),
    ]

    def code(self, cfg, ctx):
        keys = [k for k in cfg["keys"] or [] if k.get("column")]
        if not keys:
            raise ToolError("Pick a column to sort by")
        cols = [k["column"] for k in keys]
        ctx.require_columns(cols)
        asc = [k.get("order", "asc") == "asc" for k in keys]
        return f"{ctx.out()} = {ctx.var()}.sort_values(by={lit(cols)}, ascending={lit(asc)}, na_position={lit(cfg['nulls'])}, kind='stable').reset_index(drop=True)"

    def summary(self, cfg):
        keys = [k for k in cfg["keys"] or [] if k.get("column")]
        return short(", ".join(f"{k['column']} {'↓' if k.get('order') == 'desc' else '↑'}" for k in keys))


@register
class Sample(Tool):
    type = "sample"
    label = "Sample"
    category = "Preparation"
    description = "Keep the first, last, random or every Nth rows."
    needs = "Any table. Optional: group columns to sample within each group."
    fields = [
        fld("mode", "Keep", "select", "first", options=opts(("first", "First N rows"), ("last", "Last N rows"), ("random_n", "Random N rows"), ("random_pct", "Random percent"), ("nth", "Every Nth row"))),
        fld("n", "N", "number", 100, show_if={"mode": ["first", "last", "random_n", "nth"]}),
        fld("percent", "Percent", "number", 10, show_if={"mode": ["random_pct"]}),
        fld("seed", "Random seed", "number", 1, show_if={"mode": ["random_n", "random_pct"]}),
        fld("group_by", "Per group", "columns", [], show_if={"mode": ["first", "last"]}),
    ]

    def code(self, cfg, ctx):
        inp = ctx.var()
        n = int(cfg["n"] or 0)
        mode = cfg["mode"]
        seed = int(cfg["seed"] or 0)
        gb = cfg["group_by"] or []
        ctx.require_columns(gb)
        if mode in ("first", "last"):
            fn = "head" if mode == "first" else "tail"
            src = f"{inp}.groupby({lit(gb)}, dropna=False, sort=False)" if gb else inp
            expr = f"{src}.{fn}({n})"
        elif mode == "random_n":
            expr = f"{inp}.sample(n=min({n}, len({inp})), random_state={seed}).sort_index()"
        elif mode == "random_pct":
            expr = f"{inp}.sample(frac={float(cfg['percent'] or 0) / 100!r}, random_state={seed}).sort_index()"
        else:
            if n < 1:
                raise ToolError("N must be at least 1")
            expr = f"{inp}.iloc[::{n}]"
        return f"{ctx.out()} = {expr}.reset_index(drop=True)"

    def summary(self, cfg):
        mode = cfg["mode"]
        if mode == "random_pct":
            return f"random {cfg['percent']}%"
        return {"first": "first", "last": "last", "random_n": "random", "nth": "every"}[mode] + f" {cfg['n']}"


@register
class Unique(Tool):
    type = "unique"
    label = "Unique"
    category = "Preparation"
    description = "Split rows into unique and duplicate streams."
    needs = "Any table, plus the columns that define a duplicate."
    outputs = [Port("unique", "U"), Port("dupes", "D")]
    fields = [fld("columns", "Columns that define a duplicate", "columns", [], help="Blank uses every column.")]

    def code(self, cfg, ctx):
        inp = ctx.var()
        cols = cfg["columns"] or []
        ctx.require_columns(cols)
        d = ctx.tmp("dup")
        subset = f"subset={lit(cols)}, " if cols else ""
        return "\n".join([
            f"{d} = {inp}.duplicated({subset}keep='first')",
            f"{ctx.out('unique')} = {inp}[~{d}].reset_index(drop=True)",
            f"{ctx.out('dupes')} = {inp}[{d}].reset_index(drop=True)",
        ])

    def summary(self, cfg):
        return short(", ".join(cfg["columns"] or []) or "all columns")


@register
class RecordID(Tool):
    type = "record_id"
    label = "Record ID"
    category = "Preparation"
    description = "Add a running row number."
    needs = "Any table."
    fields = [
        fld("column", "Column name", "text", "RecordID"),
        fld("start", "Start at", "number", 1),
        fld("position", "Position", "select", "first", options=opts(("first", "First column"), ("last", "Last column"))),
    ]

    def code(self, cfg, ctx):
        inp = ctx.var()
        out = ctx.out()
        name = cfg["column"] or "RecordID"
        if name in ctx.columns():
            raise ToolError(f"Column {name!r} already exists")
        start = int(cfg["start"] or 0)
        values = f"range({start}, {start} + len({out}))"
        lines = [f"{out} = {inp}.copy()"]
        if cfg["position"] == "first":
            lines.append(f"{out}.insert(0, {name!r}, {values})")
        else:
            lines.append(f"{out}[{name!r}] = {values}")
        return "\n".join(lines)

    def summary(self, cfg):
        return cfg["column"] or ""


@register
class Cleanse(Tool):
    type = "cleanse"
    label = "Data Cleansing"
    category = "Preparation"
    description = "Trim text, fix case, fill nulls and drop empty rows or columns."
    needs = "Any table, usually with text columns to tidy."
    fields = [
        fld("columns", "Columns", "columns", [], help="Blank applies to every column."),
        fld("trim", "Trim leading and trailing spaces", "bool", True),
        fld("collapse", "Collapse repeated spaces", "bool", False),
        fld("case", "Change case", "select", "", options=opts(("", "No change"), ("upper", "UPPER"), ("lower", "lower"), ("title", "Title"))),
        fld("fill_text", "Replace null text with blank", "bool", False),
        fld("fill_numbers", "Replace null numbers with 0", "bool", False),
        fld("drop_rows", "Drop rows that are all null", "bool", False),
        fld("drop_columns", "Drop columns that are all null", "bool", False),
    ]

    def code(self, cfg, ctx):
        inp = ctx.var()
        out = ctx.out()
        chosen = cfg["columns"] or ctx.columns()
        ctx.require_columns(chosen)
        text = [c for c in chosen if is_text(ctx.dtype(c))]
        nums = [c for c in chosen if is_numeric(ctx.dtype(c))]
        lines = [f"{out} = {inp}.copy()"]
        text_ops = []
        if cfg["trim"]:
            text_ops.append(".str.strip()")
        if cfg["collapse"]:
            text_ops.append(".str.replace(r'\\s+', ' ', regex=True)")
        if cfg["case"]:
            text_ops.append(f".str.{cfg['case']}()")
        if text and text_ops:
            lines.append(f"{out}[{lit(text)}] = {out}[{lit(text)}].apply(lambda s: s{''.join(text_ops)})")
        if text and cfg["fill_text"]:
            lines.append(f"{out}[{lit(text)}] = {out}[{lit(text)}].fillna('')")
        if nums and cfg["fill_numbers"]:
            lines.append(f"{out}[{lit(nums)}] = {out}[{lit(nums)}].fillna(0)")
        if cfg["drop_rows"]:
            lines.append(f"{out} = {out}.dropna(how='all').reset_index(drop=True)")
        if cfg["drop_columns"]:
            lines.append(f"{out} = {out}.dropna(axis=1, how='all')")
        return "\n".join(lines)

    def summary(self, cfg):
        flags = [k for k in ("trim", "collapse", "fill_text", "fill_numbers", "drop_rows", "drop_columns") if cfg[k]]
        if cfg["case"]:
            flags.append(cfg["case"])
        return short(", ".join(flags).replace("_", " "))


@register
class FindReplace(Tool):
    type = "replace"
    label = "Replace Text"
    category = "Preparation"
    description = "Find and replace text inside columns. To swap values using a lookup table, use Find Replace in Join."
    needs = "A table with the text columns to search."
    fields = [
        fld("columns", "Columns", "columns", []),
        fld("find", "Find", "text", ""),
        fld("replace", "Replace with", "text", ""),
        fld("regex", "Regular expression", "bool", False),
        fld("case", "Case sensitive", "bool", True),
    ]

    def code(self, cfg, ctx):
        cols = cfg["columns"] or []
        ctx.require(cols, "Pick at least one column")
        ctx.require(cfg["find"], "Enter text to find")
        ctx.require_columns(cols)
        out = ctx.out()
        lines = [f"{out} = {ctx.var()}.copy()"]
        for c in cols:
            ref = f"{out}[{c!r}]"
            lines.append(f"{ref} = {ref}.astype('string').str.replace({cfg['find']!r}, {(cfg['replace'] or '')!r}, regex={bool(cfg['regex'])}, case={bool(cfg['case'])})")
        return "\n".join(lines)

    def summary(self, cfg):
        return short(f"{cfg['find']} → {cfg['replace']}") if cfg["find"] else ""
