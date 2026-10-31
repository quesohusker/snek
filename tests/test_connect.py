import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from snek import connect, server
from snek.codegen import export_script
from snek.engine import Engine
from snek.projects import ROOT

KEY = "test-key-0123456789"


class FakeAPI(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def reply(self, code, body, kind="application/json"):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/bearer":
            if self.headers.get("Authorization") != f"Bearer {KEY}":
                return self.reply(401, {"message": "Unauthorized"})
            return self.reply(200, [{"id": 1, "home": {"team": "Nebraska", "points": 31}, "lines": [{"spread": -7}]}])
        if url.path == "/items":
            if q.get("api_key") != KEY:
                return self.reply(403, "forbidden", "text/plain")
            return self.reply(200, {"data": {"items": [{"a": 1, "b": {"c": 2}}, {"a": 3, "b": {"c": 4}}]}})
        if url.path == "/table.csv":
            return self.reply(200, "x,y\n1,2\n3,4\n", "text/csv")
        return self.reply(404, {"message": "missing"})


@pytest.fixture
def api(tmp_path, monkeypatch):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeAPI)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    monkeypatch.setenv("SNEK_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("DEMO_API_KEY", raising=False)
    yield base
    httpd.shutdown()


def run_tool(tool, cfg):
    ev = Engine().evaluate({"nodes": [{"id": "1", "type": tool, "config": cfg}], "edges": []}, run_side_effects=True)
    return ev, ev.results["1"]


def test_keys_are_private_and_masked(api, tmp_path):
    connect.set_key("weather", KEY)
    path = tmp_path / "home" / "connections.json"
    assert json.loads(path.read_text()) == {"weather": KEY}
    if os.name == "posix":
        assert oct(path.stat().st_mode & 0o777) == "0o600"
    info = {k["name"]: k for k in connect.list_keys()}
    assert info["weather"]["hint"] == "…6789" and KEY not in json.dumps(info)
    with pytest.raises(ValueError):
        connect.set_key("Bad Name", "x")
    connect.delete_key("weather")
    assert connect.api_key("weather") == ""


def test_bearer_key_flattens_nested_fields(api):
    connect.set_key("demo", "wrong-key-000000")
    _, res = run_tool("api_request", {"url": f"{api}/bearer", "auth": "bearer", "key": "demo"})
    assert res.status == "error" and "401" in res.error
    connect.set_key("demo", KEY)
    ev, res = run_tool("api_request", {"url": f"{api}/bearer", "auth": "bearer", "key": "demo"})
    df = ev.frames[("1", "out")]
    assert df.loc[0, "home.team"] == "Nebraska" and df.loc[0, "lines"] == [{"spread": -7}]


def test_api_request_json_path_query_key_and_csv(api):
    connect.set_key("demo", KEY)
    ev, res = run_tool("api_request", {"url": f"{api}/items", "auth": "query", "key": "demo", "header": "api_key", "records": "data.items"})
    assert res.status == "ok", res.error
    assert ev.frames[("1", "out")].to_dict("list") == {"a": [1, 3], "b.c": [2, 4]}
    _, res = run_tool("api_request", {"url": f"{api}/items", "auth": "query", "key": "missing", "header": "api_key"})
    assert res.status == "error" and "No API key saved" in res.error
    ev, res = run_tool("api_request", {"url": f"{api}/table.csv", "fmt": "csv"})
    assert ev.frames[("1", "out")].to_dict("list") == {"x": [1, 3], "y": [2, 4]}
    _, res = run_tool("api_request", {"url": f"{api}/nothing"})
    assert res.status == "error" and "404" in res.error


def test_declared_keys_only_go_to_their_own_host(api):
    connect.set_key("anthropic", KEY)
    connect.set_key("demo", KEY)
    connect.declare_connection("locked", "Locked API", "Locked", host="api.locked.example")
    connect.set_key("locked", KEY)
    try:
        for name in ("anthropic", "locked"):
            _, res = run_tool("api_request", {"url": f"{api}/bearer", "auth": "bearer", "key": name})
            assert res.status == "error" and f"The {name} key only goes to" in res.error and "127.0.0.1" in res.error
        _, res = run_tool("api_request", {"url": f"{api}/bearer", "auth": "bearer", "key": "demo"})
        assert res.status == "ok", res.error
        connect.HOSTS["locked"] = "127.0.0.1"
        _, res = run_tool("api_request", {"url": f"{api}/bearer", "auth": "bearer", "key": "locked"})
        assert res.status == "ok", res.error
    finally:
        connect.DECLARED.pop("locked", None)
        connect.HOSTS.pop("locked", None)


def test_export_keeps_the_key_out_and_still_runs(api, tmp_path):
    connect.set_key("demo", KEY)
    out = tmp_path / "items.csv"
    wf = {
        "nodes": [{"id": "1", "type": "api_request", "config": {"url": f"{api}/items", "auth": "query", "key": "demo", "header": "api_key", "records": "data.items"}}, {"id": "2", "type": "output", "config": {"path": str(out)}}],
        "edges": [{"source": "1", "sourceHandle": "out", "target": "2", "targetHandle": "in"}],
    }
    ev = Engine().evaluate(wf, run_side_effects=True)
    engine_df = pd.read_csv(out)
    script = export_script(ev)
    assert KEY not in script and "api_request(" in script
    path = tmp_path / "flow.py"
    path.write_text(script, encoding="utf-8")
    out.unlink()
    subprocess.run([sys.executable, str(path)], check=True, cwd=tmp_path, env={**os.environ})
    pd.testing.assert_frame_equal(pd.read_csv(out), engine_df)


def test_connection_endpoints(api, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(server.app, base_url="http://127.0.0.1:8765")
    assert client.put("/api/connections", json={"name": "Weather", "key": KEY}).status_code == 200
    keys = {k["name"]: k for k in client.get("/api/connections").json()["keys"]}
    assert keys["weather"]["saved"] and KEY not in json.dumps(keys)
    assert client.put("/api/connections", json={"name": "bad name", "key": KEY}).status_code == 400
    client.delete("/api/connections/weather")
    assert "weather" not in {k["name"] for k in client.get("/api/connections").json()["keys"]}
    server.projects.current = ROOT
