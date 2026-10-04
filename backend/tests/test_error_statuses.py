"""A deliberate 4xx (or 501) inside a route must reach the client as itself. Three routes wrapped their own HTTPException in
`except Exception` and answered 500 with a message like "400: Unknown isotope": an unknown ROI isotope, an empty SNIP request and a
missing scikit-learn."""
import ast
import pathlib

import pytest
from fastapi.testclient import TestClient

from main import app

BACKEND = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_unknown_roi_isotope_is_a_400_with_a_clean_message(client):
    response = client.post("/analyze/roi", json={"energies": [float(i) for i in range(20)], "counts": [1.0] * 20,
                                                 "isotope": "Unobtainium-1", "acquisition_time_s": 60})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail.startswith("Unknown isotope: Unobtainium-1") and not detail.startswith("400:")


def test_empty_snip_request_is_a_400(client):
    response = client.post("/analyze/snip-background", json={"counts": []})
    assert response.status_code == 400
    assert response.json()["detail"] == "counts is required"


def test_missing_scikit_learn_is_a_501(client, monkeypatch):
    import ml.ml_analysis as ml
    monkeypatch.setattr(ml, "get_ml_identifier", lambda *a, **k: None)
    response = client.post("/analyze/ml-identify", json={"counts": [1.0] * 1024, "energies": [float(i) for i in range(1024)]})
    assert response.status_code == 501
    assert response.json()["detail"] == "scikit-learn not installed"


def test_no_route_swallows_its_own_http_errors():
    """The pattern behind the three bugs: `raise HTTPException` in a try whose first matching handler is a broad `except Exception`."""
    def handler_names(handler):
        t = handler.type
        if t is None:
            return {"<bare>"}
        if isinstance(t, ast.Tuple):
            return {getattr(e, "id", getattr(e, "attr", "?")) for e in t.elts}
        return {getattr(t, "id", getattr(t, "attr", "?"))}

    def raises_http(nodes):
        return any(isinstance(sub, ast.Raise) and isinstance(sub.exc, ast.Call) and getattr(sub.exc.func, "id", "") == "HTTPException"
                   for n in nodes for sub in ast.walk(n))

    swallowed = []
    for path in sorted((BACKEND / "routers").glob("*.py")) + [BACKEND / "main.py"]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Try) and raises_http(node.body):
                    for h in node.handlers:
                        names = handler_names(h)
                        if "HTTPException" in names:
                            break
                        if names & {"Exception", "<bare>", "BaseException"}:
                            swallowed.append(f"{path.name}:{fn.name} (handler at line {h.lineno})")
                            break
    assert not swallowed, "add `except HTTPException: raise` before the broad handler in: " + ", ".join(swallowed)
