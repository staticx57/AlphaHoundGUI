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

from typing import List, Dict, Optional, Tuple
from functools import lru_cache
import logging
import math

logger = logging.getLogger(__name__)

# Import radioactivedecay
try:
    import radioactivedecay as rd
    HAS_RADIOACTIVEDECAY = True
except ImportError:
    HAS_RADIOACTIVEDECAY = False
    logger.warning("radioactivedecay not installed - using the built-in chain tables")

# Import IAEA data for gamma line lookup
try:
    from formats.iaea_parser import IAEA_DATA, get_isotope_gammas
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
                except Exception as exc:
                    logger.debug("No decay data for %s: %s", nuclide_name, exc)
            current = new_members
            
        return members
        
    except Exception as e:
        logger.warning("Error getting chain for %s: %s", parent, e)
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
        logger.debug("No nuclide info for %s: %s", nuclide, e)
    
    return info


def get_chain_sequence_info(parent: str) -> List[Dict]:
    """
    Get full chain sequence with half-lives and branching ratios.

    Members are listed in decay order, but a chain branches (Bi-212 decays to Po-212 64 % and to Tl-208 36 %), so each entry
    also says which member feeds it:
        {'nuclide': 'Tl-208', 'half_life': '3.053 m', 'half_life_s': 183.18,
         'feeder': 'Bi-212', 'branching_from_feeder': 0.3594, 'is_branch': True,   # an alternative to the entry before it
         'branching_to_next': None}                                                # Tl-208 does not decay to the next entry
    'branching_to_next' is the share of this nuclide's decays that lead to the entry after it; None when that entry is its
    sibling (a branch), 1.0 for the last entry.
    """
    members = get_decay_chain_members(parent)
    infos = {m: get_nuclide_info(m) for m in members}

    def fed_by(member, earlier):
        """(nuclide, share of its decays) of the nearest earlier member that decays into `member`."""
        for candidate in reversed(earlier):
            info = infos[candidate]
            for progeny, fraction in zip(info.get('progeny', []), info.get('branching_fractions', [])):
                if progeny == member:
                    return candidate, float(fraction)
        return None, 1.0

    feeders = [fed_by(member, members[:i]) if i else (None, 1.0) for i, member in enumerate(members)]
    sequence = []
    for i, member in enumerate(members):
        info = infos[member]
        feeder, share = feeders[i]
        if i < len(members) - 1:
            next_feeder, next_share = feeders[i + 1]
            to_next = next_share if next_feeder == member else None
        else:
            to_next = 1.0
        sequence.append({
            'nuclide': str(member),
            'half_life': info.get('half_life_readable', 'unknown'),
            'half_life_s': info.get('half_life_s'),
            'branching_to_next': to_next,
            'feeder': feeder,
            'branching_from_feeder': share,
            'is_branch': bool(feeder is not None and i > 0 and feeder != members[i - 1]),
        })

    return sequence


def _peak_strength(peak: Dict) -> float:
    """Net counts of a detected peak: the net area if the detector pipeline gave one, else its counts."""
    for key in ('net_area', 'area', 'counts'):
        value = peak.get(key)
        if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
            return float(value)
    return 0.0


# Two members of a chain whose gamma lines the ROI engine can measure, and whose activities are equal in equilibrium. The ROI
# database branching ratios are per chain decay, so a branch product (Tl-208, 35.94 % of Bi-212) already counts as the chain.
#   U-238: the two radon daughters. Equal activities unless radon escaped or arrived after one of them.
#   Th-232: Ac-228 (follows Ra-228, 5.75 y) and Tl-208 (follows Th-228, 1.9 y): unequal when Ra-228 or Th-228 was separated
#           (refined thorium, an aged lens).
GENERIC_EFFICIENCY_DETECTOR = "AlphaHound CsI(Tl)"   # when the detector is not known
EQUILIBRIUM_ROI_PAIRS = {
    'U-238': ('Bi-214 (609 keV)', 'Pb-214 (352 keV)'),
    'Th-232': ('Ac-228 (911 keV)', 'Tl-208 (2614 keV)'),
}
EQUILIBRIUM_CONSISTENT = 2.5     # activity ratio within this factor of 1: consistent with equilibrium (generic efficiencies, unresolved lines)
EQUILIBRIUM_DEPARTED = 6.0       # outside this factor: the chain is clearly not in equilibrium; in between, the data cannot say
EQUILIBRIUM_MIN_SNR = 5.0


