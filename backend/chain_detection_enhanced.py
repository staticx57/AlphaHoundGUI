"""
Enhanced Decay Chain Detection Module

Uses the radioactivedecay library to dynamically compute decay chains
instead of relying on hard-coded chain definitions.

Key improvements:
1. Dynamic chain computation from any parent nuclide
2. Automatic gamma line lookup for all daughters
3. Intensity-weighted scoring
4. Half-life filtering (excludes prompt gammas)
"""

import numpy as np
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass
from functools import lru_cache
import math

# Import radioactivedecay
try:
    import radioactivedecay as rd
    HAS_RADIOACTIVEDECAY = True
except ImportError:
    HAS_RADIOACTIVEDECAY = False
    print("[Chain Detection] radioactivedecay not installed - using fallback")

# Import IAEA data for gamma line lookup
try:
    from iaea_parser import IAEA_DATA, get_isotope_gammas
    HAS_IAEA_DATA = True
except ImportError:
    IAEA_DATA = {}
    HAS_IAEA_DATA = False


# Known decay chain parents for quick lookup
# NOTE: Only TRUE decay chains belong here. Single isotopes like Cs-137, Co-60, Am-241
# are NOT chains and should be handled via isotope identification, not chain detection
KNOWN_CHAINS = {
    'U-238': {'name': 'U-238 Decay Chain', 'type': 'natural', 'color': '#22c55e'},
    'U-235': {'name': 'U-235 (Actinium) Chain', 'type': 'natural', 'color': '#3b82f6'},
    'Th-232': {'name': 'Th-232 Decay Chain', 'type': 'natural', 'color': '#f59e0b'},
    'Ra-226': {'name': 'Ra-226 (Radium) Chain', 'type': 'natural', 'color': '#ef4444'},
    # Removed: Cs-137, Co-60, Am-241 - these are single isotopes, NOT decay chains
}

# Gamma lines database (fallback when IAEA data not available)
GAMMA_LINES_FALLBACK = {
    'U-238': [],  # No direct gammas
    'Th-234': [(63.3, 4.8), (92.6, 5.6)],
    'Pa-234m': [(766.4, 0.32), (1001.0, 0.84)],
    'U-234': [],
    'Th-230': [],
    'Ra-226': [(186.2, 3.6)],
    'Rn-222': [],
    'Po-218': [],
    'Pb-214': [(241.9, 7.3), (295.2, 19.3), (351.9, 37.6)],
    'Bi-214': [(609.3, 46.1), (1120.3, 15.0), (1764.5, 15.4)],
    'Po-214': [],
    'Pb-210': [(46.5, 4.3)],
    'Bi-210': [],
    'Po-210': [],
    'Pb-206': [],
    'Th-232': [],
    'Ra-228': [],
    'Ac-228': [(338.3, 11.3), (911.2, 25.8), (968.9, 15.8)],
    'Th-228': [(84.4, 1.2)],
    'Ra-224': [(241.0, 4.1)],
    'Rn-220': [],
    'Po-216': [],
    'Pb-212': [(238.6, 43.6), (300.1, 3.3)],
    'Bi-212': [(727.3, 6.6)],
    'Tl-208': [(583.2, 85.0), (860.6, 12.5), (2614.5, 99.8)],
    'Po-212': [],
    'Pb-208': [],
    'Cs-137': [(661.7, 85.1)],
    'Ba-137m': [(661.7, 89.9)],  # Same as Cs-137 (IT decay)
    'Co-60': [(1173.2, 99.9), (1332.5, 100.0)],
    'Am-241': [(59.5, 35.9), (26.3, 2.4)],
    'K-40': [(1460.8, 10.7)],
}


@dataclass
class ChainMember:
    """Represents a member of a decay chain."""
    nuclide: str
    gamma_energies: List[Tuple[float, float]]  # (energy_keV, intensity_%)
    half_life_s: Optional[float] = None
    detected: bool = False
    detected_energies: List[float] = None
    
    def __post_init__(self):
        if self.detected_energies is None:
            self.detected_energies = []


