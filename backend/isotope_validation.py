"""
Centralized Isotope Validation Rules Module

SINGLE SOURCE OF TRUTH for all isotope validation, gating, and confidence rules.
Both isotope_database.py and chain_detection_enhanced.py import from here.

Rules are physics-based and consider:
1. Number of gamma lines (multi-peak isotopes need 2+ matches)
2. Energy ranges (low-energy near detector threshold get penalties)
3. Detector capabilities (gated by detector profile)
4. Known problematic isotopes (special overrides)
"""

from typing import Dict, List, Tuple, Optional

# =======================================================================================
# DETECTOR PROFILES - Energy thresholds based on detector type
# =======================================================================================
DETECTOR_PROFILES = {
    "AlphaHound CsI(Tl)": {
        "min_energy_keV": 30.0,
        "energy_resolution_pct": 7.0,
        "xrf_capable": False,
    },
    "AlphaHound BGO": {
        "min_energy_keV": 25.0,
        "energy_resolution_pct": 10.0,
        "xrf_capable": False,
    },
    "NaI(Tl) 2x2": {
        "min_energy_keV": 20.0,
        "energy_resolution_pct": 7.0,
        "xrf_capable": False,
    },
    "HPGe": {
        "min_energy_keV": 3.0,
        "energy_resolution_pct": 0.2,
        "xrf_capable": True,
    },
    "CdZnTe/CZT": {
        "min_energy_keV": 10.0,
        "energy_resolution_pct": 2.0,
        "xrf_capable": True,
    },
}

# Default detector
DEFAULT_DETECTOR = "AlphaHound CsI(Tl)"


# =======================================================================================
# ISOTOPE INTRINSIC PROPERTIES
# These are physics-based, detector-independent properties of each isotope
# =======================================================================================
ISOTOPE_INTRINSICS = {
    # ===== Man-made calibration sources =====
    "Co-60": {
        "type": "manmade",
        "required_peaks": 2,  # MUST have BOTH 1173 and 1332 keV
        "expected_ratio": {"1173/1332": (0.8, 1.2)},  # Should be ~1:1
        "is_chain": False,
    },
    "Cs-137": {
        "type": "manmade",
        "required_peaks": 1,  # Single peak isotope
        "primary_energy": 661.7,
        "is_chain": False,
    },
    "Am-241": {
        "type": "manmade",
        "required_peaks": 1,
        "primary_energy": 59.5,
        "low_energy": True,  # Near CsI threshold
        "is_chain": False,
    },
    "Na-22": {
        "type": "manmade",
        "required_peaks": 2,  # Need both 511 and 1274.5
        "is_chain": False,
    },
    "Ba-133": {
        "type": "manmade",
        "required_peaks": 2,  # Multiple peaks available
        "is_chain": False,
    },
    
    # ===== Natural decay chain parents =====
    "U-238": {
        "type": "natural_chain",
        "is_chain": True,
        "min_chain_members": 2,  # Need 2+ daughters detected
    },
    "Th-232": {
        "type": "natural_chain", 
        "is_chain": True,
        "min_chain_members": 2,
    },
    "U-235": {
        "type": "natural_chain",
        "is_chain": True,
        "min_chain_members": 2,
    },
    "K-40": {
        "type": "natural",
        "required_peaks": 1,
        "primary_energy": 1460.8,
        "is_chain": False,
    },
    
    # ===== Medical/Reactor isotopes (incompatible with natural sources) =====
    "I-131": {"type": "medical", "is_chain": False, "primary_energy": 364.5},
    "F-18": {"type": "medical", "is_chain": False, "primary_energy": 511.0},
    "Tc-99m": {"type": "medical", "is_chain": False, "primary_energy": 140.5},
    "Sr-90": {"type": "fission", "is_chain": False},
    "Pu-239": {"type": "weapons", "is_chain": False},
    "Np-237": {"type": "reactor", "is_chain": False},
}

# =======================================================================================
# ISOTOPE CLASSIFICATION LISTS (imported by isotope_database.py and analysis.py)
# =======================================================================================

# Isotopes that should NOT appear together with natural uranium/thorium samples
# If these are detected in a spectrum with natural chain, they are likely false positives
INCOMPATIBLE_WITH_NATURAL = [
    "Cs-137",   # Fission product / medical
    "I-131",    # Medical isotope  
    "F-18",     # PET imaging
    "Tc-99m",   # Medical
    "Co-60",    # Industrial/medical
    "Sr-90",    # Fission product
    "Pu-239",   # Weapons-grade
    "Np-237",   # Reactor product
]

# Medical isotopes - for special handling in analysis
MEDICAL_ISOTOPES = {"Cs-137", "I-131", "F-18", "Tc-99m", "Co-60"}

