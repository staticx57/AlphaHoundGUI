"""Managed acquisition must work with a Radiacode, not only the AlphaHound."""
import asyncio
import math

from fastapi.testclient import TestClient

import acquisition_manager as am_module
from main import app
from routers import device as device_router


def _rc_spectrum():
    energies = [3.0 + 2.4 * i + 0.0004 * i * i for i in range(1024)]
    counts = [20 + int(3000 * math.exp(-((e - 661.7) ** 2) / (2 * 23.0 ** 2))) for e in energies]
    return counts, energies, {"calibration_source": "device", "duration_s": 60.0}


def test_start_route_uses_radiacode_adapter(monkeypatch):
    captured = {}

    async def fake_start(duration_minutes, device, source_name="AlphaHound Device", dose_rate_fn=None, instrument=None):
        captured.update(duration=duration_minutes, device=device, source=source_name, dose=dose_rate_fn, instrument=instrument)
        return {"success": True}

    monkeypatch.setattr(device_router.acquisition_manager, "start", fake_start)
    r = TestClient(app).post("/device/acquisition/start", json={"duration_minutes": 1, "device": "radiacode"})
    assert r.status_code == 200, r.text
    assert isinstance(captured["device"], device_router.RadiacodeAcquisitionDevice)
    assert captured["source"].startswith("Radiacode Device")
    assert callable(captured["dose"])  # exposure is integrated from the Radiacode dose rate
    assert "instrument_model" in captured["instrument"]  # saved N42 must name the real device


def test_start_route_defaults_to_alphahound(monkeypatch):
    captured = {}

    async def fake_start(duration_minutes, device, source_name="AlphaHound Device", dose_rate_fn=None, instrument=None,
                         cps_fn=None):
        captured.update(device=device, source=source_name, dose=dose_rate_fn, instrument=instrument, cps=cps_fn)
        return {"success": True}

    monkeypatch.setattr(device_router.acquisition_manager, "start", fake_start)
    TestClient(app).post("/device/acquisition/start", json={"duration_minutes": 1})
    assert captured["device"] is device_router.alphahound_device
    assert captured["source"] == "AlphaHound Device"
    assert captured["dose"] is device_router.alphahound_dose_rate_uSv_h
    assert captured["instrument"] == {"instrument_model": "AlphaHound"}
    assert captured["cps"] is device_router.alphahound_cps       # per-channel rates are recorded for the AlphaHound


def test_radiacode_not_connected_is_reported(monkeypatch):
    monkeypatch.setattr(device_router.radiacode_device, "is_connected", lambda: False)
    r = TestClient(app).post("/device/acquisition/start", json={"duration_minutes": 1, "device": "radiacode"})
    assert r.status_code == 400 and "not connected" in r.json()["detail"].lower()


def test_manager_polls_radiacode_and_labels_results(monkeypatch):
    monkeypatch.setattr(device_router.radiacode_device, "is_connected", lambda: True)
    monkeypatch.setattr(device_router.radiacode_device, "get_spectrum", _rc_spectrum)
    mgr = am_module.AcquisitionManager()
    saved = (mgr._device, mgr._source_name, mgr._is_calibrated, mgr.state)
    try:
        mgr._device = device_router.RadiacodeAcquisitionDevice()
        mgr._source_name = "Radiacode Device"
        mgr.state = am_module.AcquisitionState(elapsed_seconds=60.0)
        asyncio.run(mgr._poll_spectrum())
        data = mgr.get_latest_data()
        assert data["metadata"]["source"] == "Radiacode Device"
        assert data["is_calibrated"] is True
        assert data["energies"][100] > 200  # real Radiacode axis, not channel numbers
        assert "Cs-137" in [i["isotope"] for i in data["isotopes"]]
    finally:
        mgr._device, mgr._source_name, mgr._is_calibrated, mgr.state = saved


def test_radiacode_identity_names_model_from_serial(monkeypatch):
    from routers import device_radiacode as rc
    from source_templates import resolve_detector
    monkeypatch.setattr(rc.radiacode_device, "get_device_info", lambda: {"serial_number": "RC-110-001593"})
    ident = rc.radiacode_identity()
    assert ident["instrument_model"] == "RadiaCode-110"
    assert resolve_detector(ident) == "Radiacode 110"
    monkeypatch.setattr(rc.radiacode_device, "get_device_info", lambda: {"serial_number": "RC-103G-000001"})
    assert resolve_detector(rc.radiacode_identity()) == "Radiacode 103G"


