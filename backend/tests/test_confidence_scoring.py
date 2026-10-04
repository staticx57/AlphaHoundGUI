"""
The enhanced isotope confidence must come from the isotope's own matched peaks.

It read `matched_energy` / `energy` from the identification, keys the line matcher never writes, so every isotope was scored as a perfect
match of a line at 0 keV: the result was a constant set by table membership (Th-232 and U-238 always 74 %, any isotope missing from the
intensity table 71 %, Ba-133 53.5 %, Am-241 43.5 %), whatever the spectrum held. A single backscatter bump made Tl-201 (71 %) outrank the
three strong lines of a real Ba-133 source (53.5 %).
"""
from nuclides.isotope_database import identify_isotopes
from spectroscopy.confidence_scoring import enhance_isotope_identifications


def peak(energy, counts=5000.0):
    return {"energy": energy, "counts": counts, "area": counts, "snr": 30.0, "r_squared": 0.98, "fit_valid": True}


def scored(peaks):
    return {i["isotope"]: i for i in enhance_isotope_identifications(identify_isotopes(peaks, energy_tolerance=20.0), peaks)}


def test_three_strong_lines_outrank_one_coincidental_line():
    """The real Ba-133 source's peaks: 81, 303, 356 keV and a 164 keV backscatter bump that sits on Tl-201's 167 keV line."""
    result = scored([peak(81.0), peak(164.0, 800.0), peak(303.0), peak(356.0, 9000.0)])
    assert result["Ba-133"]["confidence"] > result["Tl-201"]["confidence"]


def test_the_score_follows_the_spectrum_not_the_isotope_name():
    good = scored([peak(661.7)])["Cs-137"]["confidence"]
    off = scored([peak(675.0)])["Cs-137"]["confidence"]      # same isotope, the peak 13 keV away from the line
    weak = scored([{"energy": 661.7, "counts": 40.0, "snr": 2.5}])["Cs-137"]["confidence"]
    assert good > off and good > weak


def test_matched_energy_recorded_is_the_observed_peak():
    result = scored([peak(661.0)])["Cs-137"]
    assert result["matched_energy"] == 661.0 and result["expected_energy"] == 661.7


def test_one_peak_cannot_stand_for_two_lines_of_the_same_isotope():
    """A 164 keV bump matched both Tl-201 lines (135 and 167 keV) and scored a 2/2 'match'; it is one line's worth of evidence."""
    tl = {i["isotope"]: i for i in identify_isotopes([peak(164.0)], energy_tolerance=30.0)}["Tl-201"]
    assert tl["matches"] == 1 and [m["expected"] for m in tl["matched_peaks"]] == [167.0]
    ba = {i["isotope"]: i for i in identify_isotopes([peak(305.0), peak(354.0)], energy_tolerance=30.0)}["Ba-133"]
    observed = [m["observed"] for m in ba["matched_peaks"]]
    assert len(observed) == len(set(observed)) == 2


def test_low_energy_tolerance_follows_the_detector_resolution():
    """Pb X-rays (74 keV, lead shield) are 14.5 keV from Am-241's 59.5 keV line: inside a fixed 20 keV window, outside a RadiaCode peak."""
    found = lambda peaks, det: {i["isotope"] for i in identify_isotopes(peaks, energy_tolerance=20.0, detector=det)}
    assert "Am-241" not in found([peak(74.0)], "Radiacode 103")
    assert "Am-241" in found([peak(61.0)], "Radiacode 103")
    assert "Am-241" in found([peak(74.0)], None)                       # no detector: the configured tolerance, as before
    # high energies keep the configured tolerance (the resolution term is wider there)
    assert "Cs-137" in found([peak(675.0)], "Radiacode 103")


def test_the_matchers_physics_caps_survive_the_rescoring():
    """A two-line isotope seen through one line is capped by the validation rules (Tl-201: both 135 and 167 keV required); the rescoring
    replaced the capped value and the cap was lost, so a single 167 keV bump on a uranium glaze read as Tl-201 at 41-49 %."""
    peaks = [peak(171.6, 181.0), peak(100.3, 268.0)]
    raw = {i["isotope"]: i for i in identify_isotopes(peaks, energy_tolerance=30.0)}
    assert raw["Tl-201"]["matches"] == 1 and raw["Tl-201"]["confidence"] <= 20.0
    assert scored(peaks)["Tl-201"]["confidence"] <= 20.0
