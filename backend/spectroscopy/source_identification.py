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
from typing import List, Optional


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
    
    "takumar_lens": SourceSignature(
        name="Super Takumar Lens (ThO₂ + Natural U)",
        description="Pentax Super Takumar 50mm f/1.4 and similar lenses containing thorium dioxide with trace natural uranium.",
        required_isotopes=["Ac-228 (911 keV)"],
        supporting_isotopes=["Th-234 (93 keV)", "Bi-214 (609 keV)", "Pb-214 (352 keV)"],
        excluding_isotopes=[],
        notes="Th-232 in secular equilibrium with daughters. Ra-226 (from U-238 decay) may be present from trace natural uranium. Apply Ra-226 equivalence for accurate activity estimation."
    ),
    
    "uranium_ore": SourceSignature(
        name="Uranium Ore (Natural Uranium)",
        description="Natural uranium ore containing U-238 and U-235 in secular equilibrium with all daughter products.",
        required_isotopes=["Th-234 (93 keV)", "Bi-214 (609 keV)", "Pb-214 (352 keV)"],
        supporting_isotopes=["Pa-234m (1001 keV)", "U-235 (186 keV)"],
        excluding_isotopes=["Am-241 (60 keV)", "Cs-137 (662 keV)"],
        notes="Contains full U-238 decay chain in secular equilibrium. U-235 visible at 186 keV (~0.72% natural abundance). Higher activity than uranium glass."
    ),
    
    "cesium_source": SourceSignature(
        name="Cesium-137 Source",
        description="Cs-137 calibration source, check source, or environmental contamination.",
        required_isotopes=["Cs-137 (662 keV)"],
        supporting_isotopes=[],
        excluding_isotopes=["Bi-214 (609 keV)", "Ac-228 (911 keV)", "Th-234 (93 keV)"],
        notes="Cs-137 emits 662 keV gamma (85% branching ratio). Half-life 30.17 years. Common calibration source."
    ),
    
    "cobalt_source": SourceSignature(
        name="Cobalt-60 Source",
        description="Co-60 calibration source or industrial radiography source.",
        required_isotopes=["Co-60 (1173 keV)", "Co-60 (1332 keV)"],
        supporting_isotopes=[],
        excluding_isotopes=["Bi-214 (609 keV)", "Cs-137 (662 keV)"],
        notes="Co-60 emits two gammas at 1173 keV and 1332 keV (both ~100% BR). Half-life 5.27 years."
    ),
}

# === Secular Equilibrium Constants ===
# For Th-232 chain in secular equilibrium, all daughters have equal activity
# Ra-226 equivalence factor for thoriated lenses with trace natural uranium
RA226_EQUILIBRIUM_FACTOR = 1.0  # Activity ratio when in secular equilibrium


def get_source_signature(source_id: str) -> Optional[SourceSignature]:
    """
    Get the signature definition for a specific source ID.
    Useful for validation in other modules.
    """
    return SOURCE_SIGNATURES.get(source_id)
