from snek.tools import connect, fields, grouping, investigate, io, join, model, parse, prep, rows, sports, timeseries, transform
from snek.tools.base import TOOLS, Ctx, Tool, ToolError, output_var

CATEGORY_ORDER = ["Open & Save", "Rows", "Columns", "Clean", "SQL", "Group & Pivot", "Explore", "Model", "Segment", "Forecast", "Sports", "Code"]

__all__ = ["TOOLS", "CATEGORY_ORDER", "Ctx", "Tool", "ToolError", "output_var", "fields", "grouping", "investigate", "io", "join", "model", "parse", "prep", "rows", "sports", "timeseries", "transform"]


def add_category(name, after=None):
    if name in CATEGORY_ORDER:
        return
    CATEGORY_ORDER.insert(CATEGORY_ORDER.index(after) + 1 if after in CATEGORY_ORDER else len(CATEGORY_ORDER) - 1, name)


from snek.plugins import load_plugins  # noqa: E402

load_plugins()
