import json
import re
import time
import urllib.request

from snek import __version__
from snek.paths import snek_home

RELEASES = "https://api.github.com/repos/quesohusker/snek/releases/latest"
DAY = 24 * 60 * 60


def version_tuple(text):
    return tuple(int(p) for p in re.findall(r"\d+", text or "")[:3])


def state_path():
    return snek_home() / "updates.json"


def load_state():
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state):
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def fetch_latest():
    req = urllib.request.Request(RELEASES, headers={"Accept": "application/vnd.github+json", "User-Agent": "Snek"})
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.loads(r.read())
    return data["tag_name"], data["html_url"]


def check(force=False, fetch=fetch_latest):
    state = load_state()
    enabled = state.get("enabled", True)
    result = {"current": __version__, "enabled": enabled, "latest": state.get("latest"), "url": state.get("url"), "error": ""}
    stale = time.time() - state.get("checked", 0) > DAY
    if force or (enabled and stale):
        try:
            result["latest"], result["url"] = fetch()
            state.update(latest=result["latest"], url=result["url"])
        except Exception as e:
            result["error"] = f"Could not reach GitHub: {e}"
        state["checked"] = time.time()
        save_state(state)
    result["update"] = bool(result["latest"]) and version_tuple(result["latest"]) > version_tuple(__version__)
    return result


def set_enabled(enabled):
    state = load_state()
    state["enabled"] = bool(enabled)
    save_state(state)
    return check()
