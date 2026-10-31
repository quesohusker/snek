import html
import json

import pandas as pd


def make_chart(df, kind, x, y=None, color=None, agg="none", title="", bins=20, facet=None, max_rows=5000):
    def vl_type(col):
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            return "temporal"
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            return "quantitative"
        return "nominal"

    def enc(col, **extra):
        return {"field": col, "type": vl_type(col), "title": col, **extra}

    count = {"aggregate": "count", "title": "Count"}
    cols = list(dict.fromkeys(c for c in (x, y, color, facet) if c))
    data = df[cols].head(int(max_rows))
    encoding = {}
    if kind == "histogram":
        mark = {"type": "bar"}
        encoding["x"] = enc(x, bin={"maxbins": int(bins)})
        encoding["y"] = count
    elif kind == "box":
        mark = {"type": "boxplot", "extent": 1.5}
        encoding["y"] = enc(y or x)
        if y:
            encoding["x"] = enc(x, type="nominal")
    elif kind == "heatmap":
        mark = {"type": "rect"}
        encoding["x"] = enc(x, type="ordinal")
        encoding["y"] = enc(y, type="ordinal")
        encoding["color"] = enc(color, aggregate="mean" if agg == "none" else agg) if color else count
    else:
        mark = {"bar": {"type": "bar"}, "line": {"type": "line", "point": True}, "scatter": {"type": "point", "filled": True}, "area": {"type": "area", "opacity": 0.8}}[kind]
        encoding["x"] = enc(x)
        if kind == "bar" and vl_type(x) == "quantitative":
            encoding["x"]["type"] = "ordinal"
        elif pd.api.types.is_integer_dtype(df[x]) and df[x].dropna().between(1000, 9999).all():
            encoding["x"]["axis"] = {"format": "d"}
        encoding["y"] = enc(y, **({"aggregate": agg} if agg != "none" else {})) if y else count
        if kind == "bar" and encoding["x"]["type"] == "nominal":
            encoding["x"]["sort"] = "-y"
    if color and kind != "heatmap":
        encoding["color"] = enc(color)
    mark["tooltip"] = True
    default_title = (y or x) if kind in ("histogram", "box") else f"{y or 'Count'} by {x}"
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
        "title": title or default_title,
        "data": {"values": json.loads(data.to_json(orient="records", date_format="iso"))},
        "mark": mark,
        "encoding": encoding,
        "height": 280,
    }
    if facet:
        spec["encoding"]["facet"] = enc(facet, type="nominal", columns=3)
        spec["width"] = 220
        spec["height"] = 180
    else:
        spec["width"] = "container"
    return pd.DataFrame([{"Kind": kind, "Title": spec["title"], "Rows plotted": len(data), "Rows in data": len(df), "Vega-Lite": json.dumps(spec)}])


def chart_html(df):
    libraries = (
        ("vega@6.4.0/build/vega.min.js", "sha384-VKdcJr3ZaBIJMbVcopTAI/JEuUkSY6qnwVu9iLuw0DnQ9gQ1JjsfZJhXFQAgNi43"),
        ("vega-lite@6.5.0/build/vega-lite.min.js", "sha384-pV2l7nzmyxZh02knvUH7N8zvtyCYsYiGt+SsE/emG/dFiBI6G0YJZFZ2FzEX72P3"),
        ("vega-embed@7.3.0/build/vega-embed.min.js", "sha384-Muy1QRxYFeNrA1zShc1KtN4OfipkR/61gt+HWqN57c1Zxu3Oe16TsilsruVVjfKL"),
    )
    options = '{"actions": {"export": true, "source": false, "compiled": false, "editor": false}}'
    specs = [json.loads(s) for s in df["Vega-Lite"]]
    title = html.escape(str(specs[0].get("title", "Chart")) if specs else "Chart")
    scripts = "".join(f'<script src="https://cdn.jsdelivr.net/npm/{name}" integrity="{sri}" crossorigin="anonymous"></script>' for name, sri in libraries)
    blocks = "".join(f'<div id="chart{i}" style="width:100%;margin-bottom:32px"></div>' for i in range(len(specs)))
    calls = "".join(f"vegaEmbed('#chart{i}', {json.dumps(s).replace('</', '<' + chr(92) + '/')}, {options});" for i, s in enumerate(specs))
    return f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>{scripts}<style>body{{font-family:system-ui,sans-serif;margin:24px}}</style></head><body>{blocks}<script>{calls}</script></body></html>'
