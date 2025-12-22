"""
Detector Efficiency Database for ROI Analysis

Contains efficiency curves for AlphaHound ABG detectors and common lab detectors.
Efficiencies are approximate and should be calibrated with known sources for
accurate quantitative analysis.

Data sources:
- AlphaHound specs: RadView Detection documentation
- Efficiency curves: Approximate values based on crystal type and volume
"""

from typing import Dict, Optional
import math

# AlphaHound AB+G Detector Specifications
# Source: RadView Detection official product specs (August 2025)
# 
# BGO (legacy): 42.0 cps/μSv/h, 0.6 cm³, Resolution ≤13%
# CsI(Tl) (current): 48.0 cps/μSv/h, 1.1 cm³, Resolution ≤10%

DETECTOR_DATABASE = {
    # === AlphaHound AB+G Detectors (Official Specs) ===
    "AlphaHound CsI(Tl)": {
        "type": "CsI(Tl)",
        "description": "AlphaHound AB+G - CsI(Tl) crystal (Official Current Spec)",
        "dimensions_mm": None,  # Not specified
        "volume_cm3": 1.1,
        "min_energy_keV": 20,  # Lowered from BGO's 50 keV
        "cs137_sensitivity_cps_per_uSv_h": 48.0,  # Official: 48 cps/μSv/h
        "energy_resolution_662keV": 0.10,  # ≤10% FWHM at 662 keV
        "efficiencies": {
            # Scaled based on 1.1 cm³ CsI(Tl) crystal
            # Higher efficiency than BGO due to larger volume
            20: 25.0,  # Low energy threshold
            60: 22.0,
            93: 18.5,
            122: 15.5,
            186: 13.0,
            352: 7.5,
            511: 5.5,
            609: 4.5,
            662: 4.0,
            1173: 2.0,
            1332: 1.7,
            1461: 1.5,
            2614: 0.8,
        }
    },
    "AlphaHound BGO": {
        "type": "BGO",
        "description": "AlphaHound AB+G - BGO crystal (Legacy Spec)",
        "dimensions_mm": (5, 5, 25),
        "volume_cm3": 0.6,  # 5×5×25mm = 0.625 cm³
        "min_energy_keV": 50,  # >50 keV gamma detection
        "cs137_sensitivity_cps_per_uSv_h": 42.0,  # Official: 42 cps/μSv/h
        "energy_resolution_662keV": 0.13,  # ≤13% FWHM at 662 keV
        "efficiencies": {
            # Based on 0.6 cm³ BGO crystal
            60: 15.0,
            93: 12.5,
            122: 10.5,
            186: 8.75,
            352: 5.2,
            511: 3.5,
            609: 3.1,
            662: 2.8,
            1173: 1.5,
            1332: 1.2,
            1461: 1.0,
            2614: 0.5,
        }
    },
    
    # === Other Common Detectors ===
    "NaI 2x2": {
        "type": "NaI(Tl)",
        "description": "Standard 2×2 inch NaI scintillator",
        "dimensions_mm": (50.8, 50.8),  # 2" diameter × 2" height
        "volume_cm3": 103.0,
        "min_energy_keV": 20,
        "cs137_sensitivity_cps_per_uSv_h": 350,  # Approximate
        "efficiencies": {
            60: 55.0,
            93: 45.0,
            122: 40.0,
            186: 32.0,
            352: 18.0,
            511: 12.0,
            609: 9.5,
            662: 8.2,
            1173: 3.8,
            1332: 3.2,
            1461: 2.8,
            2614: 1.2,
        }
    },
    
    # === Radiacode Detectors ===
    "Radiacode 103": {
        "type": "CsI(Tl)",
        "description": "Radiacode 103 - CsI(Tl) 10×10×10mm",
        "dimensions_mm": (10, 10, 10),
        "volume_cm3": 1.0,
        "min_energy_keV": 20,
        "cs137_sensitivity_cps_per_uSv_h": 30.0,
        "energy_resolution_662keV": 0.084,  # 8.4% FWHM
        "efficiencies": {
            # Based on 1.0 cm³ CsI(Tl) crystal
            20: 22.0,
            60: 19.0,
            93: 16.0,
            122: 13.5,
            186: 11.0,
            352: 6.5,
            511: 4.8,
            609: 3.9,
            662: 3.5,
            1173: 1.8,
            1332: 1.5,
            1461: 1.3,
            2614: 0.7,
        }
    },
    "Radiacode 103G": {
        "type": "GAGG",
        "description": "Radiacode 103G - GAGG 10×10×10mm (best resolution)",
        "dimensions_mm": (10, 10, 10),
        "volume_cm3": 1.0,
        "min_energy_keV": 20,
        "cs137_sensitivity_cps_per_uSv_h": 40.0,
        "energy_resolution_662keV": 0.074,  # 7.4% FWHM - best resolution
        "efficiencies": {
            # GAGG has higher light yield than CsI(Tl)
            20: 24.0,
            60: 21.0,
            93: 17.5,
            122: 14.5,
            186: 12.0,
            352: 7.0,
            511: 5.2,
            609: 4.2,
            662: 3.8,
            1173: 1.9,
            1332: 1.6,
            1461: 1.4,
            2614: 0.75,
        }
    },
    "Radiacode 110": {
        "type": "CsI(Tl)",
        "description": "Radiacode 110 - CsI(Tl) 14×14×14mm (highest sensitivity)",
        "dimensions_mm": (14, 14, 14),
        "volume_cm3": 3.0,  # ~2.7 cm³
        "min_energy_keV": 20,
        "cs137_sensitivity_cps_per_uSv_h": 77.0,  # Highest sensitivity
        "energy_resolution_662keV": 0.084,  # 8.4% FWHM
        "efficiencies": {
            # Larger crystal = higher efficiency
            20: 35.0,
            60: 30.0,
            93: 25.0,
            122: 21.0,
            186: 17.5,
            352: 10.5,
            511: 7.5,
            609: 6.2,
            662: 5.5,
            1173: 2.8,
            1332: 2.4,
            1461: 2.1,
            2614: 1.1,
        }
    },
    
    "Custom": {
        "type": "Custom",
        "description": "User-defined detector efficiency",
        "dimensions_mm": None,
        "volume_cm3": 1.0,
        "min_energy_keV": 50,
        "cs137_sensitivity_cps_per_uSv_h": None,
        "efficiencies": {}  # User will input
    }
}



