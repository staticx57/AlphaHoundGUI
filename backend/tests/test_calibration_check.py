"""The energy-axis check: known shifts are found and corrected, none is invented, and the real captures that fooled the old estimate."""
import pathlib
import shutil
import sys

import numpy as np
import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "tools"))

import recalibrate_n42 as rc  # noqa: E402
import spectrum_synth as ss  # noqa: E402
from formats.n42_parser import parse_n42  # noqa: E402
from formats.radiacode_xml_parser import parse_radiacode_xml  # noqa: E402
from spectroscopy.analysis_utils import analyze_spectrum_peaks  # noqa: E402
from spectroscopy.calibration_check import check_calibration, measure_line  # noqa: E402

DETECTOR = "AlphaHound CsI(Tl)"
TRUE_AXIS = ss.linear_axis(1024, 3000.0)
ACQ = BACKEND / "tests" / "data" / "real_spectra"
AXIS_CSV = ACQ / "spectrum_2025-12-12_08-41-27.csv"
TAKUMARS = ["spectrum_2025-12-15_takumar_90min.n42", "spectrum_takumar_8hr_reference.n42", "takumar 942pm to 558am.n42"]


def thorium_spectrum(gain_error=1.0, offset_kev=0.0, seed=1):
    """Counts made on the true axis, and the axis a drifted device would label them with."""
    _, counts = ss.series_spectrum(DETECTOR, ss.THORIUM_SERIES, 400.0, live_time_s=3600.0, seed=seed, energies=TRUE_AXIS)
    return TRUE_AXIS * gain_error + offset_kev, counts


@pytest.mark.parametrize("gain_error, offset", [(0.97, 0), (0.95, 0), (1.04, 0), (1.0, -15), (0.98, 12)])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_a_known_shift_is_found_and_the_correction_restores_the_axis(gain_error, offset, seed):
    seen, counts = thorium_spectrum(gain_error, offset, seed)
    check = check_calibration(seen, counts, ["thorium_series"], 0.10)
    assert len(check["lines"]) == 3 and check["consistent"]
    assert check["message"] and "Recalibrate" in check["message"]
    corr = check["correction"]
    for true_energy in (600.0, 2000.0):                                    # the axis the device should have shown
        assert (true_energy * gain_error + offset - corr["offset_keV"]) / corr["gain"] == pytest.approx(true_energy, abs=2.0)


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_a_correct_axis_raises_no_warning(seed):
    seen, counts = thorium_spectrum(seed=seed)
    check = check_calibration(seen, counts, ["thorium_series"], 0.10)
    assert check["message"] is None
    assert abs(check["shift_percent"]) < 0.3


def test_a_shift_within_the_threshold_is_measured_but_not_reported():
    seen, counts = thorium_spectrum(gain_error=1.02)
    check = check_calibration(seen, counts, ["thorium_series"], 0.10)
    assert check["shift_percent"] == pytest.approx(2.0, abs=0.3) and check["message"] is None


def test_no_sources_means_no_lines_and_no_claim():
    seen, counts = thorium_spectrum()
    check = check_calibration(seen, counts, [], 0.10)
    assert check == {"lines": [], "shift_percent": None, "consistent": False, "correction": None, "message": None}


def test_a_line_that_is_not_there_is_not_measured():
    flat = np.full(1024, 40.0)
    assert measure_line(TRUE_AXIS, flat, 1460.8, 0.10) is None


def test_lines_that_disagree_are_not_averaged_into_a_correction():
    seen, counts = thorium_spectrum()
    # drag the 583 keV line 5 % down on its own: a gain error would move every line the same way
    moved = counts.copy()
    window = (TRUE_AXIS > 500) & (TRUE_AXIS < 680)
    moved[window] = np.interp(TRUE_AXIS[window] * 1.05, TRUE_AXIS, counts)
    check = check_calibration(seen, moved, ["thorium_series"], 0.10)
    assert not check["consistent"] and check["correction"] is None and check["message"] is None


# What the live AlphaHound showed on 2026-10-04 (28.8 deg C): measured/nominal of the thorium lines on its own axis
LIVE_DRIFT = [(0.0, 0.97), (238.6, 0.966), (338.3, 0.937), (583.2, 0.923), (1588.2, 0.920), (2614.5, 0.882), (3100.0, 0.875)]


def test_lines_all_clearly_off_the_same_way_are_reported_without_a_correction():
    """A drifted gain on a nonlinear axis: every line low by 3-12 %, but not by one straight-line map. Silence hid it."""
    _, counts = ss.series_spectrum(DETECTOR, ss.THORIUM_SERIES, 400.0, live_time_s=3600.0, seed=1, energies=TRUE_AXIS)
    drift = np.interp(TRUE_AXIS, *zip(*LIVE_DRIFT))
    check = check_calibration(TRUE_AXIS * drift, counts, ["thorium_series"], 0.10)
    assert len(check["lines"]) >= 2 and all(m["shift_percent"] < -2.5 for m in check["lines"])
    assert not check["consistent"] and check["correction"] is None   # no straight line to offer
    assert check["message"] and "low" in check["message"] and "Open Calibration Tool" in check["message"]


