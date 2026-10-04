"""The instrument's temperature and compensation factor travel with the spectrum (they used to stop at the device panel, so no saved
capture could be matched to the temperature it was taken at)."""
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from devices import acquisition_manager as am
from formats.n42_exporter import generate_n42_xml
from formats.n42_parser import parse_n42
from main import app

CUBIC = (15.0001 + 1.68372 * np.arange(1024) - 4.75865e-05 * np.arange(1024) ** 2 + 5.49654e-06 * np.arange(1024) ** 3).tolist()


@pytest.fixture
def mgr():
    m = am.AcquisitionManager()
    saved = m.state
    m.state = am.AcquisitionState()
    yield m
    m.state = saved


def test_latest_lowest_and_highest_temperature_are_kept(mgr):
    for t in (30.25, 30.125, 31.5, 30.5):
        mgr.record_device_readings(t, 0.95)
    assert mgr._device_metadata() == {"temperature_c": 30.5, "temperature_min_c": 30.125, "temperature_max_c": 31.5, "compensation_factor": 0.95}


def test_unusable_readings_are_ignored(mgr):
    mgr.record_device_readings(30.0, 0.95)
    for bad in (None, float("nan"), float("inf"), "hot", True, False):
        mgr.record_device_readings(bad, bad)
    assert mgr._device_metadata()["temperature_c"] == 30.0 and mgr._device_metadata()["compensation_factor"] == 0.95


def test_a_device_without_these_readings_adds_nothing(mgr):
    mgr._device = object()                                     # the Radiacode adapter has neither attribute
    mgr._record_device_readings()
    assert mgr._device_metadata() == {}


def test_the_manager_reads_them_from_the_device_object(mgr):
    class Device:
        temperature, comp_factor = 29.875, 0.9503
    mgr._device = Device()
    mgr._record_device_readings()
    assert mgr._device_metadata()["temperature_c"] == 29.875 and mgr._device_metadata()["compensation_factor"] == 0.9503


def test_live_data_metadata_carries_them(mgr):
    mgr._instrument = {"instrument_model": "AlphaHound"}
    mgr.state.last_spectrum_counts = [int(20 + 5 * math.sin(i / 30)) for i in range(1024)]
    mgr.state.last_spectrum_energies = CUBIC
    mgr.record_device_readings(30.25, 0.95012)
    mgr.record_device_readings(31.0, 0.95)
    meta = mgr.get_latest_data()["metadata"]
    assert (meta["temperature_c"], meta["temperature_min_c"], meta["temperature_max_c"], meta["compensation_factor"]) == (31.0, 30.25, 31.0, 0.95)
    assert meta["instrument_model"] == "AlphaHound"


def test_they_survive_an_n42_round_trip():
    metadata = {"live_time": 600.0, "real_time": 600.0, "source": "AlphaHound Device", "temperature_c": 30.25, "temperature_min_c": 29.875,
                "temperature_max_c": 31.5, "compensation_factor": 0.95012}
    xml = generate_n42_xml({"counts": [int(c) for c in np.arange(1024) % 50], "energies": CUBIC, "metadata": metadata})
    assert "TemperatureC" in xml and "CompensationFactor" in xml
    back = parse_n42(xml)["metadata"]
    assert (back["temperature_c"], back["temperature_min_c"], back["temperature_max_c"], back["compensation_factor"]) == (30.25, 29.875, 31.5, 0.95012)


def test_a_manual_read_reports_the_reading_that_came_with_the_spectrum(monkeypatch):
    from routers import device as d
    monkeypatch.setattr(d.alphahound_device, "is_connected", lambda: True)
    monkeypatch.setattr(d.alphahound_device, "request_spectrum", lambda: None)
    monkeypatch.setattr(d.alphahound_device, "get_spectrum", lambda: [(20 + i % 7, CUBIC[i]) for i in range(1024)])
    monkeypatch.setattr(d.alphahound_device, "get_temperature", lambda: 30.25)
    monkeypatch.setattr(d.alphahound_device, "get_comp_factor", lambda: 0.95012)
    response = TestClient(app).post("/device/spectrum", json={"count_minutes": 0})
    assert response.status_code == 200
    meta = response.json()["metadata"]
    assert meta["temperature_c"] == 30.25 and meta["compensation_factor"] == 0.95012


def test_a_manual_read_without_readings_has_no_such_keys(monkeypatch):
    from routers import device as d
    monkeypatch.setattr(d.alphahound_device, "is_connected", lambda: True)
    monkeypatch.setattr(d.alphahound_device, "request_spectrum", lambda: None)
    monkeypatch.setattr(d.alphahound_device, "get_spectrum", lambda: [(20 + i % 7, CUBIC[i]) for i in range(1024)])
    monkeypatch.setattr(d.alphahound_device, "get_temperature", lambda: None)
    monkeypatch.setattr(d.alphahound_device, "get_comp_factor", lambda: None)
    meta = TestClient(app).post("/device/spectrum", json={"count_minutes": 0}).json()["metadata"]
    assert "temperature_c" not in meta and "compensation_factor" not in meta
