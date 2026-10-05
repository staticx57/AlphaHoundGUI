"""
Enhanced Confidence Scoring Module

Provides improved confidence calculation for isotope identification
by incorporating:
1. Gamma line intensity weights (authoritative data)
2. Peak fit quality metrics
3. Signal-to-noise ratios
4. Multiple peak consistency
5. Half-life plausibility (short-lived isotopes penalized)
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import math

# Import activity estimation
try:
    from spectroscopy.detector_efficiency import estimate_activity, interpolate_efficiency
    HAS_ACTIVITY_ESTIMATION = True
except ImportError:
    HAS_ACTIVITY_ESTIMATION = False


@dataclass
class ConfidenceFactors:
    """Breakdown of confidence calculation factors."""
    energy_match: float      # How well energy matches (0-0.25)
    intensity_weight: float  # Based on gamma line intensity (0-0.25)
    fit_quality: float       # Based on Gaussian fit R² (0-0.20)
    snr_factor: float        # Signal-to-noise ratio (0-0.15)
    consistency: float       # Multiple peak consistency (0-0.15)
    total: float             # Combined score (0-1.0)
    halflife_penalty: float = 1.0  # Half-life plausibility (0-1.0)


# Authoritative gamma line intensities (from IAEA/NNDC)
# Format: isotope -> {energy: intensity_percent}
GAMMA_INTENSITIES = {
    'U-238': {},  # No direct gammas
    'Th-234': {63.3: 4.8, 92.6: 5.6},
    'Pa-234m': {766.4: 0.32, 1001.0: 0.84},
    'Ra-226': {186.2: 3.6},
    'Pb-214': {241.9: 7.3, 295.2: 19.3, 351.9: 37.6},
    'Bi-214': {609.3: 46.1, 768.4: 4.9, 1120.3: 15.0, 1238.1: 5.8, 1764.5: 15.4},
    'Pb-210': {46.5: 4.3},
    'Th-232': {},
    'Ra-228': {},
    'Ac-228': {338.3: 11.3, 911.2: 25.8, 968.9: 15.8},
    'Th-228': {84.4: 1.2},
    'Ra-224': {241.0: 4.1},
    'Pb-212': {238.6: 43.6, 300.1: 3.3},
    'Bi-212': {727.3: 6.6, 1620.5: 1.5},
    'Tl-208': {583.2: 85.0, 860.6: 12.5, 2614.5: 99.8},
    'Cs-137': {661.7: 85.1},
    'Co-60': {1173.2: 99.9, 1332.5: 100.0},
    'Am-241': {59.5: 35.9, 26.3: 2.4},
    'K-40': {1460.8: 10.7},
    'U-235': {143.8: 11.0, 185.7: 57.2, 205.3: 5.0},
    'I-131': {364.5: 81.7, 636.9: 7.2},
    'Ba-133': {81.0: 32.9, 356.0: 62.1, 383.8: 8.9},
    'Eu-152': {121.8: 28.6, 344.3: 26.6, 1408.0: 21.0},
    'Na-22': {511.0: 180.7, 1274.5: 99.9},  # 511 is annihilation
}


# What a line really emits: the emission probability (%) the activity estimate divides by. A series parent lists lines its daughters emit
# (IAEA_DATA has no entry for Th-232, and its own 63.8 keV line is 0.26 %), so the daughter in its chain is looked up too.
_OWN_EMISSION = {"Th-232": {63.8: 0.26}}
_EMISSION_CACHE: Dict = {}


def line_emission(isotope: str, energy: float) -> Optional[float]:
    """Emission probability (%) of the gamma line near `energy` that `isotope`'s list means; None when no data says."""
    key = (isotope, round(energy, 1))
    if key in _EMISSION_CACHE:
        return _EMISSION_CACHE[key]
    found = None
    for e, i in _OWN_EMISSION.get(isotope, {}).items():
        if abs(e - energy) <= 1.0:
            found = i
    if found is None:
        try:
            from nuclides.isotope_database import IAEA_DATA
            names = [isotope]
            try:
                from nuclides.chain_detection_enhanced import get_decay_chain_members
                names += [m for m in get_decay_chain_members(isotope) if m != isotope]
            except Exception:
                pass
            best = None
            for n in names:
                for e, i in IAEA_DATA.get(n, {}).get("gammas", []):
                    gap = abs(e - energy)
                    if gap <= 1.0 and (best is None or gap < best[0]):
                        best = (gap, i)
            found = best[1] if best else None
        except Exception:
            found = None
    _EMISSION_CACHE[key] = found
    return found


