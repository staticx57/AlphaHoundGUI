"""CSV column handling: single-column files, calibration lines above the table, and the delimiters that must keep working.

Each of the first three used to be read wrongly: pandas guessed the delimiter among all characters and split a one-column file
on a letter of its header (the counts ended up on the energy axis, or the first value was lost), and a 'Calibration: a0 a1'
line as the first line was taken for the header."""
import pytest

from formats.csv_parser import parse_csv_spectrum

COUNTS = [57, 50, 61, 49, 55, 52, 58, 47, 53, 60, 48, 51]
ENERGIES = [round(3.0 + 2.7 * i, 3) for i in range(len(COUNTS))]


def lines(*rows):
    return ("\n".join(rows) + "\n").encode("utf-8")


def parse(data):
    return parse_csv_spectrum(data, "t.csv")


@pytest.mark.parametrize("header", ["counts", "Counts", "Data"])
def test_single_column_with_header_is_counts_on_a_channel_axis(header):
    result = parse(lines(header, *map(str, COUNTS)))
    assert result["counts"] == COUNTS
    assert result["energies"] == list(range(len(COUNTS)))
    assert result["is_calibrated"] is False


def test_headerless_single_column_keeps_its_first_value():
    result = parse(lines(*map(str, COUNTS)))
    assert result["counts"] == COUNTS
    assert result["is_calibrated"] is False


def test_single_column_with_duration_comment_keeps_the_time():
    result = parse(b"# duration_s,300\n" + lines("counts", *map(str, COUNTS)))
    assert result["counts"] == COUNTS and result["metadata"]["live_time"] == 300.0
    assert result["is_calibrated"] is False


def test_calibration_line_above_the_table_calibrates_the_spectrum():
    result = parse(b"Calibration: 2.0 3.1\n" + lines("counts", *map(str, COUNTS)))
    assert result["counts"] == COUNTS
    assert result["energies"][:3] == pytest.approx([2.0, 5.1, 8.2])
    assert result["is_calibrated"] is True


def test_trivial_calibration_line_means_channels():
    result = parse(b"Calibration: 0 1\n" + lines("counts", *map(str, COUNTS)))
    assert result["counts"] == COUNTS and result["is_calibrated"] is False


@pytest.mark.parametrize("sep", [",", ";", "\t"])
def test_energy_and_counts_columns_with_each_delimiter(sep):
    rows = [sep.join(("Energy (keV)", "Counts"))] + [sep.join((str(e), str(c))) for e, c in zip(ENERGIES, COUNTS)]
    result = parse(lines(*rows))
    assert result["counts"] == COUNTS
    assert result["energies"] == pytest.approx(ENERGIES)
    assert result["is_calibrated"] is True


def test_whitespace_separated_columns():
    result = parse(lines("energy counts", *(f"{e} {c}" for e, c in zip(ENERGIES, COUNTS))))
    assert result["counts"] == COUNTS and result["energies"] == pytest.approx(ENERGIES)


def test_excel_byte_order_mark_is_ignored():
    rows = ["energy,counts"] + [f"{e},{c}" for e, c in zip(ENERGIES, COUNTS)]
    result = parse(b"\xef\xbb\xbf" + lines(*rows))
    assert result["counts"] == COUNTS and result["is_calibrated"] is True


def test_undecodable_bytes_are_rejected_with_a_clear_error():
    with pytest.raises(ValueError):
        parse(b"energy,counts\n\xff\xfe,5\n1,6\n")


def test_unreadable_csv_says_why_and_needs_no_third_party_reader():
    """The parser is pandas only: an unreadable file is explained by the real cause (it used to be wrapped in a message about a
    spectrum library that cannot read CSV files, and the whole upload was refused when that library was not installed)."""
    with pytest.raises(ValueError) as caught:
        parse(b"")
    message = str(caught.value)
    assert "Becquerel" not in message and "No columns to parse" in message
