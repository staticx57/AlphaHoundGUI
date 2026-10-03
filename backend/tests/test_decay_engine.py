"""Decay engines: the Bateman solver, the three engines and their agreement, input validation and the API.

Each engine is tested for what it claims: radioactivedecay (ICRP-107), curie (ENSDF) and the built-in solver (the same ICRP-107
data embedded). The old versions of these tests only checked that engines were listed."""
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

import bateman
import decay_engine
from decay_calculator import (CHAINS, GRAPH, DecayInputError, bateman_solution, format_half_life, get_decay_chain,
                              get_decay_constant, get_isotope_info, normalize_isotope, predict_decay_chain)
from decay_engine import BaseDecayEngine, BuiltinEngine, DecayEngineManager, decay_engine_manager
from main import app

YEAR = 365.25 * 86400
ENGINES = ["builtin", "radioactivedecay", "curie"]
manager = decay_engine_manager


def available(name):
    return next(e for e in manager.list_engines() if e["name"] == name)["available"]


def engines_here():
    return [e for e in ENGINES if available(e)]


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ------------------------------------------------------------------------------------------------ the solver

def two_chain(l1, l2):
    ln2 = math.log(2)
    return {"A": (ln2 / l1, (("B", 1.0),)), "B": (ln2 / l2, (("C", 1.0),)), "C": (None, ())}


def test_two_member_chain_matches_the_textbook_formula():
    l1, l2 = 1e-3, 5e-3
    times = [0.0, 100.0, 1000.0, 5000.0]
    out = bateman.solve_chain(two_chain(l1, l2), "A", 1000.0, times)
    # the graph holds half-lives; recompute lambda from them so the comparison is exact
    lam1, lam2 = math.log(2) / (math.log(2) / l1), math.log(2) / (math.log(2) / l2)
    for i, t in enumerate(times):
        a1 = 1000.0 * math.exp(-lam1 * t)
        a2 = 1000.0 * lam2 / (lam2 - lam1) * (math.exp(-lam1 * t) - math.exp(-lam2 * t))
        assert out["A"][i] == pytest.approx(a1, rel=1e-12)
        assert out["B"][i] == pytest.approx(a2, rel=1e-9, abs=1e-12)


def test_equal_half_lives_do_not_blow_up():
    graph = two_chain(1e-3, 1e-3)                       # the closed form divides by (lambda2 - lambda1)
    out = bateman.solve_chain(graph, "A", 100.0, [0.0, 500.0, 2000.0])
    lam = 1e-3
    for i, t in enumerate([0.0, 500.0, 2000.0]):
        assert out["B"][i] == pytest.approx(100.0 * lam * t * math.exp(-lam * t), rel=1e-6, abs=1e-9)   # A2 = A0 lambda t e^(-lambda t)


def test_branching_splits_the_activity_and_branches_rejoin():
    """Checked against an independent numerical integration (scipy, implicit Radau) of the same rate equations."""
    from scipy.integrate import solve_ivp
    ln2 = math.log(2)
    hl = {"P": 1.0, "X": 10.0, "Y": 4.0, "Z": 100.0}
    lam = {k: ln2 / v for k, v in hl.items()}
    graph = {
        "P": (hl["P"], (("X", 0.3), ("Y", 0.7))),
        "X": (hl["X"], (("Z", 1.0),)),
        "Y": (hl["Y"], (("Z", 1.0),)),          # the two branches rejoin in Z
        "Z": (hl["Z"], (("S", 1.0),)),
        "S": (None, ()),
    }

    def rate(t, n):
        p, x, y, z = n
        return [-lam["P"] * p, -lam["X"] * x + 0.3 * lam["P"] * p, -lam["Y"] * y + 0.7 * lam["P"] * p,
                -lam["Z"] * z + lam["X"] * x + lam["Y"] * y]

    times = np.linspace(0, 400, 9)
    ref = solve_ivp(rate, (0, 400), [1.0 / lam["P"], 0, 0, 0], t_eval=times, method="Radau", rtol=1e-11, atol=1e-14)
    out = bateman.solve_chain(graph, "P", 1.0, times)
    assert list(out) == ["P", "X", "Y", "Z"] or list(out) == ["P", "Y", "X", "Z"]      # Z only after both of its parents
    for i, k in enumerate(["P", "X", "Y", "Z"]):
        assert np.allclose(out[k], lam[k] * ref.y[i], rtol=1e-6, atol=1e-12), k
    assert [out[k][0] for k in ("X", "Y", "Z")] == [0.0, 0.0, 0.0]


