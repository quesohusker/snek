import os

from snek.tools.base import Tool, file_stamp, fld, lit, opts, register, short

READ_FORMATS = opts(("auto", "Detect from extension"), ("csv", "CSV"), ("tsv", "Tab-delimited"), ("excel", "Excel"), ("json", "JSON"), ("jsonl", "JSON Lines"), ("parquet", "Parquet"))
WRITE_FORMATS = opts(("auto", "Detect from extension"), ("csv", "CSV"), ("tsv", "Tab-delimited"), ("excel", "Excel"), ("json", "JSON"), ("jsonl", "JSON Lines"), ("parquet", "Parquet"), ("html", "HTML (a chart page, or a table)"))


@register
class InputData(Tool):
    type = "input"
    label = "Open File"
    category = "Open & Save"
    description = "Read CSV, Excel, JSON, JSON Lines or Parquet. Put * in the path to stack many files."
    needs = "No input. Reads a file from disk."
    inputs = []
    fields = [
        fld("path", "File", "file", "", help="Use * to stack files, e.g. …/2025/games_teams_regular_w*.json"),
        fld("format", "Format", "select", "auto", options=READ_FORMATS),
        fld("sheet", "Sheet", "text", "", show_if={"format": ["auto", "excel"]}, help="Excel only. Blank reads the first sheet."),
        fld("delimiter", "Delimiter", "text", "", show_if={"format": ["auto", "csv"]}, help="Blank means comma."),
        fld("encoding", "Encoding", "text", "utf-8"),
        fld("flatten", "Flatten nested JSON objects", "bool", False, show_if={"format": ["auto", "json"]}),
        fld("skip_rows", "Skip rows", "number", 0),
        fld("max_rows", "Max rows (0 = all)", "number", 0),
        fld("filename_col", "File name column", "text", "", help="Adds a column that holds the source file name."),
    ]

    def code(self, cfg, ctx):
        ctx.require(cfg["path"], "Pick a file")
        args = [lit(cfg["path"])]
        if cfg["format"] != "auto":
            args.append(f"fmt={lit(cfg['format'])}")
        if cfg["sheet"]:
            args.append(f"sheet={lit(cfg['sheet'])}")
        if cfg["delimiter"]:
            args.append(f"sep={lit(cfg['delimiter'])}")
        if cfg["encoding"] and cfg["encoding"] != "utf-8":
            args.append(f"encoding={lit(cfg['encoding'])}")
        if cfg["flatten"]:
            args.append("flatten=True")
        if cfg["skip_rows"]:
            args.append(f"skiprows={int(cfg['skip_rows'])}")
        if cfg["max_rows"]:
            args.append(f"nrows={int(cfg['max_rows'])}")
        if cfg["filename_col"]:
            args.append(f"filename_col={lit(cfg['filename_col'])}")
        return f"{ctx.out()} = read_any({', '.join(args)})"

    def stamp(self, cfg, inputs=None):
        return file_stamp(cfg["path"]) if cfg["path"] else ""

    def summary(self, cfg):
        return short(os.path.basename(cfg["path"] or ""))


@register
class TextInput(Tool):
    type = "text_input"
    label = "Type or Paste Data"
    category = "Open & Save"
    description = "Type or paste a small table as CSV."
    needs = "No input. Type or paste the data."
    inputs = []
    fields = [
        fld("data", "Data (CSV, first row = headers)", "textarea", "name,value\na,1\nb,2"),
        fld("delimiter", "Delimiter", "text", ","),
    ]

    def code(self, cfg, ctx):
        ctx.require(cfg["data"], "Enter some data")
        sep = cfg["delimiter"] or ","
        return f"{ctx.out()} = pd.read_csv(io.StringIO({lit(cfg['data'])}), sep={lit(sep)})"

    def summary(self, cfg):
        rows = max(len((cfg["data"] or "").strip().splitlines()) - 1, 0)
        return f"{rows} rows"


