import json
import re
import subprocess
from importlib import metadata
from pathlib import Path

try:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
except ImportError:
    from pip._vendor.packaging.markers import default_environment
    from pip._vendor.packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent
LICENSE_NAMES = re.compile(r"(^|/)(LICEN[CS]E|COPYING|NOTICE|AUTHORS)[^/]*$", re.IGNORECASE)


def python_closure():
    env = default_environment()
    seen, queue = {}, [("snek", ())]
    while queue:
        name, extras = queue.pop()
        key = name.lower().replace("_", "-")
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        if key in seen and set(extras) <= seen[key][1]:
            continue
        seen[key] = (dist, set(extras) | (seen[key][1] if key in seen else set()))
        for raw in dist.requires or []:
            req = Requirement(raw)
            if req.marker and not any(req.marker.evaluate({**env, "extra": e}) for e in (list(extras) or [""])):
                continue
            queue.append((req.name, tuple(req.extras)))
    return [d for k, (d, _) in sorted(seen.items()) if k != "snek"]


def python_license_text(dist):
    texts = []
    for f in dist.files or []:
        if LICENSE_NAMES.search(str(f)) and ".dist-info" in str(f):
            try:
                texts.append(Path(dist.locate_file(f)).read_text(encoding="utf-8", errors="replace").strip())
            except OSError:
                continue
    return "\n\n".join(t for t in texts if t)


def node_packages():
    out = subprocess.run(["npm", "ls", "--omit=dev", "--all", "--parseable"], cwd=ROOT / "frontend", capture_output=True, text=True)
    paths = [Path(p) for p in out.stdout.splitlines()[1:]]
    pkgs = {}
    for p in paths:
        meta = json.loads((p / "package.json").read_text())
        files = sorted(f for f in p.iterdir() if f.is_file() and LICENSE_NAMES.search(f.name))
        text = "\n\n".join(f.read_text(encoding="utf-8", errors="replace").strip() for f in files)
        pkgs[f"{meta['name']}@{meta.get('version', '')}"] = (meta["name"], meta.get("version", ""), meta.get("license", ""), text)
    return pkgs


def main():
    parts = [
        "# Third-party notices",
        "",
        "Snek's apps and source download include the components below. Each keeps its own license, reproduced here as those licenses require. Snek's own license is in LICENSE.",
        "",
        "## Python packages",
        "",
    ]
    for dist in python_closure():
        meta = dist.metadata
        lic = meta.get("License-Expression") or meta.get("License") or ", ".join(c.split(" :: ")[-1] for c in meta.get_all("Classifier") or [] if c.startswith("License ::"))
        lic = lic.splitlines()[0][:80] if lic else "see text"
        parts += [f"### {meta['Name']} {dist.version}", "", f"License: {lic}", ""]
        text = python_license_text(dist)
        parts += ["```", text or "License file not shipped with the package; see the project's homepage.", "```", ""]
    parts += ["## JavaScript packages (bundled into the interface)", ""]
    for _, (name, version, lic, text) in sorted(node_packages().items()):
        parts += [f"### {name} {version}", "", f"License: {lic or 'see text'}", "", "```", text or "No license file in the package.", "```", ""]
    (ROOT / "THIRD_PARTY_NOTICES.md").write_text("\n".join(parts))
    print("wrote THIRD_PARTY_NOTICES.md")


if __name__ == "__main__":
    main()