# Man-made source signatures with characteristic energies
# Used to detect if a spectrum contains man-made sources
MANMADE_SIGNATURES = {
    "Cs-137": [661.7],
    "Co-60": [1173.2, 1332.5],
    "Am-241": [59.5],
    "Na-22": [511.0, 1274.5],
    "Ba-133": [356.0, 302.9, 81.0],
}


def get_detector_min_energy(detector_name: str = DEFAULT_DETECTOR) -> float:
    """Get minimum detectable energy for a detector type."""
    profile = DETECTOR_PROFILES.get(detector_name, DETECTOR_PROFILES[DEFAULT_DETECTOR])
    return profile["min_energy_keV"]


def generate_validation_rules(
    isotope_database: Dict[str, List[float]],
    detector_name: str = DEFAULT_DETECTOR
) -> Dict[str, Dict]:
    """
    Generate intrinsic validation rules for ALL isotopes based on their characteristics.
    
    Args:
        isotope_database: Dict mapping isotope names to gamma energies
        detector_name: Name of detector being used
        
    Returns:
        Dict mapping isotope names to validation rules
    """
    detector_min_energy = get_detector_min_energy(detector_name)
    rules = {}
    
    for iso_name, iso_energies in isotope_database.items():
        if not iso_energies:
            continue
            
        num_lines = len(iso_energies)
        min_energy = min(iso_energies) if iso_energies else 100
        
        # Start with physics-based intrinsics if available
        intrinsics = ISOTOPE_INTRINSICS.get(iso_name, {})
        
        # Default rule
        rule = {
            "required_peaks": intrinsics.get("required_peaks", 1),
            "min_confidence_single": 42.0,  # Default cap for single match
            "low_energy_penalty": intrinsics.get("low_energy", False),
            "is_chain": intrinsics.get("is_chain", False),
            "type": intrinsics.get("type", "unknown"),
        }
        
        # === Multi-peak isotopes should require 2+ matches ===
        if num_lines >= 2 and rule["required_peaks"] < 2:
            rule["required_peaks"] = 2
            rule["min_confidence_single"] = 20.0
        
        if num_lines >= 4:
            rule["min_confidence_single"] = 15.0
        
        # === Low-energy isotopes (near detector threshold) ===
        if min_energy < detector_min_energy * 1.5:
            rule["low_energy_penalty"] = True
            rule["min_confidence_single"] = min(rule["min_confidence_single"], 25.0)
        
        # === Single-line isotopes are less reliable ===
        if num_lines == 1:
            rule["required_peaks"] = 1
            rule["min_confidence_single"] = 42.0
        
        # === Apply known intrinsic overrides ===
        if iso_name == "Co-60":
            rule["required_peaks"] = 2
            rule["min_confidence_single"] = 10.0
        
        if iso_name == "Am-241":
            rule["low_energy_penalty"] = True
            rule["min_confidence_single"] = 20.0
            
        rules[iso_name] = rule
    
    return rules


def validate_isotope_detection(
    isotope: str,
    matches: int,
    matched_peaks: List[Dict],
    rules: Dict[str, Dict],
    any_natural_chain_detected: bool = False
) -> Tuple[float, str]:
    """
    Validate an isotope detection and compute confidence penalty.
    
    Args:
        isotope: Isotope name
        matches: Number of matched peaks
        matched_peaks: List of matched peak info
        rules: Validation rules from generate_validation_rules()
        any_natural_chain_detected: True if U-238/Th-232 chain detected
        
    Returns:
        Tuple of (confidence_cap, reason)
    """
    if isotope not in rules:
        return (100.0, "no_rule")
    
    rule = rules[isotope]
    required = rule.get("required_peaks", 1)
    min_conf = rule.get("min_confidence_single", 42.0)
    is_manmade = rule.get("type") == "manmade"
    
    # Check required peaks
    if matches < required:
        reason = f"insufficient_peaks_{matches}/{required}"
        return (min_conf, reason)
    
    # Man-made isotopes in presence of natural chains are suspicious
    if is_manmade and any_natural_chain_detected:
        # Single match of man-made in natural spectrum is likely coincidental
        if matches == 1:
            return (min(min_conf, 15.0), "manmade_in_natural_spectrum")
    
    # Low energy penalty
    if rule.get("low_energy_penalty") and matches == 1:
        return (min(min_conf * 0.6, 25.0), "low_energy_single_match")
    
    return (100.0, "passed")


def should_include_as_chain(isotope: str, rules: Dict[str, Dict]) -> bool:
    """
    Determine if an isotope should be displayed as a 'decay chain'.
    Single isotopes like Am-241, Co-60, Cs-137 are NOT chains.
    
    Args:
        isotope: Isotope name
        rules: Validation rules
        
    Returns:
        True if isotope is a true decay chain (U-238, Th-232, etc.)
    """
    if isotope not in rules:
        return False
    return rules[isotope].get("is_chain", False)
