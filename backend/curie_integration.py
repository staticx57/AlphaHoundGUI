"""
Curie Library Integration Module
================================

This module provides wrappers for the `curie` nuclear data library,
enabling dynamic gamma line lookups, X-ray emission energies, and 
mass attenuation coefficient calculations for shielding correction.

Usage:
    from curie_integration import (
        get_isotope_gammas,
        get_element_xrays,
        calculate_attenuation,
        HAS_CURIE
    )
"""

import numpy as np
from typing import List, Dict, Optional, Tuple

# Try to import curie
try:
    import curie
    HAS_CURIE = True
except ImportError:
    HAS_CURIE = False
    print("[Curie Integration] curie not installed, using fallback data")


# ============================================================================
# X-Ray Emission Line Data (Hardcoded fallback when curie unavailable)
# Data from NIST X-Ray Transition Energies Database
# Only includes Ka1, Ka2, Kb1 lines for common elements
# ============================================================================

XRAY_FALLBACK_DATA = {
    # Element: [(energy_keV, line_name, intensity_relative), ...]
    "Pb": [
        (72.80, "Ka1", 100.0),
        (74.97, "Ka2", 60.0),
        (84.94, "Kb1", 30.0),
        (10.55, "La1", 20.0),
    ],
    "Ba": [  # Cs-137 decays to Ba-137m which emits Ba X-rays
        (32.19, "Ka1", 100.0),
        (31.82, "Ka2", 52.0),
        (36.38, "Kb1", 20.0),
        (4.47, "La1", 5.0),
    ],
    "U": [
        (98.44, "Ka1", 100.0),
        (94.66, "Ka2", 62.0),
        (111.30, "Kb1", 28.0),
        (13.61, "La1", 15.0),
    ],
    "Th": [
        (93.35, "Ka1", 100.0),
        (89.96, "Ka2", 61.0),
        (105.60, "Kb1", 27.0),
        (12.97, "La1", 14.0),
    ],
    "Ra": [
        (83.79, "Ka1", 100.0),
        (81.07, "Ka2", 60.0),
        (94.87, "Kb1", 26.0),
        (12.20, "La1", 13.0),
    ],
    "Am": [  # Am-241 has Np X-rays
        (103.38, "Ka1", 100.0),
        (99.54, "Ka2", 63.0),
        (117.00, "Kb1", 29.0),
        (14.28, "La1", 16.0),
    ],
    "Cs": [
        (30.97, "Ka1", 100.0),
        (30.63, "Ka2", 51.0),
        (34.99, "Kb1", 19.0),
        (4.29, "La1", 4.0),
    ],
    "I": [  # I-131
        (28.61, "Ka1", 100.0),
        (28.32, "Ka2", 50.0),
        (32.29, "Kb1", 18.0),
    ],
    "Co": [
        (6.93, "Ka1", 100.0),
        (6.92, "Ka2", 50.0),
        (7.65, "Kb1", 15.0),
    ],
    "Np": [  # Neptunium - daughter of Am-241
        (101.07, "Ka1", 100.0),
        (97.07, "Ka2", 62.0),
        (114.23, "Kb1", 28.0),
        (13.95, "La1", 15.0),
    ],
    "Bi": [  # Bismuth - Bi-214 in U-238 chain
        (77.11, "Ka1", 100.0),
        (74.81, "Ka2", 60.0),
        (87.34, "Kb1", 28.0),
        (10.84, "La1", 14.0),
    ],
}

# Map isotopes to their daughter/X-ray-emitting elements
ISOTOPE_XRAY_ELEMENT_MAP = {
    "Cs-137": "Ba",   # Decays to Ba-137m
    "Am-241": "Np",   # Actually emits Np X-rays, using Am as fallback
    "I-131": "I",
    "Co-60": "Co",
    "Ba-133": "Ba",
    "U-238": "U",
    "U-235": "U",
    "Th-232": "Th",
    "Ra-226": "Ra",
    "Pb-210": "Pb",
    "Pb-214": "Pb",
    "Bi-214": "Bi",
}


def get_isotope_gammas(isotope_name: str, min_intensity: float = 1.0) -> List[Dict]:
    """
    Get gamma emission lines for an isotope from curie.
    
    Args:
        isotope_name: Isotope name (e.g., "Cs-137", "Co-60")
        min_intensity: Minimum intensity threshold (percent)
        
    Returns:
        List of dicts with 'energy', 'intensity' keys
    """
    if not HAS_CURIE:
        return []
    
    try:
        iso = curie.Isotope(isotope_name)
        gammas_df = iso.gammas()
        
        if gammas_df is None or len(gammas_df) == 0:
            return []
        
        result = []
        for _, row in gammas_df.iterrows():
            energy = float(row['energy'])
            intensity = float(row['intensity'])
            
            if intensity >= min_intensity:
                result.append({
                    'energy': energy,
                    'intensity': intensity,
                    'source': 'curie'
                })
        
        return sorted(result, key=lambda x: -x['intensity'])
    
    except Exception as e:
        print(f"[Curie] Failed to get gammas for {isotope_name}: {e}")
        return []


