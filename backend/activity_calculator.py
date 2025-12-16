
"""
Activity & Dose Rate Calculator
"""
import math
from typing import List, Dict, Tuple

# === CONSTANTS ===
BQ_TO_UCI = 1 / 37000.0  # 1 uCi = 37,000 Bq
UCI_TO_BQ = 37000.0

def calculate_activity_bq(
    net_counts: float,
    acquisition_time_s: float,
    efficiency_fraction: float,
    branching_ratio_fraction: float
) -> float:
    """
    Calculate activity in Becquerels (Bq).
    
    A = NetCounts / (Time * Efficiency * BranchingRatio)
    """
    if acquisition_time_s <= 0 or efficiency_fraction <= 0 or branching_ratio_fraction <= 0:
        return 0.0
        
    return net_counts / (acquisition_time_s * efficiency_fraction * branching_ratio_fraction)

def bq_to_uci(bq: float) -> float:
    """Convert Bq to uCi."""
    return bq * BQ_TO_UCI

def calculate_mda_bq(
    background_counts: float,
    acquisition_time_s: float,
    efficiency_fraction: float,
    branching_ratio_fraction: float
) -> float:
    """
    Calculate Minimum Detectable Activity (limit) using Curie Equation.
    
    L_D (counts) = 2.71 + 4.65 * sqrt(Background)
    MDA (Bq) = L_D / (Time * Eff * BR)
    """
    if acquisition_time_s <= 0 or efficiency_fraction <= 0 or branching_ratio_fraction <= 0:
        return 0.0
        
    ld_counts = 2.71 + 4.65 * math.sqrt(background_counts)
    return ld_counts / (acquisition_time_s * efficiency_fraction * branching_ratio_fraction)

def calculate_dose_rate_sv_h(
    activity_bq: float,
    gamma_energies_jev: List[Tuple[float, float]], # (Energy MeV, Yield)
    distance_m: float = 0.1
) -> float:
    """
    Estimate Gamma Dose Rate at a distance (point source approximation).
    
    Simplified formula:
    D (Sv/h) = (GammaConstant * Activity) / Distance^2
    
    Or summing contributions:
    Gamma Constant approx = Sum(Energy_MeV * Yield) * 0.5 (rough factor for air kerma)
    
    This is highly approximate.
    """
    # Placeholder - reliable dose constants required per isotope
    return 0.0
