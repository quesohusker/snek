from importlib.metadata import entry_points

LOADED = []
ERRORS = []


def load_plugins():
    for ep in entry_points(group="snek.plugins"):
        if ep.name in LOADED:
            continue
        try:
            ep.load()
            LOADED.append(ep.name)
        except Exception as e:
            ERRORS.append(f"{ep.name}: {e}")
