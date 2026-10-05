"""
Server startup (the FastAPI lifespan that replaced the deprecated on_event handlers): the dose log is attached and the AlphaHound
auto-connect starts when asked to, and neither happens when switched off.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest                                   # noqa: E402
from fastapi.testclient import TestClient       # noqa: E402

import main                                     # noqa: E402


def wait_until(condition, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def recorder(monkeypatch):
    calls = {"log": [], "connect": [], "watchdog": []}
    monkeypatch.setattr(main.alphahound_device, "enable_log_persistence", lambda path: calls["log"].append(path))
    monkeypatch.setattr(main, "autoconnect_alphahound", lambda port, *a, **k: calls["connect"].append(port))
    monkeypatch.setattr(main, "_watchdog_loop", lambda port: calls["watchdog"].append(port))
    return calls


def test_startup_attaches_the_dose_log_and_starts_autoconnect(recorder, monkeypatch):
    monkeypatch.delenv("ALPHAHOUND_DOSE_LOG", raising=False)
    monkeypatch.setenv("ALPHAHOUND_AUTOCONNECT_PORT", "COM9")
    monkeypatch.setattr(main, "AUTORECONNECT", True)
    with TestClient(main.app) as client:                     # entering the client runs the lifespan
        assert client.get("/detectors").status_code == 200
        assert wait_until(lambda: recorder["connect"] == ["COM9"] and recorder["watchdog"] == ["COM9"])
    assert recorder["log"] == [main.DOSE_LOG_FILE]


def test_startup_respects_the_switches(recorder, monkeypatch):
    monkeypatch.setenv("ALPHAHOUND_DOSE_LOG", "off")
    monkeypatch.setenv("ALPHAHOUND_AUTOCONNECT_PORT", "")
    with TestClient(main.app):
        pass
    time.sleep(0.2)
    assert recorder == {"log": [], "connect": [], "watchdog": []}
    # autoconnect without the watchdog
    monkeypatch.setenv("ALPHAHOUND_AUTOCONNECT_PORT", "COM3")
    monkeypatch.setattr(main, "AUTORECONNECT", False)
    with TestClient(main.app):
        assert wait_until(lambda: recorder["connect"] == ["COM3"])
    assert recorder["watchdog"] == []
    assert not any(t.name == "watchdog" and t.is_alive() for t in threading.enumerate())


def test_startup_keeps_runs_interrupted_by_the_last_shutdown(recorder, monkeypatch):
    kept = []
    monkeypatch.setattr(main, "recover_interrupted_checkpoints", lambda: kept.append(True) or [])
    with TestClient(main.app):
        pass
    assert kept == [True]