def get_intensity_weight(isotope: str, energy: float, tolerance: float = 5.0) -> float:
    """
    Get the relative intensity weight for an isotope's gamma line.
    
    Args:
        isotope: Isotope name (e.g., 'Bi-214')
        energy: Gamma energy (keV)
        tolerance: Matching tolerance (keV)
        
    Returns:
        Intensity as fraction (0.0-1.0), or 1.0 if not found
    """
    if isotope not in GAMMA_INTENSITIES:
        return 1.0  # Unknown isotope - don't penalize
    
    gammas = GAMMA_INTENSITIES[isotope]
    if not gammas:
        return 1.0  # No gammas defined
    
    # Find matching energy
    for gamma_energy, intensity in gammas.items():
        if abs(gamma_energy - energy) <= tolerance:
            # Convert percentage to fraction, normalize to 0-1
            # Stronger lines (higher intensity) get higher weight
            return min(1.0, intensity / 100.0)
    
    return 0.1  # Energy doesn't match any known line - low weight


def calculate_energy_match_score(
    detected_energy: float,
    expected_energy: float,
    tolerance: float = 15.0
) -> float:
    """
    Calculate score based on how well the detected energy matches expected.
    
    Args:
        detected_energy: Detected peak energy (keV)
        expected_energy: Expected gamma line energy (keV)
        tolerance: Maximum acceptable difference (keV)
        
    Returns:
        Score from 0.0 to 0.25
    """
    diff = abs(detected_energy - expected_energy)
    
    if diff > tolerance:
        return 0.0
    
    # Linear falloff
    match_fraction = 1.0 - (diff / tolerance)
    return 0.25 * match_fraction


def calculate_intensity_score(
    isotope: str,
    energy: float,
    detected_area: Optional[float] = None,
    other_peaks: Optional[List[Dict]] = None
) -> float:
    """
    Calculate score based on gamma line intensity.
    
    Higher intensity lines should be detected with higher probability,
    so we give more weight to matches with high-intensity lines.
    
    Args:
        isotope: Isotope name
        energy: Gamma energy (keV)
        detected_area: Peak area (optional, for relative intensity check)
        other_peaks: Other detected peaks (for consistency check)
        
    Returns:
        Score from 0.0 to 0.25
    """
    intensity_weight = get_intensity_weight(isotope, energy)
    return 0.25 * intensity_weight


def calculate_fit_quality_score(
    r_squared: Optional[float] = None,
    fit_valid: bool = False
) -> float:
    """
    Calculate score based on Gaussian fit quality.
    
    Args:
        r_squared: R² value from Gaussian fit
        fit_valid: Whether fit passed validation
        
    Returns:
        Score from 0.0 to 0.20
    """
    if r_squared is None:
        return 0.10  # No fit info - give partial credit
    
    if not fit_valid:
        return 0.05  # Invalid fit - minimal credit
    
    # Scale R² to score
    return 0.20 * max(0, min(1, r_squared))


def calculate_snr_score(
    peak_counts: Optional[float] = None,
    background: Optional[float] = None,
    snr: Optional[float] = None
) -> float:
    """
    Calculate score based on signal-to-noise ratio and raw peak counts.
    
    Uses Poisson statistics to penalize low-count peaks that may be noise.
    
    Args:
        peak_counts: Net counts in peak
        background: Background counts
        snr: Pre-calculated SNR (if available)
        
    Returns:
        Score from 0.0 to 0.15
    """
    # Calculate effective SNR
    if snr is not None:
        effective_snr = snr
    elif peak_counts is not None and background is not None and background > 0:
        effective_snr = peak_counts / math.sqrt(background)
    else:
        effective_snr = 5.0  # Default moderate SNR
    
    # SNR thresholds:
    # < 2: Poor (noise level)
    # 2-5: Marginal
    # 5-10: Good
    # > 10: Excellent
    
    if effective_snr < 2:
        snr_component = 0.02
    elif effective_snr < 5:
        snr_component = 0.05 + 0.03 * (effective_snr - 2) / 3
    elif effective_snr < 10:
        snr_component = 0.08 + 0.04 * (effective_snr - 5) / 5
    else:
        snr_component = 0.12
    
    # Poisson quality factor: penalize low-count peaks
    # sqrt(N)/threshold gives quality based on statistical uncertainty
    # For N=100 counts, sqrt(100)/30 = 0.33 (poor)
    # For N=500 counts, sqrt(500)/30 = 0.75 (decent)
    # For N=900 counts, sqrt(900)/30 = 1.0 (full credit)
    MIN_RELIABLE_COUNTS = 500  # Minimum counts for full confidence
    
    if peak_counts is not None and peak_counts > 0:
        poisson_quality = min(1.0, math.sqrt(peak_counts) / math.sqrt(MIN_RELIABLE_COUNTS))
    else:
        poisson_quality = 0.5  # Unknown counts - partial credit
    
    # Combine SNR component with Poisson quality
    return snr_component * poisson_quality