def test_extreme_half_life_spread_keeps_full_precision():
    """U-238 (1.4e17 s) with Po-214 (164 us) below it: 23 orders of magnitude, where ordinary floats lose everything."""
    t = [1e13]                                                # about 300,000 years
    out = bateman.solve_chain(GRAPH, "U-238", 1.0, t)
    assert out["Po-214"][0] == pytest.approx(out["Bi-214"][0] * 0.99979, rel=1e-3)         # fast daughter sits at its parent's activity x branching
    assert out["Th-234"][0] == pytest.approx(out["U-238"][0], rel=1e-6)


def test_solver_rejects_bad_requests():
    with pytest.raises(ValueError):
        bateman.solve_chain(GRAPH, "Ni-60", 1.0, [0.0])        # stable
    with pytest.raises(ValueError):
        bateman.solve_chain(GRAPH, "Cs-137", 0.0, [0.0])
    with pytest.raises(ValueError):
        bateman.solve_chain(GRAPH, "Nope-1", 1.0, [0.0])       # unknown


def test_topological_order_puts_parents_before_children():
    order = bateman.topological_order(GRAPH, "U-238")
    assert order[0] == "U-238"
    assert order.index("Pa-234m") < order.index("U-234") and order.index("Pa-234") < order.index("U-234")
    assert order.index("Po-210") > order.index("Pb-210")
    assert len(order) == len(set(order))


# ------------------------------------------------------------------------------------------------ names and data

@pytest.mark.parametrize("given,expected", [
    ("Cs-137", "Cs-137"), ("cs-137", "Cs-137"), ("Cs137", "Cs-137"), ("137Cs", "Cs-137"), ("CS 137", "Cs-137"), (" cs137 ", "Cs-137"),
    ("Tc99m", "Tc-99m"), ("99mTc", "Tc-99m"), ("tc-99m", "Tc-99m"), ("Ba-137m", "Ba-137m"), ("Uranium", "U-238"), ("thorium", "Th-232"),
    ("Am-241", "Am-241"), ("K40", "K-40"),
])
def test_isotope_names_are_normalised(given, expected):
    assert normalize_isotope(given) == expected


@pytest.mark.parametrize("junk", ["", "   ", None, "Zz", "137", "Cesium-137 and more", "12345-678"])
def test_unreadable_isotope_names_raise(junk):
    with pytest.raises(DecayInputError):
        normalize_isotope(junk)


def test_embedded_data_is_complete_and_consistent():
    assert len(GRAPH) > 100
    for name, (half_life, products) in GRAPH.items():
        assert half_life is None or half_life > 0, name
        if half_life is not None:
            assert products, f"{name} decays but has no products"
            # fractions add up (spontaneous fission aside); the only gap in the data is At-219, where ICRP-107 as packaged lists the
            # 97 % alpha branch and not the 3 % beta one
            assert (0.96 if name == "At-219" else 0.995) < sum(f for _, f in products) < 1.0001, (name, products)
        for daughter, fraction in products:
            assert 0 < fraction <= 1 and daughter in GRAPH, (name, daughter)
    assert GRAPH["Co-60"][0] == pytest.approx(5.2713 * YEAR, rel=1e-3)
    assert GRAPH["Cs-137"][1][0][0] == "Ba-137m"


def test_half_life_formatting():
    assert format_half_life(None) == "stable" and format_half_life(0) == "stable" and format_half_life(float("inf")) == "stable"
    assert format_half_life(164.3e-6) == "164.3 µs" and format_half_life(153.12) == "2.552 min"
    assert format_half_life(30.17 * YEAR) == "30.17 y" and format_half_life(4.468e9 * YEAR) == "4.468e+09 y"


@pytest.mark.parametrize("name", engines_here())
def test_half_lives_come_from_every_engine(name):
    engine = manager._engines[name]
    assert engine.get_half_life("Co-60") == pytest.approx(5.2713 * YEAR, rel=2e-3)
    assert engine.get_half_life("Cs-137") == pytest.approx(30.1 * YEAR, rel=5e-3)
    assert engine.get_half_life("Ni-60") is None                    # stable
    assert engine.get_half_life("Xx-999") is None                   # unknown


