"""Uploads the server cannot read must be answered with a client error (400) and a message, never a fake spectrum or a 500."""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.mark.parametrize("name,body", [
    # text where counts belong used to come back as a "spectrum" of strings
    ("words.csv", b"this,is,not\nnumbers,at,all\n"),
    ("mixed.csv", b"Energy,Counts\n0,10\n10,oops\n20,50\n"),
    ("html.csv", b"<html><body>404 not found</body></html>"),
    # the generic parser failing is a bad file, not a server fault
    ("junk.txt", b"hello, this is not a spectrum"),
    ("broken.n42", b"<not xml"),
    ("empty.csv", b""),
])
def test_unreadable_uploads_are_client_errors(client, name, body):
    response = client.post("/upload", files={"file": (name, body, "application/octet-stream")})
    assert response.status_code == 400, (response.status_code, response.text[:200])
    assert response.json()["detail"]


def test_csv_text_column_message_names_the_problem(client):
    response = client.post("/upload", files={"file": ("words.csv", b"this,is,not\nnumbers,at,all\n", "text/csv")})
    assert response.status_code == 400
    assert "not a number" in response.json()["detail"], response.text


def test_unsupported_extension_is_refused(client):
    response = client.post("/upload", files={"file": ("photo.png", b"\x89PNG\r\n", "image/png")})
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


@pytest.mark.parametrize("body", [
    b"Energy,Counts\n0,10\n10,20\n20,50",
    b"0,10\n10,20\n20,50",
    b"channel,counts\n0,1\n1,2\n2,3\n3,4",
    b"1.5;2\n2.5;3\n3.5;9\n",
])
def test_numeric_csv_variants_still_parse(client, body):
    response = client.post("/upload", files={"file": ("ok.csv", body, "text/csv")})
    assert response.status_code == 200, (body, response.text[:200])
    data = response.json()
    assert data["counts"] and all(isinstance(c, (int, float)) for c in data["counts"])
    assert all(isinstance(e, (int, float)) for e in data["energies"])
