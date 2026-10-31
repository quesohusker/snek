from snek.tools.base import Tool, fld, opts, register, short


@register
class TextToColumns(Tool):
    type = "split"
    label = "Text to Columns"
    category = "Parse"
    description = "Split a text column on a delimiter into new columns or new rows."
    fields = [
        fld("column", "Column", "column", ""),
        fld("delimiter", "Delimiter", "text", ","),
        fld("mode", "Split into", "select", "columns", options=opts(("columns", "Columns"), ("rows", "Rows"))),
        fld("parts", "Max columns (0 = as many as needed)", "number", 0, show_if={"mode": ["columns"]}),
        fld("trim", "Trim spaces from each part", "bool", True),
        fld("drop", "Drop the original column", "bool", False, show_if={"mode": ["columns"]}),
    ]

    def code(self, cfg, ctx):
        inp = ctx.var()
        out = ctx.out()
        col = cfg["column"]
        ctx.require(col, "Pick a column")
        ctx.require(cfg["delimiter"], "Enter a delimiter")
        ctx.require_columns([col])
        delim = cfg["delimiter"]
        if cfg["mode"] == "rows":
            lines = [f"{out} = {inp}.assign(**{{{col!r}: {inp}[{col!r}].astype('string').str.split({delim!r}, regex=False)}}).explode({col!r}, ignore_index=True)"]
            if cfg["trim"]:
                lines.append(f"{out}[{col!r}] = {out}[{col!r}].str.strip()")
            return "\n".join(lines)
        parts = ctx.tmp("parts")
        n = int(cfg["parts"] or 0)
        lines = [
            f"{parts} = {inp}[{col!r}].astype('string').str.split({delim!r}, n={n - 1 if n > 0 else -1}, expand=True, regex=False)",
            f"{parts}.columns = [f'{col}_{{i + 1}}' for i in range({parts}.shape[1])]",
        ]
        if cfg["trim"]:
            lines.append(f"{parts} = {parts}.apply(lambda s: s.str.strip())")
        base = f"{inp}.drop(columns=[{col!r}])" if cfg["drop"] else inp
        lines.append(f"{out} = pd.concat([{base}, {parts}], axis=1)")
        return "\n".join(lines)

    def summary(self, cfg):
        return short(f"{cfg['column']} on '{cfg['delimiter']}' → {cfg['mode']}") if cfg["column"] else ""


@register
class Explode(Tool):
    type = "explode"
    label = "Explode List"
    category = "Parse"
    description = "Turn a column of lists into one row per item. Use it on nested JSON arrays."
    fields = [fld("column", "List column", "column", "")]

    def code(self, cfg, ctx):
        col = cfg["column"]
        ctx.require(col, "Pick a column")
        ctx.require_columns([col])
        return f"{ctx.out()} = {ctx.var()}.explode({col!r}, ignore_index=True)"

    def summary(self, cfg):
        return cfg["column"] or ""


@register
class Unnest(Tool):
    type = "unnest"
    label = "Unnest JSON"
    category = "Parse"
    description = "Spread a column of JSON objects (dicts) into one column per key."
    fields = [
        fld("column", "Object column", "column", ""),
        fld("prefix", "Prefix new columns with the column name", "bool", True),
    ]

    def code(self, cfg, ctx):
        col = cfg["column"]
        ctx.require(col, "Pick a column")
        ctx.require_columns([col])
        prefix = "" if cfg["prefix"] else ", prefix=False"
        return f"{ctx.out()} = unnest({ctx.var()}, {col!r}{prefix})"

    def summary(self, cfg):
        return cfg["column"] or ""
