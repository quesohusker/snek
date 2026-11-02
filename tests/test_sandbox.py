import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snek import sandbox, server
from snek.engine import Engine
from snek.projects import ROOT


@pytest.fixture
def sandboxed(tmp_path, monkeypatch):
    fake_home = tmp_path / "container"
    (fake_home / "Desktop").mkdir(parents=True)
    granted = tmp_path / "granted"
    other = tmp_path / "other"
    project = tmp_path / "project"
    for folder in (granted, other, project):
        folder.mkdir()
    (granted / "a.csv").write_text("x\n1\n", encoding="utf-8")
    (other / "b.csv").write_text("x\n2\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.setenv("SNEK_HOME", str(fake_home / ".snek"))
    monkeypatch.setenv("SNEK_SANDBOXED", "1")
    monkeypatch.chdir(project)
    (fake_home / ".snek").mkdir()
    (fake_home / ".snek" / "grants.json").write_text(json.dumps([str(granted)]), encoding="utf-8")
    client = TestClient(server.app, base_url="http://127.0.0.1:8765")
    yield {"client": client, "granted": granted, "other": other, "project": project, "home": fake_home}
    server.projects.current = ROOT
    server.projects.recent = []


def test_everything_is_allowed_when_not_sandboxed(tmp_path, monkeypatch):
    monkeypatch.delenv("SNEK_SANDBOXED", raising=False)
    assert not sandbox.active()
    assert sandbox.allowed(tmp_path / "anywhere" / "file.csv")
    assert sandbox.rewrite(PermissionError(1, "Operation not permitted", "/x/y.csv"), "PermissionError: raw") == "PermissionError: raw"


def test_allowed_covers_grants_project_and_snek_home(sandboxed):
    assert sandbox.active()
    assert sandbox.allowed(sandboxed["granted"] / "a.csv")
    assert sandbox.allowed(sandboxed["granted"] / "deeper" / "c.csv")
    assert sandbox.allowed(sandboxed["project"] / "data" / "d.csv")
    assert sandbox.allowed("data/relative.csv")
    assert sandbox.allowed(sandboxed["home"] / ".snek" / "uploads" / "e.csv")
    assert not sandbox.allowed(sandboxed["other"] / "b.csv")
    assert not sandbox.allowed(sandboxed["granted"].parent / "elsewhere.csv")


def test_missing_or_broken_grants_file_means_no_grants(sandboxed):
    (sandboxed["home"] / ".snek" / "grants.json").write_text("not json", encoding="utf-8")
    assert sandbox.grants() == []
    (sandboxed["home"] / ".snek" / "grants.json").unlink()
    assert sandbox.grants() == []


def test_file_browser_refuses_folders_that_were_not_granted(sandboxed):
    client = sandboxed["client"]
    refused = client.get("/api/fs", params={"path": str(sandboxed["other"])})
    assert refused.status_code == 403
    assert "Allow Folder Access" in refused.json()["detail"]
    assert str(sandboxed["other"]) in refused.json()["detail"]
    listed = client.get("/api/fs", params={"path": str(sandboxed["granted"])})
    assert listed.status_code == 200
    assert [e["name"] for e in listed.json()["entries"]] == ["a.csv"]


def test_places_list_grants_and_hide_the_home_folders(sandboxed):
    places = {p["label"]: p["path"] for p in server.projects.places()}
    assert places["granted"] == str(sandboxed["granted"])
    assert "Desktop" not in places and "Home" not in places
    assert server.projects.info()["sandboxed"] is True


def test_places_keep_the_home_folders_when_not_sandboxed(sandboxed, monkeypatch):
    monkeypatch.delenv("SNEK_SANDBOXED")
    places = {p["label"] for p in server.projects.places()}
    assert {"Desktop", "Home"} <= places
    assert server.projects.info()["sandboxed"] is False


def test_permission_errors_name_the_file_and_the_fix(sandboxed):
    text = sandbox.rewrite(PermissionError(1, "Operation not permitted", str(sandboxed["other"] / "b.csv")), "PermissionError: raw")
    assert "Allow Folder Access" in text
    assert str(sandboxed["other"] / "b.csv") in text
    assert sandbox.rewrite(ValueError("nope"), "ValueError: nope") == "ValueError: nope"


def test_empty_pattern_in_a_refused_folder_blames_access_not_the_files(sandboxed):
    pattern = str(sandboxed["other"] / "*.csv")
    text = sandbox.rewrite(FileNotFoundError(f"No files match {pattern}"), f"FileNotFoundError: No files match {pattern}")
    assert "Allow Folder Access" in text
    inside = str(sandboxed["granted"] / "*.zzz")
    kept = sandbox.rewrite(FileNotFoundError(f"No files match {inside}"), f"FileNotFoundError: No files match {inside}")
    assert kept == f"FileNotFoundError: No files match {inside}"


def input_workflow(path):
    return {"nodes": [{"id": "1", "type": "input", "config": {"path": path}}], "edges": []}


def test_engine_reports_refused_pattern_as_an_access_problem(sandboxed):
    result = Engine().evaluate(input_workflow(str(sandboxed["other"] / "*.zzz")), run_side_effects=True).to_json()["results"]["1"]
    assert result["status"] == "error"
    assert "Allow Folder Access" in result["error"]
    assert "at:" not in result["error"]


def test_engine_runs_files_inside_a_grant(sandboxed):
    result = Engine().evaluate(input_workflow(str(sandboxed["granted"] / "a.csv")), run_side_effects=True).to_json()["results"]["1"]
    assert result["status"] == "ok"
