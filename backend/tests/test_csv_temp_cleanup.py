"""A CSV upload leaves no temporary file behind, whether it parses or is rejected (rejected files used to be left in the
temp directory, one per bad upload)."""
import os
import tempfile

import pytest

from csv_parser import parse_csv_spectrum

GOOD = b"energy,counts\n" + b"".join(f"{3 + 2.7 * i},{50 + i}\n".encode() for i in range(32))
REJECTED = {
    "text counts": b"channel,counts\n" + b"".join(f"{i},abc\n".encode() for i in range(10)),
    "infinite": b"channel,counts\n0,inf\n1,5\n2,5\n",
    "empty": b"",
    "header only": b"energy,counts\n",
}


@pytest.fixture
def private_tempdir(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return tmp_path


def test_parsed_csv_leaves_no_temp_file(private_tempdir):
    result = parse_csv_spectrum(GOOD, "good.csv")
    assert len(result["counts"]) == 32
    assert os.listdir(private_tempdir) == []


@pytest.mark.parametrize("name", sorted(REJECTED))
def test_rejected_csv_leaves_no_temp_file(private_tempdir, name):
    with pytest.raises(ValueError):
        parse_csv_spectrum(REJECTED[name], "bad.csv")
    assert os.listdir(private_tempdir) == []