def test_legacy_helpers_still_work():
    assert get_decay_constant("Co-60") == pytest.approx(math.log(2) / (5.2713 * YEAR), rel=1e-3)   # used to be 0.0: treated as stable
    assert get_decay_constant("Ni-60") == 0.0 and get_decay_constant("junk") == 0.0
    chain = predict_decay_chain("U-238", 1.0, 10.0, steps=5)
    assert chain["isotopes"][0] == "U-238" and "Pb-210" in chain["isotopes"] and "Po-210" in chain["isotopes"]
    assert len(chain["time_points_days"]) == 5 and all(len(v) == 5 for v in chain["activities"].values())
    assert predict_decay_chain("Xx-999", 1.0, 10.0) is None
    assert predict_decay_chain("Ni-60", 1.0, 10.0) is None
    assert "U-238" in CHAINS["U-238 Sequence"] and "Tl-208" in CHAINS["Th-232 Sequence"]
    lin = bateman_solution(["Cs-137", "Ba-137m"], 100.0, [0.0, 3600.0])
    assert lin["Cs-137"][0] == pytest.approx(100.0) and lin["Ba-137m"][0] == 0.0 and lin["Ba-137m"][1] > 0


def test_isotope_info_and_chain():
    info = get_isotope_info("cs137")
    assert info["isotope"] == "Cs-137" and info["half_life_readable"] == "30.17 y" and not info["stable"]
    assert [d["isotope"] for d in info["daughters"]][:1] == ["Ba-137m"]
    assert get_isotope_info("Ni-60")["stable"] is True
    assert get_isotope_info("U-238")["series"] == "U-238 Sequence"
    chain = get_decay_chain("Th-232")
    names = [c["isotope"] for c in chain]
    assert names[0] == "Th-232" and names[-1] == "Pb-208" and chain[-1]["stable"] is True and "Tl-208" in names
    with pytest.raises(DecayInputError):
        get_isotope_info("Xx-999")


# ------------------------------------------------------------------------------------------------ the engines

def test_engine_listing_is_honest():
    names = [e["name"] for e in manager.list_engines()]
    assert names == ["builtin", "radioactivedecay", "curie"] and "pyne" not in names
    info = {e["name"]: e for e in manager.list_engines()}
    assert info["builtin"]["available"] is True and "ICRP" in info["builtin"]["data_source"]
    if info["radioactivedecay"]["available"]:
        assert "ICRP" in info["radioactivedecay"]["data_source"] and info["radioactivedecay"]["is_default"]
    if info["curie"]["available"]:
        assert "ENSDF" in info["curie"]["data_source"]
    assert sum(e["is_default"] for e in info.values()) == 1


def test_fallback_behavior():
    engine = DecayEngineManager().get_engine("non_existent_engine")
    assert isinstance(engine, BaseDecayEngine) and engine.name == "builtin"


def test_builtin_decay_prediction_shape():
    result = manager.predict_decay("Cs-137", 1000.0, 86400, points=10, engine_name="builtin")
    assert result["isotope"] == "Cs-137" and result["initial_activity"] == 1000.0 and result["engine_used"] == "builtin"
    assert len(result["time_points"]) == 10 and len(result["time_labels"]) == 10 and result["time_points"][-1] == pytest.approx(86400)
    assert result["isotopes"] == list(result["series"]) and result["isotopes"][0] == "Cs-137"
    assert result["activities"] == result["series"] and len(result["time_points_days"]) == 10
    assert result["data_source"] and "omitted" in result and result["warnings"] == []


CASES = [("Cs-137", 1), ("Cs-137", 100), ("Cs-137", 301), ("Cs-137", 400), ("Co-60", 30), ("Sr-90", 200), ("U-238", 1e6), ("Th-232", 50),
         ("Ra-226", 5000), ("Am-241", 2000), ("K-40", 5e9), ("Mo-99", 0.08), ("I-131", 0.55), ("Tc-99m", 0.003), ("Ba-137m", 1e-5)]


@pytest.mark.parametrize("name", engines_here())
@pytest.mark.parametrize("isotope,years", CASES)
def test_series_are_full_length_start_at_the_parent_and_never_shift(name, isotope, years):
    """Regression: a nuclide below 0.1 % of the start at some time points used to be dropped there and front-padded with zeros,
    so Cs-137 over 301 years drew 0 -> 2 Bq instead of 1000 -> 1."""
    r = manager.predict_decay(isotope, 1000.0, years * YEAR, points=24, engine_name=name)
    n = len(r["time_points"])
    assert n == 24 and r["engine_used"] == name
    for nuclide, values in r["series"].items():
        assert len(values) == n, (nuclide, len(values))
        assert all(v >= 0 and math.isfinite(v) for v in values), nuclide
    parent = r["series"][r["isotope"]]
    assert parent[0] == pytest.approx(1000.0)
    assert all(b <= a * (1 + 1e-9) for a, b in zip(parent, parent[1:])), "the parent only decays"
    for nuclide, values in r["series"].items():
        if nuclide != r["isotope"]:
            assert values[0] == pytest.approx(0.0, abs=1e-6), f"{nuclide} must start empty"
    assert list(r["series"])[0] == r["isotope"]


