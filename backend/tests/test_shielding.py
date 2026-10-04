"""Shielding: coefficients against published NIST XCOM values, the physics that must hold, and the routes."""
import math

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("curie")

from main import app
from nuclides import shielding
from nuclides.shielding import ShieldingError, attenuation, isotope_lines, mass_coefficients

# NIST XCOM, mass attenuation coefficient mu/rho in cm2/g (https://physics.nist.gov/PhysRefData/XrayMassCoef/tab3.html)
NIST = [
    ("lead", 100, 5.549), ("lead", 500, 0.1614), ("lead", 1000, 0.07102),
    ("iron", 100, 0.3717), ("iron", 500, 0.08414), ("iron", 1000, 0.05995),
    ("aluminium", 100, 0.1704), ("aluminium", 500, 0.08445), ("aluminium", 1000, 0.06146),
    ("water", 1000, 0.07072),
]


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.mark.parametrize("material, energy, expected", NIST)
def test_mass_attenuation_matches_nist(material, energy, expected):
    assert mass_coefficients(material, energy)["mu_rho_cm2_g"] == pytest.approx(expected, rel=2e-3)


def test_concrete_from_the_nist_composition_is_close_to_the_nist_value():
    assert mass_coefficients("concrete", 1000)["mu_rho_cm2_g"] == pytest.approx(0.06372, rel=0.012)


def test_every_listed_material_loads_and_attenuates():
    for entry in shielding.list_materials():
        result = attenuation(entry["key"], 662, thickness_cm=1.0)
        assert 0 < result["transmission"] <= 1, entry
        assert result["density_g_cm3"] == entry["density_g_cm3"]


def test_half_and_tenth_value_layers_are_what_their_names_say():
    result = attenuation("lead", 662, thickness_cm=1.0)
    assert math.exp(-result["linear_attenuation_per_cm"] * result["half_value_layer_cm"]) == pytest.approx(0.5)
    assert math.exp(-result["linear_attenuation_per_cm"] * result["tenth_value_layer_cm"]) == pytest.approx(0.1)
    # narrow beam: ln2 / (0.1110 cm2/g * 11.34 g/cm3) = 0.55 cm (the 0.65 cm often quoted for lead includes scatter buildup)
    assert result["half_value_layer_cm"] == pytest.approx(0.55, abs=0.02)


def test_two_slabs_multiply_and_the_target_thickness_round_trips():
    one = attenuation("iron", 1332, thickness_cm=2.0)["transmission"]
    two = attenuation("iron", 1332, thickness_cm=4.0)["transmission"]
    assert two == pytest.approx(one * one)
    need = attenuation("iron", 1332, target_transmission=0.01)["thickness_for_target_cm"]
    assert attenuation("iron", 1332, thickness_cm=need)["transmission"] == pytest.approx(0.01)


def test_a_denser_version_of_the_same_material_attenuates_more():
    normal = attenuation("water", 662, thickness_cm=10.0)["transmission"]
    heavy = attenuation("water", 662, thickness_cm=10.0, density_g_cm3=1.2)["transmission"]
    assert heavy < normal


def test_cs137_through_a_centimetre_of_lead_keeps_about_a_quarter_of_its_photons():
    result = isotope_lines("Cs-137", "lead", 1.0)
    assert result["strongest_line_kev"] == pytest.approx(661.66, abs=0.1)
    assert result["transmission"] == pytest.approx(math.exp(-0.1110 * 11.34), rel=0.03)      # 0.28
    assert all(0 < row["transmission"] < 1 for row in result["lines"])


def test_a_pure_beta_emitter_has_no_gamma_lines_to_shield():
    with pytest.raises(ShieldingError, match="No gamma lines"):
        isotope_lines("Sr-90", "lead", 1.0)


@pytest.mark.parametrize("call", [
    lambda: attenuation("unobtainium", 662, thickness_cm=1),
    lambda: attenuation("lead", 0.5, thickness_cm=1),
    lambda: attenuation("lead", 30000, thickness_cm=1),
    lambda: attenuation("lead", 662, thickness_cm=-1),
    lambda: attenuation("lead", 662, target_transmission=1.5),
    lambda: attenuation("lead", 662, density_g_cm3=0),
])
def test_bad_input_raises_shielding_error(call):
    with pytest.raises(ShieldingError):
        call()


def test_route_lists_materials(client):
    body = client.get("/analyze/shielding/materials").json()
    assert {m["key"] for m in body["materials"]} >= {"lead", "water", "concrete", "air"}
    assert "narrow" in body["note"].lower()