def test_accumulated_spectrum_is_view_only(monkeypatch):
    """Accumulated = whole device history (many places/sources): exposure reference, never identified."""
    from routers import device_radiacode as rc
    counts, energies, _ = _rc_spectrum()
    monkeypatch.setattr(rc.radiacode_device, "is_connected", lambda: True)
    monkeypatch.setattr(rc.radiacode_device, "get_device_info", lambda: {"serial_number": "RC-110-001593"})
    monkeypatch.setattr(rc.radiacode_device, "get_accumulated_spectrum",
                        lambda: {"counts": counts, "duration": 3600.0, "a0": 3.0, "a1": 2.4, "a2": 0.0004, "channels": 1024})
    for url in ("/radiacode/spectrum/accumulated", "/radiacode/spectrum/accumulated?analyze=false"):
        body = TestClient(app).get(url).json()
        assert body["identification_skipped"] is True
        assert body["peaks"] == [] and body["isotopes"] == [] and body["decay_chains"] == []
        assert "source_fit" not in body
        assert len(body["counts"]) == 1024 and body["energies"][1] > body["energies"][0]
        assert body["metadata"]["instrument_model"] == "RadiaCode-110"
        assert any("without identification" in w for w in body["warnings"])


def test_accumulated_spectrum_analyzed_when_user_confirms_single_source(monkeypatch):
    """Reset + one source makes the accumulated spectrum a valid measurement: analyze on request."""
    from routers import device_radiacode as rc
    counts, energies, _ = _rc_spectrum()
    monkeypatch.setattr(rc.radiacode_device, "is_connected", lambda: True)
    monkeypatch.setattr(rc.radiacode_device, "get_device_info", lambda: {"serial_number": "RC-110-001593"})
    monkeypatch.setattr(rc.radiacode_device, "get_accumulated_spectrum",
                        lambda: {"counts": counts, "duration": 3600.0, "a0": 3.0, "a1": 2.4, "a2": 0.0004, "channels": 1024})
    body = TestClient(app).get("/radiacode/spectrum/accumulated?analyze=true").json()
    assert "identification_skipped" not in body
    assert body["source_fit"]["detector"] == "Radiacode 110"
    assert "Cs-137" in [i["isotope"] for i in body["isotopes"]]
    assert any("single source" in w for w in body["warnings"])


def test_n42_records_the_real_instrument_and_round_trips():
    """A RadiaCode acquisition was saved stamped 'RadView Detection / AlphaHound'."""
    from n42_exporter import generate_n42_xml
    from n42_parser import parse_n42
    from source_templates import resolve_detector
    counts, energies, _ = _rc_spectrum()
    meta = {"live_time": 300.0, "source": "Radiacode Device (RadiaCode-110)",
            "instrument_model": "RadiaCode-110", "serial_number": "RC-110-001593"}
    xml = generate_n42_xml({"counts": counts, "energies": energies, "metadata": meta})
    assert "<Model>RadiaCode-110</Model>" in xml and "RC-110-001593" in xml and "AlphaHound" not in xml
    reloaded = parse_n42(xml)
    assert resolve_detector(reloaded["metadata"]) == "Radiacode 110"


def test_n42_model_from_source_string_only():
    from n42_exporter import instrument_from_metadata
    assert instrument_from_metadata({"source": "Radiacode Device (RadiaCode-103G)"})["model"] == "RadiaCode-103G"
    assert instrument_from_metadata({"source": "RadiaCode XML", "instrument_model": "RadiaCode-103"})["model"] == "RadiaCode-103"


def test_n42_defaults_to_alphahound_when_unknown():
    from n42_exporter import generate_n42_xml
    counts, energies, _ = _rc_spectrum()
    xml = generate_n42_xml({"counts": counts, "energies": energies, "metadata": {"live_time": 10.0}})
    assert "<Model>AlphaHound</Model>" in xml
