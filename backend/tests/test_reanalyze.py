"""Analysing a spectrum on an axis the user chose (the calibration dialog), and the validation of that dialog's calibration request."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

import spectrum_synth as ss
from main import app

DETECTOR = "AlphaHound CsI(Tl)"
AXIS = ss.linear_axis(1024, 3000.0)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def thorium_counts(seed=1):
    return ss.series_spectrum(DETECTOR, ss.THORIUM_SERIES, 400.0, live_time_s=3600.0, seed=seed, energies=AXIS)[1]


def test_the_axis_given_is_the_axis_analysed_and_peaks_follow_it(client):
    counts = thorium_counts()
    body = client.post("/analyze/reanalyze", json={"energies": AXIS.tolist(), "counts": counts.tolist(), "live_time": 3600.0,
                                                   "metadata": {"source": "AlphaHound Device", "calibration": {"slope": 2.93, "intercept": 1.46}}}).json()
    assert np.allclose(body["energies"], AXIS)
    assert body["metadata"]["calibration"] == {"slope": 2.93, "intercept": 1.46}               # the caller's metadata comes back
    assert "Th-232" in [c["parent"] for c in body["decay_chains"]]
    energies = [p["energy"] for p in body["peaks"]]
    assert any(abs(e - 238.6) < 15 for e in energies) and any(abs(e - 583.2) < 25 for e in energies), energies


def test_a_different_axis_moves_the_reported_peaks_with_it(client):
    counts = thorium_counts()
    stretched = AXIS * 1.10                                       # the same channels, labelled 10 % higher
    body = client.post("/analyze/reanalyze", json={"energies": stretched.tolist(), "counts": counts.tolist(), "live_time": 3600.0}).json()
    energies = [p["energy"] for p in body["peaks"]]
    assert any(abs(e - 1.10 * 238.6) < 20 for e in energies) and any(abs(e - 1.10 * 583.2) < 35 for e in energies), energies
    assert not any(abs(e - 238.6) < 10 for e in energies)               # nothing is left at the old position


@pytest.mark.parametrize("payload", [
    {"energies": [1.0, 2.0, 3.0], "counts": [1.0, 2.0]},                      # lengths differ
    {"energies": [1.0, 3.0, 2.0], "counts": [1.0, 2.0, 3.0]},                 # not increasing (a negative slope from bad points)
    {"energies": [1.0, 1.0, 2.0], "counts": [1.0, 2.0, 3.0]},                 # flat step
    {"energies": [], "counts": []},
])
def test_an_unusable_axis_is_refused(client, payload):
    assert client.post("/analyze/reanalyze", json=payload).status_code == 422


def test_the_calibration_dialog_request_is_checked(client):
    ok = client.post("/analyze/calibrate", json={"channels": [100, 200], "known_energies": [330, 660]})
    assert ok.status_code == 200 and ok.json()["params"]["slope"] == pytest.approx(3.3)
    assert client.post("/analyze/calibrate", json={"channels": [100, 200, 300], "known_energies": [330, 660]}).status_code == 422
    assert client.post("/analyze/calibrate", json={"channels": [100, 100], "known_energies": [330, 660]}).status_code == 422
