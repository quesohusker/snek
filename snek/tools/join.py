from snek.tools.base import Port, Tool, ToolError, fld, lit, opts, register, short


@register
class Join(Tool):
    type = "join"
    label = "Join"
    category = "Join"
    description = "Match two inputs on key columns. L = left only, J = matched, R = right only."
    inputs = [Port("left", "L"), Port("right", "R")]
    outputs = [Port("left", "L"), Port("join", "J"), Port("right", "R")]
    fields = [
        fld("keys", "Join on", "list", [{"left": "", "right": ""}], fields=[
            fld("left", "Left column", "column", "", port="left"),
            fld("right", "Right column", "column", "", port="right"),
        ]),
        fld("suffix", "Suffix for duplicate right columns", "text", "_right"),
    ]

    def code(self, cfg, ctx):
        left = ctx.var("left")
        right = ctx.var("right")
        keys = [k for k in cfg["keys"] or [] if k.get("left") or k.get("right")]
        if not keys or any(not k.get("left") or not k.get("right") for k in keys):
            raise ToolError("Pick a left and right column for every key")
        lk = [k["left"] for k in keys]
        rk = [k["right"] for k in keys]
        ctx.require_columns(lk, "left")
        ctx.require_columns(rk, "right")
        outs = ", ".join(ctx.out(p) for p in ("left", "join", "right"))
        return f"{outs} = join_lrj({left}, {right}, {lit(lk)}, {lit(rk)}, suffix={lit(cfg['suffix'] or '_right')})"

    def summary(self, cfg):
        keys = [k for k in cfg["keys"] or [] if k.get("left")]
        return short(", ".join(k["left"] if k["left"] == k.get("right") else f"{k['left']}={k.get('right', '')}" for k in keys))


@register
class Union(Tool):
    type = "union"
    label = "Union"
    category = "Join"
    description = "Stack any number of inputs. Connect them in the order you want."
    inputs = [Port("in", "", multi=True)]
    fields = [
        fld("mode", "Match columns by", "select", "name", options=opts(("name", "Name, keep all columns"), ("common", "Name, common columns only"), ("position", "Position"))),
    ]

    def code(self, cfg, ctx):
        names = ctx.vars()
        out = ctx.out()
        if cfg["mode"] == "position":
            first = names[0]
            parts = [first] + [f"{n}.set_axis({first}.columns, axis=1)" for n in names[1:]]
            return f"{out} = pd.concat([{', '.join(parts)}], ignore_index=True)"
        join = ", join='inner'" if cfg["mode"] == "common" else ""
        return f"{out} = pd.concat([{', '.join(names)}], ignore_index=True{join})"

    def summary(self, cfg):
        return {"name": "by name", "common": "common columns", "position": "by position"}[cfg["mode"]]


@register
class AppendFields(Tool):
    type = "append"
    label = "Append Fields"
    category = "Join"
    description = "Cross join: add every source row to every target row."
    inputs = [Port("target", "T"), Port("source", "S")]
    fields = [fld("suffix", "Suffix for duplicate source columns", "text", "_source")]

    def code(self, cfg, ctx):
        return f"{ctx.out()} = {ctx.var('target')}.merge({ctx.var('source')}, how='cross', suffixes=('', {lit(cfg['suffix'] or '_source')}))"


@register
class FindReplace(Tool):
    type = "find_replace"
    label = "Find Replace"
    category = "Join"
    description = "Look values up in a second table. Replace them, or add columns from the lookup table. F = data, R = lookup table."
    inputs = [Port("find", "F"), Port("lookup", "R")]
    fields = [
        fld("column", "Column to look up", "column", "", port="find"),
        fld("key", "Match it to (lookup column)", "column", "", port="lookup"),
        fld("mode", "Then", "select", "replace", options=opts(("replace", "Replace the value"), ("append", "Add columns from the lookup"))),
        fld("value", "Replace with (lookup column)", "column", "", port="lookup", show_if={"mode": ["replace"]}),
        fld("append", "Columns to add", "columns", [], port="lookup", show_if={"mode": ["append"]}),
        fld("case", "Case sensitive", "bool", True),
    ]

    def code(self, cfg, ctx):
        data = ctx.var("find")
        lookup = ctx.var("lookup")
        out = ctx.out()
        col, key = cfg["column"], cfg["key"]
        ctx.require(col, "Pick the column to look up")
        ctx.require(key, "Pick the lookup column to match")
        ctx.require_columns([col], "find")
        ctx.require_columns([key], "lookup")
        fold = "" if cfg["case"] else ".astype('string').str.lower()"
        if cfg["mode"] == "replace":
            value = cfg["value"]
            ctx.require(value, "Pick the replacement column")
            ctx.require_columns([value], "lookup")
            table = ctx.tmp("lookup")
            return "\n".join([
                f"{table} = {lookup}.dropna(subset=[{key!r}]).drop_duplicates({key!r})",
                f"{table} = dict(zip({table}[{key!r}]{fold}, {table}[{value!r}]))",
                f"{out} = {data}.copy()",
                f"{out}[{col!r}] = {out}[{col!r}]{fold}.map({table}).fillna({out}[{col!r}])",
            ])
        cols = [c for c in cfg["append"] or [] if c != key]
        ctx.require(cols, "Pick the columns to add")
        ctx.require_columns(cols, "lookup")
        if cfg["case"]:
            right = f"{lookup}[{lit([key] + cols)}].drop_duplicates({key!r})"
            lines = [f"{out} = {data}.merge({right}, left_on={col!r}, right_on={key!r}, how='left', suffixes=('', '_lookup'))"]
            if key != col:
                lines.append(f"{out} = {out}.drop(columns=[{key!r}])")
            return "\n".join(lines)
        right = f"{lookup}.assign(_key={lookup}[{key!r}]{fold})[['_key'] + {lit(cols)}].drop_duplicates('_key')"
        return f"{out} = {data}.assign(_key={data}[{col!r}]{fold}).merge({right}, on='_key', how='left', suffixes=('', '_lookup')).drop(columns=['_key'])"

    def summary(self, cfg):
        if not cfg["column"]:
            return ""
        return short(f"{cfg['column']} → {cfg['value'] if cfg['mode'] == 'replace' else '+' + str(len(cfg['append'] or []))}")


@register
class JoinMultiple(Tool):
    type = "join_multiple"
    label = "Join Multiple"
    category = "Join"
    description = "Join three or more inputs on columns they share. Connect them in the order you want."
    inputs = [Port("in", "", multi=True)]
    fields = [
        fld("keys", "Join on", "columns", []),
        fld("how", "Keep", "select", "inner", options=opts(("inner", "Rows found in every input"), ("outer", "All rows from every input"), ("left", "Every row of the first input"))),
    ]

    def code(self, cfg, ctx):
        names = ctx.vars()
        keys = cfg["keys"] or []
        ctx.require(keys, "Pick the shared key columns")
        ctx.require_columns(keys)
        if len(names) < 2:
            raise ToolError("Connect at least two inputs")
        expr = names[0]
        for i, n in enumerate(names[1:], start=2):
            expr += f".merge({n}, on={lit(keys)}, how={cfg['how']!r}, suffixes=('', '_{i}'))"
        return f"{ctx.out()} = {expr}"

    def summary(self, cfg):
        return short(", ".join(cfg["keys"] or []))