@register
class OutputData(Tool):
    type = "output"
    label = "Save File"
    category = "Open & Save"
    description = "Write CSV, Excel, JSON or Parquet when the workflow runs."
    needs = "Any table to save."
    outputs = []
    side_effect = True
    fields = [
        fld("path", "File", "file", "", save=True, help="Writes when you click Run. A name with no folder saves inside the project folder. A name with no extension gets one from Format."),
        fld("format", "Format", "select", "auto", options=WRITE_FORMATS),
    ]

    def code(self, cfg, ctx):
        ctx.require(cfg["path"], "Pick an output file")
        fmt = f", fmt={lit(cfg['format'])}" if cfg["format"] != "auto" else ""
        return f"write_any({ctx.var()}, {lit(cfg['path'])}{fmt})"

    def summary(self, cfg):
        return short(os.path.basename(cfg["path"] or ""))


@register
class Browse(Tool):
    type = "browse"
    label = "Preview"
    hidden = True
    category = "Open & Save"
    description = "Show the data at this point. Every step already shows its output, so this is only kept for older workflows."
    needs = "Any table."
    outputs = []
    fields = []

    def code(self, cfg, ctx):
        ctx.var()
        return ""


@register
class Directory(Tool):
    type = "directory"
    label = "List Files"
    category = "Open & Save"
    description = "List the files in a folder: path, name, extension, size and date. Feed it to Read Listed Files to read them all."
    needs = "No input. Reads a folder on disk."
    inputs = []
    fields = [
        fld("folder", "Folder", "file", "", help="A folder path, e.g. data or ~/Downloads"),
        fld("pattern", "File pattern", "text", "*", help="e.g. *.csv or games_*.json"),
        fld("recursive", "Include subfolders", "bool", False),
    ]

    def code(self, cfg, ctx):
        ctx.require(cfg["folder"], "Pick a folder")
        args = [lit(cfg["folder"]), lit(cfg["pattern"] or "*")]
        if cfg["recursive"]:
            args.append("recursive=True")
        return f"{ctx.out()} = list_files({', '.join(args)})"

    def stamp(self, cfg, inputs=None):
        from snek.runtime import list_files

        if not cfg["folder"]:
            return ""
        listing = list_files(cfg["folder"], cfg["pattern"] or "*", bool(cfg["recursive"]))
        return "|".join(f"{p}:{s}:{m}" for p, s, m in zip(listing["path"], listing["size_bytes"], listing["modified"]))

    def summary(self, cfg):
        return short(f"{os.path.basename(str(cfg['folder']).rstrip('/')) or cfg['folder']}/{cfg['pattern']}") if cfg["folder"] else ""


@register
class DynamicInput(Tool):
    type = "dynamic_input"
    label = "Read Listed Files"
    category = "Open & Save"
    description = "Read every file listed in a column, such as the path column from List Files, and stack them."
    needs = "A table with a column of file paths, such as the output of List Files."
    fields = [
        fld("column", "Column with file paths", "column", ""),
        fld("format", "Format", "select", "auto", options=READ_FORMATS),
        fld("filename_col", "File name column", "text", "FileName", help="Blank skips it."),
    ]

    def code(self, cfg, ctx):
        col = cfg["column"]
        ctx.require(col, "Pick the column that holds file paths")
        ctx.require_columns([col])
        args = [f"{ctx.var()}[{col!r}].dropna().astype(str).tolist()"]
        if cfg["filename_col"]:
            args.append(f"filename_col={lit(cfg['filename_col'])}")
        if cfg["format"] != "auto":
            args.append(f"fmt={lit(cfg['format'])}")
        return f"{ctx.out()} = read_many({', '.join(args)})"

    def stamp(self, cfg, inputs=None):
        frames = (inputs or {}).get("in") or []
        if not frames or cfg["column"] not in frames[0].columns:
            return ""
        return "|".join(file_stamp(str(p)) for p in frames[0][cfg["column"]].dropna())

    def summary(self, cfg):
        return cfg["column"] or ""


@register
class DateTimeNow(Tool):
    type = "now"
    label = "Current Time"
    category = "Open & Save"
    description = "One row with the current date and time, refreshed on every run."
    needs = "No input."
    inputs = []
    volatile = True
    fields = [
        fld("name", "Column name", "text", "DateTimeNow"),
        fld("what", "Value", "select", "datetime", options=opts(("datetime", "Date and time"), ("date", "Date only"))),
    ]

    def code(self, cfg, ctx):
        value = "pd.Timestamp.now().floor('s')" if cfg["what"] == "datetime" else "pd.Timestamp.now().normalize()"
        return f"{ctx.out()} = pd.DataFrame({{{(cfg['name'] or 'DateTimeNow')!r}: [{value}]}})"