def test_a_real_alphahound_capture_with_the_gain_drift_seen_live_is_flagged(tmp_path):
    """The December Takumar capture on the device axis, with the 0.943 gain change measured between it and the live spectrum."""
    src = tmp_path / "in.n42"
    shutil.copy(ACQ / "takumar 942pm to 558am.n42", src)
    assert rc.main(["--axis-csv", str(AXIS_CSV), str(src)]) == 0
    parsed = parse_n42((tmp_path / "in.recal.n42").read_text(encoding="utf-8"))
    drifted = [e * 0.943 for e in parsed["energies"]]
    # the check itself, on the source this capture really holds (the whole-spectrum fit's verdict at this drift is a separate matter)
    check = check_calibration(drifted, parsed["counts"], ["thorium_series"], 0.10)
    assert len(check["lines"]) >= 2 and all(m["shift_percent"] < -2.5 for m in check["lines"])
    assert check["message"] and "calibration looks low" in check["message"]


def analysed(parsed):
    return analyze_spectrum_peaks(parsed, True, 0)


@pytest.mark.parametrize("name", TAKUMARS)
def test_real_alphahound_captures_no_longer_get_a_false_calibration_warning(name, tmp_path):
    """The whole-spectrum fit's gain said 4-5 % low for all three; their lines are within 1-3 % and scattered both ways."""
    src = tmp_path / "in.n42"
    shutil.copy(ACQ / name, src)
    assert rc.main(["--axis-csv", str(AXIS_CSV), str(src)]) == 0
    result = analysed(parse_n42((tmp_path / "in.recal.n42").read_text(encoding="utf-8")))
    assert not [w for w in result.get("warnings", []) if "calibration looks" in w]


def test_real_radiacode_radium_capture_is_flagged_with_the_gain_three_lines_agree_on():
    parsed = parse_radiacode_xml((BACKEND / "tests" / "data" / "radiacode_fisicas" / "Ra-226.xml").read_text(encoding="utf-8"))
    result = analysed(parsed)
    check = result["calibration_check"]
    assert check["consistent"] and len(check["lines"]) == 3
    assert check["correction"]["gain"] == pytest.approx(0.974, abs=0.005)
    assert any("calibration looks low" in w for w in result["warnings"])


# ---- applying the correction the check found ----

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def correct(client, seen, counts, check, **extra):
    corr = check["correction"]
    return client.post("/analyze/correct-axis", json={"energies": seen.tolist(), "counts": counts.tolist(), "gain": corr["gain"],
                                                      "offset_keV": corr["offset_keV"], "metadata": {"source": "AlphaHound Device"}, **extra})


@pytest.mark.parametrize("gain_error, offset", [(0.95, 0), (1.04, 0), (0.98, 12)])
def test_applying_the_correction_restores_the_axis_and_the_check_then_agrees(client, gain_error, offset):
    seen, counts = thorium_spectrum(gain_error, offset)
    check = check_calibration(seen, counts, ["thorium_series"], 0.10)
    assert check["message"]
    response = correct(client, seen, counts, check, live_time=3600.0)
    assert response.status_code == 200
    body = response.json()
    assert np.allclose(body["energies"], TRUE_AXIS, atol=3.0)                 # the axis the counts were really made on
    assert body["metadata"]["energy_correction"]["gain"] == pytest.approx(check["correction"]["gain"])
    assert not [w for w in body.get("warnings", []) if "calibration looks" in w]
    assert abs(body["calibration_check"]["shift_percent"]) < 0.5
    assert "Th-232" in [c["parent"] for c in body["decay_chains"]]


def test_correction_keeps_the_shape_of_a_nonlinear_axis(client):
    cubic = (15.0001 + 1.68372 * np.arange(1024) - 4.75865e-05 * np.arange(1024) ** 2 + 5.49654e-06 * np.arange(1024) ** 3)
    counts = np.full(1024, 30.0)
    body = client.post("/analyze/correct-axis", json={"energies": cubic.tolist(), "counts": counts.tolist(), "gain": 0.97, "offset_keV": 5.0}).json()
    expected = (cubic - 5.0) / 0.97
    assert np.allclose(body["energies"], expected, atol=1e-6)
    assert np.all(np.diff(body["energies"]) > 0)


@pytest.mark.parametrize("payload", [
    {"energies": [1.0, 2.0], "counts": [1.0], "gain": 1.0, "offset_keV": 0.0},                 # lengths differ
    {"energies": [1.0, 2.0], "counts": [1.0, 2.0], "gain": 3.0, "offset_keV": 0.0},            # a gain no real drift reaches
    {"energies": [1.0, 2.0], "counts": [1.0, 2.0], "gain": 1.0, "offset_keV": 1000.0},
    {"energies": [], "counts": [], "gain": 1.0, "offset_keV": 0.0},
])
def test_unreasonable_corrections_are_refused(client, payload):
    assert client.post("/analyze/correct-axis", json=payload).status_code == 422
