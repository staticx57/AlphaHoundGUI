"""
Nuclear Data Module - Gamma and X-Ray Line Database

Provides gamma line search and X-ray fluorescence line lookup.
Ported from PyGammaSpec with enhancements.
"""

from typing import List, Dict, Tuple, Optional

# === Common Gamma Line Database ===
# Format: (energy_keV, intensity_%, isotope, halflife_s, decay_mode, notes)
GAMMA_LINES_DB = [
    # Calibration Sources
    (59.54, 35.9, "Am-241", 1.364e10, "α", "Primary calibration peak"),
    (661.66, 85.1, "Cs-137", 9.47e8, "β-", "Primary calibration peak"),
    (1173.23, 99.85, "Co-60", 1.663e8, "β-", "Calibration doublet"),
    (1332.49, 99.98, "Co-60", 1.663e8, "β-", "Calibration doublet"),
    (1460.83, 10.7, "K-40", 4.0e16, "β-/EC", "Natural background"),
    
    # Uranium-238 Decay Chain
    (63.29, 4.8, "Th-234", 2.08e6, "β-", "U-238 daughter"),
    (92.38, 2.8, "Th-234", 2.08e6, "β-", "U-238 daughter"),
    (92.80, 2.7, "Th-234", 2.08e6, "β-", "U-238 daughter"),
    (186.21, 3.6, "Ra-226", 5.05e10, "α", "U-238 chain - interferes with U-235"),
    (295.22, 18.5, "Pb-214", 1614, "β-", "U-238 chain"),
    (351.93, 35.6, "Pb-214", 1614, "β-", "U-238 chain"),
    (609.31, 45.5, "Bi-214", 1186, "β-", "U-238 chain - primary signature"),
    (768.36, 4.9, "Bi-214", 1186, "β-", "U-238 chain"),
    (1001.03, 0.84, "Pa-234m", 70, "β-", "U-238 chain"),
    (1120.29, 15.0, "Bi-214", 1186, "β-", "U-238 chain"),
    (1764.49, 15.3, "Bi-214", 1186, "β-", "U-238 chain"),
    (2204.21, 5.0, "Bi-214", 1186, "β-", "U-238 chain"),
    
    # Uranium-235
    (143.76, 10.9, "U-235", 2.22e16, "α", "Enriched U marker"),
    (185.72, 57.2, "U-235", 2.22e16, "α", "Primary U-235 peak - interferes with Ra-226"),
    (205.31, 5.0, "U-235", 2.22e16, "α", "U-235 secondary"),
    
    # Thorium-232 Decay Chain
    (238.63, 43.6, "Pb-212", 3.83e4, "β-", "Th-232 chain"),
    (338.32, 11.3, "Ac-228", 2.21e4, "β-", "Th-232 chain"),
    (583.19, 30.6, "Tl-208", 183, "β-", "Th-232 chain"),
    (727.33, 6.6, "Bi-212", 3636, "β-/α", "Th-232 chain"),
    (860.56, 4.5, "Tl-208", 183, "β-", "Th-232 chain"),
    (911.20, 25.8, "Ac-228", 2.21e4, "β-", "Th-232 chain - primary"),
    (968.97, 15.8, "Ac-228", 2.21e4, "β-", "Th-232 chain"),
    (2614.51, 99.8, "Tl-208", 183, "β-", "Th-232 chain - highest energy"),
    
    # Other Common Sources
    (122.06, 85.6, "Co-57", 2.35e7, "EC", "Medical/industrial"),
    (136.47, 10.7, "Co-57", 2.35e7, "EC", "Co-57 secondary"),
    (511.00, 200.0, "Annihilation", 0, "β+", "Positron annihilation"),
    (1274.54, 99.9, "Na-22", 8.21e7, "β+", "PET calibration"),
]


# === X-Ray Fluorescence Database ===
# Format: (energy_keV, element, shell)
XRAY_LINES_DB = [
    # K-shell X-rays (most common)
    (8.04, "Cu", "Kα"),
    (8.91, "Cu", "Kβ"),
    (10.55, "As", "Kα"),
    (12.61, "Se", "Kα"),
    (14.96, "Y", "Kα"),
    (17.48, "Mo", "Kα"),
    (22.16, "Ag", "Kα"),
    (25.27, "Sn", "Kα"),
    (29.78, "Ba", "Kα"),
    (32.19, "La", "Kα"),
    (46.70, "Gd", "Kα"),
    (59.32, "W", "Kα"),
    (67.24, "W", "Kβ"),
    (74.97, "Pb", "Kα1"),
    (72.80, "Pb", "Kα2"),
    (84.94, "Pb", "Kβ1"),
    (87.30, "Pb", "Kβ2"),
    
    # L-shell X-rays (lower energy)
    (10.55, "Pb", "Lα"),
    (12.61, "Pb", "Lβ"),
    (14.76, "Pb", "Lγ"),
    (13.61, "U", "Lα"),
    (17.22, "U", "Lβ"),
    (20.17, "U", "Lγ"),
    (12.97, "Th", "Lα"),
    (16.20, "Th", "Lβ"),
    (18.98, "Th", "Lγ"),
]


