import urllib.parse

from snek import connect
from snek.tools.base import Tool, ToolError, fld, opts, register, short


@register
class APIRequest(Tool):
    type = "api_request"
    label = "Web API"
    category = "Open & Save"
    description = "Download JSON or CSV from any web API with a GET request. Nested JSON fields become columns; lists stay as lists for One Row per Item."
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
            key = str(cfg["key"] or "").strip()
            if not key:
                raise ToolError("Enter the name of the saved API key")
            try:
                connect.check_host(key, url)
            except ValueError as e:
                raise ToolError(str(e)) from None
            args += [f"auth={cfg['auth']!r}", f"key={key!r}"]
            if cfg["auth"] in ("header", "query"):
                args.append(f"header={str(cfg['header'] or 'X-API-Key').strip()!r}")
        if cfg["fmt"] == "csv":
            args.append("fmt='csv'")
        elif str(cfg["records"] or "").strip():
            args.append(f"records={str(cfg['records']).strip()!r}")
        return f"{ctx.out()} = api_request({', '.join(args)})"

    def summary(self, cfg):
        return short(urllib.parse.urlparse(str(cfg["url"] or "")).netloc or "")


@register
class GitHub(Tool):
    type = "github"
    label = "GitHub"
    category = "Open & Save"
    connection = "github"
    description = "Read a user's or organization's repositories, a repository's issues, pull requests, commits, releases or folder listing, or a CSV, Excel, JSON or Parquet file stored in a repository."
    needs = "No input. An owner such as quesohusker, and a repository for everything except the repository list. Public data works without a token. Private repositories need a GitHub token saved in Edit ▸ Settings."
    inputs = []
    LISTS = ["issues", "pulls", "commits", "releases", "files", "file"]
    fields = [
        fld("what", "What to get", "select", "repos", options=opts(("repos", "Repositories"), ("issues", "Issues and pull requests"), ("pulls", "Pull requests"), ("commits", "Commits"), ("releases", "Releases"), ("files", "Files in a folder"), ("file", "A data file"))),
        fld("owner", "Owner", "text", "", help="A user or organization name, such as quesohusker. For Repositories, leave it blank to list your own repositories (needs a saved token)."),
        fld("repo", "Repository", "text", "", show_if={"what": LISTS}, help="Just the name, such as snek."),
        fld("path", "Path in the repository", "text", "", show_if={"what": ["files", "file"]}, help="A folder for Files in a folder (blank is the top). A file such as data/games.csv for A data file."),
        fld("ref", "Branch, tag or commit", "text", "", show_if={"what": ["commits", "files", "file"]}, help="Blank uses the repository's default branch."),
        fld("state", "State", "select", "all", show_if={"what": ["issues", "pulls"]}, options=opts(("all", "All"), ("open", "Open"), ("closed", "Closed"))),
        fld("limit", "Most rows to fetch", "number", 500, show_if={"what": ["repos", "issues", "pulls", "commits", "releases"]}, help="GitHub sends 100 rows per request. Snek stops at this many and says so."),
        fld("fmt", "File format", "select", "auto", show_if={"what": ["file"]}, options=opts(("auto", "Auto-detect"), ("csv", "CSV"), ("tsv", "TSV"), ("excel", "Excel"), ("json", "JSON"), ("jsonl", "JSON Lines"), ("parquet", "Parquet"))),
    ]

    def code(self, cfg, ctx):
        what = cfg["what"]
        owner = str(cfg["owner"] or "").strip()
        repo = str(cfg["repo"] or "").strip()
        path = str(cfg["path"] or "").strip()
        if what != "repos" or owner:
            ctx.require(owner, "Enter the owner, such as quesohusker")
        if what in self.LISTS:
            ctx.require(repo, "Enter the repository name")
        if what == "file":
            ctx.require(path, "Enter the path of the file in the repository")
        args = [repr(what), repr(owner)]
        extra = []
        if what in self.LISTS:
            extra.append(f"repo={repo!r}")
        if what in ("files", "file") and path:
            extra.append(f"path={path!r}")
        if what in ("commits", "files", "file") and str(cfg["ref"] or "").strip():
            extra.append(f"ref={str(cfg['ref']).strip()!r}")
        if what in ("issues", "pulls") and cfg["state"] != "all":
            extra.append(f"state={cfg['state']!r}")
        if what in ("repos", "issues", "pulls", "commits", "releases"):
            limit = int(cfg["limit"] or 500)
            if limit < 1:
                raise ToolError("Most rows to fetch must be 1 or more")
            if limit != 500:
                extra.append(f"limit={limit}")
        if what == "file" and cfg["fmt"] != "auto":
            extra.append(f"fmt={cfg['fmt']!r}")
        return f"{ctx.out()} = github({', '.join(args + extra)})"

    def summary(self, cfg):
        owner, repo = str(cfg["owner"] or "").strip(), str(cfg["repo"] or "").strip()
        where = f"{owner}/{repo}" if repo else owner
        return short(f"{cfg['what']} · {where}" if where else str(cfg["what"]))
