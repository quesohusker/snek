import json

from snek.paths import snek_home

AI_MODELS = {"claude-opus-5-5": "Claude Opus 5.5 (best results)", "claude-sonnet-5-5": "Claude Sonnet 5.5 (faster, half the price)", "claude-haiku-5-5": "Claude Haiku 5.5 (fastest, cheapest)"}
DEFAULT_AI_MODEL = "claude-opus-5-5"
DEFAULTS = {"autosave_minutes": 5, "autosave_mode": "file", "ai_model": DEFAULT_AI_MODEL}
MODES = ("file", "backup")


def settings_path():
    return snek_home() / "settings.json"


def load():
    try:
        stored = json.loads(settings_path().read_text(encoding="utf-8"))
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
    if "ai_model" in changes:
        if changes["ai_model"] not in AI_MODELS:
            raise ValueError(f"AI model must be one of {', '.join(AI_MODELS)}")
        current["ai_model"] = changes["ai_model"]
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def autosave_folder():
    return snek_home() / "autosave"
