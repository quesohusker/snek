import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "snek" / "__init__.py").read_text(encoding="utf-8")).group(1)
ICON = str(ROOT / "packaging" / ("snek.ico" if sys.platform.startswith("win") else "snek.png"))

datas = [(str(ROOT / "frontend" / "dist"), "frontend/dist"), (str(ROOT / "examples"), "examples"), (str(ROOT / "LICENSE"), "."), (str(ROOT / "THIRD_PARTY_NOTICES.md"), ".")]
datas += [(str(p), "workflows") for p in sorted((ROOT / "workflows").glob("*.snek")) if not p.name.startswith("CFB")]

a = Analysis(
    [str(ROOT / "packaging" / "snek_app.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=collect_submodules("snek") + collect_submodules("uvicorn"),
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "PIL"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Snek",
    console=sys.platform != "darwin",
    argv_emulation=sys.platform == "darwin",
    icon=ICON,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Snek")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Snek.app",
        icon=ICON,
        bundle_identifier="com.quesohusker.snek",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSUIElement": True,
            "NSHighResolutionCapable": True,
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Snek workflow",
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Owner",
                "LSItemContentTypes": ["com.quesohusker.snek.workflow"],
            }],
            "UTExportedTypeDeclarations": [{
                "UTTypeIdentifier": "com.quesohusker.snek.workflow",
                "UTTypeDescription": "Snek workflow",
                "UTTypeConformsTo": ["public.json", "public.data"],
                "UTTypeTagSpecification": {"public.filename-extension": ["snek"]},
            }],
        },
    )
