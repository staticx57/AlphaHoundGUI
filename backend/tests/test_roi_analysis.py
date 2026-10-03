"""
ROI analysis: accuracy against synthetic spectra with known peak areas, for the AlphaHound (CsI(Tl), BGO) and the Radiacode
(103, 103G, 110) detector profiles; detection / non-detection; axes the instruments really produce; the uranium ratio.

The spectra are an exponential continuum (as tall as the peak, a hard case) plus Gaussians whose width follows the detector's
resolution, with Poisson noise from a fixed seed. Tolerances are a few sigma plus a small allowance for the curvature of the
continuum under a linear baseline (1-4 % measured).
"""

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from detector_efficiency import DETECTOR_DATABASE, interpolate_efficiency   # noqa: E402
from isotope_roi_database import ISOTOPE_ROI_DATABASE                         # noqa: E402
from spectrum_synth import THORIUM_SERIES, URANIUM_SERIES, linear_axis, make_spectrum, series_spectrum   # noqa: E402
from roi_analysis import ROIAnalyzer, analyze_roi, analyze_uranium_enrichment, channel_width_at  # noqa: E402

DEVICES = ["AlphaHound CsI(Tl)", "AlphaHound BGO", "Radiacode 103", "Radiacode 103G", "Radiacode 110"]
TRUTH = 3000.0


# --------------------------------------------------------------------------- accuracy
@pytest.mark.parametrize("detector", DEVICES)
@pytest.mark.parametrize("isotope", list(ISOTOPE_ROI_DATABASE))
def test_isolated_peak_net_counts_match_truth(detector, isotope):
    energy = ISOTOPE_ROI_DATABASE[isotope]["energy_keV"]
    e = linear_axis()
    y = make_spectrum(detector, [(energy, TRUTH)], e, seed=11)
    r = ROIAnalyzer(detector).analyze(e.tolist(), y.tolist(), isotope, 600)
    assert r.analysis_valid and r.detected
    assert abs(r.net_counts - TRUTH) <= 3.5 * r.uncertainty_sigma + 0.06 * TRUTH, (r.net_counts, r.uncertainty_sigma, r.background_method)
    # a sane uncertainty: Poisson on ~3000 counts over a continuum as tall as the peak
    assert 40 < r.uncertainty_sigma < 350


@pytest.mark.parametrize("detector", ["AlphaHound CsI(Tl)", "Radiacode 110"])
def test_resolvable_neighbours_are_separated(detector):
    """Co-60: both lines present, 160 keV apart. Each net count must be its own line, not the pair."""
    e = linear_axis()
    y = make_spectrum(detector, [(1173.2, TRUTH), (1332.5, TRUTH)], e, seed=5)
    a = ROIAnalyzer(detector)
    for isotope in ("Co-60 (1173 keV)", "Co-60 (1332 keV)"):
        r = a.analyze(e.tolist(), y.tolist(), isotope, 600)
        assert abs(r.net_counts - TRUTH) <= 3.5 * r.uncertainty_sigma + 0.06 * TRUTH, (isotope, r.net_counts)


def test_unresolved_neighbour_is_reported_not_hidden():
    """Cs-137 beside a Bi-214 609 keV line is closer than an AlphaHound can resolve: the result must say so."""
    e = linear_axis()
    y = make_spectrum("AlphaHound CsI(Tl)", [(661.7, TRUTH)], e)
    r = ROIAnalyzer("AlphaHound CsI(Tl)").analyze(e.tolist(), y.tolist(), "Cs-137 (662 keV)", 600)
    assert any("609.3" in w and "resolve" in w for w in r.warnings)


