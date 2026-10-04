"""
What an isotope emits besides gamma rays, and how far it gets: the AlphaHound has alpha and beta channels, and whether a source can
reach them depends on these ranges as much as on its activity.

Lines and intensities come from curie (ENSDF). Alpha range uses curie's stopping power (Ziegler); beta range uses the Katz-Penfold
empirical formula on the endpoint energy, which is the farthest a beta goes (the mean beta stops sooner).
"""
import logging
import math
from typing import Dict

logger = logging.getLogger(__name__)

try:
    import curie
    from nuclides.curie_compat import CURIE_LOCK, make_curie_thread_safe
    make_curie_thread_safe(curie)
    HAS_CURIE = True
except ImportError:
    HAS_CURIE = False

from nuclides.shielding import ShieldingError, alpha_range_cm, MATERIALS

AIR_DENSITY_G_CM3 = MATERIALS["air"][3]
ALUMINIUM_DENSITY_G_CM3 = MATERIALS["aluminium"][3]


def beta_range_mg_cm2(endpoint_kev: float) -> float:
    """Katz-Penfold: the maximum range of a beta of this endpoint energy, in mg/cm2 (any material, to a few percent)."""
    e = endpoint_kev / 1000.0                                        # MeV
    if e <= 0:
        raise ShieldingError("The beta endpoint energy must be more than zero")
    if e < 2.5:
        return 412.0 * e ** (1.265 - 0.0954 * math.log(e))
    return 530.0 * e - 106.0


def particle_emissions(isotope: str, min_intensity: float = 1.0) -> Dict:
    """
    Alpha and beta emissions of an isotope with the lines of at least `min_intensity` percent, each with how far it travels
    (alpha: range in air; beta: maximum range in air and in aluminium), plus the count of gamma lines for context.
    """
    if not HAS_CURIE:
        raise ShieldingError("The curie package is not installed")
    with CURIE_LOCK:
        try:
            iso = curie.Isotope(isotope)
            alphas, betas, electrons, gammas = iso.alphas(), iso.beta_minus(), iso.electrons(), iso.gammas()
        except Exception as e:
            raise ShieldingError(f"No decay data for '{isotope}'") from e

    alpha_rows = [
        {"energy_kev": float(r.energy), "intensity_percent": float(r.intensity),
         "range_air_cm": alpha_range_cm("air", float(r.energy))}
        for r in alphas.itertuples() if r.intensity >= min_intensity
    ]
    beta_rows = []
    for r in betas.itertuples():
        if r.intensity < min_intensity:
            continue
        mg = beta_range_mg_cm2(float(r.endpoint_energy))
        beta_rows.append({
            "mean_energy_kev": float(r.mean_energy), "endpoint_energy_kev": float(r.endpoint_energy),
            "intensity_percent": float(r.intensity),
            "max_range_air_cm": mg / 1000.0 / AIR_DENSITY_G_CM3,
            "max_range_aluminium_mm": mg / 1000.0 / ALUMINIUM_DENSITY_G_CM3 * 10.0,
        })
    alpha_rows.sort(key=lambda r: -r["intensity_percent"])
    beta_rows.sort(key=lambda r: -r["intensity_percent"])

    channels = [name for name, rows in (("alpha", alpha_rows), ("beta", beta_rows), ("gamma", gammas.index)) if len(rows)]
    return {
        "isotope": isotope, "min_intensity_percent": min_intensity,
        "alphas": alpha_rows, "betas": beta_rows,
        "gamma_lines": int(len(gammas)), "conversion_electron_lines": int(len(electrons)),
        "channels": channels,
        "note": "A pure alpha or beta emitter needs to be within the stated range of the detector window, with nothing in between.",
    }
