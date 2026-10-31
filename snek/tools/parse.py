import re

from snek.tools.base import Tool, ToolError, fld, opts, register, short


@register
class TextToColumns(Tool):
    type = "split"
    label = "Split Text"
    category = "Clean"
    description = "Split a text column on a delimiter into new columns or new rows."
    needs = "A table with a text column to split on a delimiter."
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
    label = "One Row per Item"
    category = "Clean"
    description = "Turn a column of lists into one row per item. Use it on nested JSON arrays."
    needs = "A table with a column of lists, such as a nested JSON array."
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
    label = "Spread Out Fields"
    category = "Clean"
    description = "Spread a column of JSON objects (dicts) into one column per key."
    needs = "A table with a column of JSON objects (dicts)."
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


DATE_FORMATS = opts(
    ("", "Detect automatically"),
    ("%Y-%m-%d", "2025-09-06"),
    ("%m/%d/%Y", "09/06/2025"),
    ("%d/%m/%Y", "06/09/2025"),
    ("%Y-%m-%d %H:%M:%S", "2025-09-06 19:30:00"),
    ("%Y-%m-%dT%H:%M:%S", "2025-09-06T19:30:00"),
    ("%b %d, %Y", "Sep 06, 2025"),
    ("%B %d, %Y", "September 06, 2025"),
    ("%Y%m%d", "20250906"),
    ("custom", "Custom…"),
)
DATE_PARTS = opts(("year", "Year"), ("quarter", "Quarter"), ("month", "Month number"), ("month_name", "Month name"), ("week", "ISO week"), ("day", "Day of month"), ("weekday", "Day of week (Monday = 0)"), ("day_name", "Day name"), ("hour", "Hour"), ("date", "Date only"))


@register
class DateTime(Tool):
    type = "datetime"
    label = "Dates and Times"
    category = "Clean"
    description = "Turn text into dates, dates into text, or pull out parts like year, week or day name."
    needs = "A table with a date or date-like text column."
    fields = [
        fld("mode", "Do", "select", "parse", options=opts(("parse", "Text to date"), ("format", "Date to text"), ("extract", "Pull out a part"))),
        fld("column", "Column", "column", ""),
        fld("format", "Format", "select", "", options=DATE_FORMATS, show_if={"mode": ["parse", "format"]}),
        fld("custom", "Custom format", "text", "", show_if={"format": ["custom"]}, help="Python strftime codes, e.g. %d-%b-%Y"),
        fld("part", "Part", "select", "year", options=DATE_PARTS, show_if={"mode": ["extract"]}),
        fld("utc", "Convert time zones to UTC", "bool", False, show_if={"mode": ["parse"]}),
        fld("name", "Output column", "text", "", placeholder="blank = replace the column (new column for parts)"),
    ]

    def code(self, cfg, ctx):
        col = cfg["column"]
        ctx.require(col, "Pick a column")
        ctx.require_columns([col])
        out = ctx.out()
        mode = cfg["mode"]
        fmt = cfg["custom"] if cfg["format"] == "custom" else cfg["format"]
        if cfg["format"] == "custom":
            ctx.require(fmt, "Enter a custom format")
        src = f"{out}[{col!r}]"
        dtype = ctx.dtype(col) or ""
        as_date = src if dtype.startswith("datetime") else f"pd.to_datetime({src}, errors='coerce', format='mixed')"
        if mode == "parse":
            args = [f"format={fmt!r}" if fmt else "format='mixed'"]
            if cfg["utc"]:
                args.append("utc=True")
            expr = f"pd.to_datetime({src}, errors='coerce', {', '.join(args)})"
            name = cfg["name"] or col
        elif mode == "format":
            ctx.require(fmt, "Pick the text format to write")
            expr = f"{as_date}.dt.strftime({fmt!r})"
            name = cfg["name"] or col
        else:
            part = cfg["part"]
            accessor = {
                "month_name": ".dt.month_name()",
                "day_name": ".dt.day_name()",
                "week": ".dt.isocalendar().week.astype('Int64')",
                "date": ".dt.date",
                "weekday": ".dt.weekday",
            }.get(part, f".dt.{part}")
            expr = f"{as_date}{accessor}"
            name = cfg["name"] or f"{col}_{part}"
        return f"{out} = {ctx.var()}.copy()\n{out}[{name!r}] = {expr}"

    def summary(self, cfg):
        if not cfg["column"]:
            return ""
        return short({"parse": f"{cfg['column']} → date", "format": f"{cfg['column']} → text", "extract": f"{cfg['part']} of {cfg['column']}"}[cfg["mode"]])