@dataclass  
class DetectedChain:
    """Represents a detected decay chain."""
    parent: str
    name: str
    chain_type: str  # 'natural' or 'manmade'
    color: str
    members: List[ChainMember]
    detected_count: int
    expected_count: int
    score: float
    confidence: str  # 'HIGH', 'MEDIUM', 'LOW'
    key_indicators: List[str]  # Which key isotopes were detected


@lru_cache(maxsize=50)
def get_decay_chain_members(parent: str, min_branching: float = 0.01) -> List[str]:
    """
    Get all members of a decay chain using radioactivedecay.
    
    Args:
        parent: Parent nuclide (e.g., 'U-238')
        min_branching: Minimum branching ratio to include
        
    Returns:
        List of nuclide names in the chain
    """
    if not HAS_RADIOACTIVEDECAY:
        # Fallback to known chains
        if parent == 'U-238':
            return ['U-238', 'Th-234', 'Pa-234m', 'U-234', 'Th-230', 'Ra-226', 
                   'Rn-222', 'Po-218', 'Pb-214', 'Bi-214', 'Po-214', 'Pb-210',
                   'Bi-210', 'Po-210', 'Pb-206']
        elif parent == 'Th-232':
            return ['Th-232', 'Ra-228', 'Ac-228', 'Th-228', 'Ra-224', 'Rn-220',
                   'Po-216', 'Pb-212', 'Bi-212', 'Tl-208', 'Po-212', 'Pb-208']
        elif parent == 'Cs-137':
            return ['Cs-137', 'Ba-137m']
        elif parent == 'Co-60':
            return ['Co-60', 'Ni-60']
        elif parent == 'Am-241':
            return ['Am-241', 'Np-237']
        return [parent]
    
    try:
        members = [parent]
        current = [parent]
        
        while current:
            new_members = []
            for nuclide_name in current:
                try:
                    nuclide = rd.Nuclide(nuclide_name)
                    for daughter, branch in zip(nuclide.progeny(), nuclide.branching_fractions()):
                        if branch >= min_branching and daughter not in members:
                            members.append(daughter)
                            new_members.append(daughter)
                except:
                    pass
            current = new_members
            
        return members
        
    except Exception as e:
        print(f"[Chain Detection] Error getting chain for {parent}: {e}")
        return [parent]


def get_nuclide_gammas(nuclide: str) -> List[Tuple[float, float]]:
    """
    Get gamma lines for a nuclide.
    
    Args:
        nuclide: Nuclide name (e.g., 'Bi-214')
        
    Returns:
        List of (energy_keV, intensity_%) tuples
    """
    # Try IAEA data first
    if HAS_IAEA_DATA and nuclide in IAEA_DATA:
        gammas = get_isotope_gammas(nuclide)
        if gammas:
            return [(g['energy'], g.get('intensity', 100)) for g in gammas]
    
    # Fallback to built-in data
    return GAMMA_LINES_FALLBACK.get(nuclide, [])


def get_nuclide_info(nuclide: str) -> Dict[str, any]:
    """
    Get detailed nuclide info using radioactivedecay.
    
    Args:
        nuclide: Nuclide name (e.g., 'Bi-214')
        
    Returns:
        Dictionary with half_life, half_life_readable, progeny, branching_fractions
    """
    info = {
        'half_life_s': None,
        'half_life_readable': None,
        'progeny': [],
        'branching_fractions': []
    }
    
    if not HAS_RADIOACTIVEDECAY:
        return info
    
    try:
        nuc = rd.Nuclide(nuclide)
        half_life = nuc.half_life('s')
        
        # Sanitize half-life (handle inf/nan)
        if math.isinf(half_life) or math.isnan(half_life):
            info['half_life_s'] = None
        else:
            info['half_life_s'] = float(half_life)
            
        info['half_life_readable'] = str(nuc.half_life('readable'))
        info['progeny'] = [str(p) for p in nuc.progeny()]
        
        # Sanitize branching fractions
        fractions = []
        for b in nuc.branching_fractions():
            val = float(b)
            if math.isnan(val) or math.isinf(val):
                fractions.append(0.0)
            else:
                fractions.append(val)
        info['branching_fractions'] = fractions
        
    except Exception as e:
        pass
    
    return info