@pytest.mark.parametrize("name", engines_here())
def test_parent_follows_the_exponential_law(name):
    for isotope in ("Cs-137", "Co-60", "Am-241"):
        hl = manager._engines[name].get_half_life(isotope)
        r = manager.predict_decay(isotope, 1000.0, 5 * hl, points=6, engine_name=name)
        assert r["series"][isotope][-1] == pytest.approx(1000.0 * 2 ** -5, rel=1e-6)


@pytest.mark.parametrize("name", engines_here())
def test_daughters_appear_and_reach_equilibrium(name):
    r = manager.predict_decay("Cs-137", 1000.0, 3600.0, points=4, engine_name=name)           # an hour: Ba-137m is long since in equilibrium
    assert r["isotopes"][:2] == ["Cs-137", "Ba-137m"]
    assert r["series"]["Ba-137m"][-1] / r["series"]["Cs-137"][-1] == pytest.approx(0.9455, abs=0.002)   # the ~94.5 % branch: ICRP-107 says 94.4, ENSDF 94.7
    r = manager.predict_decay("Sr-90", 1000.0, 20 * YEAR, points=5, engine_name=name)
    assert "Y-90" in r["series"] and r["series"]["Y-90"][-1] == pytest.approx(r["series"]["Sr-90"][-1], rel=0.01)
    r = manager.predict_decay("Co-60", 1000.0, 10 * YEAR, points=3, engine_name=name)
    assert list(r["series"]) == ["Co-60"]                                                      # decays to stable Ni-60: nothing else to plot
    assert r["series"]["Co-60"][-1] == pytest.approx(1000.0 * 2 ** (-10 / 5.2713), rel=3e-3)


@pytest.mark.parametrize("name", engines_here())
def test_branching_is_respected(name):
    r = manager.predict_decay("Th-232", 1.0, 50 * YEAR, points=3, engine_name=name)
    assert r["series"]["Tl-208"][-1] / r["series"]["Bi-212"][-1] == pytest.approx(0.3594, abs=0.002)   # Bi-212 -> Tl-208 is 35.94 %
    r = manager.predict_decay("U-238", 1.0, 1e5 * YEAR, points=3, engine_name=name)
    ratio = r["series"]["Pa-234"][-1] / r["series"]["Pa-234m"][-1]                                      # the rare Pa-234 branch
    if name == "curie":
        # curie >= 0.3 carries a newer ENSDF evaluation in which Th-234 also feeds the Pa-234 ground state directly (0.68 %),
        # so the ratio is 0.0085; curie 0.0.x and ICRP-107 (radioactivedecay) have only Pa-234m -> Pa-234 (0.16 %)
        assert ratio == pytest.approx(0.0016, abs=0.0001) or ratio == pytest.approx(0.0085, abs=0.0003)
    else:
        assert ratio == pytest.approx(0.0016, abs=0.0001)


PARENTS = ["U-238", "Th-232", "Cs-137", "Sr-90", "Co-60", "Am-241", "Ra-226", "Mo-99", "I-131", "K-40", "Pb-210", "Eu-152", "Na-22"]


@pytest.mark.parametrize("isotope", PARENTS)
def test_builtin_agrees_with_radioactivedecay(isotope):
    if not available("radioactivedecay"):
        pytest.skip("radioactivedecay not installed")
    hl = manager._engines["builtin"].get_half_life(isotope)
    duration = min(hl * 3, 2e6 * YEAR)
    a = manager.predict_decay(isotope, 1.0, duration, points=12, engine_name="builtin")
    b = manager.predict_decay(isotope, 1.0, duration, points=12, engine_name="radioactivedecay")
    shared = set(a["series"]) & set(b["series"])
    assert isotope in shared and len(shared) >= max(1, 0.7 * min(len(a["series"]), len(b["series"])))
    for nuclide in shared:
        x, y = np.array(a["series"][nuclide]), np.array(b["series"][nuclide])
        significant = np.maximum(x, y) > 1e-6
        assert np.allclose(x[significant], y[significant], rtol=2e-4, atol=0), nuclide      # same data: only the arithmetic differs


