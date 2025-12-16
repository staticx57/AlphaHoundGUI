"""
Source Type Identification

Identifies common radioactive source types based on spectral signatures.
This module uses a rule-based approach to identify sources commonly found
in antiques, collectibles, and consumer products.

Supported source types:
- Uranium Glass (Vaseline Glass) - U-238 decay chain
- Thoriated Camera Lenses - Th-232 decay chain (sometimes mixed with U-238)
- Radium Dial Watches/Clocks - Refined Ra-226 (separated from uranium ore)
- Smoke Detectors - Am-241
- Natural Background - K-40

Key spectral signatures:
- U-238 chain: Th-234 (93 keV), Pa-234m (1001 keV), Bi-214 (609 keV), Pb-214 (352 keV)
- Th-232 chain: Ac-228 (911 keV), Tl-208 (2614 keV)
- Ra-226 refined: Bi-214/Pb-214 WITHOUT Th-234/Pa-234m
- Am-241: 60 keV peak
- K-40: 1461 keV peak
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from roi_analysis import ROIAnalyzer


@dataclass
class SourceSignature:
    """Defines spectral signature for a source type."""
    name: str
    description: str
    required_isotopes: List[str]      # Must be detected
    supporting_isotopes: List[str]    # Increase confidence if detected
    excluding_isotopes: List[str]     # Should NOT be detected (or very weak)
    notes: str


# Define source signatures based on physics
SOURCE_SIGNATURES = {
    "uranium_glass": SourceSignature(
        name="Uranium Glass (Vaseline Glass)",
        description="Decorative glass containing uranium oxide, common in antiques from 1840s-1940s. Contains natural uranium in secular equilibrium.",
        required_isotopes=["Th-234 (93 keV)", "Bi-214 (609 keV)"],
        supporting_isotopes=["Pa-234m (1001 keV)", "Pb-214 (352 keV)"],
        excluding_isotopes=["Ac-228 (911 keV)", "Tl-208 (2614 keV)"],  # Th-232 chain
        notes="U-238 decay chain in secular equilibrium. Glows green under UV light."
    ),
    
    "thoriated_lens": SourceSignature(
        name="Thoriated Camera Lens",
        description="Vintage camera lenses (1940s-1980s) containing thorium oxide for optical properties. Some also contain uranium.",
        required_isotopes=["Ac-228 (911 keV)"],
        supporting_isotopes=["Tl-208 (2614 keV)", "Th-234 (93 keV)"],  # Th-232 chain + possible U
        excluding_isotopes=[],  # Can have both Th and U
        notes="Th-232 decay chain. Common in Super Takumar, Canon FL, and some Kodak lenses. May also contain uranium."
    ),
    
    "radium_dial": SourceSignature(
        name="Radium Dial (Watch/Clock)",
        description="Luminous paint on vintage watches and clocks (1910s-1960s) containing refined Ra-226.",
        required_isotopes=["Bi-214 (609 keV)", "Pb-214 (352 keV)"],
        supporting_isotopes=[],
        excluding_isotopes=["Th-234 (93 keV)", "Pa-234m (1001 keV)"],  # No U-238 parents
        notes="Refined Ra-226 separated from uranium ore. No Th-234/Pa-234m because Ra-226 was chemically isolated."
    ),
    
    "smoke_detector": SourceSignature(
        name="Smoke Detector (Am-241)",
        description="Ionization smoke detector containing americium-241.",
        required_isotopes=["Am-241 (60 keV)"],
        supporting_isotopes=[],
        excluding_isotopes=["Bi-214 (609 keV)", "Ac-228 (911 keV)"],
        notes="Am-241 emits 60 keV gamma and alpha particles. Activity typically 0.9 µCi."
    ),
    
    "natural_background": SourceSignature(
        name="Natural Background",
        description="Natural environmental radioactivity from potassium-40 in the environment.",
        required_isotopes=["K-40 (1461 keV)"],
        supporting_isotopes=[],
        excluding_isotopes=["Am-241 (60 keV)"],  # Not natural
        notes="K-40 is present in soil, building materials, and living tissue."
    ),
    
    "mixed_uranium_thorium": SourceSignature(
        name="Mixed Uranium-Thorium Source",
        description="Source containing both uranium and thorium, such as some thoriated lenses with uranium glass elements.",
        required_isotopes=["Th-234 (93 keV)", "Ac-228 (911 keV)"],
        supporting_isotopes=["Bi-214 (609 keV)", "Tl-208 (2614 keV)"],
        excluding_isotopes=[],
        notes="Both U-238 and Th-232 decay chains present. Common in some vintage optical equipment."
    ),
}


def get_source_signature(source_id: str) -> Optional[SourceSignature]:
    """
    Get the signature definition for a specific source ID.
    Useful for validation in other modules.
    """
    return SOURCE_SIGNATURES.get(source_id)


def identify_source_type(
    energies: List[float],
    counts: List[int],
    detector_name: str,
    acquisition_time_s: float,
    min_counts_threshold: int = 50
) -> Dict:
    """
    Identify the likely source type based on spectral signatures.
    
    Args:
        energies: List of energy values (keV)
        counts: List of counts per channel
        detector_name: Name of detector for efficiency lookup
        acquisition_time_s: Acquisition time in seconds
        min_counts_threshold: Minimum net counts to consider a peak "detected"
    
    Returns:
        Dictionary with identification results
    """
    analyzer = ROIAnalyzer(detector_name)
    
    # Analyze all relevant isotopes
    isotope_results = {}
    isotopes_to_check = [
        "Th-234 (93 keV)",
        "Bi-214 (609 keV)",
        "Pb-214 (352 keV)",
        "Pa-234m (1001 keV)",
        "Ac-228 (911 keV)",
        "Tl-208 (2614 keV)",
        "Am-241 (60 keV)",
        "K-40 (1461 keV)",
        "U-235 (186 keV)",
        "Cs-137 (662 keV)",
    ]
    
    detected_isotopes = []
    
    for isotope in isotopes_to_check:
        try:
            result = analyzer.analyze(energies, counts, isotope, acquisition_time_s)
            isotope_results[isotope] = {
                "net_counts": result.net_counts,
                "uncertainty": result.uncertainty_sigma,
                "detected": result.detected,
                "snr": result.snr,
                "confidence": result.confidence
            }
            if result.detected:
                detected_isotopes.append(isotope)
        except Exception as e:
            isotope_results[isotope] = {
                "net_counts": 0,
                "uncertainty": 0,
                "detected": False,
                "snr": 0,
                "confidence": 0,
                "error": str(e)
            }
    
    # Score each source type
    source_scores = {}
    
    for source_id, signature in SOURCE_SIGNATURES.items():
        score = 0.0
        matching_required = 0
        matching_supporting = 0
        matching_excluding = 0
        details = []
        
        # Check required isotopes (each contributes 0.3)
        for isotope in signature.required_isotopes:
            if isotope in detected_isotopes:
                score += 0.3
                matching_required += 1
                details.append(f"✓ Required: {isotope}")
            else:
                details.append(f"✗ Missing required: {isotope}")
        
        # Normalize required score
        if len(signature.required_isotopes) > 0:
            required_fraction = matching_required / len(signature.required_isotopes)
        else:
            required_fraction = 0
        
        # Check supporting isotopes (each contributes 0.1)
        for isotope in signature.supporting_isotopes:
            if isotope in detected_isotopes:
                score += 0.1
                matching_supporting += 1
                details.append(f"✓ Supporting: {isotope}")
        
        # Check excluding isotopes (each deducts 0.2)
        for isotope in signature.excluding_isotopes:
            if isotope in detected_isotopes:
                score -= 0.2
                matching_excluding += 1
                details.append(f"✗ Unexpected: {isotope}")
        
        # Must have at least 50% of required isotopes to be considered
        if required_fraction < 0.5:
            score = 0.0
        
        source_scores[source_id] = {
            "name": signature.name,
            "description": signature.description,
            "score": max(0, min(1.0, score)),
            "required_matched": f"{matching_required}/{len(signature.required_isotopes)}",
            "supporting_matched": matching_supporting,
            "excluding_matched": matching_excluding,
            "details": details,
            "notes": signature.notes
        }
    
    # Find best match
    best_match = None
    best_score = 0.0
    
    for source_id, data in source_scores.items():
        if data["score"] > best_score:
            best_score = data["score"]
            best_match = source_id
    
    # Determine confidence level
    if best_score >= 0.7:
        confidence_level = "HIGH"
    elif best_score >= 0.4:
        confidence_level = "MEDIUM"
    elif best_score > 0.2:
        confidence_level = "LOW"
    else:
        confidence_level = "NONE"
        best_match = None  # Don't claim a match if score is too low
    
    # Build result
    if best_match and confidence_level != "NONE":
        return {
            "identified_source": best_match,
            "source_name": source_scores[best_match]["name"],
            "source_description": source_scores[best_match]["description"],
            "confidence": best_score,
            "confidence_level": confidence_level,
            "detected_isotopes": detected_isotopes,
            "isotope_details": isotope_results,
            "all_scores": source_scores,
            "notes": source_scores[best_match]["notes"]
        }
    else:
        # Unknown source - just present the data as-is
        return {
            "identified_source": None,
            "source_name": "Unknown Source",
            "source_description": (
                "This spectrum does not match any known source signature in our database. "
                "The detected isotopes are listed below for manual interpretation."
            ),
            "confidence": 0.0,
            "confidence_level": "NONE",
            "detected_isotopes": detected_isotopes,
            "isotope_details": isotope_results,
            "all_scores": source_scores,
            "notes": (
                "No automatic classification possible. "
                "Review the detected isotopes manually to determine the source type. "
                f"Detected: {', '.join(detected_isotopes) if detected_isotopes else 'No isotopes above detection threshold'}"
            )
        }
