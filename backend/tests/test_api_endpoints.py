"""Smoke and contract tests for the read-only / lightweight API endpoints."""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.mark.parametrize("url", [
    "/settings",
    "/detectors",
    "/analyze/detectors",
    "/analyze/roi-isotopes",
    "/analyze/source-types",
    "/analyze/gamma-constants",
    "/analyze/search-gamma?energy=661.7",
    "/analyze/search-xray?energy=59",
    "/analyze/decay-chain?parent=U-238",
    "/analyze/isotope-lines?isotope=Cs-137",
    "/isotopes/custom",
    "/isotopes/custom/export",
    "/radiacode/available",
    "/radiacode/status",
])
def test_get_endpoints_return_200(client, url):
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert response.json() is not None


def test_gamma_constants_contents(client):
    """Regression: handler imported the renamed GAMMA_CONSTANTS and 500'd."""
    body = client.get("/analyze/gamma-constants").json()
    assert body["constants"]["Cs-137"] > 0
    assert "units" in body


def test_search_gamma_finds_cs137(client):
    matches = client.get("/analyze/search-gamma?energy=661.7").json()["matches"]
    assert any(abs(m["energy_keV"] - 661.66) < 0.1 for m in matches)


def test_radiacode_status_disconnected_by_default(client):
    assert client.get("/radiacode/status").json()["connected"] is False


@pytest.mark.parametrize("url", [
    "/analyze/dose-rate",
    "/analyze/estimate-time",
])
def test_post_endpoints_validate_body(client, url):
    assert client.post(url, json={}).status_code == 422


def test_upload_rejects_unsupported_garbage(client):
    response = client.post("/upload", files={"file": ("x.csv", b"", "text/csv")})
    assert response.status_code in (400, 422), response.text


def test_cors_disabled_by_default(client):
    """The UI is same-origin; no wildcard CORS unless ALPHAHOUND_CORS_ORIGINS is set."""
    response = client.get("/settings", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_cpu_bound_analysis_routes_run_in_threadpool():
    """Sync `def` handlers run in FastAPI's threadpool; `async def` would block the loop."""
    import inspect
    from routers import analysis
    for route in analysis.router.routes:
        if route.path == "/upload":
            continue  # awaits file.read()
        assert not inspect.iscoroutinefunction(route.endpoint), route.path
