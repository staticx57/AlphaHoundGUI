"""The server has no login, so what it must not do is act for a web page that is not its own, write an unusable
calibration to a device, or store a custom isotope name that carries markup."""
import json
import os
import re
import sys

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import main
from main import app, origin_allowed
from nuclides import isotope_database as db
from routers import device_radiacode as rc

client = TestClient(app)
BACKEND = os.path.join(os.path.dirname(__file__), '..')


# ---- requests from other web pages

@pytest.mark.parametrize("origin, host, allowed", [
    (None, "localhost:3200", True),                                   # curl, devctl, the tests: not a web page
    ("http://localhost:3200", "localhost:3200", True),
    ("http://127.0.0.1:3200", "127.0.0.1:3200", True),
    ("http://192.168.1.152:3200", "192.168.1.152:3200", True),        # a phone on the LAN
    ("http://[::1]:3200", "[::1]:3200", True),
    ("http://LOCALHOST:3200", "localhost:3200", True),
    ("http://evil.example", "localhost:3200", False),                 # another site's page
    ("http://localhost:8000", "localhost:3200", False),               # another server on this machine
    ("http://127.0.0.1:3200", "localhost:3200", False),               # not the address the page was opened at
    ("http://evil.example:3200", "evil.example:3200", False),         # DNS rebinding: its own name, pointed here
    ("null", "localhost:3200", False),                                # a sandboxed frame or a file:// page
    ("", "localhost:3200", False),
    ("http://localhost:3200", None, False),
])
def test_only_the_servers_own_pages_may_change_anything(origin, host, allowed):
    assert origin_allowed(origin, host) is allowed


def test_this_computers_name_and_a_configured_name_count_as_the_server(monkeypatch):
    monkeypatch.setattr(main, "_OWN_HOSTNAMES", {"localhost", "bench-pc", "spectra.lan"})
    assert origin_allowed("http://bench-pc:3200", "bench-pc:3200")
    assert origin_allowed("http://spectra.lan:3200", "spectra.lan:3200")
    assert not origin_allowed("http://other-pc:3200", "other-pc:3200")


def test_an_origin_listed_for_cors_is_allowed(monkeypatch):
    monkeypatch.setattr(main, "_cors_origins", ["http://frontend.example:3000"])
    assert origin_allowed("http://frontend.example:3000", "localhost:3200")


@pytest.mark.parametrize("path", [
    "/device/clear", "/device/disconnect", "/device/acquisition/stop", "/device/dose/log/clear",
    "/radiacode/power/off", "/radiacode/reset-dose", "/radiacode/clear", "/radiacode/settings/brightness?level=0",
])
def test_another_sites_page_cannot_reach_a_route_that_changes_something(path):
    response = client.post(path, headers={"Origin": "http://evil.example", "Host": "localhost:3200"})
    assert response.status_code == 403
    assert "another web page" in response.json()["detail"]


def test_a_rebound_name_is_refused_although_origin_and_host_agree():
    headers = {"Origin": "http://evil.example:3200", "Host": "evil.example:3200"}
    assert client.post("/device/dose/log/clear", headers=headers).status_code == 403


def test_the_apps_own_page_and_a_plain_client_are_served():
    own = {"Origin": "http://localhost:3200", "Host": "localhost:3200"}
    assert client.post("/device/clear", headers=own).status_code == 400          # reached the route: no device
    assert client.post("/device/clear").status_code == 400
    lan = {"Origin": "http://192.168.1.152:3200", "Host": "192.168.1.152:3200"}
    assert client.post("/device/clear", headers=lan).status_code == 400


def test_reading_is_not_restricted():
    assert client.get("/isotopes/custom", headers={"Origin": "http://evil.example"}).status_code == 200


def test_the_dose_socket_refuses_another_sites_page():
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/dose", headers={"Origin": "http://evil.example", "Host": "localhost:3200"}):
            pass


def test_the_dose_socket_serves_the_apps_own_page():
    with client.websocket_connect("/ws/dose", headers={"Origin": "http://localhost:3200", "Host": "localhost:3200"}) as ws:
        assert "dose_rate" in ws.receive_json()


def test_no_rate_limiter_is_declared_that_limits_nothing():
    """A Limiter was created and never applied to a route; the documents called it a security feature."""
    source = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
    assert "slowapi" not in source
    assert "slowapi" not in open(os.path.join(BACKEND, "requirements.txt"), encoding="utf-8").read()


# ---- Radiacode energy calibration (written to the device)

class FakeCalibrationDevice:
    def __init__(self):
        self.written = []

    def is_connected(self):
        return True

    def set_energy_calibration(self, a0, a1, a2):
        self.written.append((a0, a1, a2))
        return True

    def get_last_error(self):
        return None


@pytest.fixture
def calibration_device(monkeypatch):
    fake = FakeCalibrationDevice()
    monkeypatch.setattr(rc, "radiacode_device", fake)
    return fake


def test_a_usable_calibration_reaches_the_device(calibration_device):
    response = client.post("/radiacode/calibration/energy", json={"a0": -5.2, "a1": 2.37, "a2": 0.00041})
    assert response.status_code == 200
    assert calibration_device.written == [(-5.2, 2.37, 0.00041)]


