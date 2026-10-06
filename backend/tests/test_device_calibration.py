"""AlphaHound energy-axis handling: use the device's nonlinear axis, fall back only when unusable."""

import math

import pytest
from fastapi.testclient import TestClient

from devices.device_calibration import (
    SOURCE_DEVICE, SOURCE_FALLBACK, energies_from_device_spectrum,
)
from main import app


def _device_axis(n=1024):
    """Nonlinear axis shaped like the real unit: 15 keV at ch0 .. ~7572 keV at ch1023, steeper at the top."""
    return [15.0 + 1.68 * i + 0.0161 * i * i for i in range(n)]


def test_valid_device_axis_is_used_verbatim():
    axis = _device_axis()
    spectrum = [(10.0, e) for e in axis]
    energies, source = energies_from_device_spectrum(spectrum)
    assert source == SOURCE_DEVICE
    assert energies == axis
    assert energies[-1] > 7000  # not the linear 3.0 keV/ch axis (3069)


@pytest.mark.parametrize("bad_axis", [
    [0.0] * 8,                                   # all zeros
    [1.0, 2.0, 2.0, 4.0],                        # not strictly increasing
    [5.0, 4.0, 3.0, 2.0],                        # decreasing
    [1.0, float("nan"), 3.0, 4.0],               # NaN
    [-1.0, 0.0, 1.0, 2.0],                       # negative energy
    [10.0],                                      # too short
    [],
])
def test_unusable_axis_falls_back_to_linear(bad_axis):
    spectrum = [(1.0, e) for e in bad_axis]
    energies, source = energies_from_device_spectrum(spectrum)
    assert source == SOURCE_FALLBACK
    assert energies == [i * 3.0 for i in range(len(bad_axis))]


@pytest.fixture
def mocked_device(monkeypatch):
    from routers import device as device_router
    dev = device_router.alphahound_device
    monkeypatch.setattr(dev, "is_connected", lambda: True)
    monkeypatch.setattr(dev, "clear_spectrum", lambda: None)
    monkeypatch.setattr(dev, "request_spectrum", lambda: None)
    return dev


def _spectrum(axis):
    return [(20 + (int(400 * math.exp(-((i - 150) ** 2) / 60))), e) for i, e in enumerate(axis)]


def test_device_spectrum_endpoint_keeps_device_energies(mocked_device, monkeypatch):
    axis = _device_axis()
    monkeypatch.setattr(mocked_device, "get_spectrum", lambda: _spectrum(axis))
    body = TestClient(app).post("/device/spectrum", json={"count_minutes": 0}).json()
    assert body["energies"] == axis
    assert body["metadata"]["energy_calibration"] == SOURCE_DEVICE


def test_device_spectrum_endpoint_fallback_skips_identification(mocked_device, monkeypatch):
    monkeypatch.setattr(mocked_device, "get_spectrum", lambda: _spectrum([0.0] * 1024))
    body = TestClient(app).post("/device/spectrum", json={"count_minutes": 0}).json()
    assert body["energies"][:3] == [0.0, 3.0, 6.0]
    assert body["metadata"]["energy_calibration"] == SOURCE_FALLBACK
    assert body["isotopes"] == [] and body["decay_chains"] == []


