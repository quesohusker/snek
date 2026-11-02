import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings

import pandas as pd

from snek.paths import snek_home

NAME_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
DECLARED = {}
HOSTS = {"anthropic": "api.anthropic.com", "github": "api.github.com"}
DECLARED["github"] = {
    "label": "GitHub token",
    "section": "GitHub",
    "url": "https://github.com/settings/personal-access-tokens",
    "help": "Optional. Public repositories work without a token, but GitHub limits how many requests an anonymous user can make. A private repository needs a token with read access to it. The token only goes to api.github.com.",
}


def declare_connection(name, label, section, url="", help="", host=""):
    DECLARED[name] = {"label": label, "section": section, "url": url, "help": help}
    if host:
        HOSTS[name] = host


def check_host(key, url):
    host = HOSTS.get(key)
    if host and (urllib.parse.urlsplit(url).hostname or "").lower() != host:
        raise ValueError(f"The {key} key only goes to {host}. Use a different saved key for {urllib.parse.urlsplit(url).hostname or url}.")


def connections_path():
    return snek_home() / "connections.json"


def load_keys():
    try:
        data = json.loads(connections_path().read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if isinstance(v, str)}
    except (OSError, ValueError):
        return {}


def list_keys():
    keys = load_keys()
    names = sorted(set(keys) | set(DECLARED))
    return [
        {
            "name": name,
            "saved": name in keys,
            "hint": f"…{keys[name][-4:]}" if name in keys and len(keys[name]) > 8 else ("saved" if name in keys else ""),
            "env": env_name(name),
            "from_env": bool(os.environ.get(env_name(name))),
            **({"declared": DECLARED[name]} if name in DECLARED else {}),
        }
        for name in names
    ]


def set_key(name, key):
    if not NAME_RE.match(name):
        raise ValueError("Use lowercase letters, numbers, dashes or underscores for the name")
    key = key.strip()
    if not key:
        raise ValueError("Paste a key")
    keys = load_keys()
    keys[name] = key
    write_keys(keys)


def delete_key(name):
    keys = load_keys()
    keys.pop(name, None)
    write_keys(keys)


def write_keys(keys):
    path = connections_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def env_name(name):
    return re.sub(r"\W", "_", name).upper() + "_API_KEY"


def api_key(name):
    env = os.environ.get(re.sub(r"\W", "_", name).upper() + "_API_KEY")
    if env:
        return env
    home = os.environ.get("SNEK_HOME") or os.path.join(os.path.expanduser("~"), ".snek")
    try:
        with open(os.path.join(home, "connections.json"), encoding="utf-8") as f:
            return json.load(f).get(name, "")
    except (OSError, ValueError):
        return ""


def http_get(url, params=None, headers=None, timeout=60):
    query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v not in (None, "")}, doseq=True)
    request = urllib.request.Request(url + (("&" if "?" in url else "?") + query if query else ""), headers={"Accept": "application/json, text/csv, */*", "User-Agent": "Snek", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace").strip()[:300]
        raise ValueError(f"{e.code} {e.reason} from {url}" + (f": {detail}" if detail else "")) from None
    except urllib.error.URLError as e:
        raise ValueError(f"Could not reach {url}: {e.reason}") from None


def json_frame(data, records=""):
    for part in [p for p in str(records or "").split(".") if p]:
        data = data[int(part)] if isinstance(data, list) else data[part]
    if isinstance(data, dict):
        data = [data]
    if not data:
        return pd.DataFrame()
    if not isinstance(data[0], dict):
        return pd.DataFrame({"value": data})
    return pd.json_normalize(data)


def api_request(url, params=None, auth="none", key="", header="X-API-Key", records="", fmt="json"):
    params, headers, secret = dict(params or {}), {}, ""
    if auth != "none":
        secret = api_key(key)
        if not secret:
            raise ValueError(f"No API key saved as {key!r}. Add it in Edit ▸ Settings ▸ Data Connections.")
        if auth == "bearer":
            headers["Authorization"] = f"Bearer {secret}"
        elif auth == "header":
            headers[header] = secret
        else:
            params[header] = secret
    try:
        text = http_get(url, params, headers)
    except ValueError as e:
        raise ValueError(str(e).replace(secret, f"…{secret[-4:]}") if secret else str(e)) from None
    if fmt == "csv":
        return pd.read_csv(io.StringIO(text))
    return json_frame(json.loads(text), records)


def github_next(link):
    for part in link.split(","):
        pieces = part.split(";")
        if len(pieces) > 1 and 'rel="next"' in pieces[1]:
            return pieces[0].strip().strip("<>")
    return ""


def github_request(url, params=None, token="", raw=False):
    query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v not in (None, "")})
    headers = {"Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json", "User-Agent": "Snek"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url + (("&" if "?" in url else "?") + query if query else ""), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read(), response.headers.get("Link", "")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429) and e.headers.get("X-RateLimit-Remaining") == "0":
            reset = e.headers.get("X-RateLimit-Reset", "")
            when = time.strftime("%H:%M", time.localtime(int(reset))) if reset.isdigit() else "later"
            hint = "" if token else " Save a GitHub token in Edit ▸ Settings to raise the limit."
            raise ValueError(f"GitHub rate limit reached. It resets at {when}.{hint}") from None
        if e.code == 401:
            raise ValueError("GitHub rejected the saved token. Save a new one in Edit ▸ Settings." if token else "This needs a GitHub token. Save one in Edit ▸ Settings.") from None
        if e.code == 404:
            hint = "" if token else " A private repository needs a saved GitHub token."
            raise ValueError(f"GitHub could not find that. Check the owner, repository and path.{hint}") from None
        detail = e.read().decode("utf-8", errors="replace").strip()[:200]
        if token:
            detail = detail.replace(token, "…")
        raise ValueError(f"{e.code} {e.reason} from GitHub" + (f": {detail}" if detail else "")) from None
    except urllib.error.URLError as e:
        raise ValueError(f"Could not reach GitHub: {e.reason}") from None