@register
class RegEx(Tool):
    type = "regex"
    label = "Text Pattern"
    category = "Clean"
    description = "Use a regular expression to test, pull apart, replace, or split text."
    needs = "A table with a text column."
    fields = [
        fld("column", "Column", "column", ""),
        fld("pattern", "Regular expression", "code", "", placeholder=r"(\d+)-(\d+)", help="Python regex. Name groups with (?P<name>...) to name the new columns."),
        fld("mode", "Do", "select", "parse", options=opts(("parse", "Parse groups into columns"), ("match", "Mark rows that match"), ("replace", "Replace matches"), ("tokenize", "Split every match out"))),
        fld("full", "Whole value must match", "bool", True, show_if={"mode": ["match"]}),
        fld("replacement", "Replace with", "text", "", show_if={"mode": ["replace"]}, help=r"Use \1, \2 to insert groups."),
        fld("into", "Split into", "select", "columns", show_if={"mode": ["tokenize"]}, options=opts(("columns", "Columns"), ("rows", "Rows"))),
        fld("case", "Case sensitive", "bool", True),
        fld("name", "Output column or prefix", "text", "", placeholder="blank = based on the column name"),
    ]

    def code(self, cfg, ctx):
        col = cfg["column"]
        pattern = cfg["pattern"] or ""
        ctx.require(col, "Pick a column")
        ctx.require(pattern, "Enter a regular expression")
        ctx.require_columns([col])
        try:
            compiled = re.compile(pattern)
        except re.error as e:
            raise ToolError(f"Bad regular expression: {e}") from None
        pat = pattern if cfg["case"] else f"(?i){pattern}"
        inp = ctx.var()
        out = ctx.out()
        text = f"{inp}[{col!r}].astype('string')"
        mode = cfg["mode"]
        if mode == "match":
            fn = "fullmatch" if cfg["full"] else "contains"
            name = cfg["name"] or f"{col}_match"
            return f"{out} = {inp}.copy()\n{out}[{name!r}] = {text}.str.{fn}({pat!r}).fillna(False).astype(bool)"
        if mode == "replace":
            name = cfg["name"] or col
            return f"{out} = {inp}.copy()\n{out}[{name!r}] = {text}.str.replace({pat!r}, {(cfg['replacement'] or '')!r}, regex=True)"
        parts = ctx.tmp("parts")
        prefix = cfg["name"] or col
        if mode == "parse":
            if compiled.groups == 0:
                raise ToolError("Add a capture group ( ) to say what to pull out")
            lines = [f"{parts} = {text}.str.extract({pat!r})"]
            if not compiled.groupindex:
                lines.append(f"{parts}.columns = [f'{prefix}_{{i + 1}}' for i in range({parts}.shape[1])]")
            lines.append(f"{out} = pd.concat([{inp}, {parts}], axis=1)")
            return "\n".join(lines)
        tokens = ctx.tmp("tokens")
        if cfg["into"] == "rows":
            return f"{tokens} = {text}.str.findall({pat!r})\n{out} = {inp}.assign(**{{{prefix!r}: {tokens}}}).explode({prefix!r}, ignore_index=True)"
        return "\n".join([
            f"{tokens} = {text}.str.findall({pat!r}).map(lambda v: v if isinstance(v, list) else [])",
            f"{parts} = pd.DataFrame({tokens}.tolist(), index={inp}.index)",
            f"{parts}.columns = [f'{prefix}_{{i + 1}}' for i in range({parts}.shape[1])]",
            f"{out} = pd.concat([{inp}, {parts}], axis=1)",
        ])

    def summary(self, cfg):
        return short(f"{cfg['mode']}: {cfg['pattern']}") if cfg["pattern"] else ""


@register
class JSONParse(Tool):
    type = "json_parse"
    label = "Read JSON Text"
    category = "Clean"
    description = "Turn a column of JSON text into objects you can Unnest or Explode, or spread it into columns right away."
    needs = "A table with a column of JSON text."
    fields = [
        fld("column", "JSON text column", "column", ""),
        fld("flatten", "Spread objects into columns", "bool", True),
        fld("prefix", "Prefix new columns with the column name", "bool", True, show_if={"flatten": ["true"]}),
        fld("strict", "Stop on invalid JSON", "bool", False, help="Off: invalid values become null."),
    ]

    def code(self, cfg, ctx):
        col = cfg["column"]
        ctx.require(col, "Pick a column")
        ctx.require_columns([col])
        out = ctx.out()
        strict = ", strict=True" if cfg["strict"] else ""
        lines = [f"{out} = {ctx.var()}.copy()", f"{out}[{col!r}] = {out}[{col!r}].map(lambda v: parse_json(v{strict}))"]
        if cfg["flatten"]:
            prefix = "" if cfg["prefix"] else ", prefix=False"
            lines.append(f"{out} = unnest({out}, {col!r}{prefix})")
        return "\n".join(lines)

    def summary(self, cfg):
        return cfg["column"] or ""
