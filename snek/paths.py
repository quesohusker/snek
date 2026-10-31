import os
import shutil
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
SOURCE_ROOT = Path(__file__).resolve().parent.parent
BUNDLE = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))
DIST = BUNDLE / "frontend" / "dist"


def snek_home():
    return Path(os.environ.get("SNEK_HOME", Path.home() / ".snek"))


def examples_root():
    if not FROZEN:
        return SOURCE_ROOT
    target = snek_home() / "Snek examples"
    for sub in ("examples", "workflows"):
        for src in (BUNDLE / sub).rglob("*"):
            dest = target / src.relative_to(BUNDLE)
            if src.is_file() and not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
    return target
