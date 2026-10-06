"""
tools/standardise_n42.py: an old N42 file (axis only as the app's own List/ChannelEnergies pair, which InterSpec and SpecUtils ignore) gets the
standard EnergyCalibration, and nothing else changes.
"""
import pathlib
import re
import shutil
import sys

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "tools"))

import recalibrate_n42 as rc            # noqa: E402
import standardise_n42 as std           # noqa: E402
from formats.n42_exporter import channel_edges, generate_n42_xml   # noqa: E402
from formats.n42_parser import parse_n42                            # noqa: E402

REAL = BACKEND / "tests" / "data" / "real_spectra"


@pytest.fixture(scope="module")
def old_file_text():
    """A real old-format file: an acquisition of December 2025 (placeholder axis) with the device's own axis restored."""
    text = (REAL / "takumar 942pm to 558am.n42").read_text(encoding="utf-8")
    return rc.recalibrate_text(text, rc.load_axis(REAL / "spectrum_2025-12-12_08-41-27.csv"))


def test_the_old_file_has_no_standard_calibration_and_the_upgrade_adds_it(old_file_text):
    assert "EnergyBoundaryValues" not in old_file_text
    upgraded = std.standardise_text(old_file_text)
    edges = [float(v) for v in re.search(r"<EnergyBoundaryValues>([^<]*)", upgraded).group(1).split()]
    energies = parse_n42(old_file_text)["energies"]
    assert len(edges) == len(energies) + 1
    assert edges == pytest.approx(channel_edges(energies), abs=1e-4)
    assert f'energyCalibrationReference="{std.ENERGY_CALIBRATION_ID}"' in upgraded
    assert f'<EnergyCalibration id="{std.ENERGY_CALIBRATION_ID}">' in upgraded


def test_the_upgrade_changes_nothing_but_the_two_additions(old_file_text):
    """The saved isotope identifications, times, instrument and counts survive: removing the two inserted pieces gives the original text."""
    upgraded = std.standardise_text(old_file_text)
    without_block = re.sub(r"[ \t]*<EnergyCalibration id=\"[^\"]*\">\n.*?</EnergyCalibration>\n", "", upgraded, count=1, flags=re.S)
    without_reference = re.sub(r' energyCalibrationReference="[^"]*"', "", without_block, count=1)
    assert without_reference == old_file_text
    assert "IsotopeIdentification" in upgraded or "IsotopeIdentification" not in old_file_text


def test_the_apps_own_parser_reads_the_same_spectrum_from_the_upgraded_file(old_file_text):
    before, after = parse_n42(old_file_text), parse_n42(std.standardise_text(old_file_text))
    assert after["counts"] == before["counts"] and after["energies"] == before["energies"]
    assert after["metadata"].get("live_time") == before["metadata"].get("live_time")


def test_other_software_reads_the_axis_after_the_upgrade_and_not_before(old_file_text, tmp_path):
    """SpecUtils (what InterSpec reads files with): no energy axis from the old file, the right one from the upgraded file."""
    pytest.importorskip("SpecUtils")
    from formats.specutils_parser import parse_spectrum_generic
    old, new = tmp_path / "old.n42", tmp_path / "new.n42"
    old.write_text(old_file_text, encoding="utf-8")
    new.write_text(std.standardise_text(old_file_text), encoding="utf-8")
    assert not (parse_spectrum_generic(str(old)).get("energies") or [])
    energies = parse_spectrum_generic(str(new))["energies"]
    ours = parse_n42(old_file_text)["energies"]
    assert len(energies) == len(ours)
    lower_edges = channel_edges(ours)[:-1]                              # SpecUtils reports each channel's lower edge, not its centre
    assert max(abs(a - b) for a, b in zip(energies, lower_edges)) < 0.01


def test_a_file_that_is_already_standard_is_left_alone():
    current = generate_n42_xml({"counts": [1, 2, 3, 4], "energies": [10.0, 12.0, 14.0, 16.0], "metadata": {"live_time": 5.0}})
    with pytest.raises(std.AlreadyStandard):
        std.standardise_text(current)


def test_the_placeholder_axis_is_refused_with_the_way_out():
    placeholder = (REAL / "takumar 942pm to 558am.n42").read_text(encoding="utf-8")
    with pytest.raises(std.NotStandardisable, match="recalibrate_n42"):
        std.standardise_text(placeholder)


@pytest.mark.parametrize("broken, reason", [("<RadInstrumentData><RadMeasurement/></RadInstrumentData>", "ChannelEnergies"),
                                             ("<ChannelEnergies>1.0</ChannelEnergies><RadMeasurement>", "fewer than two")])
def test_a_file_without_a_usable_axis_is_refused(broken, reason):
    with pytest.raises(std.NotStandardisable, match=reason):
        std.standardise_text(broken)


def test_the_command_writes_a_copy_and_never_touches_the_original(old_file_text, tmp_path, capsys):
    source = tmp_path / "run.n42"
    source.write_text(old_file_text, encoding="utf-8")
    original_bytes = source.read_bytes()
    assert std.main([str(source)]) == 0
    assert source.read_bytes() == original_bytes
    written = tmp_path / "run.std.n42"
    assert written.exists() and "EnergyBoundaryValues" in written.read_text(encoding="utf-8")
    assert "OK" in capsys.readouterr().out


def test_the_command_skips_a_standard_file_fails_a_placeholder_one_and_says_which(old_file_text, tmp_path, capsys):
    standard = tmp_path / "standard.n42"
    standard.write_text(generate_n42_xml({"counts": [1, 2, 3, 4], "energies": [10.0, 12.0, 14.0, 16.0], "metadata": {}}), encoding="utf-8")
    placeholder = tmp_path / "placeholder.n42"
    shutil.copy(REAL / "takumar 942pm to 558am.n42", placeholder)
    out = tmp_path / "out"
    assert std.main([str(standard), str(placeholder), "--out-dir", str(out)]) == 1
    text = capsys.readouterr().out
    assert "SKIP  standard.n42" in text and "FAIL  placeholder.n42" in text
    assert not list(out.glob("*")) if out.exists() else True
