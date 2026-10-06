"""
Energy axes for spectra that arrive as channel numbers only (spectroscopy/energy_presets.py and its routes).

The claims are checked on real data: the AlphaHound preset against the axis a real unit sent, the RadiaCode preset against the calibration of every
RadiaCode spectrum in the tests, and the whole path on two real community captures of a RadiaCode (a 9-hour uranium glass and a 14-hour radium dial)
that carry channel numbers only and so could not be analysed at all.
"""
import glob
import pathlib

import pytest
from fastapi.testclient import TestClient

from formats.csv_parser import parse_csv_spectrum
from formats.radiacode_xml_parser import parse_radiacode_xml
from main import app
from spectroscopy import energy_presets as ep

DATA = pathlib.Path(__file__).resolve().parent / "data"
COMMUNITY = DATA / "real_spectra" / "community"
client = TestClient(app)


def community(name):
    return parse_csv_spectrum((COMMUNITY / name).read_bytes(), name)


# --------------------------------------------------------------------------- the polynomials
def test_energies_are_the_polynomial_in_the_channel():
    assert ep.energies([1.0, 2.0, 0.5], 4) == [1.0, 3.5, 7.0, 11.5]
    assert ep.linear(2.4, 3.0) == [3.0, 2.4]
    assert ep.energies(ep.linear(3.0), 3) == [0.0, 3.0, 6.0]


@pytest.mark.parametrize("coefficients, channels, why", [
    ([], 10, "1 to 6"), ([1, 2, 3, 4, 5, 6, 7], 10, "1 to 6"), ([0.0, 1.0], 1, "fewer than two"),
    ([0.0, -1.0], 10, "do not increase"), ([10.0, -0.001, 0.0], 10000, "increase"), ([-50.0, 0.0001], 100, "positive energy"),
])
def test_a_bad_polynomial_is_refused_with_the_reason(coefficients, channels, why):
    with pytest.raises(ValueError, match=why):
        ep.energies(coefficients, channels)


def test_the_alphahound_preset_is_the_axis_a_real_unit_sent():
    axis = [float(l.split(",")[0]) for l in (DATA / "real_spectra" / "spectrum_2025-12-12_08-41-27.csv").read_text(encoding="utf-8").splitlines()[1:] if l.strip()]
    mine = ep.energies(ep.preset("alphahound")["coefficients"], len(axis))
    assert max(abs(a - b) for a, b in zip(axis, mine)) < 0.05          # keV, over 1024 channels from 15 to 7572 keV