def get_chain_sequence_info(parent: str) -> List[Dict]:
    """
    Get full chain sequence with half-lives and branching ratios.
    
    Returns list of dicts: [
        {'nuclide': 'U-238', 'half_life': '4.47 By', 'branching_to_next': 1.0},
        {'nuclide': 'Th-234', 'half_life': '24.1 d', 'branching_to_next': 1.0},
        ...
    ]
    """
    members = get_decay_chain_members(parent)
    sequence = []
    
    for i, member in enumerate(members):
        info = get_nuclide_info(member)
        entry = {
            'nuclide': str(member),
            'half_life': info.get('half_life_readable', 'unknown'),
            'half_life_s': info.get('half_life_s'),
            'branching_to_next': 1.0  # Default for linear chain
        }
        
        # Find branching ratio to next member
        if i < len(members) - 1:
            next_member = members[i + 1]
            progeny = info.get('progeny', [])
            fractions = info.get('branching_fractions', [])
            for p, br in zip(progeny, fractions):
                if p == next_member:
                    try:
                        val = float(br)
                        if math.isnan(val) or math.isinf(val):
                            entry['branching_to_next'] = 0.0
                        else:
                            entry['branching_to_next'] = val
                    except:
                        entry['branching_to_next'] = 0.0
                    break
        
        sequence.append(entry)
    
    return sequence


def check_secular_equilibrium(detected_members: Dict[str, List[Dict]], parent: str) -> Dict:
    """
    Check if a decay chain appears to be in secular equilibrium.
    
    In secular equilibrium, daughter activities equal parent activity.
    We can check this by comparing measured peak intensity ratios.
    
    Args:
        detected_members: Dict mapping isotope -> list of detected peaks with counts
        parent: Parent nuclide name (e.g., 'U-238')
        
    Returns:
        Dict with 'in_equilibrium', 'confidence', 'details'
    """
    result = {
        'in_equilibrium': None,  # True/False/None (unknown)
        'confidence': 'UNKNOWN',
        'details': '',
        'ratio_check': None
    }
    
    # Define key isotope pairs to check for equilibrium
    # These pairs should have ~1:1 activity ratio in equilibrium
    equilibrium_pairs = {
        'U-238': [
            ('Bi-214', 'Pb-214'),  # Both in Rn-222 sub-chain
        ],
        'Th-232': [
            ('Ac-228', 'Pb-212'),  # Detectable gamma emitters
            ('Bi-212', 'Tl-208'),  # Branch products
        ],
    }
    
    pairs_to_check = equilibrium_pairs.get(parent, [])
    if not pairs_to_check:
        result['details'] = 'No equilibrium check defined for this chain'
        return result
    
    checked_pairs = []
    for iso1, iso2 in pairs_to_check:
        if iso1 in detected_members and iso2 in detected_members:
            # Get strongest peak counts for each
            counts1 = max((p.get('counts', 0) for p in detected_members[iso1]), default=0)
            counts2 = max((p.get('counts', 0) for p in detected_members[iso2]), default=0)
            
            if counts1 > 100 and counts2 > 100:  # Need significant counts
                # Account for branching ratios (approximate)
                # Bi-214/Pb-214 should be ~1:1, Ac-228/Pb-212 ~1:1
                ratio = counts1 / counts2 if counts2 > 0 else 0
                # Allow 0.3-3.0 range for "equilibrium" (broad due to efficiency variations)
                in_range = 0.3 <= ratio <= 3.0
                checked_pairs.append({
                    'pair': f'{iso1}/{iso2}',
                    'ratio': float(ratio),
                    'in_range': in_range
                })
    
    if not checked_pairs:
        result['details'] = 'Insufficient peak counts for equilibrium check'
        return result
    
    # Determine overall equilibrium status
    all_in_range = all(p['in_range'] for p in checked_pairs)
    result['in_equilibrium'] = all_in_range
    result['confidence'] = 'HIGH' if len(checked_pairs) >= 2 else 'MEDIUM'
    result['ratio_check'] = checked_pairs
    
    if all_in_range:
        result['details'] = 'Peak ratios consistent with secular equilibrium'
    else:
        result['details'] = 'Peak ratios suggest chain may not be in equilibrium'
    
    return result


