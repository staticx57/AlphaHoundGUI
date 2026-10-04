"""
Automatic energy-axis correction (spectroscopy/auto_calibration.py), on real spectra with known content.

The AlphaHound read 5.7 % lower in October 2026 than in December 2025. On a drifted axis the full-spectrum fit can slide the one-line
fresh-uranium template onto thorium's 239 keV peak and report the U-238 series for a thoriated lens. The correction finds the source from
several of its lines, lets the spectrum fit confirm it on the corrected axis, and only then moves the axis.
Measured on every labelled spectrum drifted by 0.90-1.10: the series verdict went from 267/307 to 286/307 right, none made worse, and no
correction ever named the wrong source.
"""
import pathlib
import shutil

import numpy as np
import pytest
from fastapi.testclient import TestClient

import real_benchmark as rb
from formats.radiacode_xml_parser import parse_radiacode_xml
from main import app
from spectroscopy.analysis_utils import analyze_spectrum_peaks

WEB = pathlib.Path(__file__).resolve().parent / "data" / "web_spectra"


def benchmark(case_id):
    case = next(c for c in rb.CASES if c[0] == case_id)
    return rb.load(case[2], case[3])


def drifted(parsed, gain):
    return {**parsed, "energies": [e * gain for e in parsed["energies"]], "metadata": dict(parsed.get("metadata") or {})}


def chains(result):
    return {c["parent"] for c in result["decay_chains"]}


def test_a_drifted_thoriated_lens_is_corrected_and_read_as_thorium():
    """The December 8 h Takumar capture at the gain the live AlphaHound showed in October (0.943): it read as no series at all."""
    parsed = drifted(benchmark("ah_takumar_8h"), 0.943)
    raw_axis = list(parsed["energies"])
    result = analyze_spectrum_peaks(parsed, True, 0)
    auto = result["auto_calibration"]
    assert auto["applied"] and auto["source"] == "thorium_series"
    assert chains(result) == {"Th-232"}
    assert result["original_energies"] == raw_axis                        # what Undo restores
    assert parsed["energies"] is not raw_axis and result["energies"] != raw_axis
    assert result["metadata"]["energy_correction"]["automatic"] is True
    assert any("corrected automatically" in w for w in result["warnings"])


@pytest.mark.parametrize("name", ["ra-88-spd.xml", "rn-86-spd.xml"])
def test_a_drifted_radium_source_is_corrected_back_to_radium(name):
    """At gain 0.90 these radium sources read as Ba-133 + Eu-152 with no series."""
    parsed = drifted(parse_radiacode_xml((WEB / "dmamontov" / name).read_text(encoding="utf-8")), 0.90)
    result = analyze_spectrum_peaks(parsed, True, 0)
    assert result["auto_calibration"]["applied"] and result["auto_calibration"]["source"] == "radium_series"
    assert chains(result) == {"U-238"}


@pytest.mark.parametrize("case_id", ["rc103_th232", "rc103_ra226", "ah_cs137", "rc103_am241"])
def test_a_spectrum_on_a_good_axis_is_left_alone(case_id):
    parsed = benchmark(case_id)
    axis = list(parsed["energies"])
    result = analyze_spectrum_peaks(parsed, True, 0)
    assert not result.get("auto_calibration", {}).get("applied")
    assert result["energies"] == axis and "original_energies" not in result


def test_an_axis_the_user_chose_is_not_corrected_again():
    """Reanalyse (the calibration dialog) and the axis-correction route analyse on the axis given, as given."""
    parsed = drifted(benchmark("ah_takumar_8h"), 0.943)
    body = TestClient(app).post("/analyze/reanalyze", json={"energies": parsed["energies"], "counts": parsed["counts"]}).json()
    assert not body.get("auto_calibration", {}).get("applied")
    assert body["energies"] == pytest.approx(parsed["energies"])


def test_the_correction_is_never_applied_to_germanium():
    from formats.chn_spe_parser import parse_spe_file
    parsed = parse_spe_file(str(WEB / "lbl-anp" / "1110C NAA cave background May 2017.spe"))
    parsed["energies"] = [e * 0.95 for e in parsed["energies"]]
    result = analyze_spectrum_peaks(parsed, True, 0)
    assert not result.get("auto_calibration", {}).get("applied")
