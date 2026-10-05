"""
Decay-chain detection: the chain sequence (branching), the secular-equilibrium check, the matching helpers, and end-to-end series
identification on synthetic series spectra for the AlphaHound and Radiacode profiles.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nuclides import chain_detection_enhanced as chains   # noqa: E402
from spectroscopy.analysis_utils import analyze_spectrum_peaks   # noqa: E402
from spectrum_synth import THORIUM_SERIES, URANIUM_SERIES, linear_axis, series_spectrum   # noqa: E402

DEVICES = ["AlphaHound CsI(Tl)", "Radiacode 103", "Radiacode 110"]


# --------------------------------------------------------------------------- sequence and branching
def by_name(sequence):
    return {entry["nuclide"]: entry for entry in sequence}


def test_thorium_sequence_marks_the_bismuth_212_branch():
    seq = by_name(chains.get_chain_sequence_info("Th-232"))
    assert seq["Bi-212"]["branching_to_next"] == pytest.approx(0.6406, abs=1e-3)          # to Po-212
    assert seq["Po-212"]["feeder"] == "Bi-212" and not seq["Po-212"]["is_branch"]
    assert seq["Tl-208"]["feeder"] == "Bi-212" and seq["Tl-208"]["is_branch"]
    assert seq["Tl-208"]["branching_from_feeder"] == pytest.approx(0.3594, abs=1e-3)
    # Po-212 does not decay into Tl-208 (its sibling in the list): no arrow percentage between them
    assert seq["Po-212"]["branching_to_next"] is None
    assert seq["Pb-208"]["half_life"] == "stable"


def test_uranium_sequence_is_linear_apart_from_minor_branches():
    sequence = chains.get_chain_sequence_info("U-238")
    assert [e["nuclide"] for e in sequence][:3] == ["U-238", "Th-234", "Pa-234m"]
    assert not any(e["is_branch"] for e in sequence)
    assert sequence[-1]["nuclide"] == "Pb-206" and sequence[-1]["branching_to_next"] == 1.0
    assert all(e["feeder"] == sequence[i - 1]["nuclide"] for i, e in enumerate(sequence) if i)


def test_chain_summary_uses_the_keys_the_chains_really_have():
    peaks = [{"energy": e, "net_area": 500} for e in (238.6, 338.3, 583.2, 911.2, 969.0, 2614.5)]
    found = chains.identify_decay_chains_enhanced(peaks, energy_tolerance=15.0, min_score=0.25)
    assert found and found[0]["parent"] == "Th-232"
    text = chains.get_chain_summary(found)
    assert "Th-232" in text and "chain members detected" in text
    assert chains.get_chain_summary([]) == "No radioactive decay chains detected."


# --------------------------------------------------------------------------- matching
def test_a_line_takes_the_closest_peak_not_the_first_listed():
    peaks = [{"energy": 625.0, "net_area": 1}, {"energy": 610.0, "net_area": 1000}]       # 609.3 keV line
    _, _, nuclides, detail = chains.match_peaks_to_chain_detail(peaks, "U-238", energy_tolerance=20.0)
    assert "Bi-214" in nuclides
    assert detail["Bi-214"][0]["energy"] == 610.0 and detail["Bi-214"][0]["counts"] == 1000.0


def test_match_peaks_to_chain_keeps_its_old_return_shape():
    detected, expected, nuclides, matches = chains.match_peaks_to_chain([{"energy": 609.3, "net_area": 10}], "U-238", 15.0)
    assert detected >= 1 and expected > detected and "Bi-214" in nuclides
    assert matches["Bi-214"] == [609.3]


# --------------------------------------------------------------------------- equilibrium
@pytest.mark.parametrize("detector", DEVICES)
@pytest.mark.parametrize("series, parent, depleted, activity", [
    (URANIUM_SERIES, "U-238", "Pb-214", 40.0),
    (THORIUM_SERIES, "Th-232", "Tl-208", 150.0),       # the 2614 keV line is faint: it needs more activity to prove a factor of 6
])
def test_equilibrium_verdicts_follow_the_known_activities(detector, series, parent, depleted, activity):
    e = linear_axis()
    live = 3600.0
    # equilibrium: every member at the same activity
    _, y = series_spectrum(detector, series, activity, live, seed=3)
    status = chains.check_secular_equilibrium({}, parent, e, y, detector, live)
    assert status["in_equilibrium"] is True, status
    assert 0.4 < status["ratio_check"][0]["ratio"] < 2.5
    # one member of the measured pair at 8 % of the others: clearly not in equilibrium
    _, y = series_spectrum(detector, series, activity, live, scale={depleted: 0.08}, seed=4)
    status = chains.check_secular_equilibrium({}, parent, e, y, detector, live)
    assert status["in_equilibrium"] is False, status
    # 40 %: neither consistent nor clearly broken: the data cannot say
    _, y = series_spectrum(detector, series, activity, live, scale={depleted: 0.3}, seed=5)
    status = chains.check_secular_equilibrium({}, parent, e, y, detector, live)
    assert status["in_equilibrium"] in (None, True) and status["confidence"] in ("LOW", "MEDIUM")


def test_equilibrium_is_unknown_without_a_spectrum_or_signal():
    assert chains.check_secular_equilibrium({}, "U-238")["in_equilibrium"] is None
    assert chains.check_secular_equilibrium({}, "Th-232")["details"] == "Equilibrium needs the spectrum itself"
    e = linear_axis()
    _, y = series_spectrum("Radiacode 110", URANIUM_SERIES, 0.0, 600.0, seed=2)      # background only
    status = chains.check_secular_equilibrium({}, "U-238", e, y, "Radiacode 110", 600.0)
    assert status["in_equilibrium"] is None and status["details"].startswith("Insufficient")
    assert chains.check_secular_equilibrium({}, "Cs-137")["in_equilibrium"] is None


# --------------------------------------------------------------------------- end to end
@pytest.mark.parametrize("detector", DEVICES)
@pytest.mark.parametrize("series, parent, other", [
    (URANIUM_SERIES, "U-238", "Th-232"),
    (THORIUM_SERIES, "Th-232", "U-238"),
])
def test_series_are_identified_and_not_confused(detector, series, parent, other):
    e = linear_axis()
    live = 3600.0
    _, y = series_spectrum(detector, series, 60.0, live, seed=7)
    data = {"energies": e.tolist(), "counts": y.tolist(), "metadata": {"instrument_model": detector, "live_time": live}}
    result = analyze_spectrum_peaks(data, True, live)
    found = [c["parent"] for c in result["decay_chains"]]
    assert parent in found, found
    assert other not in found, found
    chain = next(c for c in result["decay_chains"] if c["parent"] == parent)
    assert chain["equilibrium_status"]["in_equilibrium"] in (True, None)       # never a false DISEQUILIBRIUM on an equilibrium source
    assert chain["chain_sequence"] and chain["chain_sequence"][0]["nuclide"] == parent


def test_no_chain_on_an_empty_background():
    e = linear_axis()
    _, y = series_spectrum("Radiacode 110", URANIUM_SERIES, 0.0, 600.0, seed=9)
    data = {"energies": e.tolist(), "counts": y.tolist(), "metadata": {"instrument_model": "Radiacode 110", "live_time": 600.0}}
    assert analyze_spectrum_peaks(data, True, 600.0)["decay_chains"] == []


# --------------------------------------------------------------------------- through the HTTP API, on real captures
def test_upload_of_real_files_reports_detector_profile_and_chain_fields():
    import pathlib
    from fastapi.testclient import TestClient
    from main import app
    backend = pathlib.Path(__file__).resolve().parents[1]
    client = TestClient(app)

    xml = backend / "tests" / "data" / "radiacode_fisicas" / "Th-232.xml"           # Radiacode 103, thorium source
    body = client.post("/upload", files={"file": (xml.name, xml.read_bytes(), "text/xml")})
    assert body.status_code == 200, body.text
    data = body.json()
    assert data["detector_profile"].startswith("Radiacode")
    thorium = next(c for c in data["decay_chains"] if c["parent"] == "Th-232")
    assert thorium["equilibrium_status"]["in_equilibrium"] is not False       # a real thorium source is not reported out of equilibrium
    assert any(step["nuclide"] == "Tl-208" and step["is_branch"] for step in thorium["chain_sequence"])

    n42 = backend / "Cs137_Verification_Spectra.n42"                                  # AlphaHound
    body = client.post("/upload", files={"file": (n42.name, n42.read_bytes(), "application/xml")})
    assert body.status_code == 200, body.text
    assert body.json()["detector_profile"].startswith("AlphaHound")
    assert body.json()["decay_chains"] == []


# --------------------------------------------------------------------------- the card and the isotope table say the same thing
def _card(parent, **extra):
    detected = {"Ac-228": [{"energy": 911.0}] * 2, "Th-228": [{"energy": 84.0}], "Ra-224": [{"energy": 241.0}]}
    return {"parent": parent, "chain_sequence": chains.get_chain_sequence_info(parent), "detected_members": detected, **extra}


def test_one_decision_per_member_table_first_then_the_chains_own_lines():
    from spectroscopy.analysis_utils import _attach_member_status
    chain = _card("Th-232")
    _attach_member_status([chain], [{"isotope": "Th-232", "matches": 3, "total_lines": 5}, {"isotope": "Ac-228", "matches": 3, "total_lines": 4}])
    st = chain["member_status"]
    assert st["Th-232"] == {"state": "detected", "matches": 3, "total_lines": 5, "source": "isotope table"}      # no line of its own, same as Ac-228
    assert st["Ac-228"]["state"] == "detected" and st["Ac-228"]["source"] == "isotope table"
    assert st["Th-228"]["source"] == "chain lines" and st["Th-228"]["state"] == "detected"                          # not in the database: the chain's lines
    assert st["Ra-228"] == {"state": "inferred", "from": "Ac-228"}                                                  # no line, not identified: only implied
    assert "Po-212" not in st and "Bi-212" not in st and "Pb-208" not in st   # a sibling branch or a downstream member is never implied
    assert "Pb-208" not in st                                                                                       # nothing is said about the rest


def test_a_member_the_table_can_judge_but_did_not_list_is_not_ticked_whatever_the_lines_say():
    from spectroscopy.analysis_utils import _attach_member_status
    chain = _card("Th-232")
    _attach_member_status([chain], [{"isotope": "Ac-228", "suppressed": True}])
    assert "Ac-228" not in chain["member_status"]                                                                   # in the database, suppressed by the table


def test_the_member_states_agree_with_the_isotope_table_on_real_spectra():
    """The invariant, on every real Th/U spectrum: a nuclide the table can judge is ticked on the card exactly when the table lists it."""
    from nuclides.isotope_database import ISOTOPE_DATABASE
    from routers.analysis import _analyze_upload
    data = os.path.join(os.path.dirname(__file__), "data")
    paths = [os.path.join(data, "real_spectra", f) for f in ("spectrum_2025-12-15_takumar_90min.n42", "spectrum_takumar_8hr_reference.n42")]
    paths += [os.path.join(data, "radiacode_fisicas", f) for f in ("Th-232.xml", "Ra-226.xml", "U-238-U-235-FiestaWare.xml")]
    checked = 0
    for path in paths:
        with open(path, "rb") as handle:
            result = _analyze_upload(handle.read(), os.path.basename(path), os.path.basename(path))
        listed = {i["isotope"] for i in result.get("isotopes", []) if not i.get("suppressed")}
        for chain in result.get("decay_chains", []):
            status = chain["member_status"]
            for entry in chain["chain_sequence"]:
                name = entry["nuclide"]
                if name in ISOTOPE_DATABASE:
                    assert (status.get(name, {}).get("state") == "detected") == (name in listed), f"{os.path.basename(path)} {name}"
                    checked += 1
                assert status.get(name, {}).get("state") != "detected" or status[name]["total_lines"], f"no line count for {name}"
    assert checked
