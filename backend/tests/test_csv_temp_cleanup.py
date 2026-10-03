"""A CSV upload leaves no temporary file behind, whether it parses or is rejected (rejected files used to be left in the
temp directory, one per bad upload). The parser is given its own folder to work in, so the folder can be inspected."""
import os

import pytest

from formats.csv_parser import parse_csv_spectrum

GOOD = b"energy,counts\n" + b"".join(f"{3 + 2.7 * i},{50 + i}\n".encode() for i in range(32))
REJECTED = {
    "text counts": b"channel,counts\n" + b"".join(f"{i},abc\n".encode() for i in range(10)),
    "infinite": b"channel,counts\n0,inf\n1,5\n2,5\n",
    "empty": b"",
    "header only": b"energy,counts\n",
}


def test_parsed_csv_leaves_no_temp_file(tmp_path):
    result = parse_csv_spectrum(GOOD, "good.csv", temp_dir=str(tmp_path))
    assert len(result["counts"]) == 32
    assert os.listdir(tmp_path) == []


@pytest.mark.parametrize("name", sorted(REJECTED))
def test_rejected_csv_leaves_no_temp_file(tmp_path, name):
    with pytest.raises(ValueError):
        parse_csv_spectrum(REJECTED[name], "bad.csv", temp_dir=str(tmp_path))
    assert os.listdir(tmp_path) == []


def test_the_folder_argument_is_really_used(tmp_path):
    """Without this the two tests above could pass for nothing: a folder that does not exist must fail loudly."""
    with pytest.raises(OSError):
        parse_csv_spectrum(GOOD, "good.csv", temp_dir=str(tmp_path / "does_not_exist"))
