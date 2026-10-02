"""RadiaCode export formats, detector resolution handling and the source template fit."""
import math
import pathlib

import numpy as np
import pytest
from fastapi.testclient import TestClient

from main import app
from radiacode_xml_parser import is_radiacode_xml, parse_radiacode_xml
from source_templates import TEMPLATES, fit_source_templates, resolve_detector

RC = pathlib.Path(__file__).parent / "data" / "radiacode_fisicas"


def test_radiacode_xml_parsed_with_device_calibration():
    text = (RC / "Th-232.xml").read_text(encoding="utf-8")
    assert is_radiacode_xml(text)
    r = parse_radiacode_xml(text)
    assert r["is_calibrated"] is True
    assert len(r["counts"]) == 1024
    assert r["metadata"]["instrument_model"] == "RadiaCode-103"
    assert r["metadata"]["live_time"] == 3710.0
    a0, a1, a2 = 8.0997305, 2.35303, 0.0003807156
    assert r["energies"][100] == pytest.approx(a0 + a1 * 100 + a2 * 100 * 100)


def test_radiacode_xml_matches_dataset_manual_peaks():
    """Dataset's hand-fitted channels map to the device-calibrated energies we compute."""
    import csv
    rows = list(csv.DictReader(open(RC / "manual_primary_peaks.csv", encoding="utf-8")))
    for row in rows:
        r = parse_radiacode_xml((RC / pathlib.Path(row["source_file"]).name).read_text(encoding="utf-8"))
        cal = r["metadata"]["calibration"]
        ch = float(row["fitted_channel"])
        device_energy = cal["a0"] + cal["a1"] * ch + cal["a2"] * ch * ch
        # factory calibration on this unit reads within ~4 % of the true line energy
        assert device_energy == pytest.approx(float(row["assigned_energy_keV"]), rel=0.045)


def test_radiacode_xml_upload_route():
    client = TestClient(app)
    body = client.post("/upload", files={"file": ("Ra-226.xml", (RC / "Ra-226.xml").read_bytes(), "text/xml")}).json()
    assert body["is_calibrated"] is True
    assert [c["parent"] for c in body["decay_chains"]] == ["U-238"]
    assert body["source_fit"]["detector"] == "Radiacode 103"


def test_bad_radiacode_xml_reports_error():
    assert "error" in parse_radiacode_xml("<ResultDataFile><ResultDataList/></ResultDataFile>")


def test_csv_with_hash_metadata_lines_uses_energy_column_and_duration():
    from csv_parser import parse_csv_spectrum
    rows = "\n".join(f"{i},{3.0 + 2.4 * i:.2f},{10 + (i == 200) * 500}" for i in range(1024))
    raw = ("# RadiaCode-110 spectrum export\n# duration_s,1048\n# calib_a0,3.0\n"
           "channel,energy_keV,counts\n" + rows + "\n").encode()
    r = parse_csv_spectrum(raw, "rc.csv")
    assert r["is_calibrated"] is True
    assert r["energies"][1] == pytest.approx(5.4)
    assert r["metadata"]["live_time"] == 1048


@pytest.mark.parametrize("meta,expected", [
    ({"instrument_model": "RadiaCode-103"}, "Radiacode 103"),
    ({"instrument_model": "RadiaCode-103G"}, "Radiacode 103G"),
    ({"source": "Radiacode Device"}, "Radiacode 103"),
    ({"instrument_model": "RC-110 RadiaCode-110"}, "Radiacode 110"),
    ({"source": "AlphaHound Device"}, "AlphaHound CsI(Tl)"),
    ({}, "AlphaHound CsI(Tl)"),
])
def test_resolve_detector(meta, expected):
    assert resolve_detector(meta) == expected


def _synthetic(template, scale, gain=1.0, r662=0.084, seed=1):
    """Template lines on a smooth continuum, Poisson-noised, on a RadiaCode-like quadratic axis."""
    rng = np.random.default_rng(seed)
    ch = np.arange(1024)
    E = 3.0 + 2.4 * ch + 0.0004 * ch ** 2
    dE = np.gradient(E)
    cont = 4000.0 * np.exp(-E / 300.0) + 40.0
    lines = np.zeros_like(E)
    for line, inten in TEMPLATES[template]:
        s = r662 * 662 * math.sqrt(line / 662) / 2.355
        lines += scale * inten * np.exp(-0.5 * ((E - line * gain) / s) ** 2) / (s * math.sqrt(2 * math.pi)) * dE
    return E.tolist(), rng.poisson(cont + lines).tolist()


@pytest.mark.parametrize("template,chain,other", [
    ("thorium_series", "Th-232", "U-238"),
    ("radium_series", "U-238", "Th-232"),
])
def test_fit_separates_series_even_with_calibration_error(template, chain, other):
    E, c = _synthetic(template, scale=3000.0, gain=0.97)
    fit = fit_source_templates(E, c, {"instrument_model": "RadiaCode-103"})
    assert fit["chains"][chain]["present"]
    assert not fit["chains"][other]["present"]
    assert fit["gain"] == pytest.approx(0.97, abs=0.02)


def test_fit_reports_nothing_for_featureless_continuum():
    rng = np.random.default_rng(3)
    E = (3.0 + 2.4 * np.arange(1024)).tolist()
    c = rng.poisson(4000.0 * np.exp(-np.array(E) / 300.0) + 40.0).tolist()
    fit = fit_source_templates(E, c, {"instrument_model": "RadiaCode-103"})
    assert not any(s["present"] for s in fit["sources"].values())


def test_fit_returns_none_for_tiny_input():
    assert fit_source_templates([1.0, 2.0], [1, 2]) is None
