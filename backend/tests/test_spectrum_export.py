"""PCF and CHN export: what is written must read back the same, and the calibration error must be reported, not hidden."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

pytest.importorskip("SpecUtils")

from formats.chn_spe_parser import parse_chn_file
from formats.specutils_parser import parse_spectrum_generic
from main import app

N = 1024
CHANNELS = np.arange(N)
COUNTS = [int((i * 13 + 5) % 307 + (900 if 400 <= i < 412 else 0)) for i in range(N)]
QUADRATIC = (15.0 + 7.4 * CHANNELS + 2.0e-4 * CHANNELS ** 2).tolist()
# the real AlphaHound axis: a cubic (a quadratic is off by almost 300 keV), coefficients fitted to a live device
DEVICE = (15.0001 + 1.68372 * CHANNELS - 4.75865e-05 * CHANNELS ** 2 + 5.49654e-06 * CHANNELS ** 3).tolist()
# an axis no polynomial of degree 3 reproduces: ripples of about 8 keV on a smooth curve
WAVY = (15.0 + 7.4 * CHANNELS + 2.0e-4 * CHANNELS ** 2 + 8.0 * np.sin(CHANNELS / 60.0)).tolist()
# one a quadratic nearly reproduces: ripples of 0.3 keV
SLIGHTLY_OFF = (15.0 + 7.4 * CHANNELS + 2.0e-4 * CHANNELS ** 2 + 0.3 * np.sin(CHANNELS / 60.0)).tolist()
METADATA = {"live_time": 600.0, "real_time": 612.5, "start_time": "2026-10-03T12:30:15Z", "source": "AlphaHound Device"}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def post(client, fmt, energies=QUADRATIC, counts=COUNTS, filename="run1.n42", metadata=METADATA):
    return client.post(f"/export/{fmt}", json={"counts": counts, "energies": energies, "metadata": metadata, "filename": filename})


def test_pcf_reads_back_with_counts_times_and_calibration(client, tmp_path):
    response = post(client, "pcf")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="run1.pcf"'
    path = tmp_path / "out.pcf"
    path.write_bytes(response.content)
    back = parse_spectrum_generic(str(path))
    assert back["counts"] == COUNTS
    assert back["live_time"] == pytest.approx(600.0) and back["real_time"] == pytest.approx(612.5)
    assert np.allclose(back["energies"], QUADRATIC, atol=0.01)
    assert float(response.headers["x-calibration-max-error-kev"]) < 0.01
    assert response.headers["x-calibration-calibrated"] == "true"


def test_chn_reads_back_with_counts_times_and_calibration(client, tmp_path):
    response = post(client, "chn")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="run1.chn"'
    path = tmp_path / "out.chn"
    path.write_bytes(response.content)
    back = parse_chn_file(str(path))
    assert back["counts"] == COUNTS
    assert back["live_time"] == pytest.approx(600.0, abs=0.02) and back["real_time"] == pytest.approx(612.5, abs=0.02)
    assert np.allclose(back["energies"], QUADRATIC, atol=0.01)


def read_back(fmt, content, tmp_path):
    path = tmp_path / f"back.{fmt}"
    path.write_bytes(content)
    return parse_chn_file(str(path)) if fmt == "chn" else parse_spectrum_generic(str(path))


def test_pcf_holds_the_real_devices_cubic_axis(client, tmp_path):
    response = post(client, "pcf", energies=DEVICE)
    assert response.status_code == 200
    back = read_back("pcf", response.content, tmp_path)
    assert back["counts"] == COUNTS
    assert float(np.abs(np.asarray(back["energies"]) - DEVICE).max()) < 0.1
    assert float(response.headers["x-calibration-max-error-kev"]) < 0.1


def test_chn_refuses_an_axis_its_three_coefficients_cannot_hold(client):
    response = post(client, "chn", energies=DEVICE)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "degree 2" in detail and "PCF" in detail


def test_chn_accepts_an_axis_a_quadratic_nearly_reproduces_and_reports_the_error(client, tmp_path):
    response = post(client, "chn", energies=SLIGHTLY_OFF)
    assert response.status_code == 200
    back = read_back("chn", response.content, tmp_path)
    actual = float(np.abs(np.asarray(back["energies"]) - SLIGHTLY_OFF).max())
    assert 0.05 < actual < 1.0
    assert float(response.headers["x-calibration-max-error-kev"]) == pytest.approx(actual, abs=0.02)


def test_pcf_reports_the_error_left_by_an_axis_no_cubic_reproduces(client, tmp_path):
    response = post(client, "pcf", energies=WAVY)
    assert response.status_code == 200
    back = read_back("pcf", response.content, tmp_path)
    actual = float(np.abs(np.asarray(back["energies"]) - WAVY).max())
    assert actual > 1                                                    # the file really is that far off ...
    assert float(response.headers["x-calibration-max-error-kev"]) == pytest.approx(actual, rel=0.05, abs=0.1)   # ... and says so


def test_a_spectrum_without_calibration_is_flagged(client):
    response = post(client, "pcf", energies=CHANNELS.astype(float).tolist())
    assert response.status_code == 200
    assert response.headers["x-calibration-calibrated"] == "false"


@pytest.mark.parametrize("fmt", ["pcf", "chn"])
def test_unusable_requests_are_the_clients_fault(client, fmt):
    assert post(client, fmt, counts=[1, 2], energies=[1.0, 2.0]).status_code == 400
    assert post(client, fmt, energies=QUADRATIC[:-1]).status_code == 400
    assert post(client, fmt, energies=[5.0] * N).status_code == 400
