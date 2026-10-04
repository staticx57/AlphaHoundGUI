"""
The "Fit Peaks" Gaussian fit (POST /analyze/fit-peaks): position, width and area of peaks whose truth is known.

It used a fixed +-10 keV window. A scintillator peak is 25 to 130 keV wide (FWHM), so the window held less than one FWHM: on every real
AlphaHound and Radiacode spectrum the table showed FWHMs of 0.1-0.7 % and areas 10-100 times too small, and where the AlphaHound's
channels are wider than 4 keV (above ~400 keV) the window held fewer than 5 channels and the peak was silently left out.
"""
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

import spectrum_synth as ss
from main import app
from spectroscopy.spectral_analysis import fit_gaussian

CUBIC = 15.0001 + 1.68372 * np.arange(1024) - 4.75865e-05 * np.arange(1024) ** 2 + 5.49654e-06 * np.arange(1024) ** 3  # the AlphaHound's axis
RADIACODE = 5.56 + 2.36 * np.arange(1024) + 4.0e-4 * np.arange(1024) ** 2                                              # ~2.4 keV/ch, quadratic
LINES = [(238.6, 60000.0), (661.7, 40000.0), (1460.8, 15000.0), (2614.5, 6000.0)]


def truth_fwhm(detector, energy):
    return ss.DETECTOR_DATABASE[detector]["energy_resolution_662keV"] * 662.0 * math.sqrt(energy / 662.0)


@pytest.mark.parametrize("detector, axis", [("AlphaHound CsI(Tl)", CUBIC), ("Radiacode 110", RADIACODE), ("Radiacode 103", ss.linear_axis())])
@pytest.mark.parametrize("seed", [1, 2])
def test_scintillator_peaks_get_their_real_width_and_area(detector, axis, seed):
    counts = ss.make_spectrum(detector, LINES, axis, continuum=300.0, seed=seed)
    fits = fit_gaussian(axis, counts, [e for e, _ in LINES])
    assert len(fits) == len(LINES)                                   # none silently dropped on a coarse channel
    for fit, (energy, area) in zip(fits, LINES):
        assert fit["energy"] == pytest.approx(energy, rel=0.01)
        assert fit["fwhm"] == pytest.approx(truth_fwhm(detector, energy), rel=0.15)
        assert fit["net_area"] == pytest.approx(area, rel=0.12)
        assert fit["net_area_unc"] > 0


def test_a_narrow_germanium_peak_keeps_a_narrow_window():
    """An HPGe line (1.6 keV FWHM on 0.5 keV channels) next to another 12 keV away: each is fitted on its own."""
    axis = np.arange(4096) * 0.5
    rng = np.random.default_rng(3)
    y = np.full(axis.size, 20.0)
    for energy, area in ((661.7, 20000.0), (673.7, 10000.0)):
        s = 1.6 / 2.3548
        y += area * 0.5 / (s * math.sqrt(2 * math.pi)) * np.exp(-0.5 * ((axis - energy) / s) ** 2)
    counts = rng.poisson(y).astype(float)
    fits = fit_gaussian(axis, counts, [661.7, 673.7])
    assert [round(f["energy"], 0) for f in fits] == [662.0, 674.0]
    assert fits[0]["fwhm"] == pytest.approx(1.6, rel=0.15) and fits[0]["net_area"] == pytest.approx(20000.0, rel=0.05)
    assert fits[1]["net_area"] == pytest.approx(10000.0, rel=0.05)


def test_the_route_fits_every_detected_peak_of_an_alphahound_spectrum():
    counts = ss.make_spectrum("AlphaHound CsI(Tl)", LINES, CUBIC, seed=4)
    body = TestClient(app).post("/analyze/fit-peaks", json={"energies": CUBIC.tolist(), "counts": counts.tolist(),
                                                             "peaks": [{"energy": e} for e, _ in LINES]}).json()
    assert len(body["fits"]) == len(LINES)
    assert all(5.0 < f["fwhm"] / f["energy"] * 100 < 20.0 for f in body["fits"])    # a CsI resolution, not 0.1-0.7 %


def test_real_radiacode_radium_lines_are_fitted_at_the_detectors_resolution():
    """RadiaCode-103 Ra-226 capture (committed, MIT): the 186/242/295/352/609 keV lines, each at a scintillator width, not a sliver."""
    import pathlib
    from formats.radiacode_xml_parser import parse_radiacode_xml
    path = pathlib.Path(__file__).resolve().parent / "data" / "radiacode_fisicas" / "Ra-226.xml"
    parsed = parse_radiacode_xml(path.read_text(encoding="utf-8"))
    fits = fit_gaussian(parsed["energies"], parsed["counts"], [182.8, 237.5, 289.6, 345.8, 592.0])
    assert len(fits) == 5
    for fit, line in zip(fits, (186.2, 242.0, 295.2, 351.9, 609.3)):
        assert abs(fit["energy"] / line - 1) < 0.04                     # this unit reads ~2-3 % low (see the calibration check)
        assert 6.0 < fit["fwhm"] / fit["energy"] * 100 < 14.0
        assert fit["net_area"] > 3 * fit["net_area_unc"]                 # the 186 keV line sits on a flank: about 5 sigma
