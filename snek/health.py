import importlib
import importlib.metadata
import importlib.util
import platform
import re
import sys

from snek import __version__

PYTHON_MINIMUM = (3, 12)

PACKAGES = [
    ("fastapi", "fastapi", None),
    ("uvicorn", "uvicorn", None),
    ("pandas", "pandas", (3, 0)),
    ("numpy", "numpy", None),
    ("openpyxl", "openpyxl", None),
    ("pyarrow", "pyarrow", None),
    ("scikit-learn", "sklearn", None),
    ("scipy", "scipy", None),
    ("statsmodels", "statsmodels", None),
    ("anthropic", "anthropic", None),
    ("pyshp", "shapefile", None),
]


def parse_version(text):
    return tuple(int(p) for p in re.findall(r"\d+", text or "")[:2])


def installed_version(dist, module):
    if module is not None:
        found = getattr(module, "__version__", "")
        if found:
            return str(found)
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return ""


def check(deep=False):
    rows = []
    for dist, name, minimum in PACKAGES:
        row = {"package": dist, "module": name, "ok": True, "version": "", "problem": ""}
        loaded = None
        try:
            if deep:
                loaded = importlib.import_module(name)
            elif importlib.util.find_spec(name) is None:
                row.update(ok=False, problem="not installed")
        except Exception as e:
            row.update(ok=False, problem=f"{type(e).__name__}: {e}")
        if row["ok"]:
            row["version"] = installed_version(dist, loaded)
            if minimum and row["version"] and parse_version(row["version"]) < minimum:
                row.update(ok=False, problem=f"needs version {'.'.join(map(str, minimum))} or newer")
        rows.append(row)
    python_ok = sys.version_info[:2] >= PYTHON_MINIMUM
    missing = [r["package"] for r in rows if not r["ok"]]
    return {
        "ok": python_ok and not missing,
        "snek": __version__,
        "python": platform.python_version(),
        "python_ok": python_ok,
        "frozen": bool(getattr(sys, "frozen", False)),
        "deep": deep,
        "packages": rows,
        "missing": missing,
    }


def report(result):
    lines = [f"Snek {result['snek']} on Python {result['python']}" + ("" if result["python_ok"] else f" (needs {'.'.join(map(str, PYTHON_MINIMUM))} or newer)")]
    for r in result["packages"]:
        lines.append(f"  {'ok     ' if r['ok'] else 'PROBLEM'} {r['package']} {r['version']}".rstrip() + (f": {r['problem']}" if r["problem"] else ""))
    lines.append("All needed packages are present." if result["ok"] else "Something is missing or too old.")
    return "\n".join(lines)


def import_hint(name):
    from snek import sandbox

    if not (getattr(sys, "frozen", False) or sandbox.active()):
        return ""
    top = (name or "").split(".")[0]
    return f"'{top}' is not included with this copy of Snek, and this copy cannot install packages. To use it, export the workflow as a Python script and run it with your own Python, where you can pip install {top}."
