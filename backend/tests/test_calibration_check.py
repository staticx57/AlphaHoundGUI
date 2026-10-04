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
