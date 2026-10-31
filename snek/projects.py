import json
import os
from pathlib import Path

from snek.paths import examples_root, snek_home

ROOT = examples_root()
EXAMPLES_NAME = "Snek examples"
SUBFOLDERS = ("data", "output", "workflows")


def config_path():
    return snek_home() / "config.json"


class Projects:
    def __init__(self):
        self.current = ROOT
        self.recent = []

    def load(self):
        try:
            data = json.loads(config_path().read_text())
        except (OSError, ValueError):
            data = {}
        self.recent = [p for p in data.get("recent", []) if Path(p).is_dir()]
        start = data.get("project")
        self.open(start if start and Path(start).is_dir() else ROOT, remember=False)

    def save(self):
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"project": str(self.current), "recent": self.recent[:10]}, indent=2))

    def open(self, path, remember=True):
        folder = Path(os.path.expanduser(str(path))).resolve()
        if not folder.is_dir():
            raise ValueError(f"Not a folder: {folder}")
        self.current = folder
        os.chdir(folder)
        if remember:
            if folder != ROOT:
                self.recent = [str(folder)] + [p for p in self.recent if p != str(folder)]
            self.save()
        return folder

    def create(self, parent, name):
        name = (name or "").strip()
        if not name or "/" in name or "\\" in name or name.startswith("."):
            raise ValueError("Give the project a name without slashes")
        folder = Path(os.path.expanduser(parent or "~")).resolve() / name
        if folder.exists() and any(folder.iterdir()):
            raise ValueError(f"{folder} already exists and is not empty. Use Open project folder instead.")
        for sub in SUBFOLDERS:
            (folder / sub).mkdir(parents=True, exist_ok=True)
        return self.open(folder)

    @property
    def workflows(self):
        return self.current / "workflows"

    def name_of(self, path):
        return EXAMPLES_NAME if Path(path) == ROOT else Path(path).name

    def places(self):
        home = Path.home()
        items = [
            ("Project", self.current),
            ("Project output", self.current / "output"),
            ("Project data", self.current / "data"),
            ("Desktop", home / "Desktop"),
            ("Documents", home / "Documents"),
            ("Downloads", home / "Downloads"),
            ("Home", home),
            (EXAMPLES_NAME, ROOT / "examples" / "data"),
        ]
        extra = [tuple(p.split("=", 1)) for p in os.environ.get("SNEK_PLACES", "").split(";") if "=" in p]
        items += [(label, Path(os.path.expanduser(path))) for label, path in extra]
        seen = set()
        out = []
        for label, path in items:
            if path.is_dir() and (label, str(path)) not in seen:
                seen.add((label, str(path)))
                out.append({"label": label, "path": str(path)})
        return out

    def info(self):
        return {
            "path": str(self.current),
            "name": self.name_of(self.current),
            "is_examples": self.current == ROOT,
            "workflows": str(self.workflows),
            "recent": [{"path": p, "name": self.name_of(p)} for p in self.recent],
            "examples": str(ROOT),
            "places": self.places(),
        }
