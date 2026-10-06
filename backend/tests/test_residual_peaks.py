"""
Unassigned excesses (spectroscopy/residual_peaks.py): structure the fitted peaks do not explain, shown but never used to identify anything.

The synthetic spectrum is the geometry of an 8-hour thoriated lens on a scintillator: a smooth continuum, a very large peak at 239 keV and a
smaller one at 338 keV, and (when asked) a broad shelf near 142 keV about 20 % over the continuum (what the 8-hour run shows).
"""
import json
import math
import os

import numpy as np
import pytest

from spectroscopy import interspec_peaks
from spectroscopy.analysis_utils import analyze_spectrum_peaks
from spectroscopy.residual_peaks import MAX_MARKERS, find_unassigned_excess

R662 = 0.10
E = np.arange(1.0, 2001.0, 2.0)                       # 1000 channels of 2 keV
PEAKS = [(239.0, 700_000.0), (338.0, 60_000.0)]       # centre, net area


def fwhm(energy):
    return R662 * 662.0 * math.sqrt(energy / 662.0)


def fitted_peaks(scale=1.0):
    return [{"energy": e, "net_area": area * scale, "fwhm": fwhm(e)} for e, area in PEAKS]


def spectrum(seed, bump=0.0, bump_at=142.0, extra_peak=None):
    """Counts: continuum + the two peaks + a Gaussian shelf `bump` times the continuum at `bump_at`, with Poisson noise."""
    continuum = 30_000.0 * np.exp(-E / 800.0) + 2_000.0
    model = continuum.copy()
    for centre, area in PEAKS + ([extra_peak] if extra_peak else []):
        sigma = fwhm(centre) / 2.3548
        model += area * 2.0 / (sigma * math.sqrt(2 * math.pi)) * np.exp(-0.5 * ((E - centre) / sigma) ** 2)
    if bump:
        sigma = fwhm(bump_at) / 2.3548
        model += bump * float(np.interp(bump_at, E, continuum)) * np.exp(-0.5 * ((E - bump_at) / sigma) ** 2)
    return np.random.RandomState(seed).poisson(model).astype(float)


def test_a_shelf_beside_a_huge_peak_is_found_where_it_is():
    found = find_unassigned_excess(E, spectrum(1, bump=0.20), fitted_peaks(), R662)
    assert len(found) == 1 and abs(found[0]["energy"] - 142.0) < 10.0
    assert found[0]["significance"] >= 15.0 and found[0]["contrast"] > 0.10


def test_a_shelf_a_little_under_the_bar_is_not_reported():
    """9 % over the continuum stands 10 standard errors high: real, but under the 15 that keeps a marker meaningful."""
    assert find_unassigned_excess(E, spectrum(1, bump=0.09), fitted_peaks(), R662) == []


def test_noise_alone_gives_no_marker_even_when_the_big_peak_is_slightly_misfitted():
    """40 noise realisations, the large peaks' areas 0, 1.5 and -1.5 % off: the 2 % systematic floor is what keeps their shape misfit out."""
    hits = 0
    for seed in range(40):
        for scale in (1.0, 1.015, 0.985):
            hits += len(find_unassigned_excess(E, spectrum(seed), fitted_peaks(scale), R662))
    assert hits == 0


def test_the_misfit_of_a_peak_itself_is_not_an_unassigned_excess():
    """A fitted peak 6 % too small leaves a residual AT its centre: that is the peak, not a new feature."""
    found = find_unassigned_excess(E, spectrum(2), fitted_peaks(0.94), R662)
    assert not [f for f in found if abs(f["energy"] - 239.0) < 20.0]


def test_a_line_the_peak_search_missed_is_reported():
    """A real 600 keV line of 150,000 counts that is not in the fitted list."""
    found = find_unassigned_excess(E, spectrum(3, extra_peak=(600.0, 150_000.0)), fitted_peaks(), R662)
    assert any(abs(f["energy"] - 600.0) < 20.0 for f in found)


def test_nothing_below_100_kev_or_at_the_detector_threshold():
    shelf_low = find_unassigned_excess(E, spectrum(4, bump=0.5, bump_at=60.0), fitted_peaks(), R662)
    assert not [f for f in shelf_low if f["energy"] < 100.0]
    edge = find_unassigned_excess(E, spectrum(5, bump=0.20), fitted_peaks(), R662, edge_kev=140.0)
    assert not [f for f in edge if f["energy"] < 155.0]                                   # the threshold edge pushes the search window up


def test_no_more_than_a_few_markers_are_returned():
    counts = spectrum(6, bump=0.3, bump_at=142.0) + spectrum(7, bump=0.3, bump_at=520.0) + spectrum(8, bump=0.3, bump_at=900.0) \
        + spectrum(9, bump=0.3, bump_at=1300.0) + spectrum(10, bump=0.3, bump_at=1700.0)
    assert len(find_unassigned_excess(E, counts, fitted_peaks(), R662)) <= MAX_MARKERS


def test_degenerate_input_returns_nothing():
    assert find_unassigned_excess([], [], [], R662) == []
    assert find_unassigned_excess(E[:10], np.ones(10), [], R662) == []
    assert find_unassigned_excess(E, np.zeros_like(E), [], R662) == []


# --------------------------------------------------------------------------- in the analysis
DATA = os.path.join(os.path.dirname(__file__), "data")


def _analyse(path):
    from formats.radiacode_xml_parser import parse_radiacode_xml
    with open(os.path.join(DATA, path), encoding="utf-8") as handle:
        parsed = parse_radiacode_xml(handle.read())
    return analyze_spectrum_peaks(parsed, True, float(parsed["metadata"].get("live_time") or 0))


def test_the_markers_change_neither_the_peaks_nor_the_identification(monkeypatch):
    """They are kept apart from `peaks` and never reach identification: the same spectrum analysed with the search switched off gives the
    same peaks, isotopes and chains."""
    path = "web_spectra/dmamontov/ra-88-spd.xml"
    with_markers = _analyse(path)
    monkeypatch.setattr("spectroscopy.residual_peaks.find_unassigned_excess", lambda *a, **k: [])
    without = _analyse(path)
    assert without["unassigned_excess"] == []
    keys = ("peaks", "isotopes", "decay_chains")
    assert json.dumps({k: with_markers[k] for k in keys}, sort_keys=True, default=str) == json.dumps({k: without[k] for k in keys}, sort_keys=True, default=str)


@pytest.mark.skipif(not interspec_peaks.enabled(), reason="the peak list this relies on is InterSpec's")
def test_a_real_line_the_peak_finder_missed_shows_up_as_an_unassigned_excess():
    """Radium spectrum from a RadiaCode: the 242 keV Pb-214 line is a clear excess, and no fitted peak sits there."""
    result = _analyse("web_spectra/dmamontov/ra-88-spd.xml")
    marker = next((m for m in result["unassigned_excess"] if 230.0 <= m["energy"] <= 250.0), None)
    assert marker is not None and marker["significance"] >= 15.0
    assert not [p for p in result["peaks"] if abs(p["energy"] - marker["energy"]) < 20.0]


def test_germanium_gets_no_search():
    from formats.chn_spe_parser import parse_spe_file
    parsed = parse_spe_file(os.path.join(DATA, "web_spectra", "lbl-anp", "1110C NAA cave background May 2017.spe"))
    parsed["metadata"]["live_time"] = parsed.get("live_time", 0)
    result = analyze_spectrum_peaks(parsed, parsed["calibration"] is not None, parsed.get("live_time", 0))
    assert result["detector_profile"] == "HPGe (generic)" and result["unassigned_excess"] == []
