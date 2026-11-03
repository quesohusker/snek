import os
import re
import subprocess
import sys

BUNDLE_ID = "com.quesohusker.norm"
PLACES = ("/Applications/Norm.app", "~/Applications/Norm.app")


def find_app():
    if sys.platform != "darwin":
        return None
    for place in PLACES:
        path = os.path.expanduser(place)
        if os.path.isdir(path):
            return path
    try:
        found = subprocess.run(["mdfind", f"kMDItemCFBundleIdentifier == '{BUNDLE_ID}'"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return next((line for line in found.splitlines() if line.endswith(".app")), None)


def launch(path):
    if find_app() is None:
        return False
    return subprocess.run(["open", "-b", BUNDLE_ID, path], check=False).returncode == 0


def file_name(label):
    return re.sub(r'[\\/:*?"<>|]+', "-", str(label or "")).strip(" .-") or "Snek output"
