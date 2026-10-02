"""AlphaHound HTTP / WebSocket API: CPS, details, dose log (JSON + CSV), probe, connect errors."""
import csv
import io
import logging

import pytest
from fastapi.testclient import TestClient

import main
from alphahound_serial import device as dev

CPS = {"gamma": 5.0, "beta": 1.5, "alpha": 0.5, "dose": 12.5, "total": 7.0, "age_s": 0.3}


@pytest.fixture
def client():
    logging.disable(logging.CRITICAL)
    yield TestClient(main.app)
    logging.disable(logging.NOTSET)


@pytest.fixture
def connected(monkeypatch):
    monkeypatch.setattr(dev, "is_connected", lambda: True)
    monkeypatch.setattr(dev, "get_dose_rate", lambda: 50.0)
    monkeypatch.setattr(dev, "get_temperature", lambda: 29.5)
    monkeypatch.setattr(dev, "get_comp_factor", lambda: 0.95)
    monkeypatch.setattr(dev, "get_cps", lambda *a, **k: dict(CPS))
    monkeypatch.setattr(dev, "port", "COM8")
    monkeypatch.setattr(dev, "baudrate", 115200)
    return dev


def test_status_disconnected_has_null_cps(client, monkeypatch):
    monkeypatch.setattr(dev, "is_connected", lambda: False)
    body = client.get("/device/status").json()
    assert body["connected"] is False and body["cps"] is None and body["dose_rate"] is None


def test_status_connected_keeps_existing_fields_and_adds_cps(client, connected):
    body = client.get("/device/status").json()
    assert body["connected"] is True
    assert body["dose_rate"] == 50.0 and body["temperature"] == 29.5 and body["comp_factor"] == 0.95
    assert body["cps"]["gamma"] == 5.0 and body["cps"]["total"] == 7.0


def test_cps_endpoint(client, connected, monkeypatch):
    assert client.get("/device/cps").json()["cps"]["beta"] == 1.5
    monkeypatch.setattr(dev, "is_connected", lambda: False)
    assert client.get("/device/cps").status_code == 400


def test_details_endpoint(client, connected, monkeypatch):
    monkeypatch.setattr(dev, "get_dose_log", lambda: [{"time": 1.0, "dose_rate": 1.0}] * 3)
    d = client.get("/device/details").json()
    assert d["port"] == "COM8" and d["baudrate"] == 115200
    assert d["dose_rate_uRem_h"] == 50.0 and d["dose_rate_uSv_h"] == pytest.approx(0.5)
    assert d["temperature"] == 29.5 and d["comp_factor"] == 0.95 and d["dose_log_entries"] == 3
    assert d["cps"]["alpha"] == 0.5 and d["cps_polling"] is True
    monkeypatch.setattr(dev, "is_connected", lambda: False)
    assert client.get("/device/details").status_code == 400


def test_existing_endpoints_still_present(client, connected, monkeypatch):
    assert client.get("/device/dose").json() == {"dose_rate": 50.0}
    sent = []
    monkeypatch.setattr(dev, "send_command", sent.append)
    assert client.post("/device/display/next").json()["action"] == "display_next"
    assert client.post("/device/display/prev").json()["action"] == "display_prev"
    assert sent == ["E", "Q"]
    cleared = []
    monkeypatch.setattr(dev, "clear_spectrum", lambda: cleared.append(1))
    assert client.post("/device/clear").json()["action"] == "spectrum_cleared" and cleared


ROWS = [
    {"time": 1759419600.123, "dose_rate": 50.0, "gamma": 5.0, "beta": 1.5, "alpha": 0.5},
    {"time": 1759419601.5, "dose_rate": 61.25, "gamma": None, "beta": None, "alpha": None},
]


def test_dose_log_json_and_limit(client, monkeypatch):
    monkeypatch.setattr(dev, "get_dose_log", lambda: list(ROWS))
    assert client.get("/device/dose/log").json()["count"] == 2
    one = client.get("/device/dose/log?limit=1").json()
    assert one["count"] == 1 and one["entries"][0]["dose_rate"] == 61.25


def test_dose_log_csv_format(client, monkeypatch):
    monkeypatch.setattr(dev, "get_dose_log", lambda: list(ROWS))
    r = client.get("/device/dose/log.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"] and ".csv" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["Timestamp (UTC)", "Dose Rate (uRem/hr)", "Dose Rate (uSv/hr)", "Gamma CPS", "Beta CPS", "Alpha CPS"]
    assert rows[1] == ["2025-10-02T15:40:00.123Z", "50", "0.5", "5", "1.5", "0.5"]
    assert rows[2][1] == "61.25" and rows[2][2] == "0.6125" and rows[2][3:] == ["", "", ""]


def test_dose_log_csv_empty_has_header_only(client, monkeypatch):
    monkeypatch.setattr(dev, "get_dose_log", lambda: [])
    assert client.get("/device/dose/log.csv").text.count("\n") == 1


