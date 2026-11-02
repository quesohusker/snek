import json
import threading
import time
import urllib.request
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

from snek import connect
from snek.codegen import export_script
from snek.engine import Engine

TOKEN = "fake-token-0123456789"
API = "https://api.github.com"
RESET = int(time.time()) + 600


class FakeGitHub(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def reply(self, code, body, kind="application/json", headers=None):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        self.server.seen.append((url.path, q, dict(self.headers)))
        authed = self.headers.get("Authorization") == f"Bearer {TOKEN}"
        if url.path == "/users/acme/repos":
            if q.get("page") == "2":
                return self.reply(200, [{"name": "c", "full_name": "acme/c", "private": False, "owner": {"login": "acme"}}])
            link = f'<{API}/users/acme/repos?per_page=100&page=2>; rel="next", <{API}/users/acme/repos?per_page=100&page=2>; rel="last"'
            return self.reply(200, [{"name": "a", "full_name": "acme/a", "private": False, "owner": {"login": "acme"}}, {"name": "b", "full_name": "acme/b", "private": False, "owner": {"login": "acme"}}], headers={"Link": link})
        if url.path == "/user/repos":
            if not authed:
                return self.reply(401, {"message": "Requires authentication"})
            return self.reply(200, [{"name": "mine", "full_name": "me/mine", "private": True, "owner": {"login": "me"}}])
        if url.path == "/repos/acme/data/issues":
            return self.reply(200, [
                {"number": 1, "title": "Bug", "state": "open", "user": {"login": "x"}, "labels": [{"name": "bug"}, {"name": "ui"}], "comments": 2, "body": "text"},
                {"number": 2, "title": "Fix", "state": "closed", "user": {"login": "y"}, "labels": [], "comments": 0, "pull_request": {"url": "u"}},
            ])
        if url.path == "/repos/acme/data/commits":
            return self.reply(200, [{"sha": "abc", "commit": {"author": {"name": "Ann", "date": "2026-01-01T00:00:00Z"}, "message": "first"}, "author": {"login": "ann"}}])
        if url.path == "/repos/acme/data/contents/":
            return self.reply(200, [{"name": "a.csv", "path": "a.csv", "type": "file", "size": 8, "sha": "s1", "download_url": "d1"}, {"name": "sub", "path": "sub", "type": "dir", "size": 0, "sha": "s2", "download_url": None}])
        if url.path == "/repos/acme/data/contents/data/games.csv":
            if "raw" not in self.headers.get("Accept", ""):
                return self.reply(200, {"content": "not raw"})
            return self.reply(200, "team,pts\nNebraska,24\nIowa,20\n", "text/plain")
        if url.path == "/repos/acme/limited/commits":
            return self.reply(403, {"message": "API rate limit exceeded"}, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(RESET)})
        if url.path == "/repos/acme/secret/commits":
            return self.reply(200, [{"sha": "z", "commit": {"author": {"name": "A", "date": "d"}, "message": "m"}, "author": {"login": "a"}}]) if authed else self.reply(404, {"message": "Not Found"})
        return self.reply(404, {"message": "Not Found"})