def test_the_radiacode_preset_is_close_to_every_calibration_measured():
    """26 RadiaCode spectra, six distinct calibrations (a0 -11.4..+8.1 keV, a1 2.35-2.47 keV per channel). The preset is within 12 keV of each below
    300 keV (a constant offset is a large share of 150 keV) and within 3 % above 300 keV: not a unit's own axis, close enough to start from."""
    mine = ep.energies(ep.preset("radiacode")["coefficients"], 1024)
    calibrations, worst_low, worst_high = set(), 0.0, 0.0
    for path in glob.glob(str(DATA / "web_spectra" / "*" / "*.xml")) + glob.glob(str(DATA / "radiacode_fisicas" / "*.xml")):
        try:
            parsed = parse_radiacode_xml(pathlib.Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if len(parsed["energies"]) != 1024:
            continue
        calibrations.add((round(parsed["energies"][0], 2), round(parsed["energies"][500], 1)))
        worst_low = max(worst_low, max(abs(a - b) for a, b in zip(parsed["energies"], mine) if a < 300.0))
        worst_high = max(worst_high, max(abs(a - b) / a for a, b in zip(parsed["energies"], mine) if a >= 300.0))
    assert len(calibrations) >= 6
    assert worst_low < 12.0 and worst_high < 0.03, (worst_low, worst_high)


def test_presets_are_listed_by_channel_count():
    assert {p["key"] for p in ep.presets_for(1024)} == {"radiacode", "alphahound"}
    assert ep.presets_for(4096) == []


# --------------------------------------------------------------------------- the ranking, on real captures
@pytest.mark.parametrize("name, source", [("Uranium glass 9 hours.csv", "fresh_uranium"), ("14 hour spectrum of radium dial watch.csv", "radium_series")])
def test_a_real_radiacode_capture_with_channel_numbers_only_is_recognised_as_one(name, source):
    parsed = community(name)
    assert parsed.get("is_calibrated") is False                      # the file carries no axis
    ranked = ep.suggest(parsed["counts"])
    assert ranked[0]["key"] == "radiacode" and ranked[0]["source"] == source
    assert ranked[0]["score"] >= 30.0 and ranked[1]["score"] < 10.0  # clearly one, and the other axis fits nothing


def test_the_ranking_is_empty_for_a_channel_count_no_preset_describes():
    assert ep.suggest([1.0] * 4096) == []


# --------------------------------------------------------------------------- the routes
def test_the_presets_route_lists_them_without_internals():
    body = client.get("/analyze/energy-presets", params={"channels": 1024}).json()
    assert {p["key"] for p in body["presets"]} == {"radiacode", "alphahound"}
    assert all("detector" not in p and p["coefficients"] and p["note"] for p in body["presets"])
    assert client.get("/analyze/energy-presets", params={"channels": 2048}).json() == {"presets": []}


def test_the_suggest_route_ranks_a_real_spectrum():
    body = client.post("/analyze/energy-presets/suggest", json={"counts": community("14 hour spectrum of radium dial watch.csv")["counts"]}).json()
    assert body["suggestions"][0]["key"] == "radiacode"


@pytest.mark.parametrize("payload, label_part", [
    ({"preset": "radiacode"}, "RadiaCode"), ({"kev_per_channel": 2.4, "offset_keV": 5.0}, "2.4 keV per channel"),
    ({"coefficients": [0.0, 2.38, 0.0004]}, "polynomial"),
])
def test_the_axis_route_gives_the_energies_for_each_way_of_asking(payload, label_part):
    body = client.post("/analyze/energy-axis", json={"channels": 1024, **payload}).json()
    assert len(body["energies"]) == 1024 and label_part in body["label"] and body["energies"][1] > body["energies"][0]
    assert body["approximate"] is ("preset" in payload)


@pytest.mark.parametrize("payload, detail", [
    ({"channels": 1024}, "exactly one"), ({"channels": 1024, "preset": "radiacode", "kev_per_channel": 2.0}, "exactly one"),
    ({"channels": 1024, "preset": "nope"}, "unknown preset"), ({"channels": 2048, "preset": "radiacode"}, "1024 channels"),
    ({"channels": 1024, "coefficients": [0.0, -1.0]}, "increase"), ({"channels": 1024, "coefficients": [1] * 7}, ""),
])
def test_the_axis_route_refuses_what_it_cannot_make_and_says_why(payload, detail):
    response = client.post("/analyze/energy-axis", json=payload)
    assert response.status_code in (400, 422) and detail in response.text


def test_a_preset_axis_lets_a_channel_only_capture_be_identified_end_to_end():
    """The whole path the page takes: the suggested preset's axis, then the analysis with the automatic correction allowed to refine it."""
    parsed = community("14 hour spectrum of radium dial watch.csv")
    best = client.post("/analyze/energy-presets/suggest", json={"counts": parsed["counts"]}).json()["suggestions"][0]["key"]
    axis = client.post("/analyze/energy-axis", json={"channels": len(parsed["counts"]), "preset": best}).json()
    result = client.post("/analyze/reanalyze", json={"energies": axis["energies"], "counts": parsed["counts"], "live_time": 0,
                                                     "metadata": {"calibration": {"preset": best}}, "approximate": axis["approximate"]}).json()
    assert {c["parent"] for c in result["decay_chains"]} == {"U-238"}
    assert {"Ra-226", "Pb-214", "Bi-214"} & {i["isotope"] for i in result["isotopes"]}


def test_a_hand_chosen_axis_is_analysed_exactly_as_given_but_a_preset_may_be_refined(monkeypatch):
    """`approximate` is the only thing that lets the automatic correction touch an axis."""
    seen = []
    from routers import analysis as analysis_router

    def fake(result, is_calibrated, live_time=0.0, auto_calibrate=True, **kw):
        seen.append(auto_calibrate)
        return {**result, "peaks": [], "isotopes": [], "decay_chains": []}
    monkeypatch.setattr(analysis_router, "analyze_spectrum_peaks", fake)
    body = {"energies": [float(i) for i in range(1, 21)], "counts": [10.0] * 20, "live_time": 0}
    client.post("/analyze/reanalyze", json=body)
    client.post("/analyze/reanalyze", json={**body, "approximate": True})
    assert seen == [False, True]
