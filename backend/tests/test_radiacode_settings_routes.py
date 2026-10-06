"""
The Radiacode device-settings routes (routers/device_radiacode.py), against a fake driver that records what it is asked: display
brightness, sound, vibration, display-off time and language (single and batched), the capabilities that gate the panel, the extended
info (accumulated dose, device configuration) and the alarm limits. The hardware itself is checked by hand (TODO, Pending Manual
Verification); this is the contract the panel in the page relies on.
"""
import pytest
from fastapi.testclient import TestClient

from main import app
from routers import device_radiacode as rc


class FakeRadiacode:
    UR_PER_USV = 100.0
    is_available = True
    is_ble_available = True

    def __init__(self, connected=True, accept=True):
        self.connected, self.accept = connected, accept
        self.calls = []
        self.error = None

    def is_connected(self):
        return self.connected

    def _set(self, name, value):
        self.calls.append((name, value))
        if not self.accept:
            self.error = f"device refused {name}"
        return self.accept

    def set_brightness(self, level):
        return self._set("brightness", level)

    def set_sound(self, enabled):
        return self._set("sound", enabled)

    def set_vibration(self, enabled):
        return self._set("vibration", enabled)

    def set_display_off_time(self, seconds):
        return self._set("display_off_time", seconds)

    def set_language(self, language):
        return self._set("language", language)

    def get_last_error(self):
        return self.error

    def get_device_info(self):
        return {"serial_number": "RC-110-0001", "firmware_version": "4.14", "model": "RadiaCode-110"}

    def read_dose_register_uR(self):
        return 250.0

    def get_accumulated_dose(self):
        return 9.9

    def get_accumulated_dose_raw(self):
        return 250.0

    def get_session_dose(self):
        return 1.5

    def get_dose_counter_info(self):
        return {"counter": 7}

    def get_configuration(self):
        return "NOTIFY=1\nLANG=en\n"

    def get_alarm_limits(self):
        return {"l1_cps": 100, "l2_cps": 200, "dose_rate_l1_uSv_h": 0.5} if self.accept else None


@pytest.fixture
def device(monkeypatch):
    fake = FakeRadiacode()
    monkeypatch.setattr(rc, "radiacode_device", fake)
    return fake


client = TestClient(app)

SINGLE = [
    ("/radiacode/settings/brightness?level=7", ("brightness", 7), {"status": "success", "brightness": 7}),
    ("/radiacode/settings/sound?enabled=true", ("sound", True), {"status": "success", "sound_enabled": True}),
    ("/radiacode/settings/vibration?enabled=false", ("vibration", False), {"status": "success", "vibration_enabled": False}),
    ("/radiacode/settings/display-timeout?seconds=30", ("display_off_time", 30), {"status": "success", "timeout_seconds": 30}),
    ("/radiacode/settings/language?language=ru", ("language", "ru"), {"status": "success", "language": "ru"}),
]


@pytest.mark.parametrize("url, call, body", SINGLE)
def test_each_setting_reaches_the_device_and_reports_it(device, url, call, body):
    response = client.post(url)
    assert response.status_code == 200 and response.json() == body
    assert device.calls == [call]


@pytest.mark.parametrize("url, call, body", SINGLE)
def test_a_setting_is_refused_without_a_connected_device_and_never_sent(device, url, call, body):
    device.connected = False
    response = client.post(url)
    assert response.status_code == 400 and "not connected" in response.json()["detail"]
    assert device.calls == []


@pytest.mark.parametrize("url, call, body", SINGLE)
def test_a_setting_the_device_refuses_is_an_error_with_the_devices_own_message(device, url, call, body):
    device.accept = False
    response = client.post(url)
    assert response.status_code == 500 and "device refused" in response.json()["detail"]


def test_batched_settings_send_only_what_was_given(device):
    response = client.post("/radiacode/settings", json={"brightness": 3, "sound": False})
    assert response.status_code == 200 and response.json() == {"status": "success", "results": {"brightness": True, "sound": True}}
    assert device.calls == [("brightness", 3), ("sound", False)]


def test_batched_settings_name_the_ones_that_failed(device):
    device.accept = False
    body = client.post("/radiacode/settings", json={"vibration": True, "display_off_time": 60}).json()
    assert body["status"] == "partial_success" and sorted(body["failed"]) == ["display_off_time", "vibration"]
    assert "device refused" in body["last_error"]


@pytest.mark.parametrize("payload", [{"brightness": 10}, {"brightness": -1}, {"display_off_time": -5}, {"sound": "maybe"}])
def test_batched_settings_validate_their_bounds_before_the_device_is_touched(device, payload):
    assert client.post("/radiacode/settings", json=payload).status_code == 422
    assert device.calls == []


def test_capabilities_say_the_settings_panel_is_available():
    caps = client.get("/radiacode/capabilities").json()
    assert caps["device_type"] == "radiacode" and caps["capabilities"]["deviceSettings"] is True


def test_extended_info_gives_the_accumulated_dose_the_session_dose_and_the_configuration(device):
    """The dose row and the View Configuration button read this."""
    body = client.get("/radiacode/info/extended").json()
    assert body["accumulated_dose_uSv"] == pytest.approx(2.5)          # the register (250 uR) over 100 uR per uSv, not the fallback
    assert body["session_dose"] == 1.5 and body["configuration"].startswith("NOTIFY=1")
    assert body["device_info"]["serial_number"] == "RC-110-0001" and body["device_info"]["firmware_version"] == "4.14"


def test_extended_info_falls_back_when_the_register_is_not_served(device):
    device.read_dose_register_uR = lambda: None
    assert client.get("/radiacode/info/extended").json()["accumulated_dose_uSv"] == 9.9


def test_extended_info_needs_a_connected_device(device):
    device.connected = False
    assert client.get("/radiacode/info/extended").status_code == 400


def test_the_status_carries_the_serial_number_and_firmware_the_panel_shows(device):
    info = client.get("/radiacode/status").json()["device_info"]
    assert info["serial_number"] == "RC-110-0001" and info["firmware_version"] == "4.14"


def test_alarm_limits_are_read_and_an_unavailable_reading_is_an_error(device):
    assert client.get("/radiacode/alarm-limits").json()["l2_cps"] == 200
    device.accept = False
    assert client.get("/radiacode/alarm-limits").status_code == 500
