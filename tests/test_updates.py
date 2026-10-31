import json

import pytest

from snek import __version__, updates


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SNEK_HOME", str(tmp_path))
    return tmp_path


def test_newer_release_is_flagged_and_cached(home):
    calls = []

    def fetch():
        calls.append(1)
        return "v99.0.0", "https://example.test/release"

    first = updates.check(fetch=fetch)
    assert first["update"] and first["latest"] == "v99.0.0" and first["current"] == __version__
    second = updates.check(fetch=fetch)
    assert second["update"] and len(calls) == 1
    assert json.loads((home / "updates.json").read_text())["latest"] == "v99.0.0"


def test_same_or_older_release_is_not_an_update():
    assert not updates.check(fetch=lambda: (f"v{__version__}", "u"))["update"]
    assert not updates.check(force=True, fetch=lambda: ("v0.0.1", "u"))["update"]


def test_disabled_checks_never_fetch_unless_forced():
    updates.set_enabled(False)

    def fail():
        raise AssertionError("should not fetch")

    assert updates.check(fetch=fail)["enabled"] is False
    assert updates.check(force=True, fetch=lambda: ("v99.0.0", "u"))["update"]


def test_network_errors_are_reported_not_raised():
    def boom():
        raise OSError("offline")

    result = updates.check(force=True, fetch=boom)
    assert "offline" in result["error"] and not result["update"]