def test_route_energy_mode(client):
    response = client.post("/analyze/shielding", json={"material": "lead", "energy_kev": 662, "thickness_cm": 0.55, "target_transmission": 0.5})
    assert response.status_code == 200
    body = response.json()
    assert body["transmission"] == pytest.approx(0.5, abs=0.02)
    assert body["thickness_for_target_cm"] == pytest.approx(body["half_value_layer_cm"])


def test_route_isotope_mode(client):
    response = client.post("/analyze/shielding", json={"material": "lead", "isotope": "Co-60", "thickness_cm": 2.0})
    assert response.status_code == 200
    body = response.json()
    energies = [row["energy_kev"] for row in body["lines"]]
    assert any(abs(e - 1173.2) < 0.5 for e in energies) and any(abs(e - 1332.5) < 0.5 for e in energies)
    assert 0 < body["transmission"] < 1


@pytest.mark.parametrize("payload, status", [
    ({"material": "lead"}, 422),                                                     # neither energy nor isotope
    ({"material": "lead", "energy_kev": 662, "isotope": "Cs-137", "thickness_cm": 1}, 422),
    ({"material": "lead", "isotope": "Cs-137"}, 422),                                # an isotope needs a thickness
    ({"material": "lead", "energy_kev": 662, "thickness_cm": -1}, 422),
    ({"material": "lead", "energy_kev": 662, "target_transmission": 1.0}, 422),
    ({"material": "unobtainium", "energy_kev": 662, "thickness_cm": 1}, 400),
    ({"material": "lead", "energy_kev": 5e4, "thickness_cm": 1}, 400),
    ({"material": "lead", "isotope": "Sr-90", "thickness_cm": 1}, 400),
])
def test_route_rejects_bad_requests(client, payload, status):
    assert client.post("/analyze/shielding", json=payload).status_code == status


# ---- emissions: what the alpha and beta channels can see ----

from nuclides.emissions import beta_range_mg_cm2, particle_emissions


def test_po210_is_a_pure_alpha_emitter_with_a_range_of_a_few_centimetres_of_air():
    result = particle_emissions("Po-210")
    strongest = result["alphas"][0]
    assert strongest["energy_kev"] == pytest.approx(5304.3, abs=0.1) and strongest["intensity_percent"] == pytest.approx(100)
    # curie's stopping power against the textbook R = 0.31 * E^1.5 cm (E in MeV): within 10 %
    assert strongest["range_air_cm"] == pytest.approx(0.31 * 5.3043 ** 1.5, rel=0.10)
    assert result["betas"] == [] and "alpha" in result["channels"]


def test_sr90_beta_reaches_a_metre_and_a_half_of_air_but_less_than_a_millimetre_of_aluminium():
    beta = particle_emissions("Sr-90")["betas"][0]
    assert beta["endpoint_energy_kev"] == pytest.approx(546.0)
    assert beta["max_range_air_cm"] == pytest.approx(154, rel=0.03)
    assert 0.5 < beta["max_range_aluminium_mm"] < 1.0


def test_katz_penfold_is_continuous_and_gives_the_known_y90_range():
    assert beta_range_mg_cm2(2280) / ALUMINIUM_MG_CM2_PER_MM == pytest.approx(4.06, rel=0.02)      # Y-90 betas: about 4 mm of aluminium
    assert beta_range_mg_cm2(2499.9) == pytest.approx(beta_range_mg_cm2(2500.1), rel=0.01)           # the two pieces of the formula meet


ALUMINIUM_MG_CM2_PER_MM = 269.9


def test_cs137_emits_beta_and_gamma_and_lines_below_the_threshold_are_dropped():
    everything = particle_emissions("Cs-137", min_intensity=0.0)
    main = particle_emissions("Cs-137", min_intensity=1.0)
    assert main["channels"] == ["beta", "gamma"]
    assert len(everything["betas"]) > len(main["betas"]) == 2
    assert [b["endpoint_energy_kev"] for b in main["betas"]][:1] == [pytest.approx(513.97)]


def test_unknown_isotope_is_a_shielding_error():
    with pytest.raises(ShieldingError, match="No decay data"):
        particle_emissions("Zz-999")


def test_emissions_route(client):
    body = client.get("/analyze/emissions", params={"isotope": "Po-210"}).json()
    assert body["alphas"][0]["range_air_cm"] > 3
    assert client.get("/analyze/emissions", params={"isotope": "Zz-999"}).status_code == 400
    assert client.get("/analyze/emissions").status_code == 422
    assert client.get("/analyze/emissions", params={"isotope": "Cs-137", "min_intensity": 500}).status_code == 422
