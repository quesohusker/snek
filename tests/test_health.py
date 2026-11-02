import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snek import health, server
from snek.engine import Engine

ROOT = Path(__file__).resolve().parent.parent


def test_every_declared_dependency_is_checked():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"dependencies = \[(.*?)\]", text, re.S).group(1)
    declared = {re.split(r"[\[<>=!~ ]", item.strip().strip('"'))[0].lower() for item in block.split(",") if item.strip()}
    checked = {dist for dist, _, _ in health.PACKAGES}
    assert declared <= checked, declared - checked


def test_this_install_passes_a_deep_check():
    result = health.check(deep=True)
    assert result["ok"] and not result["missing"] and result["python_ok"]
    assert all(r["version"] for r in result["packages"])
    assert "All needed packages are present." in health.report(result)


def test_a_missing_package_is_found_and_named(monkeypatch):
    monkeypatch.setattr(health, "PACKAGES", health.PACKAGES + [("no-such-package", "no_such_package_xyz", None)])
    for deep in (False, True):
        result = health.check(deep=deep)
        assert not result["ok"] and result["missing"] == ["no-such-package"]
        text = health.report(result)
        assert "PROBLEM no-such-package" in text and "Something is missing" in text


def test_an_old_package_is_reported(monkeypatch):
    monkeypatch.setattr(health, "PACKAGES", [("pandas", "pandas", (99, 0))])
    result = health.check(deep=True)
    assert result["missing"] == ["pandas"] and "needs version 99.0 or newer" in result["packages"][0]["problem"]


def test_an_old_python_is_reported(monkeypatch):
    monkeypatch.setattr(health, "PYTHON_MINIMUM", (99, 0))
    result = health.check()
    assert not result["ok"] and not result["python_ok"] and "needs 99.0 or newer" in health.report(result)


def test_health_endpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(server.app, base_url="http://127.0.0.1:8765")
    quick = client.get("/api/health").json()
    deep = client.get("/api/health", params={"deep": "true"}).json()
    assert quick["ok"] and not quick["deep"] and deep["ok"] and deep["deep"]
    assert {p["package"] for p in deep["packages"]} == {d for d, _, _ in health.PACKAGES}


@pytest.mark.parametrize("flag", [["--check"], ["--check", "quick"], ["--check=deep"]])
def test_check_flag_sets_the_exit_code(flag):
    done = subprocess.run([sys.executable, "-m", "snek", *flag], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0 and "All needed packages are present." in done.stdout


def python_step(code):
    wf = {
        "nodes": [{"id": "1", "type": "text_input", "config": {"data": "a\n1"}}, {"id": "2", "type": "python", "config": {"code": code}}],
        "edges": [{"source": "1", "sourceHandle": "out", "target": "2", "targetHandle": "in"}],
    }
    return Engine().evaluate(wf, run_side_effects=True).results["2"]


def test_import_hint_only_in_packaged_or_sandboxed_builds(monkeypatch):
    res = python_step("import no_such_package_xyz\nout = df")
    assert res.status == "error" and "ModuleNotFoundError" in res.error
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    res = python_step("import no_such_package_xyz.sub\nout = df")
    assert res.status == "error" and "'no_such_package_xyz' is not included with this copy of Snek" in res.error
    assert "pip install no_such_package_xyz" in res.error