@pytest.mark.parametrize("isotope", ["U-238", "Th-232", "Cs-137", "Sr-90", "Co-60", "Am-241", "Ra-226"])
def test_curie_agrees_with_radioactivedecay_to_the_data_differences(isotope):
    if not (available("curie") and available("radioactivedecay")):
        pytest.skip("curie or radioactivedecay not available")
    hl = manager._engines["builtin"].get_half_life(isotope)
    duration = min(hl * 2, 1e6 * YEAR)
    a = manager.predict_decay(isotope, 1.0, duration, points=8, engine_name="curie")
    b = manager.predict_decay(isotope, 1.0, duration, points=8, engine_name="radioactivedecay")
    for nuclide in set(a["series"]) & set(b["series"]):
        if isotope == "U-238" and nuclide == "Pa-234":
            continue        # a data difference, not an error: curie >= 0.3 (newer ENSDF) feeds Pa-234 from Th-234 directly, see test_branching_is_respected
        x, y = np.array(a["series"][nuclide]), np.array(b["series"][nuclide])
        significant = np.maximum(x, y) > 1e-4
        assert np.allclose(x[significant], y[significant], rtol=0.03), nuclide              # ENSDF vs ICRP-107 half-lives differ by up to ~1 %


def test_builtin_refuses_what_it_has_no_data_for_instead_of_drawing_a_flat_line():
    with pytest.raises(DecayInputError) as error:
        BuiltinEngine().predict_decay("Cf-252", 100.0, 1e6, 10)
    assert "no decay data" in str(error.value) and "radioactivedecay" in str(error.value)
    with pytest.raises(DecayInputError):
        BuiltinEngine().predict_decay("Ni-60", 100.0, 1e6, 10)         # stable


def test_auto_tries_engines_in_turn():
    r = manager.predict_decay("Cs-137", 100.0, 1e6, points=5, engine_name="auto")
    assert r["engine_requested"] == "auto" and r["engine_used"] == manager.get_default_engine_name()
    with pytest.raises(DecayInputError):
        manager.predict_decay("Xx-999", 100.0, 1e6, points=5, engine_name="auto")


def test_an_unavailable_engine_is_replaced_and_the_result_says_so(monkeypatch):
    monkeypatch.setattr(manager._engines["curie"], "available", False, raising=False)
    r = manager.predict_decay("Cs-137", 100.0, 1e6, points=5, engine_name="curie")
    assert r["engine_used"] != "curie" and r["warnings"] and "curie" in r["warnings"][0]


@pytest.mark.parametrize("kwargs", [
    dict(isotope="Xx-999", activity=100.0, duration_seconds=1e6),
    dict(isotope="", activity=100.0, duration_seconds=1e6),
    dict(isotope="Cs-137", activity=100.0, duration_seconds=-5.0),
    dict(isotope="Cs-137", activity=100.0, duration_seconds=0.0),
    dict(isotope="Cs-137", activity=100.0, duration_seconds=float("nan")),
    dict(isotope="Cs-137", activity=100.0, duration_seconds=1e30),
    dict(isotope="Cs-137", activity=0.0, duration_seconds=1e6),
    dict(isotope="Cs-137", activity=-1.0, duration_seconds=1e6),
    dict(isotope="Cs-137", activity=float("inf"), duration_seconds=1e6),
    dict(isotope="Cs-137", activity=100.0, duration_seconds=1e6, points=1),
    dict(isotope="Cs-137", activity=100.0, duration_seconds=1e6, points=100000),
    dict(isotope="Cs-137", activity=100.0, duration_seconds=1e6, engine_name="pyne"),
    dict(isotope="Ni-60", activity=100.0, duration_seconds=1e6),
])
def test_bad_input_is_rejected_by_the_manager(kwargs):
    with pytest.raises(DecayInputError):
        manager.predict_decay(**kwargs)


def test_hundreds_of_points_stay_fast():
    import time
    t0 = time.time()
    manager.predict_decay("U-238", 1000.0, 1e6 * YEAR, points=500, engine_name="builtin")
    assert time.time() - t0 < 5


# ------------------------------------------------------------------------------------------------ the API

def post(client, **body):
    return client.post("/analyze/decay-prediction", json=body)


