"""
Gamma shielding: how much of a photon beam a slab of material lets through.

Mass attenuation coefficients are NIST XCOM values read from the curie package (offline). Curie 0.0.33's own named presets
(Water, Air, SS_316 ...) fail to load, so every material here is an element or a formula/composition given explicitly; the
compositions are the NIST ones.

This is narrow-beam (good geometry) attenuation, exp(-mu * x): photons that scatter in the slab and still reach the detector are
not counted, so the real transmission of a thick shield, or a shield close to the source, is higher. Treat the result as a
lower bound on what gets through, not a dose calculation.
"""
import functools
import logging
import math
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import curie
    from nuclides.curie_compat import CURIE_LOCK, make_curie_thread_safe
    make_curie_thread_safe(curie)
    HAS_CURIE = True
except ImportError:
    HAS_CURIE = False

# XCOM covers 1 keV to 100 GeV; curie ships the range gamma spectroscopy needs
MIN_ENERGY_KEV = 1.0
MAX_ENERGY_KEV = 20000.0

# key: (display name, curie element symbol / chemical formula, composition by mass fraction or None, density g/cm3)
MATERIALS = {
    "lead":          ("Lead",                "Pb",     None, 11.34),
    "tungsten":      ("Tungsten",            "W",      None, 19.25),
    "bismuth":       ("Bismuth",             "Bi",     None, 9.78),
    "tin":           ("Tin",                 "Sn",     None, 7.31),
    "copper":        ("Copper",              "Cu",     None, 8.96),
    "iron":          ("Iron / mild steel",   "Fe",     None, 7.874),
    "aluminium":     ("Aluminium",           "Al",     None, 2.699),
    "water":         ("Water",               "H2O",    None, 1.0),
    "acrylic":       ("Acrylic (PMMA)",      "C5H8O2", None, 1.19),
    "polyethylene":  ("Polyethylene",        "CH2",    None, 0.94),
    "glass":         ("Silica glass (SiO2)", "SiO2",   None, 2.2),
    "concrete":      ("Concrete (ordinary, NIST)", None,
                      {"H": 0.010, "C": 0.001, "O": 0.529107, "Na": 0.016, "Mg": 0.002, "Al": 0.033872, "Si": 0.337021,
                       "K": 0.013, "Ca": 0.044, "Fe": 0.014}, 2.3),
    "air":           ("Dry air (sea level)", None,
                      {"C": 0.000124, "N": 0.755268, "O": 0.231781, "Ar": 0.012827}, 0.001205),
}


class ShieldingError(ValueError):
    """The request cannot be answered (unknown material, energy out of range, no gamma data ...): the caller's to fix."""


