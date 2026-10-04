"""POST /analyze/anomaly-detection: the ML cross-check must see the spectrum's energy axis, as /analyze/ml-identify does."""
from fastapi.testclient import TestClient

import ml.ml_analysis as ml_analysis
from main import app


class RecordingIdentifier:
    def __init__(self):
        self.calls = []

    def identify(self, counts, top_k=5, energies=None):
        self.calls.append(energies)
        return [{"isotope": "Th-232 series", "confidence": 90.0}]


def test_the_ml_check_gets_the_energy_axis(monkeypatch):
    """Without it the model assumes its own grid: on the real benchmark that is 3/9 right instead of 8/9."""
    stub = RecordingIdentifier()
    monkeypatch.setattr(ml_analysis, "get_ml_identifier", lambda *a, **k: stub)
    energies = [15.0 + 2.5 * i for i in range(200)]
    counts = [100.0 + (i % 7) for i in range(200)]
    response = TestClient(app).post("/analyze/anomaly-detection", json={"counts": counts, "energies": energies})
    assert response.status_code == 200
    assert stub.calls == [energies]


def test_without_an_axis_the_check_still_runs(monkeypatch):
    stub = RecordingIdentifier()
    monkeypatch.setattr(ml_analysis, "get_ml_identifier", lambda *a, **k: stub)
    response = TestClient(app).post("/analyze/anomaly-detection", json={"counts": [10.0] * 100})
    assert response.status_code == 200 and stub.calls == [None]