def test_dose_log_clear(client, monkeypatch):
    monkeypatch.setattr(dev, "clear_dose_log", lambda: 7)
    assert client.post("/device/dose/log/clear").json() == {"status": "ok", "cleared": 7}


def test_probe_ok_and_validation(client, connected, monkeypatch):
    monkeypatch.setattr(dev, "probe", lambda cmd: ["10.96"] if cmd == "D" else [])
    assert client.post("/device/probe", json={"command": "D"}).json() == {"command": "D", "lines": ["10.96"]}
    for bad in ("W", "A", "G", "d", "", "DBX"):
        assert client.post("/device/probe", json={"command": bad}).status_code == 422, bad


def test_probe_requires_connection(client, monkeypatch):
    monkeypatch.setattr(dev, "is_connected", lambda: False)
    assert client.post("/device/probe", json={"command": "D"}).status_code == 400


def test_connect_failure_codes_and_messages(client, monkeypatch):
    monkeypatch.setattr(dev, "is_connected", lambda: False)
    monkeypatch.setattr(dev, "connect", lambda port: False)
    monkeypatch.setattr(dev, "port_busy", True)
    monkeypatch.setattr(dev, "last_error", "Port COM8 is in use by another program")
    r = client.post("/device/connect", json={"port": "COM8"})
    assert r.status_code == 409 and "in use" in r.json()["detail"]
    monkeypatch.setattr(dev, "port_busy", False)
    monkeypatch.setattr(dev, "last_error", "Could not open COM8: nope")
    r = client.post("/device/connect", json={"port": "COM8"})
    assert r.status_code == 500 and "nope" in r.json()["detail"]
    monkeypatch.setattr(dev, "last_error", None)
    assert client.post("/device/connect", json={"port": "COM8"}).json()["detail"] == "Failed to connect to device"
    monkeypatch.setattr(dev, "connect", lambda port: True)
    assert client.post("/device/connect", json={"port": "COM8"}).json()["status"] == "connected"


def test_websocket_message_has_dose_and_cps(client, connected, monkeypatch):
    monkeypatch.setattr(main, "WS_DISCONNECT_GRACE_S", 0)
    monkeypatch.setattr(dev, "disconnect", lambda: None)
    with client.websocket_connect("/ws/dose") as ws:
        msg = ws.receive_json()
    assert msg["dose_rate"] == 50.0 and msg["cps"]["gamma"] == 5.0


def test_websocket_disconnected_message_unchanged(client, monkeypatch):
    monkeypatch.setattr(main, "WS_DISCONNECT_GRACE_S", 0)
    monkeypatch.setattr(dev, "is_connected", lambda: False)
    with client.websocket_connect("/ws/dose") as ws:
        msg = ws.receive_json()
    assert msg == {"dose_rate": None, "status": "disconnected"}


# ---------- unattended operation (opt-in) ----------

def test_autoconnect_retries_until_the_port_is_free(monkeypatch):
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    results = iter([False, False, True])
    attempts = []
    monkeypatch.setattr(dev, "is_connected", lambda: False)
    monkeypatch.setattr(dev, "connect", lambda port: attempts.append(port) or next(results))
    monkeypatch.setattr(dev, "get_last_error", lambda: "busy")
    assert main.autoconnect_alphahound("COM8", attempts=5, delay_s=0) is True
    assert attempts == ["COM8", "COM8", "COM8"]


def test_autoconnect_gives_up_and_skips_when_already_connected(monkeypatch):
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    monkeypatch.setattr(dev, "is_connected", lambda: False)
    monkeypatch.setattr(dev, "connect", lambda port: False)
    monkeypatch.setattr(dev, "get_last_error", lambda: "busy")
    assert main.autoconnect_alphahound("COM8", attempts=3, delay_s=0) is False
    called = []
    monkeypatch.setattr(dev, "is_connected", lambda: True)
    monkeypatch.setattr(dev, "connect", lambda port: called.append(1) or True)
    assert main.autoconnect_alphahound("COM8") is True and not called


class _LeavingSocket:
    """A websocket that accepts, delivers one message, then fails like a closed browser tab."""

    def __init__(self):
        self.sent = []

    async def accept(self):
        pass

    async def send_json(self, data):
        if self.sent:
            raise RuntimeError("client went away")
        self.sent.append(data)

    async def close(self):
        pass


@pytest.mark.parametrize("keep,expect_release", [(True, False), (False, True)])
def test_last_client_leaving_releases_the_device_unless_keep_connected(connected, monkeypatch, keep, expect_release):
    import asyncio
    monkeypatch.setattr(main, "WS_DISCONNECT_GRACE_S", 0)
    monkeypatch.setattr(main, "KEEP_CONNECTED", keep)
    released = []
    monkeypatch.setattr(dev, "disconnect", lambda: released.append(1))
    main.active_websockets.clear()
    ws = _LeavingSocket()
    asyncio.run(main.websocket_dose_stream(ws))
    assert ws.sent and ws.sent[0]["dose_rate"] == 50.0
    assert bool(released) is expect_release