def test_api_prediction_contract(client):
    r = post(client, isotope="Cs-137", initial_activity_bq=1000, duration_days=301 * 365.25)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["isotopes"][:2] == ["Cs-137", "Ba-137m"] and d["series"]["Cs-137"][0] == pytest.approx(1000.0)
    assert all(len(v) == len(d["time_points"]) for v in d["series"].values())
    assert d["engine_used"] and d["data_source"] and isinstance(d["warnings"], list)
    assert len(d["time_labels"]) == len(d["time_points"]) == len(d["time_points_days"])


@pytest.mark.parametrize("body", [
    dict(isotope="Xx-999", initial_activity_bq=1000, duration_days=10),
    dict(isotope="Cs-137", initial_activity_bq=1000, duration_days=-5),
    dict(isotope="Cs-137", initial_activity_bq=1000, duration_days=0),
    dict(isotope="Cs-137", initial_activity_bq=0, duration_days=10),
    dict(isotope="Cs-137", initial_activity_bq=1000, duration_days=1e308),
    dict(isotope="Cs-137", initial_activity_bq=1000, duration_days=10, engine="pyne"),
    dict(isotope="Ni-60", initial_activity_bq=1000, duration_days=10),
    dict(isotope="builtin-only-test", initial_activity_bq=1000, duration_days=10, engine="builtin"),
])
def test_api_rejects_what_it_cannot_compute(client, body):
    r = post(client, **body)
    assert r.status_code == 400, (r.status_code, r.text[:200])
    assert isinstance(r.json()["detail"], str) and r.json()["detail"]


def test_api_accepts_loose_isotope_names_and_hours(client):
    r = post(client, isotope="tc99m", initial_activity_bq=500, time_hours=24)
    assert r.status_code == 200 and r.json()["isotope"] == "Tc-99m"
    assert r.json()["series"]["Tc-99m"][-1] == pytest.approx(500 * 2 ** (-24 / 6.0072), rel=0.01)


def test_api_engine_list_and_isotope_picker(client):
    d = client.get("/analyze/decay-engines").json()
    assert [e["name"] for e in d["engines"]] == ["builtin", "radioactivedecay", "curie"]
    assert d["default"] in ("radioactivedecay", "curie", "builtin")
    names = [i["name"] for i in d["isotopes"]]
    assert "Cs-137" in names and "U-238" in names and len(names) > 40 and all(i["half_life"] for i in d["isotopes"])


def test_api_isotope_info(client):
    r = client.post("/analyze/isotope-info", json={"isotope": "cs-137"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["isotope"] == "Cs-137" and d["half_life_readable"] == "30.17 y" and d["decay_chain"][0]["isotope"] == "Cs-137"
    assert client.post("/analyze/isotope-info", json={"isotope": "Xx-999"}).status_code == 400
    assert client.post("/analyze/isotope-info", json={"isotope": "!"}).status_code in (400, 422)


# ------------------------------------------------------------------------------------------------ threads

@pytest.mark.skipif(not available("curie"), reason="curie not available")
def test_curie_works_from_any_worker_thread():
    """Regression: Curie opened its SQLite connection in the first thread that used it, so in a web server (a pool of threads)
    the next request often failed with "SQLite objects created in a thread can only be used in that same thread"."""
    from concurrent.futures import ThreadPoolExecutor
    isotopes = ["U-238", "Cs-137", "Co-60", "Th-232", "Sr-90", "Am-241", "Ra-226", "Mo-99"] * 3

    def run(isotope):
        return manager.predict_decay(isotope, 1000.0, 10 * YEAR, points=4, engine_name="curie")["engine_used"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(run, isotopes))
    assert results == ["curie"] * len(isotopes)
    decay_engine._curie_graph.cache_clear()                      # and a fresh lookup from yet another thread
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(run, "Eu-152").result() == "curie"


@pytest.mark.skipif(not available("curie"), reason="curie not available")
def test_curie_gamma_lookups_work_from_worker_threads():
    """The same bug made get_isotope_gammas() quietly return nothing on some threads (it swallows exceptions)."""
    from concurrent.futures import ThreadPoolExecutor
    import curie_integration
    with ThreadPoolExecutor(max_workers=4) as pool:
        lines = list(pool.map(lambda name: curie_integration.get_isotope_gammas(name), ["Cs-137", "Co-60", "Am-241", "Cs-137"] * 3))
    assert all(lines), "an empty list means the Curie lookup failed on some thread"
    assert any(abs(g["energy"] - 661.657) < 0.1 for g in lines[0])