def test_device_spectrum_endpoint_returns_everything_the_analysis_found(mocked_device, monkeypatch):
    """The reply used to be built by hand: it dropped the warnings, the calibration check, the automatic correction and the data quality
    (which /device/spectrum/current returns), and sent the device's raw axis beside peaks the analysis had found on a corrected one."""
    from routers import device as device_router
    axis = _device_axis()
    corrected = [e * 1.05 for e in axis]
    monkeypatch.setattr(mocked_device, "get_spectrum", lambda: _spectrum(axis))

    def analysis(result, is_calibrated, live_time=0.0, **kw):
        return {**result, "energies": corrected, "peaks": [{"energy": 662.0}], "isotopes": [{"isotope": "Cs-137"}], "decay_chains": [],
                "warnings": ["Energy axis corrected automatically"], "calibration_check": {"shift_percent": 5.0},
                "auto_calibration": {"applied": True, "source": "thorium_series"}, "data_quality": {"warnings": []},
                "display_min_keV": 24.0, "unassigned_excess": [{"energy": 142.0}], "is_calibrated": True,
                "metadata": {**result["metadata"], "energy_correction": {"gain": 1.05, "automatic": True}}}
    monkeypatch.setattr(device_router, "analyze_spectrum_peaks", analysis)

    body = TestClient(app).post("/device/spectrum", json={"count_minutes": 0}).json()
    for key in ("warnings", "calibration_check", "auto_calibration", "data_quality", "display_min_keV", "unassigned_excess", "is_calibrated"):
        assert key in body, key
    assert body["energies"] == corrected                              # the axis the peaks are on, not the raw one
    assert body["metadata"]["energy_correction"]["automatic"] is True  # what the analysis put in the metadata is kept
    assert body["metadata"]["energy_calibration"] == SOURCE_DEVICE and body["metadata"]["live_time"] == 0
    assert "start_time" in body["metadata"] and "end_time" in body["metadata"]       # the acquisition's own fields are still there


# ---------------------------------------------------------------- Radiacode

from types import SimpleNamespace

from devices.radiacode_driver import (
    CALIBRATION_DEVICE, CALIBRATION_FALLBACK, resolve_energy_calibration,
)


class _Dev:
    def __init__(self, calib=None, raises=False):
        self._calib, self._raises = calib, raises

    def energy_calib(self):
        if self._raises:
            raise RuntimeError("usb timeout")
        return self._calib


def test_radiacode_uses_device_energy_calib():
    coeffs, source = resolve_energy_calibration(_Dev([1.5, 2.9, 0.0004]), SimpleNamespace())
    assert source == CALIBRATION_DEVICE and coeffs == (1.5, 2.9, 0.0004)


def test_radiacode_two_coefficients_default_a2_to_zero():
    coeffs, source = resolve_energy_calibration(_Dev([0.0, 3.1]), SimpleNamespace())
    assert source == CALIBRATION_DEVICE and coeffs == (0.0, 3.1, 0.0)


def test_radiacode_falls_back_to_spectrum_coefficients_when_energy_calib_fails():
    spectrum = SimpleNamespace(a0=2.0, a1=2.8, a2=0.0002)
    coeffs, source = resolve_energy_calibration(_Dev(raises=True), spectrum)
    assert source == CALIBRATION_DEVICE and coeffs == (2.0, 2.8, 0.0002)


@pytest.mark.parametrize("calib", [None, [], [5.0], [0.0, 0.0, 0.0], [0.0, -1.0], [float("nan"), 3.0]])
def test_radiacode_unusable_everywhere_is_flagged_fallback(calib):
    coeffs, source = resolve_energy_calibration(_Dev(calib), SimpleNamespace())
    assert source == CALIBRATION_FALLBACK and coeffs == (0.0, 3.0, 0.0)


def test_radiacode_endpoint_marks_fallback_uncalibrated(monkeypatch):
    from routers import device_radiacode as rc
    counts = [20 + int(400 * math.exp(-((i - 150) ** 2) / 60)) for i in range(1024)]
    meta = {"duration_s": 600.0, "calibration_source": CALIBRATION_FALLBACK}
    monkeypatch.setattr(rc.radiacode_device, "is_connected", lambda: True)
    monkeypatch.setattr(rc.radiacode_device, "get_spectrum",
                        lambda: (counts, [i * 3.0 for i in range(1024)], meta))
    body = TestClient(app).get("/radiacode/spectrum").json()
    assert body["is_calibrated"] is False
    assert body["isotopes"] == [] and body["decay_chains"] == []
    assert body["warnings"]
