import os

from snek.tools.base import Port, Tool, file_stamp, fld, lit, opts, register, short

READ_FORMATS = opts(("auto", "Detect from extension"), ("csv", "CSV"), ("tsv", "Tab-delimited"), ("excel", "Excel"), ("json", "JSON"), ("jsonl", "JSON Lines"), ("parquet", "Parquet"))
WRITE_FORMATS = opts(("auto", "Detect from extension"), ("csv", "CSV"), ("tsv", "Tab-delimited"), ("excel", "Excel"), ("json", "JSON"), ("jsonl", "JSON Lines"), ("parquet", "Parquet"))


@register
class InputData(Tool):
    type = "input"
    label = "Input Data"
    category = "In/Out"
    description = "Read CSV, Excel, JSON, JSON Lines or Parquet. Put * in the path to stack many files."
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

    def stamp(self, cfg):
        return file_stamp(cfg["path"]) if cfg["path"] else ""

    def summary(self, cfg):
        return short(os.path.basename(cfg["path"] or ""))


@register
class TextInput(Tool):
    type = "text_input"
    label = "Text Input"
    category = "In/Out"
    description = "Type or paste a small table as CSV."
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
    label = "Output Data"
    category = "In/Out"
    description = "Write CSV, Excel, JSON or Parquet when the workflow runs."
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
    label = "Browse"
    category = "In/Out"
    description = "Show the data at this point. Click any tool to see its output too."
    outputs = []
    fields = []

    def code(self, cfg, ctx):
        ctx.var()
        return ""