@pytest.mark.parametrize("detector", ["Radiacode 110", "Radiacode 103G"])
def test_quadratic_energy_axis(detector):
    """Radiacode spectra have a quadratic energy axis: the channel width differs by 25 % between 100 keV and 2.6 MeV."""
    ch = np.arange(1024)
    e = -5 + 2.7 * ch + 0.0004 * ch ** 2
    assert channel_width_at(e, 2600) > 1.2 * channel_width_at(e, 100)
    a = ROIAnalyzer(detector)
    for isotope, energy in (("Am-241 (60 keV)", 59.5), ("Cs-137 (662 keV)", 661.7), ("Tl-208 (2614 keV)", 2614.5)):
        y = make_spectrum(detector, [(energy, TRUTH)], e, seed=21)
        r = a.analyze(e.tolist(), y.tolist(), isotope, 600)
        assert abs(r.net_counts - TRUTH) <= 3.5 * r.uncertainty_sigma + 0.06 * TRUTH, (isotope, r.net_counts)


@pytest.mark.parametrize("detector", ["AlphaHound CsI(Tl)", "AlphaHound BGO"])
def test_coarse_alphahound_binning(detector):
    """The AlphaHound reports about 7.4 keV per channel."""
    e = 7.4 * (np.arange(400) + 0.5)
    a = ROIAnalyzer(detector)
    for isotope, energy in (("Cs-137 (662 keV)", 661.7), ("K-40 (1461 keV)", 1460.8), ("Th-234 (93 keV)", 92.6)):
        y = make_spectrum(detector, [(energy, TRUTH)], e, seed=31)
        r = a.analyze(e.tolist(), y.tolist(), isotope, 600)
        assert abs(r.net_counts - TRUTH) <= 3.5 * r.uncertainty_sigma + 0.08 * TRUTH, (isotope, r.net_counts)


def test_fractional_counts_are_not_truncated():
    """Background-subtracted spectra carry fractional counts; 0.4 counts per channel must not become 0."""
    e = linear_axis()
    y = make_spectrum("Radiacode 110", [(661.7, TRUTH)], e, seed=2)
    scaled = y * 0.01 + 0.4
    r = ROIAnalyzer("Radiacode 110").analyze(e.tolist(), scaled.tolist(), "Cs-137 (662 keV)", 600)
    assert abs(r.net_counts - TRUTH * 0.01) < 0.2 * TRUTH * 0.01 + 3 * r.uncertainty_sigma
    assert r.gross_counts > 0 and r.background_counts > 0


@pytest.mark.parametrize("detector", ["AlphaHound CsI(Tl)", "Radiacode 103", "Radiacode 110"])
@pytest.mark.parametrize("series, isotope, nuclide", [
    (THORIUM_SERIES, "Ac-228 (911 keV)", "Ac-228"),         # 965 and 969 keV lines of the same nuclide blend into the peak
    (URANIUM_SERIES, "Bi-214 (609 keV)", "Bi-214"),
    (URANIUM_SERIES, "Pb-214 (352 keV)", "Pb-214"),
])
def test_activity_accounts_for_lines_blended_into_the_peak(detector, series, isotope, nuclide):
    """Activity = counts / (efficiency x emission probability): the probability must include same-nuclide lines inside the peak."""
    truth_bq = 100.0
    e = linear_axis()
    _, y = series_spectrum(detector, series, truth_bq, 3600.0, seed=17)
    r = ROIAnalyzer(detector).analyze(e.tolist(), y.tolist(), isotope, 3600.0)
    assert r.detected and r.activity_bq
    sigma_bq = r.activity_uncertainty_bq or 0.0
    assert abs(r.activity_bq - truth_bq) <= 3.5 * sigma_bq + 0.12 * truth_bq, (r.activity_bq, sigma_bq, r.effective_branching_ratio)


