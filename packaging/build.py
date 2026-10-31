import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "packaging" / "dist"


def asset_name():
    if sys.platform == "darwin":
        return "Snek-macOS-AppleSilicon.zip" if platform.machine() == "arm64" else "Snek-macOS-Intel.zip"
    if sys.platform.startswith("win"):
        return "Snek-Windows.zip"
    return "Snek-Linux.tar.gz"


def build():
    subprocess.run([sys.executable, str(ROOT / "packaging" / "third_party.py")], check=True)
    shutil.rmtree(DIST, ignore_errors=True)
    shutil.rmtree(ROOT / "packaging" / "build", ignore_errors=True)
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(DIST), "--workpath", str(ROOT / "packaging" / "build"), str(ROOT / "packaging" / "snek.spec")],
        check=True,
    )


def package():
    name = asset_name()
    target = DIST / name
    if sys.platform == "darwin":
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(DIST / "Snek.app"), str(target)], check=True)
    elif sys.platform.startswith("win"):
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            for f in (DIST / "Snek").rglob("*"):
                z.write(f, Path("Snek") / f.relative_to(DIST / "Snek"))
    else:
        with tarfile.open(target, "w:gz") as t:
            t.add(DIST / "Snek", arcname="Snek")
    print(target, round(target.stat().st_size / 1024 / 1024, 1), "MB")
    return target


def executable():
    if sys.platform == "darwin":
        return DIST / "Snek.app" / "Contents" / "MacOS" / "Snek"
    if sys.platform.startswith("win"):
        return DIST / "Snek" / "Snek.exe"
    return DIST / "Snek" / "Snek"


if __name__ == "__main__":
    if "--package-only" not in sys.argv:
        build()
    package()
    print("executable:", executable())
