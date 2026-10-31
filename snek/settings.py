import json

from snek.paths import snek_home

DEFAULTS = {"autosave_minutes": 5, "autosave_mode": "file"}
MODES = ("file", "backup")


def settings_path():
    return snek_home() / "settings.json"


def load():
    try:
        stored = json.loads(settings_path().read_text())
    except (OSError, ValueError):
        stored = {}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}


def save(changes):
    current = load()
    if "autosave_minutes" in changes:
        minutes = int(changes["autosave_minutes"])
        if not 0 <= minutes <= 240:
            raise ValueError("Autosave must be between 0 (off) and 240 minutes")
        current["autosave_minutes"] = minutes
    if "autosave_mode" in changes:
        if changes["autosave_mode"] not in MODES:
            raise ValueError(f"Autosave mode must be one of {MODES}")
        current["autosave_mode"] = changes["autosave_mode"]
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2))
    return current


def autosave_folder():
    return snek_home() / "autosave"