def test_blended_lines_are_declared_in_the_result():
    e = linear_axis()
    _, y = series_spectrum("AlphaHound CsI(Tl)", THORIUM_SERIES, 100.0, 3600.0, seed=17)
    ac = analyze_roi(e.tolist(), y.tolist(), "Ac-228 (911 keV)", "AlphaHound CsI(Tl)", 3600.0)
    assert ac["effective_branching_ratio"] > ac["branching_ratio"] * 1.3
    assert any("964.8" in w and "969" in w for w in ac["warnings"])
    # a well separated line has nothing blended into it
    cs = analyze_roi(e.tolist(), make_spectrum("Radiacode 110", [(661.7, 3000)], e).tolist(), "Cs-137 (662 keV)", "Radiacode 110", 600)
    assert cs["effective_branching_ratio"] == cs["branching_ratio"]


# --------------------------------------------------------------------------- detection
@pytest.mark.parametrize("detector", DEVICES)
def test_no_peak_is_not_detected(detector):
    e = linear_axis()
    a = ROIAnalyzer(detector)
    false_positives = 0
    trials = 0
    for seed in range(8):
        y = make_spectrum(detector, [], e, seed=100 + seed)
        for isotope in ("Cs-137 (662 keV)", "Co-60 (1332 keV)", "K-40 (1461 keV)", "Bi-214 (609 keV)", "Th-234 (93 keV)"):
            r = a.analyze(e.tolist(), y.tolist(), isotope, 600)
            trials += 1
            false_positives += bool(r.detected)
            assert r.activity_bq is None and r.mda_bq and r.mda_bq > 0      # a limit, never an activity
    assert false_positives <= 0.10 * trials      # SNR >= 2 is a ~2 % test per isotope; keep room for the sampling


def test_empty_and_flat_spectra():
    e = linear_axis()
    a = ROIAnalyzer("Radiacode 110")
    for y in (np.zeros_like(e), np.full_like(e, 5.0)):
        r = a.analyze(e.tolist(), y.tolist(), "Cs-137 (662 keV)", 600)
        assert not r.detected and r.net_counts < 1.0
        assert math.isfinite(r.uncertainty_sigma) and math.isfinite(r.detection_limit_counts)


def test_roi_outside_spectrum_is_flagged_not_analysed():
    e = linear_axis()[:200]                     # stops at ~590 keV
    y = make_spectrum("Radiacode 110", [(661.7, TRUTH)], linear_axis(), seed=3)[:200]
    r = ROIAnalyzer("Radiacode 110").analyze(e.tolist(), y.tolist(), "Cs-137 (662 keV)", 600)
    assert r.analysis_valid is False and r.detected is False
    assert r.activity_bq is None and r.mda_bq is None
    assert "outside" in r.detection_status.lower() or "not analys" in r.detection_status.lower()


def test_activity_follows_net_efficiency_branching_time():
    e = linear_axis()
    y = make_spectrum("Radiacode 110", [(661.7, TRUTH)], e, seed=4)
    d = analyze_roi(e.tolist(), y.tolist(), "Cs-137 (662 keV)", "Radiacode 110", 600)
    eff = interpolate_efficiency("Radiacode 110", 661.7)
    assert d["activity_bq"] == pytest.approx(d["net_counts"] / (eff * d["branching_ratio"] * 600), rel=0.01)
    assert d["activity_uncertainty_bq"] == pytest.approx(d["uncertainty_sigma"] / (eff * d["branching_ratio"] * 600), rel=0.02)
    assert d["mda_bq"] < d["activity_bq"]


@pytest.mark.parametrize("bad", [
    dict(energies=[1.0] * 5, counts=[1.0] * 5),                           # too short
    dict(energies=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], counts=[1.0] * 9),     # mismatched
    dict(energies=[1.0] * 10, counts=[1.0] * 10),                         # repeated energies
    dict(energies=list(range(10)), counts=[1.0] * 9 + [float("nan")]),    # not a number
])
def test_bad_input_raises_value_error(bad):
    with pytest.raises(ValueError):
        ROIAnalyzer("Radiacode 110").analyze(bad["energies"], bad["counts"], "Cs-137 (662 keV)", 600)