def name_of(isotope: str) -> str:
    """'Bi-214 (609 keV)' -> 'Bi-214'."""
    return isotope.split(' (')[0]


def check_secular_equilibrium(detected_members: Dict[str, List[Dict]], parent: str,
                              energies=None, counts=None, detector: Optional[str] = None,
                              live_time_s: float = 0.0) -> Dict:
    """
    Check whether a decay chain appears to be in secular equilibrium (daughters' activities equal the parent's).

    The activities of two members are measured with the ROI engine on the spectrum itself (peak fit, the detector's efficiency
    and the line's branching ratio), because the peak list is not good enough for this: its areas and its wide matching
    tolerance can pair a line with the wrong peak. Without a spectrum the answer is "unknown".

    Returns a dict with 'in_equilibrium' (True: consistent; False: clearly not; None: cannot tell), 'confidence',
    'details' and 'ratio_check' ([{'pair', 'ratio', 'ratio_uncertainty', 'expected_ratio', 'in_range'}]).
    """
    result = {
        'in_equilibrium': None,  # True/False/None (unknown)
        'confidence': 'UNKNOWN',
        'details': '',
        'ratio_check': None
    }

    pair = EQUILIBRIUM_ROI_PAIRS.get(parent)
    if not pair:
        result['details'] = 'No equilibrium check defined for this chain'
        return result
    if energies is None or counts is None or len(energies) < 10:
        result['details'] = 'Equilibrium needs the spectrum itself'
        return result

    try:
        from spectroscopy.roi_analysis import ROIAnalyzer
        analyzer = ROIAnalyzer(detector or GENERIC_EFFICIENCY_DETECTOR)
        first = analyzer.analyze(list(energies), list(counts), pair[0], max(float(live_time_s or 0.0), 1.0))
        second = analyzer.analyze(list(energies), list(counts), pair[1], max(float(live_time_s or 0.0), 1.0))
    except Exception as exc:
        logger.debug("Equilibrium check for %s not possible: %s", parent, exc)
        result['details'] = 'Equilibrium could not be measured on this spectrum'
        return result

    def measured(r):
        return bool(r.activity_bq and r.snr >= EQUILIBRIUM_MIN_SNR)

    if measured(first) != measured(second):
        # one member is clear and the other is not: the weak one is at most its detection limit, which may already be far below
        # the strong one (a daughter lost to radon escape, a separated parent)
        strong, weak, strong_name, weak_name = (first, second, pair[0], pair[1]) if measured(first) else (second, first, pair[1], pair[0])
        upper = max(weak.mda_bq or 0.0, (weak.activity_bq or 0.0))
        if upper > 0 and strong.activity_bq / upper > EQUILIBRIUM_DEPARTED:
            ratio = strong.activity_bq / upper
            result['in_equilibrium'] = False
            result['confidence'] = 'LOW'
            label = f'{name_of(strong_name)}/{name_of(weak_name)}'
            result['ratio_check'] = [{'pair': label, 'ratio': float(ratio), 'ratio_uncertainty': None, 'expected_ratio': 1.0,
                                      'in_range': False, 'lower_limit': True}]
            result['details'] = (f'{name_of(weak_name)} is not detected while {name_of(strong_name)} is clear: '
                                 f'at least {ratio:.0f}x weaker, so the chain may not be in equilibrium')
            return result
    if not (measured(first) and measured(second)):
        result['details'] = 'Insufficient peak counts for equilibrium check'
        return result

    ratio = first.activity_bq / second.activity_bq
    uncertainty = ratio * math.sqrt((first.uncertainty_sigma / max(first.net_counts, 1e-9)) ** 2
                                    + (second.uncertainty_sigma / max(second.net_counts, 1e-9)) ** 2)
    label = f'{name_of(pair[0])}/{name_of(pair[1])}'
    in_range = bool(1.0 / EQUILIBRIUM_CONSISTENT <= ratio <= EQUILIBRIUM_CONSISTENT)
    result['ratio_check'] = [{'pair': label, 'ratio': float(ratio), 'ratio_uncertainty': float(uncertainty),
                              'expected_ratio': 1.0, 'in_range': in_range}]
    result['confidence'] = 'MEDIUM'
    if in_range:
        result['in_equilibrium'] = True
        result['details'] = f'{label} activities agree within a factor {EQUILIBRIUM_CONSISTENT:g}: consistent with secular equilibrium'
    elif not (1.0 / EQUILIBRIUM_DEPARTED <= ratio <= EQUILIBRIUM_DEPARTED):
        result['in_equilibrium'] = False
        result['details'] = f'{label} activities differ by more than a factor {EQUILIBRIUM_DEPARTED:g}: the chain may not be in equilibrium'
    else:
        result['details'] = f'{label} activities differ by {max(ratio, 1.0 / ratio):.1f}x: too far apart to call equilibrium, too close to call it broken'
        result['confidence'] = 'LOW'
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


