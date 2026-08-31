"""
Route registration and decay-prediction endpoint tests.

The decay-prediction route was registered three times in analysis.py, so every
request was served by the first (single-engine) handler and the engine selector
was silently ignored. These tests guard against that whole class of bug.
"""

import pytest
from collections import Counter

from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_no_duplicate_route_registrations():
    """Every (path, method) pair must be registered exactly once.

    FastAPI resolves to the first match, so a duplicate silently shadows the
    later handler rather than raising.
    """
    registered = Counter()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in methods:
            registered[(path, method)] += 1

    duplicates = {key: n for key, n in registered.items() if n > 1}
    assert not duplicates, f"Duplicate route registrations shadow later handlers: {duplicates}"


def test_decay_engines_listed(client):
    response = client.get("/analyze/decay-engines")
    assert response.status_code == 200

    body = response.json()
    names = {e["name"] for e in body["engines"]}
    assert {"builtin", "radioactivedecay", "curie", "pyne"} <= names

    # builtin has no third-party dependency, so it is always available
    builtin = next(e for e in body["engines"] if e["name"] == "builtin")
    assert builtin["available"] is True

    # the advertised default must itself be available
    default = next(e for e in body["engines"] if e["name"] == body["default"])
    assert default["available"] is True


@pytest.mark.parametrize("engine", ["auto", "builtin", "radioactivedecay", "curie"])
def test_decay_prediction_honors_engine_selection(client, engine):
    response = client.post("/analyze/decay-prediction", json={
        "isotope": "U-238",
        "initial_activity_bq": 1000.0,
        "duration_days": 3652.5,
        "engine": engine,
    })
    assert response.status_code == 200

    body = response.json()
    if engine != "auto":
        assert body["engine_used"] == engine


def test_decay_prediction_unavailable_engine_falls_back(client):
    """An unavailable engine must degrade to builtin, and say so."""
    response = client.post("/analyze/decay-prediction", json={
        "isotope": "Cs-137",
        "initial_activity_bq": 1000.0,
        "duration_days": 365.0,
        "engine": "pyne",
    })
    assert response.status_code == 200
    assert response.json()["engine_used"] in ("pyne", "builtin")


@pytest.mark.parametrize("engine", ["auto", "builtin", "radioactivedecay", "curie"])
@pytest.mark.parametrize("isotope", ["Cs-137", "U-238"])
def test_decay_result_shape_is_consistent(client, engine, isotope):
    """Every engine must return the shape the decay chart consumes."""
    response = client.post("/analyze/decay-prediction", json={
        "isotope": isotope,
        "initial_activity_bq": 1000.0,
        "duration_days": 3652.5,
        "engine": engine,
    })
    assert response.status_code == 200
    body = response.json()

    for key in ("isotopes", "time_points_days", "activities", "series",
                "time_points", "time_labels", "engine_used"):
        assert key in body, f"{engine}/{isotope} result missing '{key}'"

    n_points = len(body["time_points_days"])
    assert n_points > 1
    assert len(body["time_points"]) == n_points
    assert len(body["time_labels"]) == n_points

    assert body["isotopes"], "no isotopes returned"
    for nuclide in body["isotopes"]:
        assert nuclide in body["activities"]
        assert len(body["activities"][nuclide]) == n_points

    # Parent activity must start at the requested value and never grow.
    parent = body["activities"].get(isotope)
    if parent:
        assert parent[0] == pytest.approx(1000.0, rel=0.02)
        assert parent[-1] <= parent[0] * 1.0001


CSV_PLAIN = b"\n".join(b"%d,%d" % (ch, n) for ch, n in
                       [(0, 100), (1, 150), (2, 900), (3, 150), (4, 100)]) + b"\n"

CSV_WITH_ENERGY = (b"Energy (keV),Counts\n" +
                   b"\n".join(b"%.1f,%d" % (e, n) for e, n in
                              [(10.0, 100), (20.0, 150), (30.0, 900),
                               (40.0, 150), (50.0, 100)]) + b"\n")


@pytest.mark.parametrize("name,body", [
    ("spec.csv", CSV_PLAIN),
    ("spec_with_energy.csv", CSV_WITH_ENERGY),
])
def test_upload_non_n42_formats_do_not_500(client, name, body):
    """Every parser branch must reach the shared analysis pipeline.

    Three call sites still referenced the pre-rename name
    `_analyze_spectrum_peaks`, so the CSV, CHN/SPE and generic
    SandiaSpecUtils branches all raised NameError -> HTTP 500. Only the
    N42 branch used the imported name and worked.
    """
    response = client.post("/upload", files={"file": (name, body, "text/csv")})
    assert response.status_code != 500, response.text
    assert response.status_code == 200, response.text
    assert "counts" in response.json()


def test_analysis_pipeline_name_is_bound():
    """Guard the rename directly: no stale underscore-prefixed references."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[1] / "routers" / "analysis.py"
    text = src.read_text(encoding="utf-8")
    assert "_analyze_spectrum_peaks(" not in text, \
        "stale reference to the pre-rename analysis function"