def calculate_consistency_score(
    isotope: str,
    detected_energies: List[float],
    tolerance: float = 15.0
) -> float:
    """
    Calculate score based on consistency of multiple peak detections.
    
    If an isotope has multiple expected gamma lines and we detect
    multiple of them, confidence should increase.
    
    Args:
        isotope: Isotope name
        detected_energies: List of detected peak energies
        tolerance: Matching tolerance (keV)
        
    Returns:
        Score from 0.0 to 0.15
    """
    if isotope not in GAMMA_INTENSITIES:
        return 0.07  # Unknown - partial credit
    
    expected_gammas = GAMMA_INTENSITIES[isotope]
    if not expected_gammas:
        return 0.10  # No expected gammas - partial credit
    
    # Count how many expected lines are detected
    matched_count = 0
    for expected_energy in expected_gammas.keys():
        for detected in detected_energies:
            if abs(detected - expected_energy) <= tolerance:
                matched_count += 1
                break
    
    # Score based on fraction detected
    expected_count = len(expected_gammas)
    
    # INTRINSIC PHYSICS: Ambiguous peaks that can match many isotopes
    # These should require corroborating evidence from other peaks
    AMBIGUOUS_PEAKS = {
        511.0: 'annihilation',      # Positron annihilation - matches F-18, Na-22, any positron emitter
        1460.8: 'K-40',             # K-40 is everywhere, can overwhelm nearby peaks
        2614.5: 'Tl-208',           # Strong Th-232 chain peak
    }
    
    # Check if the matched peaks are ambiguous
    all_matches_ambiguous = True
    for expected_energy in expected_gammas.keys():
        for detected in detected_energies:
            if abs(detected - expected_energy) <= tolerance:
                # Found a match - is it ambiguous?
                is_ambiguous = any(abs(expected_energy - amb) < 5 for amb in AMBIGUOUS_PEAKS.keys())
                if not is_ambiguous:
                    all_matches_ambiguous = False
                break
    
    # Single-peak penalty: isotopes with only ONE gamma line are less reliable
    # because any random peak could match by chance
    if expected_count == 1:
        if matched_count > 0:
            # Check if it's an ambiguous single peak
            single_energy = list(expected_gammas.keys())[0]
            is_ambiguous = any(abs(single_energy - amb) < 5 for amb in AMBIGUOUS_PEAKS.keys())
            if is_ambiguous:
                return 0.02  # Very low score for ambiguous single-peak isotopes
            return 0.06  # Low score for any single-peak isotope
        return 0.0
    
    match_fraction = matched_count / expected_count
    
    # Multi-peak isotopes: require at least 2 matching peaks for good confidence
    # This naturally filters false positives from single random peak matches
    if matched_count >= 3:
        return 0.15
    elif matched_count >= 2:
        # Only give full credit if matches aren't all ambiguous
        if all_matches_ambiguous:
            return 0.08
        return 0.12
    elif matched_count >= 1:
        # Single match from multi-peak isotope: suspicious
        return 0.04 * match_fraction
    else:
        return 0.0


AMBIGUOUS_LINES = (511.0, 1460.8, 2614.5)   # annihilation, K-40 and Tl-208: in many spectra whatever the source


def matched_lines_consistency(matched_lines: List[float], total_lines: int) -> float:
    """
    Multi-peak consistency (0-0.15) from the lines the matcher actually assigned to the isotope, out of the lines it lists: the same rules
    as calculate_consistency_score, but on the isotope's own line list instead of the small intensity table above.
    """
    matched = len(matched_lines)
    if matched == 0:
        return 0.0
    all_ambiguous = all(any(abs(e - a) < 5 for a in AMBIGUOUS_LINES) for e in matched_lines)
    if total_lines == 1:
        return 0.02 if all_ambiguous else 0.06
    if matched >= 3:
        return 0.15
    if matched == 2:
        return 0.08 if all_ambiguous else 0.12
    return 0.04 * matched / total_lines