@pytest.mark.parametrize("body", [
    '{"a0": 0, "a1": 1e9, "a2": 0}',            # absurd gain
    '{"a0": 0, "a1": NaN, "a2": 0}',
    '{"a0": 0, "a1": 2.4, "a2": Infinity}',
    '{"a0": 5000, "a1": 2.4, "a2": 0}',
    '{"a0": 0, "a1": 0, "a2": 0}',              # every channel at the same energy
    '{"a0": 0, "a1": 2.4, "a2": -0.004}',       # the energy falls again before the last channel
    '{"a0": 0, "a1": 2.4}',
])
def test_an_unusable_calibration_never_reaches_the_device(calibration_device, body):
    response = client.post("/radiacode/calibration/energy", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert calibration_device.written == []


def test_the_calibration_is_not_taken_from_the_address(calibration_device):
    """Query parameters made this a request any web page could send without asking."""
    assert client.post("/radiacode/calibration/energy?a0=0&a1=2.4&a2=0").status_code == 422
    assert calibration_device.written == []


def test_the_page_sends_the_calibration_as_json():
    source = open(os.path.join(BACKEND, "static", "js", "api.js"), encoding="utf-8").read()
    assert "calibration/energy?" not in source
    assert "JSON.stringify({ a0, a1, a2 })" in source


# ---- custom isotopes

@pytest.fixture
def isotope_file(tmp_path, monkeypatch):
    path = tmp_path / "data" / "custom_isotopes.json"
    monkeypatch.setattr(db, "CUSTOM_ISOTOPES_FILE", str(path))
    monkeypatch.setattr(db, "_LEGACY_CUSTOM_ISOTOPES_FILES", ())
    return path


def test_the_list_is_kept_in_backend_data_wherever_the_server_was_started():
    assert os.path.isabs(db.CUSTOM_ISOTOPES_FILE)
    assert os.path.normpath(db.CUSTOM_ISOTOPES_FILE) == os.path.normpath(
        os.path.join(os.path.abspath(BACKEND), "data", "custom_isotopes.json"))


def test_a_custom_isotope_is_stored_listed_and_deleted(isotope_file):
    assert client.post("/isotopes/custom", json={"name": " My source (lab) ", "energies": [661.7, 1332]}).json()["name"] \
        == "My source (lab)"
    assert json.loads(isotope_file.read_text(encoding="utf-8")) == {"My source (lab)": [661.7, 1332.0]}
    assert client.get("/isotopes/custom").json() == {"My source (lab)": [661.7, 1332.0]}
    assert client.delete("/isotopes/custom/My%20source%20(lab)").status_code == 200
    assert client.get("/isotopes/custom").json() == {}
    assert not os.path.exists(str(isotope_file) + ".tmp")


@pytest.mark.parametrize("name", [
    "<img src=x onerror=alert(1)>", 'a"b', "a'b", "x&y", "a/b", "tab\there", "", "   ", "n" * 65,
])
def test_a_name_that_could_carry_markup_is_refused(isotope_file, name):
    response = client.post("/isotopes/custom", json={"name": name, "energies": [100.0]})
    assert response.status_code == 400
    assert not isotope_file.exists()


@pytest.mark.parametrize("energies", [[], [0], [-5], [1e9], [100.0] * 51])
def test_energies_must_be_usable(isotope_file, energies):
    assert client.post("/isotopes/custom", json={"name": "X-1", "energies": energies}).status_code == 400
    assert not isotope_file.exists()


def test_an_imported_file_keeps_its_good_entries_and_names_the_rest(isotope_file):
    body = client.post("/isotopes/custom/import", json={
        "Good-1": [100, 200.5],
        "<script>alert(1)</script>": [300],
        "Bad energies": ["not a number"],
        "Also good": [511],
    }).json()
    assert body["imported"] == 2
    assert [s["name"] for s in body["skipped"]] == ["<script>alert(1)</script>", "Bad energies"]
    assert set(client.get("/isotopes/custom").json()) == {"Good-1", "Also good"}


def test_a_list_left_where_the_old_code_wrote_it_is_carried_over(tmp_path, monkeypatch):
    old = tmp_path / "custom_isotopes.json"
    old.write_text('{"Old-1": [123.4]}', encoding="utf-8")
    new = tmp_path / "data" / "custom_isotopes.json"
    monkeypatch.setattr(db, "CUSTOM_ISOTOPES_FILE", str(new))
    monkeypatch.setattr(db, "_LEGACY_CUSTOM_ISOTOPES_FILES", (str(old),))
    assert db.load_custom_isotopes() == {"Old-1": [123.4]}
    assert new.exists() and old.exists()


def test_a_damaged_list_reads_as_empty(isotope_file):
    isotope_file.parent.mkdir(parents=True)
    isotope_file.write_text("[1, 2", encoding="utf-8")
    assert db.load_custom_isotopes() == {}
    isotope_file.write_text("[1, 2]", encoding="utf-8")
    assert db.load_custom_isotopes() == {}


def test_names_from_the_server_and_from_history_are_escaped_in_the_page():
    js = os.path.join(BACKEND, "static", "js")
    ui = open(os.path.join(js, "ui.js"), encoding="utf-8").read()
    history = open(os.path.join(js, "settings_history.js"), encoding="utf-8").read()
    for raw in ("${iso.isotope}", "${chain.chain_name}", "<strong>${isotope}</strong>", "${iso.series_basis}"):
        assert raw not in ui, raw
    assert "${item.filename}</div>" not in history
    assert re.search(r"isotopes/custom/\$\{encodeURIComponent\(name\)\}",
                     open(os.path.join(js, "isotopes_ui.js"), encoding="utf-8").read())


# ---- upload size

def test_a_file_beyond_the_limit_is_refused():
    from routers.analysis import MAX_FILE_SIZE_MB
    big = b"0," * (MAX_FILE_SIZE_MB * 1024 * 1024 // 2 + 1024)
    response = client.post("/upload", files={"file": ("big.csv", big, "text/csv")})
    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower()
