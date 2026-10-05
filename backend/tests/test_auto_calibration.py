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


from spectroscopy import interspec_peaks  # noqa: E402


@pytest.mark.skipif(not interspec_peaks.enabled(), reason="needs InterSpec's peaks: the built-in detector's high-energy fits there "
                    "fail validation, so they are no evidence and the fresh-uranium guard cannot act (that path reads U-238, as before)")
def test_a_lens_whose_correction_missed_is_not_called_uranium():
    """
    tests/data/real_spectra/takumar_live_2026-10-05_20min_thinned.n42: the 8 h live AlphaHound capture of the thoriated Takumar lens
    (2026-10-05) binomially thinned to 20 minutes, the draw on which the automatic correction missed. The template fit then picked the
    nearest alias and the app reported U-235 at a fixed 80 % with a U-238 chain, with no U-235 line among the peaks (the flip seen
    live on 2026-10-04). Its peaks above 300 keV contradict uranium.
    """
    from formats.n42_parser import parse_n42
    path = pathlib.Path(__file__).resolve().parent / "data" / "real_spectra" / "takumar_live_2026-10-05_20min_thinned.n42"
    parsed = parse_n42(path.read_text(encoding="utf-8"))
    result = analyze_spectrum_peaks(parsed, True, 1200.0, auto_calibrate=False)
    assert "U-238" not in chains(result)
    assert not [i for i in result["isotopes"] if i["isotope"] == "U-235" and not i.get("matched_peaks")]
    assert any("not called uranium" in w for w in result.get("warnings", []))


@pytest.mark.parametrize("peaks", ["interspec", "builtin"])
def test_a_real_uranium_glaze_stays_uranium(peaks, monkeypatch):
    """The fresh-uranium guard must not touch real uranium: three failed built-in fits above 300 keV (no evidence) once withdrew it."""
    monkeypatch.setenv("ALPHAHOUND_PEAKS", peaks)
    parsed = parse_radiacode_xml((BACKEND_TESTS / "data" / "radiacode_fisicas" / "U-238-U-235-FiestaWare.xml").read_text(encoding="utf-8"))
    result = analyze_spectrum_peaks(parsed, True, float(parsed["metadata"].get("live_time") or 0))
    assert "U-238" in chains(result)
    assert not any("not called uranium" in w for w in result.get("warnings", []))


BACKEND_TESTS = pathlib.Path(__file__).resolve().parent
