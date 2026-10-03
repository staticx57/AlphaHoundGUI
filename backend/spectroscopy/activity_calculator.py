
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

# Gamma Dose Constants: mSv·m²/GBq·h (ICRP/NCRP data)
# These are air-kerma rate constants at 1 meter per GBq
GAMMA_DOSE_CONSTANTS = {
    # Common calibration sources
    'Cs-137': 0.0774,    # 662 keV
    'Co-60': 0.3090,     # 1173 + 1332 keV
    'Am-241': 0.0032,    # 59.5 keV (low energy)
    'Na-22': 0.2810,     # 511 + 1274 keV
    'Ba-133': 0.0538,    # Multiple low-energy
    'Mn-54': 0.1210,     # 835 keV
    
    # Natural decay chains
    'Ra-226': 0.196,     # With daughters in equilibrium
    'Th-232': 0.058,     # Thorium series
    'U-238': 0.0043,     # Uranium without daughters
    'K-40': 0.0218,      # 1461 keV
    
    # Medical/Industrial
    'I-131': 0.0550,     # 364 keV
    'Tc-99m': 0.0022,    # 140 keV
    'Ir-192': 0.1180,    # Industrial radiography
}

def calculate_dose_rate(
    activity_bq: float,
    isotope: str,
    distance_m: float = 1.0
) -> Dict:
    """
    Calculate gamma dose rate at a given distance using point source approximation.
    
    Formula: D (mSv/h) = Γ × A / d²
    
    Where:
        Γ = Gamma dose constant (mSv·m²/GBq·h)
        A = Activity (GBq)
        d = Distance (m)
    
    Args:
        activity_bq: Source activity in Becquerels
        isotope: Isotope name (e.g., 'Cs-137')
        distance_m: Distance from source in meters
        
    Returns:
        Dict with dose_rate_mSv_h, dose_rate_uSv_h, safe_distance_m, readable
    """
    result = {
        'dose_rate_mSv_h': None,
        'dose_rate_uSv_h': None,
        'safe_distance_m': None,
        'readable': None,
        'isotope': isotope,
        'distance_m': distance_m,
        'valid': False
    }
    
    if activity_bq <= 0 or distance_m <= 0:
        return result
    
    gamma_constant = GAMMA_DOSE_CONSTANTS.get(isotope)
    if gamma_constant is None:
        result['readable'] = f"No gamma constant for {isotope}"
        return result
    
    # Convert Bq to GBq
    activity_gbq = activity_bq / 1e9
    
    # Calculate dose rate: D = Γ × A / d²
    dose_rate_mSv_h = gamma_constant * activity_gbq / (distance_m ** 2)
    dose_rate_uSv_h = dose_rate_mSv_h * 1000
    
    result['dose_rate_mSv_h'] = float(dose_rate_mSv_h)
    result['dose_rate_uSv_h'] = float(dose_rate_uSv_h)
    result['valid'] = True
    
    # Calculate safe handling distance (where dose < 1 µSv/h)
    # 1 µSv/h = 0.001 mSv/h
    # d² = Γ × A / 0.001 → d = sqrt(Γ × A × 1000)
    safe_distance = math.sqrt(gamma_constant * activity_gbq * 1000)
    result['safe_distance_m'] = float(safe_distance)
    
    # Format readable string
    if dose_rate_uSv_h >= 1000:
        result['readable'] = f"{dose_rate_mSv_h:.2f} mSv/h at {distance_m}m"
    elif dose_rate_uSv_h >= 1:
        result['readable'] = f"{dose_rate_uSv_h:.1f} µSv/h at {distance_m}m"
    else:
        result['readable'] = f"{dose_rate_uSv_h*1000:.1f} nSv/h at {distance_m}m"
    
    return result


def calculate_dose_rate_sv_h(
    activity_bq: float,
    gamma_energies_jev: List[Tuple[float, float]], # (Energy MeV, Yield)
    distance_m: float = 0.1
) -> float:
    """
    Legacy function - Estimate Gamma Dose Rate using energy-based approximation.
    Use calculate_dose_rate() for isotope-specific calculations.
    
    Simplified formula for when isotope is unknown:
    D (Sv/h) ≈ (Sum(Energy_MeV * Yield) * 0.5 * Activity) / Distance^2
    """
    if activity_bq <= 0 or distance_m <= 0:
        return 0.0
    
    if not gamma_energies_jev:
        return 0.0
    
    # Sum weighted energy contributions
    # Approximate gamma constant from energies: 0.5 factor for conversion
    weighted_energy_sum = sum(e * y for e, y in gamma_energies_jev)
    
    # Very rough approximation: 5e-18 Sv·m²/Bq·h per MeV
    dose_rate = 5e-18 * weighted_energy_sum * activity_bq / (distance_m ** 2)
    
    return dose_rate
