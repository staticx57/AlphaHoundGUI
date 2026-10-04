"""Peak fitting on coarse and nonlinear axes. The fit window was a fixed 30 keV and a fit needs 10 channels in it, so on an axis with
channels wider than 3 keV every fit failed and the peak list was empty there. The AlphaHound's own axis is 1.7 keV/channel at the bottom and
18 at the top: no peak above about 600 keV was ever reported for it (K-40 at 1461 keV, Tl-208 at 2615 keV ...); a 5 % mislabelled axis
emptied the peak list of any spectrum."""
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
from spectroscopy.analysis_utils import analyze_spectrum_peaks  # noqa: E402
from spectroscopy.peak_detection_enhanced import detect_peaks_enhanced  # noqa: E402

DETECTOR = "AlphaHound CsI(Tl)"
CH = np.arange(1024)
DEVICE_AXIS = 15.0001 + 1.68372 * CH - 4.75865e-05 * CH ** 2 + 5.49654e-06 * CH ** 3        # the AlphaHound's own cubic axis
ACQ = BACKEND / "tests" / "data" / "real_spectra"
AXIS_CSV = ACQ / "spectrum_2025-12-12_08-41-27.csv"


def near(energies, target, tolerance):
    return any(abs(e - target) <= tolerance for e in energies)


def test_lines_up_to_2_6_mev_are_found_on_the_alphahounds_own_axis():
    area = 40000.0
    counts = ss.make_spectrum(DETECTOR, [(661.7, area), (1460.8, area), (2614.5, area)], DEVICE_AXIS, continuum=200.0, seed=2)
    energies = [p["energy"] for p in detect_peaks_enhanced(DEVICE_AXIS, counts, validate_fits=True, resolution_662=0.10)]
    assert near(energies, 661.7, 25), energies
    assert near(energies, 1460.8, 45), energies
    assert near(energies, 2614.5, 80), energies


@pytest.mark.parametrize("stretch", [1.05, 1.10, 1.15])
def test_a_mislabelled_axis_still_gets_its_peaks(stretch):
    axis = ss.linear_axis(1024, 3000.0)
    counts = ss.series_spectrum(DETECTOR, ss.THORIUM_SERIES, 400.0, live_time_s=3600.0, seed=1, energies=axis)[1]
    # peak finding on the stretched axis itself (the automatic axis correction off)
    result = analyze_spectrum_peaks({"counts": counts.tolist(), "energies": (axis * stretch).tolist(), "metadata": {}}, True, 3600.0,
                                    auto_calibrate=False)
    energies = [p["energy"] for p in result["peaks"]]
    assert near(energies, 238.6 * stretch, 0.05 * 238.6 * stretch) and near(energies, 583.2 * stretch, 0.05 * 583.2 * stretch), energies
    # with it on, a stretch within what a real drift does is taken out and the peaks sit at their true energies
    corrected = analyze_spectrum_peaks({"counts": counts.tolist(), "energies": (axis * stretch).tolist(), "metadata": {}}, True, 3600.0)
    if corrected.get("auto_calibration", {}).get("applied"):
        energies = [p["energy"] for p in corrected["peaks"]]
        assert near(energies, 238.6, 0.03 * 238.6) and near(energies, 583.2, 0.03 * 583.2), energies


def test_a_real_thoriated_lens_capture_reports_its_high_energy_peaks(tmp_path):
    """Three captures like this had no peak above 576 keV; Ac-228 911/969 and Tl-208 2615 are what identify the chain."""
    src = tmp_path / "in.n42"
    shutil.copy(ACQ / "takumar 942pm to 558am.n42", src)
    assert rc.main(["--axis-csv", str(AXIS_CSV), str(src)]) == 0
    result = analyze_spectrum_peaks(parse_n42((tmp_path / "in.recal.n42").read_text(encoding="utf-8")), True, 0)
    energies = [p["energy"] for p in result["peaks"]]
    assert max(energies) > 850, energies
    assert near(energies, 238.6, 25) and near(energies, 583.2, 40)                 # what was found before is still found