def github_file(data, name, fmt="auto"):
    kinds = {".csv": "csv", ".txt": "csv", ".tsv": "tsv", ".tab": "tsv", ".json": "json", ".jsonl": "jsonl", ".ndjson": "jsonl", ".xlsx": "excel", ".xlsm": "excel", ".xls": "excel", ".parquet": "parquet", ".pq": "parquet"}
    kind = fmt if fmt != "auto" else kinds.get(os.path.splitext(name)[1].lower(), "csv")
    buf = io.BytesIO(data)
    if kind in ("csv", "tsv"):
        return pd.read_csv(buf, sep="\t" if kind == "tsv" else ",")
    if kind == "excel":
        return pd.read_excel(buf)
    if kind == "parquet":
        return pd.read_parquet(buf)
    if kind == "jsonl":
        return pd.read_json(buf, lines=True)
    return json_frame(json.loads(data))


def github(what, owner="", repo="", path="", ref="", state="all", limit=500, fmt="auto", key="github"):
    token = api_key(key)
    api = "https://api.github.com"
    owner, repo, path = str(owner or "").strip(), str(repo or "").strip(), str(path or "").strip().strip("/")
    where = f"{api}/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}"
    if what == "file":
        data, _ = github_request(f"{where}/contents/{urllib.parse.quote(path)}", {"ref": ref}, token, raw=True)
        return github_file(data, path, fmt)
    urls = {
        "repos": f"{api}/users/{urllib.parse.quote(owner)}/repos" if owner else f"{api}/user/repos",
        "issues": f"{where}/issues",
        "pulls": f"{where}/pulls",
        "commits": f"{where}/commits",
        "releases": f"{where}/releases",
        "files": f"{where}/contents/{urllib.parse.quote(path)}",
    }
    columns = {
        "repos": ["name", "full_name", "private", "description", "language", "stargazers_count", "forks_count", "open_issues_count", "default_branch", "archived", "created_at", "updated_at", "pushed_at", "owner.login", "html_url"],
        "issues": ["number", "title", "state", "is_pull_request", "user.login", "labels", "assignee.login", "comments", "created_at", "updated_at", "closed_at", "html_url", "body"],
        "pulls": ["number", "title", "state", "draft", "user.login", "head.ref", "base.ref", "created_at", "updated_at", "closed_at", "merged_at", "html_url"],
        "commits": ["sha", "commit.author.name", "commit.author.date", "commit.message", "author.login", "html_url"],
        "releases": ["tag_name", "name", "draft", "prerelease", "published_at", "author.login", "html_url"],
        "files": ["name", "path", "type", "size", "sha", "download_url"],
    }[what]
    params = {"per_page": 100}
    if what in ("issues", "pulls"):
        params["state"] = state
    elif what == "commits":
        params["sha"] = ref
    elif what == "files":
        params = {"ref": ref}
    elif what == "repos" and not owner:
        params["sort"] = "updated"
    rows, url, more = [], urls[what], False
    while url:
        data, link = github_request(url, params, token)
        page = json.loads(data)
        rows += page if isinstance(page, list) else [page]
        url, params = github_next(link), None
        if len(rows) >= limit:
            more = bool(url)
            break
    if more:
        warnings.warn(f"Stopped at {limit} rows. Raise the row limit to fetch more.")
    rows = rows[:limit]
    frame = json_frame(rows)
    if what == "issues" and len(frame):
        frame["is_pull_request"] = frame["pull_request.url"].notna() if "pull_request.url" in frame else False
    if "labels" in frame:
        frame["labels"] = frame["labels"].map(lambda v: ", ".join(x.get("name", "") for x in v) if isinstance(v, list) else "")
    if not len(frame):
        return pd.DataFrame(columns=columns)
    return frame[[c for c in columns if c in frame.columns]].reset_index(drop=True)