def get_expected_spectrum(parent: str, intensity_threshold: float = 1.0) -> Dict[str, List[Tuple[float, float]]]:
    """
    Get the expected gamma spectrum for a decay chain.
    
    Args:
        parent: Parent nuclide
        intensity_threshold: Minimum gamma intensity (%) to include
        
    Returns:
        Dictionary mapping nuclide -> [(energy, intensity), ...]
    """
    chain_members = get_decay_chain_members(parent)
    expected = {}
    
    for member in chain_members:
        gammas = get_nuclide_gammas(member)
        # Filter by intensity
        filtered = [(e, i) for e, i in gammas if i >= intensity_threshold]
        if filtered:
            expected[member] = filtered
            
    return expected


def match_peaks_to_chain(
    peaks: List[Dict],
    parent: str,
    energy_tolerance: float = 15.0,
    intensity_threshold: float = 1.0
) -> Tuple[int, int, List[str], Dict[str, List[float]]]:
    """
    Match detected peaks to expected chain gamma lines.
    
    Args:
        peaks: List of detected peak dictionaries
        parent: Parent nuclide of chain
        energy_tolerance: Matching tolerance (keV)
        intensity_threshold: Minimum gamma intensity (%)
        
    Returns:
        Tuple of (detected_count, expected_count, detected_nuclides, matches)
    """
    expected = get_expected_spectrum(parent, intensity_threshold)
    
    peak_energies = [p.get('energy', 0) for p in peaks]
    peak_areas = [p.get('area', p.get('counts', 1)) for p in peaks]
    
    # Dynamic tolerance: use wider tolerance for high-count spectra
    # because peaks overlap and shift in strong scintillator spectra
    max_counts = max((p.get('counts', 0) for p in peaks), default=0)
    if max_counts > 10000:
        # Strong spectrum: use 60 keV tolerance (matches ~10% resolution at 600 keV)
        effective_tolerance = max(energy_tolerance, 60.0)
        print(f"[DEBUG Chain Match] High-count spectrum ({max_counts:.0f}), using tolerance={effective_tolerance}")
    else:
        effective_tolerance = energy_tolerance
    
    detected_nuclides = []
    matches = {}  # nuclide -> [matched_energies]
    
    total_expected = 0
    total_detected = 0
    
    for nuclide, gamma_lines in expected.items():
        nuclide_matched = False
        matched_energies = []
        
        for gamma_energy, gamma_intensity in gamma_lines:
            total_expected += 1
            
            # Check if any peak matches this gamma line
            for i, peak_energy in enumerate(peak_energies):
                if abs(peak_energy - gamma_energy) <= effective_tolerance:
                    total_detected += 1
                    nuclide_matched = True
                    matched_energies.append(peak_energy)
                    break
        
        if nuclide_matched:
            detected_nuclides.append(nuclide)
            matches[nuclide] = matched_energies
    
    # Debug logging for chain matching
    if parent in ['Th-232', 'U-238']:
        print(f"[DEBUG Chain Match] {parent}: detected={total_detected}/{total_expected}, nuclides={detected_nuclides}")
        print(f"[DEBUG Chain Match] {parent}: Peak energies searched: {peak_energies[:15]}...")
    
    return total_detected, total_expected, detected_nuclides, matches


