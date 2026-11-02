import json
import os
from pathlib import Path

from snek.paths import BUNDLE, snek_home

FIX = "Choose File > Allow Folder Access and pick the folder that holds it."


def active():
    return os.environ.get("SNEK_SANDBOXED") == "1"


def real(path):
    return os.path.realpath(os.path.abspath(os.path.expanduser(str(path))))


def grants():
    try:
        data = json.loads((snek_home() / "grants.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [Path(p) for p in data if isinstance(p, str) and p]


def inside(target, root):
    return target == root or target.startswith(root.rstrip(os.sep) + os.sep)


def allowed(path):
    if not active():
        return True
    target = real(path)
    roots = [real(r) for r in (snek_home(), BUNDLE, os.getcwd(), *grants())]
    return any(inside(target, r) for r in roots)


def refusal(path):
    return f"Snek can't reach {path}. {FIX}"


def rewrite(exc, text):
    if not active():
        return text
    if isinstance(exc, PermissionError):
        return refusal(exc.filename or "that location")
    if isinstance(exc, FileNotFoundError) and str(exc).startswith("No files match "):
        pattern = str(exc)[len("No files match "):]
        if not allowed(os.path.dirname(pattern)):
            return refusal(pattern)
    return text