def test_unknown_isotope_and_detector():
    e = linear_axis()
    with pytest.raises(ValueError):
        ROIAnalyzer("Radiacode 110").analyze(e.tolist(), np.ones_like(e).tolist(), "Xx-999", 600)
    with pytest.raises(ValueError):
        ROIAnalyzer("No Such Detector")


# --------------------------------------------------------------------------- uranium ratio
def uranium_glass_spectrum(detector, th234=1500.0, u235=600.0, bi214=3000.0, seed=9):
    """Th-234 93 keV, U-235 186 keV (plus the Ra-226 186 keV line that rides with Bi-214), Bi-214 609 keV."""
    eff = lambda en: interpolate_efficiency(detector, en)
    ra_186 = bi214 * (3.64 / 45.49) * (eff(186.2) / eff(609.3))
    e = linear_axis()
    return e, make_spectrum(detector, [(92.6, th234), (185.7, u235 + ra_186), (609.3, bi214)], e, seed=seed), ra_186


@pytest.mark.parametrize("detector", ["AlphaHound CsI(Tl)", "Radiacode 110"])
def test_ra226_correction_is_applied_to_the_ratio(detector):
    e, y, ra_186 = uranium_glass_spectrum(detector)
    plain = analyze_uranium_enrichment(e.tolist(), y.tolist(), detector, 600, "auto")
    glass = analyze_uranium_enrichment(e.tolist(), y.tolist(), detector, 600, "uranium_glass")
    assert plain["ra226_interference"] is True and plain["category"].startswith("Indeterminate")
    assert glass["ra226_interference"] is False
    # the corrected 186 keV count is the raw one minus the Ra-226 share: it must go down, and by about that share
    assert glass["u235_net_counts"] < plain["u235_net_counts"]
    assert plain["u235_net_counts"] - glass["u235_net_counts"] == pytest.approx(ra_186, rel=0.45)
    assert glass["ratio_percent"] < plain["ratio_percent"]
    assert glass["u235_uncertainty"] > 0 and glass["ratio_uncertainty"] > 0


def test_uranium_ratio_with_no_uranium():
    e = linear_axis()
    y = make_spectrum("Radiacode 110", [(1460.8, TRUTH)], e, seed=8)
    result = analyze_uranium_enrichment(e.tolist(), y.tolist(), "Radiacode 110", 600, "uranium_glass")
    assert result["can_analyze"] is False


def test_uranium_glass_without_bi214_does_not_crash():
    """Source type says glass but there is no Bi-214 peak: the correction is skipped, the endpoint must not raise."""
    e = linear_axis()
    y = make_spectrum("Radiacode 110", [(92.6, 1500.0), (185.7, 600.0)], e, seed=12)
    result = analyze_uranium_enrichment(e.tolist(), y.tolist(), "Radiacode 110", 600, "uranium_glass")
    assert "category" in result and result["u235_net_counts"] >= 0


# --------------------------------------------------------------------------- API
def test_roi_endpoint_accepts_fractional_counts_and_both_device_families():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    e = linear_axis()
    for detector in ("AlphaHound CsI(Tl)", "Radiacode 110"):
        y = make_spectrum(detector, [(661.7, TRUTH)], e, seed=13) * 0.5 + 0.25
        response = client.post("/analyze/roi", json={"energies": e.tolist(), "counts": y.tolist(), "isotope": "Cs-137 (662 keV)",
                                                     "detector": detector, "acquisition_time_s": 600})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["detected"] and abs(body["net_counts"] - TRUTH / 2) < 0.2 * TRUTH / 2
        assert body["detector"] == detector


def test_roi_endpoint_rejects_unknown_detector_with_400():
    from fastapi.testclient import TestClient
    from main import app
    e = linear_axis()
    response = TestClient(app).post("/analyze/roi", json={"energies": e.tolist(), "counts": [1.0] * len(e), "isotope": "Cs-137 (662 keV)",
                                                          "detector": "Nope", "acquisition_time_s": 600})
    assert response.status_code == 400