def calculate_isotope_confidence(
    isotope: str,
    detected_energy: float,
    expected_energy: float,
    peak_data: Optional[Dict] = None,
    all_peaks: Optional[List[Dict]] = None,
    tolerance: float = 15.0,
    identification: Optional[Dict] = None,
) -> Tuple[float, ConfidenceFactors]:
    """
    Calculate comprehensive confidence score for an isotope identification.
    
    Uses INTRINSIC properties only - no assumptions about sample age or source.
    
    Args:
        isotope: Isotope name
        detected_energy: Detected peak energy (keV)
        expected_energy: Expected gamma line energy (keV)
        peak_data: Dictionary with peak properties (area, snr, r_squared, etc.)
        all_peaks: All detected peaks (for consistency check)
        tolerance: Energy matching tolerance (keV)
        
    Returns:
        Tuple of (total_confidence, ConfidenceFactors breakdown)
    """
    peak_data = peak_data or {}
    all_peaks = all_peaks or []
    
    # Calculate individual factors - ALL based on observed spectrum properties
    energy_score = calculate_energy_match_score(detected_energy, expected_energy, tolerance)

    if identification and identification.get('matched_peaks'):
        # the share of the isotope's emission (its listed lines, weighted by intensity) that the spectrum shows
        expected_total = sum(e.get('intensity', 0) or 0 for e in identification.get('expected_peaks') or [])
        seen = sum(m.get('intensity', 0) or 0 for m in identification['matched_peaks'])
        intensity_score = 0.25 * (min(1.0, seen / expected_total) if expected_total > 0 else 0.5)
    else:
        intensity_score = calculate_intensity_score(isotope, expected_energy)

    fit_score = calculate_fit_quality_score(
        r_squared=peak_data.get('r_squared'),
        fit_valid=peak_data.get('fit_valid', False)
    )
    
    snr_score = calculate_snr_score(
        peak_counts=peak_data.get('area', peak_data.get('counts')),
        background=peak_data.get('background'),
        snr=peak_data.get('snr')
    )
    
    # Get all detected energies for consistency check
    # This is the KEY intrinsic filter - multi-peak consistency
    if identification and identification.get('matched_peaks'):
        consistency_score = matched_lines_consistency(
            [m['expected'] for m in identification['matched_peaks']], identification.get('total_lines') or 1)
    else:
        detected_energies = [p.get('energy', 0) for p in all_peaks]
        detected_energies.append(detected_energy)
        consistency_score = calculate_consistency_score(isotope, detected_energies, tolerance)
    
    # Total score - purely based on observed spectrum
    total = energy_score + intensity_score + fit_score + snr_score + consistency_score
    total = min(1.0, max(0.0, total))
    
    factors = ConfidenceFactors(
        energy_match=energy_score,
        intensity_weight=intensity_score,
        fit_quality=fit_score,
        snr_factor=snr_score,
        consistency=consistency_score,
        total=total
    )
    
    return total, factors


def get_confidence_label(score: float) -> str:
    """
    Convert numeric confidence to human-readable label.
    
    Args:
        score: Confidence score (0.0-1.0)
        
    Returns:
        Label string ('HIGH', 'MEDIUM', 'LOW')
    """
    if score >= 0.7:
        return 'HIGH'
    elif score >= 0.4:
        return 'MEDIUM'
    else:
        return 'LOW'


