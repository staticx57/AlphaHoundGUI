"""
Regression checks on NON-synthetic captures kept in the repo.

The Takumar (thoriated camera lens) N42s were saved with a forced linear 3.0 keV/ch
axis; tools/recalibrate_n42.py restores the AlphaHound's own axis from a CSV saved by
the same unit. Expectations come from the file names / physics, not from tuning:
a thoriated lens must show the Th-232 chain, a Cs-137 verification source no chain.
"""
import pathlib
import shutil
import sys

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "tools"))

import recalibrate_n42 as rc  # noqa: E402
from analysis_utils import analyze_spectrum_peaks  # noqa: E402
from n42_parser import parse_n42  # noqa: E402

ACQ = BACKEND / "data" / "acquisitions"
AXIS_CSV = ACQ / "spectrum_2025-12-12_08-41-27.csv"
TAKUMARS = [
    "spectrum_2025-12-15_takumar_90min.n42",
    "spectrum_takumar_8hr_reference.n42",
    "takumar 942pm to 558am.n42",
]


def _analyze_recalibrated(name, tmp_path):
    src = tmp_path / "in.n42"
    shutil.copy(ACQ / name, src)
    assert rc.main(["--axis-csv", str(AXIS_CSV), str(src)]) == 0
    return analyze_spectrum_peaks(parse_n42((tmp_path / "in.recal.n42").read_text(encoding="utf-8")), True, 0)


@pytest.mark.parametrize("name", TAKUMARS)
def test_takumar_shows_thorium_chain_after_recalibration(name, tmp_path):
    result = _analyze_recalibrated(name, tmp_path)
    assert "Th-232" in [c["parent"] for c in result["decay_chains"]]
    energies = [p["energy"] for p in result["peaks"]]
    assert any(abs(e - 239) < 15 for e in energies), energies   # Pb-212
    assert any(abs(e - 583) < 20 for e in energies), energies   # Tl-208


@pytest.mark.parametrize("name", TAKUMARS)
def test_takumar_has_no_uranium_chain(name, tmp_path):
    """Was a known false positive; fixed by the full-spectrum template fit (source_templates.py)."""
    result = _analyze_recalibrated(name, tmp_path)
    assert "U-238" not in [c["parent"] for c in result["decay_chains"]]


def test_cs137_verification_has_no_decay_chain_and_finds_cs137():
    raw = (BACKEND / "Cs137_Verification_Spectra.n42").read_text(encoding="utf-8")
    parsed = parse_n42(raw)
    result = analyze_spectrum_peaks(parsed, parsed.get("is_calibrated", True),
                                    float(parsed.get("metadata", {}).get("live_time", 0) or 0))
    assert result["decay_chains"] == []
    assert any(abs(p["energy"] - 662) < 15 for p in result["peaks"])
    assert "Cs-137" in [i["isotope"] for i in result["isotopes"]]
