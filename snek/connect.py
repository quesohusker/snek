import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from snek.paths import snek_home

NAME_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
DECLARED = {}
HOSTS = {"anthropic": "api.anthropic.com"}


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
