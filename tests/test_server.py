import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snek import server
from snek.projects import ROOT


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SNEK_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    yield TestClient(server.app)
    server.projects.current = ROOT
    server.projects.recent = []


def simple_output_workflow(path):
    return {
        "nodes": [
            {"id": "1", "type": "text_input", "config": {"data": "a,b\n1,2\n3,4"}},
            {"id": "2", "type": "output", "config": {"path": path}},
        ],
        "edges": [{"source": "1", "sourceHandle": "out", "target": "2", "targetHandle": "in"}],
    }


def test_new_project_creates_folders_and_becomes_current(client, tmp_path):
    r = client.post("/api/project/new", json={"parent": str(tmp_path / "projects"), "name": "CFB study"})
    assert r.status_code == 200, r.text
    folder = (tmp_path / "projects" / "CFB study").resolve()
    info = r.json()
    assert info["name"] == "CFB study"
    assert info["path"] == str(folder)
    assert all((folder / sub).is_dir() for sub in ("data", "output", "workflows"))
    assert Path(os.getcwd()) == folder
    saved = json.loads((tmp_path / "home" / "config.json").read_text())
    assert saved["project"] == str(folder)
    assert saved["recent"][0] == str(folder)


def test_relative_output_lands_in_project(client, tmp_path):
    client.post("/api/project/new", json={"parent": str(tmp_path), "name": "proj"})
    r = client.post("/api/run", json={"workflow": simple_output_workflow("output/results")})
    folder = (tmp_path / "proj").resolve()
    assert (folder / "output" / "results.csv").exists()
    assert r.json()["results"]["2"]["message"] == f"Wrote 2 rows to {folder / 'output' / 'results.csv'}"
    resolved = client.get("/api/resolve", params={"path": "output/other", "fmt": "excel"}).json()
    assert resolved["path"] == str(folder / "output" / "other.xlsx")


def test_workflows_save_into_project(client, tmp_path):
    client.post("/api/project/new", json={"parent": str(tmp_path), "name": "proj"})
    client.put("/api/workflows/First flow", json=simple_output_workflow("output/x.csv"))
    assert ((tmp_path / "proj").resolve() / "workflows" / "First flow.flow.json").exists()
    assert [w["name"] for w in client.get("/api/workflows").json()["workflows"]] == ["First flow"]


def test_open_examples_and_reject_bad_input(client, tmp_path):
    client.post("/api/project/new", json={"parent": str(tmp_path), "name": "proj"})
    r = client.post("/api/project/open", json={"path": str(ROOT)})
    assert r.json()["name"] == "Snek examples"
    assert r.json()["is_examples"]
    assert [p["name"] for p in r.json()["recent"]] == ["proj"]
    assert client.post("/api/project/open", json={"path": str(tmp_path / "missing")}).status_code == 400
    (tmp_path / "taken").mkdir()
    (tmp_path / "taken" / "file.txt").write_text("x")
    assert client.post("/api/project/new", json={"parent": str(tmp_path), "name": "taken"}).status_code == 400
    assert client.post("/api/project/new", json={"parent": str(tmp_path), "name": "a/b"}).status_code == 400


def test_file_browser_starts_in_project_and_lists_places(client, tmp_path):
    client.post("/api/project/new", json={"parent": str(tmp_path), "name": "proj"})
    listing = client.get("/api/fs").json()
    assert listing["path"] == str((tmp_path / "proj").resolve())
    labels = [p["label"] for p in listing["places"]]
    assert labels[:3] == ["Project", "Project output", "Project data"]
    for name in ("Desktop", "Documents", "Downloads"):
        assert (name in labels) == (Path.home() / name).is_dir()
