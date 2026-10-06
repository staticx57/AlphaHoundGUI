"""
spectroscopy/compton_edges.py: a peak near the Compton edge of a much stronger line is flagged (a hint with a hedge), nothing else is.
"""
import pytest

from spectroscopy.compton_edges import compton_edge_kev, flag_compton_edges

R662 = 0.10


def peak(energy, area):
    return {"energy": energy, "net_area": area}


def test_the_edge_of_cesium_137_is_where_physics_puts_it():
    assert compton_edge_kev(661.7) == pytest.approx(477.3, abs=0.2)
    assert compton_edge_kev(1332.5) == pytest.approx(1118.1, abs=0.5)      # Co-60
    assert compton_edge_kev(2614.5) == pytest.approx(2381.8, abs=1.0)      # Tl-208


def test_the_471_kev_bump_beside_cesium_137_is_flagged_as_its_edge():
    peaks = [peak(32.0, 40_000), peak(471.0, 60_000), peak(662.0, 900_000)]
    assert flag_compton_edges(peaks, R662) == 1
    assert peaks[1]["compton_edge_of"] == 662.0
    assert "compton_edge_of" not in peaks[0] and "compton_edge_of" not in peaks[2]


def test_the_synthetic_cesium_spectrums_451_kev_peak_is_flagged_too():
    """Half a width below the edge, as the peak finder reports it on the synthetic Cs-137 file."""
    peaks = [peak(451.0, 30_000), peak(662.0, 500_000)]
    assert flag_compton_edges(peaks, R662) == 1


def test_a_peak_that_is_not_much_weaker_than_the_line_is_not_an_edge():
    peaks = [peak(471.0, 400_000), peak(662.0, 500_000)]            # a real line of comparable size, not a shelf
    assert flag_compton_edges(peaks, R662) == 0


def test_a_peak_far_from_the_edge_is_not_flagged():
    peaks = [peak(350.0, 20_000), peak(662.0, 900_000), peak(1100.0, 5_000)]
    assert flag_compton_edges(peaks, R662) == 0


def test_low_energy_lines_have_no_clean_edge_to_flag():
    """Am-241's 59.5 keV: its edge is at 11 keV, under the threshold; and lines below 250 keV are never parents."""
    peaks = [peak(59.5, 5_000_000), peak(11.0, 100), peak(120.0, 100)]
    assert flag_compton_edges(peaks, R662) == 0


def test_flags_are_reset_on_every_call():
    peaks = [peak(471.0, 60_000), peak(662.0, 900_000)]
    flag_compton_edges(peaks, R662)
    assert "compton_edge_of" in peaks[0]
    peaks[1]["net_area"] = 10_000                                   # the parent is no longer much stronger
    flag_compton_edges(peaks, R662)
    assert "compton_edge_of" not in peaks[0]


def test_the_strongest_candidate_parent_wins():
    """Two lines whose edges are close: the larger one is named."""
    edge_a, edge_b = compton_edge_kev(661.7), compton_edge_kev(700.0)
    middle = (edge_a + edge_b) / 2
    peaks = [peak(middle, 20_000), peak(661.7, 300_000), peak(700.0, 900_000)]
    flag_compton_edges(peaks, R662)
    assert peaks[0]["compton_edge_of"] == 700.0


def test_degenerate_input_is_harmless():
    assert flag_compton_edges([], R662) == 0
    assert flag_compton_edges([peak(100.0, 5)], R662) == 0
    assert flag_compton_edges([{"energy": 500.0}, {"energy": 700.0}], R662) == 0     # no areas recorded
