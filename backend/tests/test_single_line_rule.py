"""
A peak may be the only evidence for an isotope only if it is strong enough and about as wide as the detector says a line at that energy is;
and the Compton-edge hint is withdrawn from a peak an isotope claims.
"""
from nuclides.isotope_database import _stands_alone
from spectroscopy.analysis_utils import _flag_compton_edges


def peak(significance=30.0, fwhm=10.0, expected=10.0, **extra):
    return {"energy": 59.5, "significance": significance, "fwhm": fwhm, "fwhm_expected": expected, **extra}


def test_a_strong_line_of_the_right_width_stands_alone():
    assert _stands_alone(peak(significance=500, fwhm=7.4, expected=8.0))        # a genuine Am-241 59.5 keV peak


def test_a_weak_peak_does_not():
    assert not _stands_alone(peak(significance=6.6))


def test_the_significance_bound_is_inclusive():
    assert _stands_alone(peak(significance=10.0))
    assert not _stands_alone(peak(significance=9.9))


def test_a_peak_too_narrow_or_too_wide_does_not():
    assert not _stands_alone(peak(fwhm=5.5, expected=10.0))                      # 0.55
    assert not _stands_alone(peak(fwhm=17.2, expected=10.0))                     # a Compton-edge bump, 1.72
    assert _stands_alone(peak(fwhm=6.0, expected=10.0))
    assert _stands_alone(peak(fwhm=16.0, expected=10.0))


def test_missing_measurements_are_not_judged():
    assert _stands_alone({"energy": 59.5})
    assert _stands_alone({"energy": 59.5, "significance": 40.0})
    assert _stands_alone({"energy": 59.5, "fwhm": 9.0})


DETECTOR = "RadiaCode-103"


def _peaks():
    return [{"energy": 471.0, "net_area": 60_000}, {"energy": 662.0, "net_area": 900_000}]


def test_an_unclaimed_edge_peak_keeps_its_hint():
    peaks = _peaks()
    _flag_compton_edges(peaks, DETECTOR, [])
    assert peaks[0].get("compton_edge_of") == 662.0


def test_a_peak_an_isotope_claims_loses_the_hint():
    peaks = _peaks()
    _flag_compton_edges(peaks, DETECTOR, [{"suppressed": False, "matched_peaks": [{"observed": 471.0}]}])
    assert "compton_edge_of" not in peaks[0]


def test_a_suppressed_isotopes_claim_does_not_count():
    peaks = _peaks()
    _flag_compton_edges(peaks, DETECTOR, [{"suppressed": True, "matched_peaks": [{"observed": 471.0}]}])
    assert peaks[0].get("compton_edge_of") == 662.0