@pytest.fixture
def gh(tmp_path, monkeypatch):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
    httpd.seen = []
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    real = urllib.request.urlopen

    def routed(request, timeout=None):
        assert request.full_url.startswith(API + "/"), request.full_url
        rewritten = urllib.request.Request(base + request.full_url[len(API):], headers=dict(request.header_items()))
        return real(rewritten, timeout=timeout)

    monkeypatch.setattr(urllib.request, "urlopen", routed)
    monkeypatch.setenv("SNEK_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("GITHUB_API_KEY", raising=False)
    yield httpd
    httpd.shutdown()


def run_github(cfg):
    ev = Engine().evaluate({"nodes": [{"id": "1", "type": "github", "config": cfg}], "edges": []}, run_side_effects=True)
    return ev, ev.results["1"]


def test_repositories_follow_pages_and_stop_at_the_limit(gh):
    ev, res = run_github({"what": "repos", "owner": "acme"})
    assert res.status == "ok", res.error
    assert ev.frames[("1", "out")]["name"].tolist() == ["a", "b", "c"]
    assert ev.frames[("1", "out")]["owner.login"].unique().tolist() == ["acme"]
    ev, res = run_github({"what": "repos", "owner": "acme", "limit": 2})
    assert ev.frames[("1", "out")]["name"].tolist() == ["a", "b"]
    assert any("Stopped at 2 rows" in w for w in res.warnings)


def test_no_token_means_no_authorization_header(gh):
    run_github({"what": "repos", "owner": "acme"})
    assert gh.seen and all("Authorization" not in h for _, _, h in gh.seen)


def test_saved_token_goes_in_the_header_and_lists_your_own_repositories(gh):
    _, res = run_github({"what": "repos", "owner": ""})
    assert res.status == "error" and "needs a GitHub token" in res.error
    connect.set_key("github", "wrong-token-0000")
    _, res = run_github({"what": "repos", "owner": ""})
    assert res.status == "error" and "rejected the saved token" in res.error and "wrong-token-0000" not in res.error
    connect.set_key("github", TOKEN)
    ev, res = run_github({"what": "repos", "owner": ""})
    assert res.status == "ok", res.error
    assert ev.frames[("1", "out")]["name"].tolist() == ["mine"]
    assert gh.seen[-1][2]["Authorization"] == f"Bearer {TOKEN}"


def test_issues_label_pull_requests_and_join_labels(gh):
    ev, res = run_github({"what": "issues", "owner": "acme", "repo": "data"})
    assert res.status == "ok", res.error
    df = ev.frames[("1", "out")]
    assert df["is_pull_request"].tolist() == [False, True]
    assert df["labels"].tolist() == ["bug, ui", ""]
    assert df.loc[0, "user.login"] == "x"
    assert gh.seen[-1][1]["state"] == "all"


def test_commits_and_folder_listing(gh):
    ev, res = run_github({"what": "commits", "owner": "acme", "repo": "data", "ref": "dev"})
    assert res.status == "ok", res.error
    assert ev.frames[("1", "out")].loc[0, "commit.author.name"] == "Ann"
    assert gh.seen[-1][1]["sha"] == "dev"
    ev, res = run_github({"what": "files", "owner": "acme", "repo": "data"})
    assert res.status == "ok", res.error
    assert ev.frames[("1", "out")]["type"].tolist() == ["file", "dir"]


def test_data_file_comes_back_as_a_table(gh):
    ev, res = run_github({"what": "file", "owner": "acme", "repo": "data", "path": "data/games.csv"})
    assert res.status == "ok", res.error
    assert ev.frames[("1", "out")].to_dict("list") == {"team": ["Nebraska", "Iowa"], "pts": [24, 20]}
    assert "raw" in gh.seen[-1][2]["Accept"]


def test_plain_messages_for_missing_limited_and_private(gh):
    _, res = run_github({"what": "commits", "owner": "acme", "repo": "nothing"})
    assert res.status == "error" and "could not find" in res.error and "saved GitHub token" in res.error
    _, res = run_github({"what": "commits", "owner": "acme", "repo": "limited"})
    assert res.status == "error" and "rate limit" in res.error and "resets at" in res.error and "Save a GitHub token" in res.error
    _, res = run_github({"what": "commits", "owner": "acme", "repo": "secret"})
    assert res.status == "error"
    connect.set_key("github", TOKEN)
    ev, res = run_github({"what": "commits", "owner": "acme", "repo": "secret"})
    assert res.status == "ok", res.error
    connect.set_key("github", "wrong-token-0000")
    _, res = run_github({"what": "commits", "owner": "acme", "repo": "limited"})
    assert "Save a GitHub token" not in res.error


def test_tool_asks_for_what_it_needs(gh):
    _, res = run_github({"what": "issues", "owner": "acme", "repo": ""})
    assert res.status == "error" and "repository" in res.error
    _, res = run_github({"what": "commits", "owner": "", "repo": "data"})
    assert res.status == "error" and "owner" in res.error
    _, res = run_github({"what": "file", "owner": "acme", "repo": "data", "path": ""})
    assert res.status == "error" and "path" in res.error
    _, res = run_github({"what": "repos", "owner": "", "limit": 0})
    assert res.status == "error"


def test_token_is_declared_and_locked_to_github():
    info = {k["name"]: k for k in connect.list_keys()}
    assert info["github"]["declared"]["section"] == "GitHub"
    assert connect.HOSTS["github"] == "api.github.com"
    with pytest.raises(ValueError, match="only goes to api.github.com"):
        connect.check_host("github", "https://example.com/x")


def test_export_keeps_the_token_out_and_gives_the_same_table(gh, tmp_path, monkeypatch):
    connect.set_key("github", TOKEN)
    out = tmp_path / "issues.csv"
    wf = {
        "nodes": [{"id": "1", "type": "github", "config": {"what": "issues", "owner": "acme", "repo": "data", "state": "closed"}}, {"id": "2", "type": "output", "config": {"path": str(out)}}],
        "edges": [{"source": "1", "sourceHandle": "out", "target": "2", "targetHandle": "in"}],
    }
    ev = Engine().evaluate(wf, run_side_effects=True)
    engine_df = pd.read_csv(out)
    script = export_script(ev)
    assert TOKEN not in script and "github(" in script and "state='closed'" in script
    out.unlink()
    monkeypatch.chdir(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        exec(compile(script, "flow.py", "exec"), {"__name__": "__main__"})
    pd.testing.assert_frame_equal(pd.read_csv(out), engine_df)
    assert gh.seen[-1][1]["state"] == "closed" and gh.seen[-1][2]["Authorization"] == f"Bearer {TOKEN}"
