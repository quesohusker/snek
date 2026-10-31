import urllib.parse

from snek.tools.base import Tool, ToolError, fld, opts, register, short

CATEGORY = "Data Connections"


@register
class APIRequest(Tool):
    type = "api_request"
    label = "API Request"
    category = CATEGORY
    description = "Download JSON or CSV from any web API with a GET request. Nested JSON fields become columns; lists stay as lists for Explode List."
    needs = "No input. The API's URL. If it needs a key, save the key in Edit ▸ Settings ▸ Data Connections and give its name here."
    inputs = []
    fields = [
        fld("url", "URL", "text", "", help="For example https://api.example.com/v1/items. Add query parameters below or in the URL."),
        fld("params", "Query parameters", "list", [], fields=[fld("name", "Name", "text", ""), fld("value", "Value", "text", "")]),
        fld("auth", "API key", "select", "none", options=opts(("none", "None"), ("bearer", "Bearer token header"), ("header", "Custom header"), ("query", "Query parameter"))),
        fld("key", "Saved key name", "text", "", show_if={"auth": ["bearer", "header", "query"]}, help="The name you gave the key in Edit ▸ Settings ▸ Data Connections. The key itself never goes into the workflow or the exported script."),
        fld("header", "Header or parameter name", "text", "X-API-Key", show_if={"auth": ["header", "query"]}),
        fld("fmt", "Response format", "select", "json", options=opts(("json", "JSON"), ("csv", "CSV"))),
        fld("records", "Records path (optional)", "text", "", show_if={"fmt": ["json"]}, help="Where the list of records sits in the JSON, such as data or results.items. Blank uses the whole response."),
    ]

    def code(self, cfg, ctx):
        url = str(cfg["url"] or "").strip()
        if not url.startswith(("http://", "https://")):
            raise ToolError("Enter a URL that starts with https://")
        params = {str(p.get("name", "")).strip(): str(p.get("value", "")) for p in cfg["params"] or [] if str(p.get("name", "")).strip()}
        args = [repr(url), repr(params)]
        if cfg["auth"] != "none":
            if not str(cfg["key"] or "").strip():
                raise ToolError("Enter the name of the saved API key")
            args += [f"auth={cfg['auth']!r}", f"key={str(cfg['key']).strip()!r}"]
            if cfg["auth"] in ("header", "query"):
                args.append(f"header={str(cfg['header'] or 'X-API-Key').strip()!r}")
        if cfg["fmt"] == "csv":
            args.append("fmt='csv'")
        elif str(cfg["records"] or "").strip():
            args.append(f"records={str(cfg['records']).strip()!r}")
        return f"{ctx.out()} = api_request({', '.join(args)})"

    def summary(self, cfg):
        return short(urllib.parse.urlparse(str(cfg["url"] or "")).netloc or "")