def get_detector(name: str) -> Optional[Dict]:
    """Get detector configuration by name."""
    return DETECTOR_DATABASE.get(name)


def get_detector_names() -> list:
    """Get list of available detector names."""
    return list(DETECTOR_DATABASE.keys())


def interpolate_efficiency(detector_name: str, energy_keV: float) -> float:
    """
    Interpolate detector efficiency at a given energy.
    Uses linear interpolation between known efficiency points.
    
    Args:
        detector_name: Name of detector in database
        energy_keV: Energy in keV
        
    Returns:
        Efficiency as a fraction (0.0-1.0), or 0.0 if not available
    """
    detector = get_detector(detector_name)
    if not detector or not detector["efficiencies"]:
        return 0.0
    
    efficiencies = detector["efficiencies"]
    energies = sorted(efficiencies.keys())
    
    # Check bounds
    if energy_keV <= energies[0]:
        return efficiencies[energies[0]] / 100.0
    if energy_keV >= energies[-1]:
        return efficiencies[energies[-1]] / 100.0
    
    # Find bracketing energies
    for i in range(len(energies) - 1):
        if energies[i] <= energy_keV <= energies[i + 1]:
            e1, e2 = energies[i], energies[i + 1]
            eff1, eff2 = efficiencies[e1], efficiencies[e2]
            
            # Linear interpolation
            fraction = (energy_keV - e1) / (e2 - e1)
            efficiency = eff1 + fraction * (eff2 - eff1)
            return efficiency / 100.0
    
    return 0.0