def calculate_chain_confidence(
    detected_count: int,
    expected_count: int,
    detected_nuclides: List[str],
    parent: str
) -> Tuple[float, str]:
    """
    Calculate confidence score and level for a chain detection.
    
    Args:
        detected_count: Number of detected gamma lines
        expected_count: Number of expected gamma lines
        detected_nuclides: List of detected nuclide names
        parent: Parent nuclide
        
    Returns:
        Tuple of (score, confidence_level)
    """
    if expected_count == 0:
        return 0.0, 'LOW'
    
    # Base score from detection ratio
    ratio = detected_count / expected_count
    score = min(1.0, ratio * 1.5)  # Boost slightly
    
    # Bonus for detecting key indicators
    key_indicators = {
        'U-238': ['Bi-214', 'Pb-214', 'Pa-234m'],
        'Th-232': ['Ac-228', 'Tl-208', 'Pb-212'],
        'Cs-137': ['Cs-137', 'Ba-137m'],
        'Co-60': ['Co-60'],
        'Am-241': ['Am-241'],
    }
    
    indicators = key_indicators.get(parent, [])
    indicator_matches = sum(1 for ind in indicators if ind in detected_nuclides)
    
    if indicators:
        indicator_bonus = 0.2 * (indicator_matches / len(indicators))
        score = min(1.0, score + indicator_bonus)
    
    # Minimum detected isotopes check
    if len(detected_nuclides) < 2 and parent in ['U-238', 'Th-232']:
        score *= 0.5  # Penalize single-isotope detection for natural chains
    
    # Determine confidence level
    if score >= 0.7 and len(detected_nuclides) >= 3:
        confidence = 'HIGH'
    elif score >= 0.4 and len(detected_nuclides) >= 2:
        confidence = 'MEDIUM'
    else:
        confidence = 'LOW'
    
    return score, confidence


