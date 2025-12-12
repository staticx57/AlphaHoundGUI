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
