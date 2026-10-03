import pathlib
import shutil
import sys

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "tools"))

import recalibrate_n42 as rc  # noqa: E402
from n42_parser import parse_n42  # noqa: E402

ACQ = BACKEND / "tests" / "data" / "real_spectra"   # real spectra kept as test fixtures
AXIS_CSV = ACQ / "spectrum_2025-12-12_08-41-27.csv"
TAKUMAR = ACQ / "takumar 942pm to 558am.n42"


def test_axis_csv_is_nonlinear_device_axis():
    axis = rc.load_axis(AXIS_CSV)
    assert len(axis) == 1024 and axis[0] == 15.0 and axis[-1] > 7000


def test_recalibrate_replaces_forced_axis_and_keeps_counts(tmp_path):
    src = tmp_path / "t.n42"
    shutil.copy(TAKUMAR, src)
    before = parse_n42(src.read_text(encoding="utf-8"))
    assert rc.main(["--axis-csv", str(AXIS_CSV), str(src)]) == 0
    after = parse_n42((tmp_path / "t.recal.n42").read_text(encoding="utf-8"))
    assert after["counts"] == before["counts"]
    assert after["energies"][0] == 15.0 and after["energies"][-1] > 7000
    assert before["energies"][-1] == 3069.0  # original untouched
    assert src.read_text(encoding="utf-8") == TAKUMAR.read_text(encoding="utf-8")


def test_refuses_file_without_forced_axis(tmp_path):
    src = tmp_path / "already.n42"
    shutil.copy(TAKUMAR, src)
    first = tmp_path / "already.recal.n42"
    rc.main(["--axis-csv", str(AXIS_CSV), str(src)])
    # a recalibrated file no longer has the 0..3069 axis, so it must be refused
    assert rc.main(["--axis-csv", str(AXIS_CSV), str(first)]) == 1


def test_recalibrated_takumar_peaks_line_up_with_thorium_lines(tmp_path):
    """Physical check: with the device axis, Pb-212 (239 keV) and Ac-228 (338 keV) appear."""
    from analysis_utils import analyze_spectrum_peaks
    src = tmp_path / "t.n42"
    shutil.copy(TAKUMAR, src)
    rc.main(["--axis-csv", str(AXIS_CSV), str(src)])
    result = analyze_spectrum_peaks(parse_n42((tmp_path / "t.recal.n42").read_text(encoding="utf-8")), True, 0)
    energies = [p["energy"] for p in result["peaks"]]
    assert any(abs(e - 239) < 15 for e in energies), energies
    assert any(abs(e - 338) < 15 for e in energies), energies