def _locked(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with CURIE_LOCK:
            return fn(*args, **kwargs)
    return wrapper


def list_materials() -> List[Dict]:
    return [{"key": key, "name": name, "density_g_cm3": density} for key, (name, _, _, density) in MATERIALS.items()]


@functools.lru_cache(maxsize=None)
def _material(key: str):
    if key not in MATERIALS:
        raise ShieldingError(f"Unknown material '{key}'. Choose one of: {', '.join(MATERIALS)}")
    _, formula, composition, density = MATERIALS[key]
    if len(formula or "") <= 2 and formula:
        return curie.Element(formula)
    if composition:
        return curie.Compound(key, weights={el: -fraction for el, fraction in composition.items()}, density=density)
    return curie.Compound(formula, density=density)


def _check_energy(energy_kev: float) -> float:
    if not (MIN_ENERGY_KEV <= energy_kev <= MAX_ENERGY_KEV):
        raise ShieldingError(f"The photon energy must be between {MIN_ENERGY_KEV:g} and {MAX_ENERGY_KEV:g} keV")
    return float(energy_kev)


@_locked
def mass_coefficients(material: str, energy_kev: float) -> Dict[str, float]:
    """mu/rho and mu_en/rho in cm2/g (NIST XCOM): attenuation, and energy absorption (what a dose is made from)."""
    if not HAS_CURIE:
        raise ShieldingError("The curie package is not installed")
    obj, energy = _material(material), _check_energy(energy_kev)
    return {"mu_rho_cm2_g": float(obj.mu(energy)), "mu_en_rho_cm2_g": float(obj.mu_en(energy))}


@_locked
def alpha_range_cm(material: str, energy_kev: float) -> float:
    """Range of an alpha particle in the material (curie's stopping power), in cm."""
    if not HAS_CURIE:
        raise ShieldingError("The curie package is not installed")
    if not (energy_kev > 0):
        raise ShieldingError("The alpha energy must be more than zero")
    return float(_material(material).range(energy_kev / 1000.0, particle='a', density=MATERIALS[material][3]))


def attenuation(material: str, energy_kev: float, thickness_cm: Optional[float] = None,
                target_transmission: Optional[float] = None, density_g_cm3: Optional[float] = None) -> Dict:
    """
    Narrow-beam attenuation of one photon energy by a slab.

    Returns the coefficients, the linear attenuation coefficient, the half-value and tenth-value layers, the mean free path and,
    if asked, the transmitted fraction through `thickness_cm` and the thickness that lets only `target_transmission` through.
    """
    density = MATERIALS[material][3] if material in MATERIALS else None
    if density_g_cm3 is not None:
        if not (density_g_cm3 > 0):
            raise ShieldingError("The density must be more than zero")
        density = density_g_cm3
    coefficients = mass_coefficients(material, energy_kev)
    mu = coefficients["mu_rho_cm2_g"] * density                      # per cm
    result = {
        "material": material, "energy_kev": float(energy_kev), "density_g_cm3": density, **coefficients,
        "linear_attenuation_per_cm": mu,
        "half_value_layer_cm": math.log(2) / mu, "tenth_value_layer_cm": math.log(10) / mu, "mean_free_path_cm": 1 / mu,
    }
    if thickness_cm is not None:
        if thickness_cm < 0:
            raise ShieldingError("The thickness cannot be negative")
        result["thickness_cm"] = float(thickness_cm)
        result["transmission"] = math.exp(-mu * thickness_cm)
    if target_transmission is not None:
        if not (0 < target_transmission < 1):
            raise ShieldingError("The target transmission must be between 0 and 1 (exclusive)")
        result["target_transmission"] = float(target_transmission)
        result["thickness_for_target_cm"] = -math.log(target_transmission) / mu
    return result


def isotope_lines(isotope: str, material: str, thickness_cm: float, min_intensity: float = 1.0,
                  density_g_cm3: Optional[float] = None) -> Dict:
    """
    What a slab does to each gamma line of an isotope (lines of at least `min_intensity` percent), and to the emission as a whole:
    `transmission` is the fraction of the emitted photons (weighted by line intensity) that gets through.
    """
    from nuclides.curie_integration import get_isotope_gammas
    if thickness_cm < 0:
        raise ShieldingError("The thickness cannot be negative")
    lines = get_isotope_gammas(isotope, min_intensity=min_intensity)
    lines = [line for line in lines if MIN_ENERGY_KEV <= line["energy"] <= MAX_ENERGY_KEV]
    if not lines:
        raise ShieldingError(f"No gamma lines of at least {min_intensity:g} % are known for '{isotope}'")
    rows, emitted, transmitted = [], 0.0, 0.0
    for line in lines:
        one = attenuation(material, line["energy"], thickness_cm=thickness_cm, density_g_cm3=density_g_cm3)
        rows.append({"energy_kev": line["energy"], "intensity_percent": line["intensity"], "transmission": one["transmission"],
                     "half_value_layer_cm": one["half_value_layer_cm"]})
        emitted += line["intensity"]
        transmitted += line["intensity"] * one["transmission"]
    strongest = max(rows, key=lambda r: r["intensity_percent"])
    return {"isotope": isotope, "material": material, "thickness_cm": float(thickness_cm), "lines": rows,
            "transmission": transmitted / emitted, "strongest_line_kev": strongest["energy_kev"]}