def match_peaks_to_chain_detail(
    peaks: List[Dict],
    parent: str,
    energy_tolerance: float = 15.0,
    intensity_threshold: float = 1.0
) -> Tuple[int, int, List[str], Dict[str, List[Dict]]]:
    """
    Match detected peaks to expected chain gamma lines, keeping what was matched.

    Each gamma line takes the CLOSEST peak within the tolerance (not the first in list order).

    Returns:
        (detected_count, expected_count, detected_nuclides, matches) where matches maps a nuclide to
        [{'energy': peak energy, 'line_energy': gamma line, 'intensity': line intensity %, 'counts': peak net counts}, ...]
    """
    expected = get_expected_spectrum(parent, intensity_threshold)

    peak_energies = [p.get('energy', 0) for p in peaks]

    # Dynamic tolerance: use wider tolerance for high-count spectra
    # because peaks overlap and shift in strong scintillator spectra
    max_counts = max((p.get('counts', 0) for p in peaks), default=0)
    if max_counts > 10000:
        # Strong spectrum: use 60 keV tolerance (matches ~10% resolution at 600 keV)
        effective_tolerance = max(energy_tolerance, 60.0)
        logger.debug("High-count spectrum (%.0f), using tolerance=%s", max_counts, effective_tolerance)
    else:
        effective_tolerance = energy_tolerance

    detected_nuclides = []
    matches = {}  # nuclide -> [matched peaks]

    total_expected = 0
    total_detected = 0

    for nuclide, gamma_lines in expected.items():
        matched = []

        for gamma_energy, gamma_intensity in gamma_lines:
            total_expected += 1

            best_index, best_gap = None, None
            for i, peak_energy in enumerate(peak_energies):
                gap = abs(peak_energy - gamma_energy)
                if gap <= effective_tolerance and (best_gap is None or gap < best_gap):
                    best_index, best_gap = i, gap
            if best_index is not None:
                total_detected += 1
                matched.append({'energy': peak_energies[best_index], 'line_energy': gamma_energy,
                                'intensity': gamma_intensity, 'counts': _peak_strength(peaks[best_index])})

        if matched:
            detected_nuclides.append(nuclide)
            matches[nuclide] = matched

    logger.debug("%s: detected=%s/%s, nuclides=%s", parent, total_detected, total_expected, detected_nuclides)

    return total_detected, total_expected, detected_nuclides, matches


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
        Tuple of (detected_count, expected_count, detected_nuclides, matches) with matches mapping a nuclide to the energies of
        its matched peaks (see match_peaks_to_chain_detail for the full record).
    """
    detected, expected, nuclides, detail = match_peaks_to_chain_detail(peaks, parent, energy_tolerance, intensity_threshold)
    return detected, expected, nuclides, {nuclide: [m['energy'] for m in found] for nuclide, found in detail.items()}


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
        detected_count, expected_count, detected_nuclides, matches = match_peaks_to_chain_detail(
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
        for nuclide, found in matches.items():
            detected_members[nuclide] = [{'energy': m['energy'], 'counts': m['counts'], 'intensity': m['intensity']} for m in found]
        
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
        chains: List of detected chain dictionaries (as returned by identify_decay_chains_enhanced)

    Returns:
        Summary string
    """
    if not chains:
        return "No radioactive decay chains detected."

    lines = []
    for chain in chains:
        conf_icon = {'HIGH': '\u2713', 'MEDIUM': '\u25cb', 'LOW': '?'}.get(chain['confidence_level'], '?')
        members = list(chain.get('detected_members', {}))
        lines.append(
            f"{conf_icon} {chain['chain_name']} ({chain['confidence_level']}): "
            f"{chain['num_detected']} chain members detected "
            f"[{', '.join(members[:3])}]"
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
