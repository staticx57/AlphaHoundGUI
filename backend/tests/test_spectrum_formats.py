"""Reading spectrum files written by another program.

SpecUtils (Sandia, the library behind InterSpec) is the independent writer here: if the application reads back exactly what it
wrote, the application's parsers agree with the real formats. Until now neither the CHN nor the SPE parser had a test, and the
"100+ other formats" path imported a module (`SandiaSpecUtils`) that does not exist (the package installs `SpecUtils`), so every
.pcf/.spc/.cnf/... upload was refused."""
import math

import pytest
from fastapi.testclient import TestClient

SpecUtils = pytest.importorskip("SpecUtils")

from formats.chn_spe_parser import parse_chn_file, parse_spe_file
from formats.specutils_parser import parse_spectrum_generic
from main import app

N = 1024
COUNTS = [(i * 7 + 3) % 211 + (500 if 300 <= i < 310 else 0) for i in range(N)]
COEFFS = [-3.0, 7.4, 1.0e-4]
LIVE, REAL = 600.0, 612.5
FORMATS = {
    "chn": SpecUtils.SaveSpectrumAsType.Chn,
    "spe": SpecUtils.SaveSpectrumAsType.SpeIaea,
    "pcf": SpecUtils.SaveSpectrumAsType.Pcf,
    "spc": SpecUtils.SaveSpectrumAsType.SpcBinaryInt,
    "cnf": SpecUtils.SaveSpectrumAsType.Cnf,
    "txt": SpecUtils.SaveSpectrumAsType.Txt,
}


def write_with_specutils(path, extension):
    spec_file, m = SpecUtils.SpecFile(), SpecUtils.Measurement()
    m.setGammaCounts(COUNTS, LIVE, REAL)
    m.setEnergyCalibration(SpecUtils.EnergyCalibration.fromPolynomial(N, COEFFS))
    m.setTitle("format test")
    spec_file.addMeasurement(m, True)
    target = path / f"spectrum.{extension}"
    spec_file.writeToFile(str(target), list(spec_file.sampleNumbers()), list(spec_file.detectorNames()), FORMATS[extension])
    return target


def energy_at(channel):
    return COEFFS[0] + COEFFS[1] * channel + COEFFS[2] * channel ** 2


def test_chn_file_from_another_program_is_read_exactly(tmp_path):
    result = parse_chn_file(str(write_with_specutils(tmp_path, "chn")))
    assert result["counts"] == COUNTS
    assert result["num_channels"] == N
    assert result["live_time"] == pytest.approx(LIVE, abs=0.02)
    assert result["real_time"] == pytest.approx(REAL, abs=0.02)
    cal = result["calibration"]
    assert [cal["a"], cal["b"], cal["c"]] == pytest.approx(COEFFS, rel=1e-5)
    assert result["energies"][500] == pytest.approx(energy_at(500), rel=1e-5)


def test_spe_file_from_another_program_is_read_exactly(tmp_path):
    result = parse_spe_file(str(write_with_specutils(tmp_path, "spe")))
    assert result["counts"] == COUNTS
    assert result["live_time"] == pytest.approx(LIVE) and result["real_time"] == pytest.approx(REAL)
    assert result["energies"][500] == pytest.approx(energy_at(500), rel=1e-5)


@pytest.mark.parametrize("extension", ["pcf", "spc", "cnf", "txt"])
def test_other_formats_are_read_through_specutils(tmp_path, extension):
    result = parse_spectrum_generic(str(write_with_specutils(tmp_path, extension)))
    assert result is not None, f".{extension} was not read at all"
    assert result["counts"] == COUNTS
    if extension != "txt":                                  # the text format carries the times as well, but not every variant does
        assert result["live_time"] == pytest.approx(LIVE) and result["real_time"] == pytest.approx(REAL)
    assert result["energies"][500] == pytest.approx(energy_at(500), rel=1e-4)
    assert result["energy_calibration"]["slope"] != 1


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.mark.parametrize("extension", ["chn", "spe", "pcf", "spc", "cnf"])
def test_upload_accepts_each_format(client, tmp_path, extension):
    path = write_with_specutils(tmp_path, extension)
    response = client.post("/upload", files={"file": (path.name, path.read_bytes(), "application/octet-stream")})
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["counts"]) == N and body["counts"] == COUNTS
    assert body["energies"][500] == pytest.approx(energy_at(500), rel=1e-4)
    assert not math.isnan(sum(body["energies"]))
