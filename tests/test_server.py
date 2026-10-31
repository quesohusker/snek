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
    assert ((tmp_path / "proj").resolve() / "workflows" / "First flow.snek").exists()
    assert [w["name"] for w in client.get("/api/workflows").json()["workflows"]] == ["First flow"]


def test_workflow_names_with_punctuation(client, tmp_path):
    client.post("/api/project/new", json={"parent": str(tmp_path), "name": "proj"})
    name = "Week 5 (draft), Nebraska & Iowa"
    assert client.put(f"/api/workflows/{name}", json=simple_output_workflow("output/x.csv")).status_code == 200
    assert client.get(f"/api/workflows/{name}").status_code == 200
    assert client.put("/api/workflows/a%2Fb", json={}).status_code >= 400
    assert client.put("/api/workflows/..", json={}).status_code >= 400
    assert not list((tmp_path / "proj").glob("*.flow.json"))


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


def test_snek_files_open_save_and_legacy(client, tmp_path):
    client.post("/api/project/new", json={"parent": str(tmp_path), "name": "proj"})
    saved = client.post("/api/file/save", json={"path": str(tmp_path / "Desktop" / "my flow"), "workflow": simple_output_workflow("output/x.csv")}).json()
    assert saved["path"].endswith("my flow.snek") and saved["name"] == "my flow"
    data = (tmp_path / "Desktop" / "my flow.snek").read_text()
    assert '"format": "snek"' in data
    opened = client.post("/api/file/open", json={"path": saved["path"]}).json()
    assert opened["name"] == "my flow" and len(opened["workflow"]["nodes"]) == 2
    workflows = (tmp_path / "proj").resolve() / "workflows"
    (workflows / "Old one.flow.json").write_text(json.dumps(simple_output_workflow("output/y.csv")))
    listing = client.get("/api/workflows").json()["workflows"]
    assert [w["name"] for w in listing] == ["Old one"]
    assert client.get("/api/workflows/Old one").status_code == 200
    client.put("/api/workflows/Old one", json=simple_output_workflow("output/y.csv"))
    assert (workflows / "Old one.snek").exists() and not (workflows / "Old one.flow.json").exists()
    (tmp_path / "notes.txt").write_text("hello")
    assert client.post("/api/file/open", json={"path": str(tmp_path / "notes.txt")}).status_code == 400


def test_settings_and_autosave(client, tmp_path):
    assert client.get("/api/settings").json()["autosave_minutes"] == 5
    assert client.put("/api/settings", json={"autosave_minutes": 10, "autosave_mode": "backup"}).json()["autosave_mode"] == "backup"
    assert client.get("/api/settings").json()["autosave_minutes"] == 10
    assert client.put("/api/settings", json={"autosave_minutes": 999}).status_code == 400
    assert client.put("/api/settings", json={"autosave_mode": "cloud"}).status_code == 400
    r = client.post("/api/autosave", json={"workflow": simple_output_workflow("output/x.csv"), "name": "Week 5/draft"}).json()
    path = Path(r["path"])
    assert path.parent == tmp_path / "home" / "autosave" and path.name == "Week 5_draft.snek"
    assert path.exists()


def test_upload_saves_into_project_data(client, tmp_path):
    client.post("/api/project/new", json={"parent": str(tmp_path), "name": "proj"})
    r = client.post("/api/upload?name=games.csv", content=b"a,b\n1,2\n")
    data = (tmp_path / "proj").resolve() / "data"
    assert r.json()["path"] == str(data / "games.csv")
    assert client.post("/api/upload?name=games.csv", content=b"a,b\n1,2\n").json()["path"] == str(data / "games.csv")
    assert client.post("/api/upload?name=games.csv", content=b"a,b\n3,4\n").json()["path"] == str(data / "games (2).csv")
    assert client.post("/api/upload?name=evil.sh", content=b"x").status_code == 400
    assert client.post("/api/upload?name=../../x.csv", content=b"a\n1\n").json()["path"] == str(data / "x.csv")


def test_table_copies_as_tab_separated(client):
    r = client.post("/api/table", json={"workflow": simple_output_workflow("output/x.csv"), "node": "1"})
    assert r.json() == {"text": "a\tb\n1\t2\n3\t4\n", "rows": 2, "total": 2}
