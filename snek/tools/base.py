import os
from dataclasses import asdict, dataclass

TOOLS = {}

NUMERIC_PREFIXES = ("int", "uint", "float", "Int", "UInt", "Float")

DTYPE_OPTIONS = [
    ("", "(unchanged)"),
    ("string", "Text"),
    ("Int64", "Integer (rounded)"),
    ("float64", "Decimal"),
    ("boolean", "True/False"),
    ("datetime", "Date/time"),
    ("category", "Category"),
]


class ToolError(Exception):
    pass


@dataclass
class Port:
    name: str
    label: str = ""
    multi: bool = False


def fld(key, label, kind, default=None, **extra):
    return {"key": key, "label": label, "kind": kind, "default": default, **extra}


def opts(*items):
    return [{"value": v, "label": l} for v, l in (i if isinstance(i, tuple) else (i, i) for i in items)]


def lit(value):
    return repr(value)


def is_numeric(dtype):
    return bool(dtype) and dtype.startswith(NUMERIC_PREFIXES)


def is_text(dtype):
    return dtype in ("str", "string") or (dtype or "").startswith("string")


def convert_line(frame, column, dtype):
    ref = f"{frame}[{column!r}]"
    if dtype == "Int64":
        return f"{ref} = pd.to_numeric({ref}, errors='coerce').round().astype('Int64')"
    if dtype == "float64":
        return f"{ref} = pd.to_numeric({ref}, errors='coerce')"
    if dtype == "datetime":
        return f"{ref} = pd.to_datetime({ref}, errors='coerce')"
    if dtype == "string":
        return f"{ref} = {ref}.astype('string')"
    if dtype == "boolean":
        return f"{ref} = {ref}.astype('boolean')"
    if dtype == "category":
        return f"{ref} = {ref}.astype('category')"
    raise ToolError(f"Unknown type {dtype!r}")


class Ctx:
    def __init__(self, node_id, tool, ins, schema):
        self.node_id = node_id
        self.tool = tool
        self.ins = ins
        self.schema = schema

    def var(self, port="in"):
        names = self.ins.get(port) or []
        if not names:
            raise ToolError(f"Connect the {port} input")
        return names[0]

    def vars(self, port="in"):
        names = self.ins.get(port) or []
        if not names:
            raise ToolError(f"Connect the {port} input")
        return names

    def out(self, port="out"):
        return output_var(self.tool.type, self.node_id, port, self.tool.outputs)

    def tmp(self, name):
        return f"{name}_{self.node_id}"

    def columns(self, port="in"):
        return [c["name"] for c in self.schema.get(port, [])]

    def dtype(self, column, port="in"):
        for c in self.schema.get(port, []):
            if c["name"] == column:
                return c["dtype"]
        return None

    def require(self, value, message):
        if value in (None, "", []):
            raise ToolError(message)

    def require_columns(self, columns, port="in"):
        present = set(self.columns(port))
        missing = [c for c in columns if c not in present]
        if missing:
            raise ToolError(f"Missing column{'s' if len(missing) > 1 else ''} in {port} input: {', '.join(missing)}")


def output_var(tool_type, node_id, port, outputs):
    if len(outputs) == 1:
        return f"{tool_type}_{node_id}"
    return f"{tool_type}_{node_id}_{port}"


class Tool:
    type = ""
    label = ""
    category = ""
    group = ""
    description = ""
    needs = ""
    icon = ""
    color = ""
    connection = ""
    hidden = False
    inputs = [Port("in")]
    outputs = [Port("out")]
    fields = []
    side_effect = False
    volatile = False
    needs_trust = False

    def code(self, cfg, ctx):
        raise NotImplementedError

    def summary(self, cfg):
        return ""

    def stamp(self, cfg, inputs=None):
        return ""

    def config(self, raw):
        cfg = {f["key"]: f.get("default") for f in self.fields}
        cfg.update({k: v for k, v in (raw or {}).items() if k in cfg})
        return cfg

    def spec(self):
        return {
            "type": self.type,
            "label": self.label,
            "category": self.category,
            "group": self.group,
            "description": self.description,
            "needs": self.needs,
            "icon": self.icon,
            "color": self.color,
            "connection": self.connection,
            "hidden": self.hidden,
            "inputs": [asdict(p) for p in self.inputs],
            "outputs": [asdict(p) for p in self.outputs],
            "fields": self.fields,
        }


def register(cls):
    tool = cls()
    TOOLS[tool.type] = tool
    return cls


def file_stamp(path):
    from snek.runtime import match_files

    parts = []
    for f in match_files(path):
        f = os.path.abspath(f)
        try:
            st = os.stat(f)
            parts.append(f"{f}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append(f"{f}:missing")
    return "|".join(parts)


def short(text, limit=40):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
