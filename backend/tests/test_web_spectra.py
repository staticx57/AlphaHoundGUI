"""
Identification on real spectra published by others (tests/data/web_spectra, each folder with its licence and README):
ckuethe/radiacode-tools (MIT) calibration sources and mixtures, dmamontov/periodic-table (MIT) a personal collection measured with a
RadiaCode. Expectations come from what each sample is (the authors' descriptions and the lines they confirmed), not from our output.
"""
import pathlib

import pytest

from formats.radiacode_xml_parser import parse_radiacode_xml
from spectroscopy.analysis_utils import analyze_spectrum_peaks

WEB = pathlib.Path(__file__).resolve().parent / "data" / "web_spectra"
ARTIFICIAL = ["Cs-137", "Co-60", "Am-241", "Ba-133", "Eu-152", "Na-22", "I-131", "Tc-99m", "F-18", "Tl-201", "Ir-192", "Se-75", "Co-57"]


def analysed(name):
    parsed = parse_radiacode_xml((WEB / name).read_text(encoding="utf-8"))
    return analyze_spectrum_peaks(parsed, True, float(parsed["metadata"].get("live_time") or 0))


def names(result):
    return {i["isotope"] for i in result["isotopes"]}, {c["parent"] for c in result["decay_chains"]}


@pytest.mark.parametrize("name, sources", [
    ("ckuethe/Co60_a.xml", {"Co-60"}),
    ("ckuethe/Cs137_b.xml", {"Cs-137"}),
    ("ckuethe/Co60_a+Cs137_b.xml", {"Co-60", "Cs-137"}),      # Co-60 was lost: its share of the counts is small next to Cs-137
    ("ckuethe/Eu152_b.xml", {"Eu-152"}),                       # was reported as the Th-232 series (244.7/344.3/964 keV on 238.6/338.3/969)
    ("ckuethe/Ba133_a.xml", {"Ba-133"}),
    ("ckuethe/Ba133_a+Eu152_b.xml", {"Ba-133", "Eu-152"}),
    ("ckuethe/data_am241.xml", {"Am-241"}),
    ("dmamontov/am-95-his07.xml", {"Am-241"}),
])
def test_calibration_sources_are_named_and_nothing_else_artificial(name, sources):
    isotopes, chains = names(analysed(name))
    assert sources <= isotopes
    assert not (isotopes & set(ARTIFICIAL)) - sources
    assert not chains


@pytest.mark.parametrize("name, chain", [
    ("dmamontov/ra-88-spd.xml", "U-238"), ("dmamontov/rn-86-spd.xml", "U-238"), ("dmamontov/ra-88-mazda0a2.xml", "U-238"),
    ("dmamontov/u-92-glass.xml", "U-238"), ("dmamontov/th-90-pendant.xml", "Th-232"), ("dmamontov/th-90-wt20.xml", "Th-232"),
    ("ckuethe/data_th232_plus_background.xml", "Th-232"),
])
def test_natural_sources_show_their_series_only(name, chain):
    isotopes, chains = names(analysed(name))
    assert chains == {chain}
    assert not isotopes & set(ARTIFICIAL)


@pytest.mark.parametrize("name", ["ckuethe/bg.xml", "dmamontov/bg-lead-shield.xml", "dmamontov/ni-28-r26.xml"])
def test_backgrounds_and_a_pure_beta_source_name_no_artificial_isotope(name):
    isotopes, chains = names(analysed(name))
    assert not isotopes & set(ARTIFICIAL)


@pytest.mark.parametrize("name", ["Orange Fiestaware Saucer.csv", "Orange Red Wing Chevron Salt Cellar.csv"])
def test_weak_uranium_glazes_are_not_called_thallium(name):
    """The U-235 lines (143.8/163.3 keV) sit on Tl-201's 135/167 keV. The fit uses its uranium template there (z 5.7-7.8), below the bar
    for reporting the series, but enough to explain those peaks: they were reported as Tl-201 at 41-49 %."""
    from formats.csv_parser import parse_csv_spectrum
    path = pathlib.Path(__file__).resolve().parent / "data" / "real_spectra" / "community" / name
    result = analyze_spectrum_peaks(parse_csv_spectrum(path.read_bytes(), name), True, 0)
    assert "Tl-201" not in {i["isotope"] for i in result["isotopes"]}


def test_gammavision_spe_with_a_unit_after_the_calibration_is_read():
    """GammaVision writes '$MCA_CAL:' coefficients followed by their unit ('... 0.000000E+000 keV'): the file was refused with
    'could not convert string to float'. becquerel test sample (LBNL licence in web_spectra/lbl-anp)."""
    from formats.chn_spe_parser import parse_spe_file
    result = parse_spe_file(str(WEB / "lbl-anp" / "Mendocino_07-10-13_Acq-10-10-13.Spe"))
    assert result["num_channels"] == 8192
    assert result["calibration"]["b"] == pytest.approx(0.378444)
    assert result["energies"][1000] == pytest.approx(378.444, abs=0.01)


def test_a_germanium_spectrum_that_names_no_detector_is_analysed_as_germanium():
    """An HPGe background (becquerel sample, 8192 channels): analysed as an AlphaHound CsI it read as Na-22 with no series. Its peak widths
    put it at germanium resolution, and at that resolution the natural series of a cave background are plain."""
    from formats.chn_spe_parser import parse_spe_file
    parsed = parse_spe_file(str(WEB / "lbl-anp" / "1110C NAA cave background May 2017.spe"))
    parsed["metadata"]["live_time"] = parsed.get("live_time", 0)
    result = analyze_spectrum_peaks(parsed, parsed["calibration"] is not None, parsed.get("live_time", 0))
    assert result["detector_profile"] == "HPGe (generic)" and result["measured_resolution_662"] < 0.01
    assert {c["parent"] for c in result["decay_chains"]} == {"U-238", "Th-232"}
    assert "Na-22" not in {i["isotope"] for i in result["isotopes"]}


def test_a_scintillator_file_keeps_the_scintillator_profile():
    parsed = parse_radiacode_xml((WEB / "ckuethe" / "Cs137_b.xml").read_text(encoding="utf-8"))
    parsed["metadata"] = {k: v for k, v in parsed["metadata"].items() if "adia" not in str(v)}   # strip the device name
    result = analyze_spectrum_peaks(parsed, True, 300.0)
    assert result["detector_profile"] != "HPGe (generic)" and result["measured_resolution_662"] > 0.05


def test_an_spe_with_all_zero_calibration_coefficients_is_uncalibrated():
    """digiBASE writes '0 0 0' under $MCA_CAL when it has no calibration: that was taken as one, every channel at 0 keV."""
    from formats.chn_spe_parser import parse_spe_file
    result = parse_spe_file(str(WEB / "lbl-anp" / "digibase_5min_30_1.spe"))
    assert result["calibration"] is None
    assert result["energies"] == list(range(result["num_channels"]))
