"""Two real spectra exported as CSV by other tools, through the CSV parser and the analysis pipeline.

- uraniumglass5minutes.csv: 5 min on uranium glass, "Energy (keV),Counts", calibrated; only 1,233 counts in total, so far too weak
  to identify anything (the test pins that it parses and that nothing is invented from it).
- community_spectrum_*.csv: a community-shared spectrum, "Data,Energy" where the second column is really the channel number
  (0..1023), so it must come out uncalibrated, with the counts in the first column."""
import pathlib

import pytest

from analysis_utils import analyze_spectrum_peaks
from csv_parser import parse_csv_spectrum

DATA = pathlib.Path(__file__).resolve().parent / "data" / "real_csv"
GLASS = DATA / "uraniumglass5minutes.csv"
COMMUNITY = DATA / "community_spectrum_b83c9ae0_Ologoto.csv"


def parse(path):
    return parse_csv_spectrum(path.read_bytes(), path.name)


def test_uranium_glass_csv_parses_as_a_calibrated_spectrum():
    result = parse(GLASS)
    assert len(result["counts"]) == len(result["energies"]) == 1024
    assert sum(result["counts"]) == 1233
    assert result["energies"][0] == pytest.approx(15.0)
    assert result["energies"][-1] == pytest.approx(7572.24)
    assert all(b > a for a, b in zip(result["energies"], result["energies"][1:]))
    assert result["is_calibrated"] is True
    assert result["metadata"]["filename"] == GLASS.name


def test_community_csv_energy_column_of_channel_numbers_is_not_a_calibration():
    result = parse(COMMUNITY)
    assert len(result["counts"]) == 1024
    assert sum(result["counts"]) == 599046
    assert result["energies"] == list(range(1024))
    assert result["is_calibrated"] is False


def test_uncalibrated_spectrum_is_not_identified_and_says_why():
    result = analyze_spectrum_peaks(parse(COMMUNITY), is_calibrated=False, live_time=300.0)
    assert result["isotopes"] == [] and result["decay_chains"] == []
    assert any("No energy calibration" in w for w in result["warnings"])
    assert result["peaks"], "peaks are still reported: they are what the user calibrates with"


def test_weak_uranium_glass_spectrum_runs_through_the_pipeline_without_inventing_a_series():
    result = analyze_spectrum_peaks(parse(GLASS), is_calibrated=True, live_time=300.0)
    assert result["decay_chains"] == []
    assert result["data_quality"]["low_statistics"] is True
    assert all(0 <= iso["confidence"] <= 100 for iso in result["isotopes"])