def get_element_xrays(
    element_or_isotope: str,
    min_intensity: float = 5.0
) -> List[Dict]:
    """
    Get characteristic X-ray emission lines for an element.
    
    Args:
        element_or_isotope: Element symbol (e.g., "Pb") or isotope (e.g., "Cs-137")
        min_intensity: Minimum relative intensity (percent)
        
    Returns:
        List of dicts with 'energy', 'line', 'intensity' keys
    """
    # If isotope name given, map to daughter element
    element = element_or_isotope
    if "-" in element_or_isotope:
        element = ISOTOPE_XRAY_ELEMENT_MAP.get(element_or_isotope, element_or_isotope.split("-")[0])
    
    # Use fallback data (curie doesn't have X-ray API)
    xrays = XRAY_FALLBACK_DATA.get(element, [])
    
    result = []
    for energy, line, intensity in xrays:
        if intensity >= min_intensity:
            result.append({
                'energy': energy,
                'line': f"{element} {line}",
                'element': element,
                'shell': line,
                'intensity': intensity,
                'source': 'NIST'
            })
    
    return sorted(result, key=lambda x: -x['intensity'])


def calculate_attenuation(
    element: str,
    energy_kev: float,
    thickness_cm: float,
    density_g_cm3: Optional[float] = None
) -> Dict:
    """
    Calculate gamma attenuation through a material.
    
    Uses the formula: I/I0 = exp(-mu * rho * x)
    
    Args:
        element: Element symbol (e.g., "Pb", "Fe", "Al")
        energy_kev: Gamma energy in keV
        thickness_cm: Material thickness in cm
        density_g_cm3: Material density (optional, uses standard if None)
        
    Returns:
        Dict with 'transmission', 'attenuation_percent', 'mu' keys
    """
    # Standard densities (g/cm³)
    DENSITIES = {
        "Pb": 11.34,
        "Fe": 7.87,
        "Al": 2.70,
        "Cu": 8.96,
        "Concrete": 2.3,
        "Water": 1.0,
        "Air": 0.00120,
    }
    
    if not HAS_CURIE:
        return {
            'transmission': 1.0,
            'attenuation_percent': 0.0,
            'mu': 0.0,
            'error': 'curie not installed'
        }
    
    try:
        elem = curie.Element(element)
        mu = elem.mu(energy_kev)  # Mass attenuation coefficient (cm²/g)
        
        rho = density_g_cm3
        if rho is None:
            rho = DENSITIES.get(element, 7.0)  # Default to ~iron density
        
        # Beer-Lambert law: I/I0 = exp(-mu * rho * x)
        transmission = np.exp(-mu * rho * thickness_cm)
        attenuation = 1.0 - transmission
        
        return {
            'transmission': float(transmission),
            'attenuation_percent': float(attenuation * 100),
            'mu': float(mu),
            'density': float(rho),
            'thickness_cm': float(thickness_cm)
        }
    
    except Exception as e:
        return {
            'transmission': 1.0,
            'attenuation_percent': 0.0,
            'mu': 0.0,
            'error': str(e)
        }


def get_isotope_half_life(isotope_name: str) -> Optional[float]:
    """
    Get half-life in seconds for an isotope.
    
    Args:
        isotope_name: Isotope name (e.g., "Cs-137")
        
    Returns:
        Half-life in seconds, or None if not found
    """
    if not HAS_CURIE:
        return None
    
    try:
        iso = curie.Isotope(isotope_name)
        return iso.half_life()  # Returns seconds
    except Exception:
        return None


def get_all_xrays_for_isotope(isotope_name: str) -> List[Dict]:
    """
    Get all characteristic X-rays that would be emitted when detecting an isotope.
    
    This includes X-rays from the daughter nucleus after decay.
    
    Args:
        isotope_name: Isotope name (e.g., "Cs-137")
        
    Returns:
        List of X-ray emission dicts
    """
    # Cs-137 -> Ba-137m -> Ba X-rays (32 keV range)
    # Am-241 -> Np-237 -> Np X-rays (but mostly Am gammas)
    
    xrays = get_element_xrays(isotope_name)
    
    # Add labels for display
    for xray in xrays:
        xray['associated_isotope'] = isotope_name
    
    return xrays