def enhance_isotope_identifications(
    identifications: List[Dict],
    peaks: List[Dict],
    live_time: float = 0.0,
    detector: Optional[str] = None,
) -> List[Dict]:
    """
    Enhance isotope identification list with improved confidence scores.
    
    Args:
        identifications: List of isotope identification dictionaries
        peaks: List of detected peak dictionaries
        
    Returns:
        Enhanced identification list
    """
    enhanced = []

    for ident in identifications:
        isotope = ident.get('isotope', ident.get('name', ''))
        # The isotope's own evidence: its strongest matched line (the matcher's records carry `matched_peaks`; reading keys it never
        # writes scored every isotope as a perfect match of a line at 0 keV, a constant per isotope whatever the spectrum held)
        matched = ident.get('matched_peaks') or []
        best = max(matched, key=lambda m: (m.get('intensity', 0), -m.get('diff', 0))) if matched else None
        matched_energy = best['observed'] if best else ident.get('matched_energy', ident.get('energy', 0))
        expected_energy = best['expected'] if best else ident.get('expected_energy', matched_energy)

        # The peak that line was matched to
        peak_data = min(peaks, key=lambda p: abs(p.get('energy', 0) - matched_energy), default=None)
        if peak_data is not None and abs(peak_data.get('energy', 0) - matched_energy) >= 10:
            peak_data = None

        # Calculate enhanced confidence
        confidence, factors = calculate_isotope_confidence(
            isotope=isotope,
            detected_energy=matched_energy,
            expected_energy=expected_energy,
            peak_data=peak_data,
            all_peaks=peaks,
            identification=ident,
        )

        # Create enhanced identification
        enhanced_ident = ident.copy()
        enhanced_ident['matched_energy'] = matched_energy
        enhanced_ident['expected_energy'] = expected_energy
        
        # IMPORTANT: Convert to 0-100 scale to match core.py filtering thresholds
        enhanced_confidence = round(confidence * 100, 1)
        
        # The validation rules' ceiling (a multi-line isotope seen through too few of its lines) holds whatever the peak quality
        if ident.get('validation_cap') is not None:
            enhanced_confidence = min(enhanced_confidence, ident['validation_cap'])

        # Preserve suppression from original identification
        # If the original identification was suppressed, apply the same reduction
        if ident.get('suppressed', False):
            enhanced_ident['unsuppressed_confidence'] = round(enhanced_confidence, 1)   # for a later step that can overrule the reason
            enhanced_confidence *= 0.1  # 90% reduction, same as original suppression
            enhanced_ident['suppressed'] = True
            enhanced_ident['suppression_reason'] = ident.get('suppression_reason', 'unknown')
        
        enhanced_ident['confidence'] = round(enhanced_confidence, 1)
        enhanced_ident['confidence_label'] = get_confidence_label(confidence)
        enhanced_ident['confidence_factors'] = {
            'energy_match': round(factors.energy_match, 3),
            'intensity_weight': round(factors.intensity_weight, 3),
            'fit_quality': round(factors.fit_quality, 3),
            'snr_factor': round(factors.snr_factor, 3),
            'consistency': round(factors.consistency, 3)
        }
        enhanced_ident['analysis_mode'] = 'enhanced'
        
        # Activity estimate: the peak's NET AREA over (efficiency x the line's emission probability x live time). It used the spectrum height
        # at the peak (the peak's `counts`), a branching ratio of 50 % for every isotope and a live time of 60 s, whatever the run: 480 times
        # too much on an 8-hour capture, and the ratio between isotopes only that of their peak heights. With no live time or no emission
        # data there is no estimate rather than an invented one.
        if HAS_ACTIVITY_ESTIMATION and live_time > 1.0 and matched:                  # 1 s or less is the pipeline's 'live time unknown'
            # the matched line with the most expected counts (emission x efficiency): not the one nearest in energy, which for Th-232 is its
            # own 63.8 keV line (0.26 %), a peak that is X-rays in every real spectrum
            detector_name = detector or "AlphaHound CsI(Tl)"
            candidates = []
            for m in matched:
                emission = line_emission(isotope, m['expected'])
                if emission:
                    candidates.append(((interpolate_efficiency(detector_name, m['expected']) or 0.0) * emission, emission, m))
            if candidates:
                _, emission, line = max(candidates, key=lambda t: t[0])
                peak = min(peaks, key=lambda p: abs(p.get('energy', 0) - line['observed']), default=None)
                area = (peak.get('net_area', peak.get('area', 0)) or 0) if peak is not None and abs(peak.get('energy', 0) - line['observed']) < 10 else 0
                if area > 0:
                    activity = estimate_activity(
                        peak_counts=area,
                        energy_keV=line['expected'],
                        branching_ratio=emission / 100.0,
                        live_time_s=live_time,
                        detector_name=detector_name,
                    )
                    if activity.get('valid'):
                        enhanced_ident['activity_estimate'] = {
                            'value_bq': activity['activity_bq'],
                            'readable': activity['activity_readable'],
                            'uncertainty_pct': activity['uncertainty_pct'],
                            'line_keV': line['expected'],
                        }

        enhanced.append(enhanced_ident)
    
    # Sort by confidence
    enhanced.sort(key=lambda x: x['confidence'], reverse=True)
    
    return enhanced