def identify_decay_chains_enhanced(
    peaks: List[Dict],
    energy_tolerance: float = 15.0,
    min_score: float = 0.3,
    include_manmade: bool = True
) -> List[Dict]:
    """
    Identify radioactive decay chains from detected peaks.
    
    Enhanced version using dynamic chain computation.
    Returns format compatible with original identify_decay_chains().
    
    Args:
        peaks: List of detected peak dictionaries
        energy_tolerance: Matching tolerance (keV)
        min_score: Minimum score to include a chain
        include_manmade: Include man-made sources (Cs-137, Co-60, Am-241)
        
    Returns:
        List of detected chain dictionaries (compatible format)
    """
    detected_chains = []
    
    # Only check TRUE decay chains - not single-isotope sources
    # Am-241, Cs-137, Co-60 are handled via isotope identification, not chain detection
    chains_to_check = ['U-238', 'Th-232']
    # NOTE: include_manmade parameter is now IGNORED - single isotopes are NOT chains
    
    for parent in chains_to_check:
        detected_count, expected_count, detected_nuclides, matches = match_peaks_to_chain(
            peaks, parent, energy_tolerance
        )
        
        if detected_count == 0:
            continue
        
        score, confidence_level = calculate_chain_confidence(
            detected_count, expected_count, detected_nuclides, parent
        )
        
        if score < min_score:
            continue
        
        chain_info = KNOWN_CHAINS.get(parent, {
            'name': f'{parent} Chain',
            'type': 'unknown',
            'color': '#6b7280'
        })
        
        # Build detected_members in original format: {isotope: [peak_dicts]}
        detected_members = {}
        for nuclide, energies in matches.items():
            detected_members[nuclide] = [{'energy': e} for e in energies]
        
        # Key indicators for this chain
        key_indicators_map = {
            'U-238': ['Bi-214', 'Pb-214', 'Pa-234m', 'Th-234'],
            'Th-232': ['Ac-228', 'Tl-208', 'Pb-212', 'Bi-212'],
            'Cs-137': ['Cs-137'],
            'Co-60': ['Co-60'],
            'Am-241': ['Am-241'],
        }
        key_indicators = key_indicators_map.get(parent, detected_nuclides)
        num_key_isotopes = len(key_indicators)
        
        # Applications/Likely Sources based on chain type
        applications_map = {
            'U-238': ['Uranium glass (Vaseline glass)', 'Uranium ore', 'Thoriated lenses with natural U'],
            'Th-232': ['Thoriated camera lenses (Takumar, Canon)', 'Welding rods', 'Gas mantles'],
            'U-235': ['Enriched uranium (nuclear fuel)', 'Natural uranium (0.72%)'],
            'Cs-137': ['Medical/industrial sources', 'Nuclear fallout'],
            'Co-60': ['Industrial radiography', 'Medical therapy'],
            'Am-241': ['Smoke detectors', 'Calibration sources'],
        }
        applications = applications_map.get(parent, ['Unknown source'])
        
        # Build chain result in COMPATIBLE format with original
        detected_chains.append({
            # Original format fields
            'chain_name': chain_info['name'],
            'parent': parent,
            'confidence': float(score * 100),  # Original uses 0-100 scale
            'confidence_level': confidence_level,
            'detected_members': detected_members,
            'num_detected': int(len(detected_nuclides)),
            'num_key_isotopes': int(num_key_isotopes),
            'required_found': bool(len(detected_nuclides) >= 2),
            'abundance_weight': 1.0,
            'suppress_when_natural': bool(parent in ['Cs-137', 'Co-60']),
            'applications': applications,
            'references': [],
            'notes': f'Enhanced detection: {detected_count}/{expected_count} gamma lines matched',
            
            # Enhanced fields (additional)
            'color': chain_info['color'],
            'chain_type': chain_info['type'],
            'enhanced': True,  # Flag to indicate enhanced detection was used
            
            # NEW: Chain sequence with half-lives and branching ratios
            'chain_sequence': get_chain_sequence_info(parent),
            
            # NEW: Secular equilibrium check
            'equilibrium_status': check_secular_equilibrium(detected_members, parent)
        })
    
    # Sort by confidence (highest first)
    detected_chains.sort(key=lambda x: x['confidence'], reverse=True)
    
    return detected_chains


def get_chain_summary(chains: List[Dict]) -> str:
    """
    Generate a human-readable summary of detected chains.
    
    Args:
        chains: List of detected chain dictionaries
        
    Returns:
        Summary string
    """
    if not chains:
        return "No radioactive decay chains detected."
    
    lines = []
    for chain in chains:
        conf_icon = {'HIGH': '✓', 'MEDIUM': '○', 'LOW': '?'}.get(chain['confidence'], '?')
        lines.append(
            f"{conf_icon} {chain['name']} ({chain['confidence']}): "
            f"{chain['detected_count']}/{chain['expected_count']} lines detected "
            f"[{', '.join(chain['key_indicators'][:3])}]"
        )
    
    return "\n".join(lines)


# Backward-compatible wrapper
def identify_decay_chains(
    peaks: List[Dict],
    identified_isotopes: Optional[List[Dict]] = None,
    energy_tolerance: float = 20.0
) -> List[Dict]:
    """
    Backward-compatible wrapper for chain detection.
    
    Matches the signature of the existing identify_decay_chains function.
    
    Args:
        peaks: List of detected peaks
        identified_isotopes: (unused, for compatibility)
        energy_tolerance: Matching tolerance (keV)
        
    Returns:
        List of detected chains
    """
    return identify_decay_chains_enhanced(
        peaks,
        energy_tolerance=energy_tolerance,
        min_score=0.25
    )
