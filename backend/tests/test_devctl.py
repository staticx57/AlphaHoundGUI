"""devctl: port choice, connect retries, state handling, restart sequencing (no real server or device)."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import devctl  # noqa: E402


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(devctl, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(devctl.time, "sleep", lambda s: None)


def fake_call(responses):
    """responses: {(method, path): [ (status, body), ... ]}: each call pops the next, the last repeats."""
    calls = []

    def _call(method, path, body=None, timeout=10):
        calls.append((method, path, body))
        seq = responses.get((method, path))
        if seq is None:
            return None, None
        return seq.pop(0) if len(seq) > 1 else seq[0]
    _call.calls = calls
    return _call


PORTS = (200, {"ports": [
    {"device": "COM5", "description": "Standard Serial over Bluetooth link (COM5)"},
    {"device": "COM3", "description": "Intel(R) Active Management Technology - SOL (COM3)"},
    {"device": "COM8", "description": "USB Serial Device (COM8)"}]})


def test_pick_port_explicit_remembered_and_detected(monkeypatch):
    monkeypatch.setattr(devctl, "call", fake_call({("GET", "/device/ports"): [PORTS]}))
    assert devctl.pick_port("COM1") == "COM1"
    assert devctl.pick_port(None) == "COM8"                      # the only USB serial device
    devctl.save_state(alphahound_port="COM5")
    assert devctl.pick_port(None) == "COM5"                      # remembered and still present
    devctl.save_state(alphahound_port="COM99")
    assert devctl.pick_port(None) == "COM8"                      # remembered port vanished


def test_pick_port_refuses_to_guess(monkeypatch):
    two_usb = (200, {"ports": [{"device": "COM8", "description": "USB Serial Device (COM8)"},
                               {"device": "COM9", "description": "USB Serial Device (COM9)"}]})
    monkeypatch.setattr(devctl, "call", fake_call({("GET", "/device/ports"): [two_usb]}))
    with pytest.raises(SystemExit):
        devctl.pick_port(None)


def test_state_round_trip_and_corruption(tmp_path):
    assert devctl.load_state() == {}
    devctl.save_state(alphahound_port="COM8")
    devctl.save_state(radiacode_mac="AA:BB")
    assert devctl.load_state() == {"alphahound_port": "COM8", "radiacode_mac": "AA:BB"}
    devctl.STATE_FILE.write_text("{not json", encoding="utf-8")
    assert devctl.load_state() == {}


def test_connect_retries_while_the_port_is_busy(monkeypatch):
    ready = (200, {"connected": True, "dose_rate": 70.0, "temperature": 29.5})
    c = fake_call({
        ("GET", "/device/status"): [(200, {"connected": False}), (200, {"connected": False}), ready],
        ("POST", "/device/connect"): [(409, {"detail": "Port COM8 is in use"}), (409, {"detail": "in use"}),
                                      (200, {"status": "connected"})],
        ("GET", "/device/details"): [(200, {"cps": {"gamma": 5}})],
    })
    monkeypatch.setattr(devctl, "call", c)
    assert devctl.connect_alphahound("COM8", wait=30) is True
    assert [x for x in c.calls if x[1] == "/device/connect"].__len__() == 3
    assert devctl.load_state()["alphahound_port"] == "COM8"


def test_connect_gives_up_after_the_deadline(monkeypatch):
    clock = iter(range(0, 1000, 10))
    monkeypatch.setattr(devctl.time, "time", lambda: next(clock))
    monkeypatch.setattr(devctl, "call", fake_call({
        ("GET", "/device/status"): [(200, {"connected": False})],
        ("POST", "/device/connect"): [(409, {"detail": "in use"})],
    }))
    assert devctl.connect_alphahound("COM8", wait=25) is False


def test_connect_is_a_noop_when_already_connected(monkeypatch):
    c = fake_call({("GET", "/device/status"): [(200, {"connected": True})]})
    monkeypatch.setattr(devctl, "call", c)
    assert devctl.connect_alphahound("COM8") is True
    assert not [x for x in c.calls if x[0] == "POST"]


def test_connect_reports_unreachable_server(monkeypatch):
    monkeypatch.setattr(devctl, "call", lambda *a, **k: (None, None))
    assert devctl.connect_alphahound("COM8") is False


def test_disconnect(monkeypatch):
    monkeypatch.setattr(devctl, "call", fake_call({
        ("POST", "/device/disconnect"): [(200, {"status": "disconnected"})],
        ("GET", "/device/status"): [(200, {"connected": False})]}))
    assert devctl.disconnect_alphahound() is True


def test_probe_command(monkeypatch, capsys):
    monkeypatch.setattr(devctl, "call", fake_call({("POST", "/device/probe"): [(200, {"command": "D", "lines": ["10.96"]})]}))
    assert devctl.main(["probe", "D"]) == 0
    assert "10.96" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        devctl.main(["probe", "W"])                                # not a whitelisted command


def test_restart_sequence_and_reconnect(monkeypatch):
    order = []
    state = {"connected": True}
    monkeypatch.setattr(devctl, "alphahound_status", lambda: {"connected": state["connected"]})
    monkeypatch.setattr(devctl, "radiacode_connected", lambda: False)
    monkeypatch.setattr(devctl, "call", fake_call({("GET", "/device/details"): [(200, {"port": "COM8"})]}))
    monkeypatch.setattr(devctl, "stop_server", lambda: order.append("stop") or True)
    monkeypatch.setattr(devctl, "start_server", lambda log, *a, **k: order.append("start") or True)
    monkeypatch.setattr(devctl, "connect_alphahound", lambda port, wait: order.append(f"connect:{port}") or True)
    assert devctl.main(["restart"]) == 0
    assert order == ["stop", "start", "connect:None"]
    assert devctl.load_state()["alphahound_port"] == "COM8"      # remembered before the old server was killed


def test_restart_does_not_connect_a_device_that_was_not_connected(monkeypatch):
    order = []
    monkeypatch.setattr(devctl, "alphahound_status", lambda: {"connected": False})
    monkeypatch.setattr(devctl, "radiacode_connected", lambda: False)
    monkeypatch.setattr(devctl, "stop_server", lambda: True)
    monkeypatch.setattr(devctl, "start_server", lambda log, *a, **k: True)
    monkeypatch.setattr(devctl, "connect_alphahound", lambda port, wait: order.append("connect") or True)
    assert devctl.main(["restart"]) == 0 and order == []
    assert devctl.main(["restart", "--always-connect"]) == 0 and order == ["connect"]
    order.clear()
    assert devctl.main(["restart", "--always-connect", "--no-reconnect"]) == 0 and order == []


def test_restart_fails_if_the_server_will_not_stop_or_start(monkeypatch):
    monkeypatch.setattr(devctl, "alphahound_status", lambda: {"connected": False})
    monkeypatch.setattr(devctl, "radiacode_connected", lambda: False)
    monkeypatch.setattr(devctl, "stop_server", lambda: False)
    assert devctl.main(["restart"]) == 1
    monkeypatch.setattr(devctl, "stop_server", lambda: True)
    monkeypatch.setattr(devctl, "start_server", lambda log, *a, **k: False)
    assert devctl.main(["restart"]) == 1


def test_ensure_starts_a_down_server_then_connects(monkeypatch):
    order = []
    monkeypatch.setattr(devctl, "server_up", lambda: False)
    monkeypatch.setattr(devctl, "start_server", lambda log, *a, **k: order.append("start") or True)
    monkeypatch.setattr(devctl, "connect_alphahound", lambda port, wait: order.append("connect") or True)
    assert devctl.main(["ensure"]) == 0 and order == ["start", "connect"]


def test_radiacode_connect_uses_saved_mac(monkeypatch):
    devctl.save_state(radiacode_mac="52:43:06:E0:06:39")
    c = fake_call({("GET", "/radiacode/status"): [(200, {"connected": False})],
                   ("POST", "/radiacode/connect"): [(200, {"status": "connected"})]})
    monkeypatch.setattr(devctl, "call", c)
    assert devctl.main(["rc-connect"]) == 0
    post = [x for x in c.calls if x[0] == "POST"][0]
    assert post[2] == {"use_bluetooth": True, "bluetooth_mac": "52:43:06:E0:06:39"}


def test_listening_pids_parses_windows_netstat(monkeypatch):
    out = ("  Proto  Local Address          Foreign Address        State           PID\n"
           "  TCP    0.0.0.0:3200           0.0.0.0:0              LISTENING       33916\n"
           "  TCP    127.0.0.1:3200         127.0.0.1:61921        ESTABLISHED     33916\n"
           "  TCP    0.0.0.0:32000          0.0.0.0:0              LISTENING       999\n"
           "  TCP    127.0.0.1:61921        127.0.0.1:3200         ESTABLISHED     28272\n")

    class R:
        stdout = out
    monkeypatch.setattr(devctl.os, "name", "nt")
    monkeypatch.setattr(devctl.subprocess, "run", lambda *a, **k: R())
    assert devctl.listening_pids(3200) == {33916}               # not the :32000 listener, not the clients


def test_start_server_enables_the_watchdog_only_when_given_a_port(monkeypatch, tmp_path):
    envs = []

    class FakeProc:
        pid = 1234

    monkeypatch.setattr(devctl.subprocess, "Popen", lambda *a, **k: envs.append(k["env"]) or FakeProc())
    monkeypatch.setattr(devctl, "wait_for", lambda cond, timeout, interval=0.5: True)
    for key in ("ALPHAHOUND_AUTOCONNECT_PORT", "ALPHAHOUND_AUTORECONNECT"):
        monkeypatch.delenv(key, raising=False)
    assert devctl.start_server(tmp_path / "a.log", "COM8")
    assert envs[0]["ALPHAHOUND_AUTOCONNECT_PORT"] == "COM8" and envs[0]["ALPHAHOUND_AUTORECONNECT"] == "1"
    assert envs[0]["ALPHAHOUND_KEEP_CONNECTED"] == "1"
    assert devctl.start_server(tmp_path / "b.log")
    assert "ALPHAHOUND_AUTOCONNECT_PORT" not in envs[1] and "ALPHAHOUND_AUTORECONNECT" not in envs[1]


def test_restart_hands_the_port_to_the_server(monkeypatch):
    passed = []
    monkeypatch.setattr(devctl, "alphahound_status", lambda: {"connected": True})
    monkeypatch.setattr(devctl, "radiacode_connected", lambda: False)
    monkeypatch.setattr(devctl, "call", fake_call({("GET", "/device/details"): [(200, {"port": "COM8"})],
                                                  ("GET", "/device/ports"): [PORTS]}))
    monkeypatch.setattr(devctl, "stop_server", lambda: True)
    monkeypatch.setattr(devctl, "start_server", lambda log, port=None: passed.append(port) or True)
    monkeypatch.setattr(devctl, "connect_alphahound", lambda port, wait: True)
    assert devctl.main(["restart"]) == 0
    assert passed == ["COM8"]
    passed.clear()
    assert devctl.main(["restart", "--no-reconnect"]) == 0 and passed == [None]


def test_status_shows_link_health_and_a_deliberate_disconnect(monkeypatch, capsys):
    monkeypatch.setattr(devctl, "server_up", lambda: True)
    monkeypatch.setattr(devctl, "radiacode_connected", lambda: False)
    monkeypatch.setattr(devctl, "alphahound_status", lambda: {"connected": True, "dose_rate": 60.0, "temperature": 29.0, "cps": None})
    monkeypatch.setattr(devctl, "call", fake_call({("GET", "/device/health"): [(200, {"port": "COM8", "data_age_s": 42.0,
                                                                                    "connected_for_s": 100.0})]}))
    assert devctl.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "last data 42.0s ago" in out and "no data for a while" in out
    monkeypatch.setattr(devctl, "alphahound_status", lambda: {"connected": False})
    monkeypatch.setattr(devctl, "call", fake_call({("GET", "/device/health"): [(200, {"user_disconnected": True})]}))
    devctl.main(["status"])
    assert "disconnected on purpose" in capsys.readouterr().out