def search_gamma_line(
    energy: float,
    delta: float = 5.0,
    halflife_threshold: Optional[float] = None,
    intensity_threshold: Optional[float] = None
) -> List[Dict]:
    """
    Search for gamma lines near a given energy.
    
    Args:
        energy: Target energy in keV
        delta: Search window ±keV (default: 5)
        halflife_threshold: Minimum halflife in seconds (optional)
        intensity_threshold: Minimum intensity % (optional)
        
    Returns:
        List of matching gamma lines as dicts
    """
    results = []
    
    for line in GAMMA_LINES_DB:
        e, intensity, isotope, halflife, decay, notes = line
        
        if abs(e - energy) > delta:
            continue
            
        if halflife_threshold and halflife < halflife_threshold:
            continue
            
        if intensity_threshold and intensity < intensity_threshold:
            continue
        
        results.append({
            "energy_keV": e,
            "intensity_percent": intensity,
            "isotope": isotope,
            "halflife_s": halflife,
            "decay_mode": decay,
            "notes": notes,
            "delta_keV": round(abs(e - energy), 2)
        })
    
    # Sort by closest match
    results.sort(key=lambda x: x["delta_keV"])
    return results


def search_xray_line(
    energy: float,
    delta: float = 2.0
) -> List[Dict]:
    """
    Search for X-ray fluorescence lines near a given energy.
    
    Args:
        energy: Target energy in keV
        delta: Search window ±keV (default: 2)
        
    Returns:
        List of matching X-ray lines as dicts
    """
    results = []
    
    for line in XRAY_LINES_DB:
        e, element, shell = line
        
        if abs(e - energy) > delta:
            continue
        
        results.append({
            "energy_keV": e,
            "element": element,
            "shell": shell,
            "delta_keV": round(abs(e - energy), 2)
        })
    
    results.sort(key=lambda x: x["delta_keV"])
    return results


def get_isotope_gamma_lines(
    isotope: str,
    intensity_threshold: Optional[float] = None
) -> List[Dict]:
    """
    Get all gamma lines for a specific isotope.
    
    Args:
        isotope: Isotope name (e.g., "Cs-137", "U-238")
        intensity_threshold: Minimum intensity % to include
        
    Returns:
        List of gamma lines for that isotope
    """
    results = []
    
    for line in GAMMA_LINES_DB:
        e, intensity, iso, halflife, decay, notes = line
        
        if iso != isotope:
            continue
            
        if intensity_threshold and intensity < intensity_threshold:
            continue
        
        results.append({
            "energy_keV": e,
            "intensity_percent": intensity,
            "decay_mode": decay,
            "notes": notes
        })
    
    results.sort(key=lambda x: x["intensity_percent"], reverse=True)
    return results


def decay_chain_spectrum(
    parent: str,
    intensity_threshold: float = 1.0
) -> Dict:
    """
    Get all gamma lines from a decay chain.
    
    Args:
        parent: Parent isotope (e.g., "U-238", "Th-232")
        intensity_threshold: Minimum intensity % to include
        
    Returns:
        Dict with chain info and all gamma lines
    """
    # Define decay chains
    DECAY_CHAINS = {
        "U-238": ["Th-234", "Pa-234m", "U-234", "Th-230", "Ra-226", "Rn-222", 
                  "Po-218", "Pb-214", "Bi-214", "Po-214", "Pb-210", "Bi-210", "Po-210"],
        "U-235": ["Th-231", "Pa-231", "Ac-227", "Th-227", "Ra-223", "Rn-219",
                  "Po-215", "Pb-211", "Bi-211", "Tl-207"],
        "Th-232": ["Ra-228", "Ac-228", "Th-228", "Ra-224", "Rn-220", 
                   "Po-216", "Pb-212", "Bi-212", "Po-212", "Tl-208"]
    }
    
    if parent not in DECAY_CHAINS:
        return {"parent": parent, "error": f"Unknown decay chain: {parent}", "lines": []}
    
    daughters = DECAY_CHAINS[parent]
    all_lines = []
    
    # Get parent lines
    parent_lines = get_isotope_gamma_lines(parent, intensity_threshold)
    for line in parent_lines:
        line["isotope"] = parent
        all_lines.append(line)
    
    # Get daughter lines
    for daughter in daughters:
        daughter_lines = get_isotope_gamma_lines(daughter, intensity_threshold)
        for line in daughter_lines:
            line["isotope"] = daughter
            all_lines.append(line)
    
    # Sort by energy
    all_lines.sort(key=lambda x: x["energy_keV"])
    
    return {
        "parent": parent,
        "daughters": daughters,
        "lines": all_lines,
        "total_lines": len(all_lines)
    }