def estimate_activity(
    peak_counts: float,
    energy_keV: float,
    branching_ratio: float,
    live_time_s: float,
    detector_name: str = "AlphaHound CsI(Tl)"
) -> dict:
    """
    Estimate source activity from peak counts.
    
    Formula: Activity (Bq) = Counts / (Efficiency × BranchingRatio × LiveTime)
    
    Args:
        peak_counts: Net counts in the peak (background subtracted)
        energy_keV: Gamma energy in keV
        branching_ratio: Gamma emission probability (0.0-1.0)
        live_time_s: Measurement live time in seconds
        detector_name: Name of detector for efficiency lookup
        
    Returns:
        Dict with 'activity_bq', 'activity_readable', 'uncertainty_pct', 'method'
    """
    result = {
        'activity_bq': None,
        'activity_readable': None,
        'uncertainty_pct': None,
        'method': 'peak_area',
        'valid': False
    }
    
    # Validate inputs
    if peak_counts <= 0 or live_time_s <= 0 or branching_ratio <= 0:
        result['method'] = 'invalid_input'
        return result
    
    # Get detector efficiency at this energy
    efficiency = interpolate_efficiency(detector_name, energy_keV)
    if efficiency <= 0:
        result['method'] = 'no_efficiency_data'
        return result
    
    # Calculate activity: A = N / (ε × γ × t)
    # where N = counts, ε = efficiency, γ = branching ratio, t = time
    activity_bq = peak_counts / (efficiency * branching_ratio * live_time_s)
    
    # Poisson uncertainty on counts propagates to activity
    # σ_A/A = σ_N/N = 1/√N
    uncertainty_pct = 100.0 / math.sqrt(peak_counts) if peak_counts > 0 else 100.0
    
    result['activity_bq'] = float(activity_bq)
    result['uncertainty_pct'] = float(uncertainty_pct)
    result['valid'] = True
    
    # Format readable activity string
    if activity_bq >= 1e6:
        result['activity_readable'] = f"{activity_bq/1e6:.1f} MBq"
    elif activity_bq >= 1e3:
        result['activity_readable'] = f"{activity_bq/1e3:.1f} kBq"
    elif activity_bq >= 1:
        result['activity_readable'] = f"{activity_bq:.1f} Bq"
    else:
        result['activity_readable'] = f"{activity_bq*1e3:.2f} mBq"
    
    return result


def calculate_mda(
    background_counts: float,
    energy_keV: float,
    branching_ratio: float,
    live_time_s: float,
    detector_name: str = "AlphaHound CsI(Tl)",
    confidence_level: float = 0.95
) -> dict:
    """
    Calculate Minimum Detectable Activity (MDA) using Currie's formula.
    
    MDA represents the smallest activity that can be detected with statistical
    confidence. Uses the widely accepted Currie (1968) formula:
    
    L_D = 2.71 + 4.65 × √B  (for 95% confidence)
    MDA = L_D / (ε × γ × t)
    
    Args:
        background_counts: Background counts in the ROI
        energy_keV: Gamma energy in keV (for efficiency lookup)
        branching_ratio: Gamma emission probability (0.0-1.0)
        live_time_s: Measurement live time in seconds
        detector_name: Name of detector for efficiency lookup
        confidence_level: Confidence level (default 0.95 for 95%)
        
    Returns:
        Dict with 'mda_bq', 'mda_readable', 'detection_limit_counts', 'valid'
    """
    result = {
        'mda_bq': None,
        'mda_readable': None,
        'detection_limit_counts': None,
        'valid': False,
        'confidence_level': confidence_level
    }
    
    # Validate inputs
    if background_counts < 0 or live_time_s <= 0 or branching_ratio <= 0:
        return result
    
    # Get detector efficiency at this energy
    efficiency = interpolate_efficiency(detector_name, energy_keV)
    if efficiency <= 0:
        return result
    
    # Currie's formula for detection limit (95% confidence)
    # L_D = 2.71 + 4.65 × √B
    # For different confidence levels, constants change slightly
    if confidence_level >= 0.99:
        k_alpha = 2.33
        k_beta = 2.33
    else:  # 95% default
        k_alpha = 1.645
        k_beta = 1.645
    
    # Detection limit in counts
    # L_D = k_alpha^2 + 2*k_beta*sqrt(B) for paired blank
    # Simplified Currie: L_D ≈ 2.71 + 4.65*sqrt(B) for k=1.645
    L_D = 2.71 + 4.65 * math.sqrt(max(0, background_counts))
    
    result['detection_limit_counts'] = float(L_D)
    
    # Convert to activity: MDA = L_D / (ε × γ × t)
    mda_bq = L_D / (efficiency * branching_ratio * live_time_s)
    
    result['mda_bq'] = float(mda_bq)
    result['valid'] = True
    
    # Format readable MDA string
    if mda_bq >= 1e6:
        result['mda_readable'] = f"{mda_bq/1e6:.2f} MBq"
    elif mda_bq >= 1e3:
        result['mda_readable'] = f"{mda_bq/1e3:.2f} kBq"
    elif mda_bq >= 1:
        result['mda_readable'] = f"{mda_bq:.2f} Bq"
    else:
        result['mda_readable'] = f"{mda_bq*1e3:.2f} mBq"
    
    return result
