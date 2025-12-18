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

import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import math


# Half-lives in hours (for plausibility check)
# Short-lived isotopes cannot exist in aged environmental samples
ISOTOPE_HALF_LIVES = {
    # Very short-lived (minutes to hours) - VERY unlikely in environmental samples
    'F-18': 1.83,           # 110 minutes
    'Tc-99m': 6.0,          # 6 hours
    'N-13': 0.17,           # 10 minutes
    'O-15': 0.034,          # 2 minutes
    'C-11': 0.34,           # 20 minutes
    
    # Short-lived (hours to days) - Unlikely unless fresh
    'Tl-201': 73.0,         # 73 hours (3 days)
    'Ga-67': 78.3,          # 3.3 days
    'In-111': 67.3,         # 2.8 days
    'I-123': 13.2,          # 13 hours
    
    # Medium-lived (days to weeks)
    'I-131': 192.5,         # 8.02 days
    'Mo-99': 66.0,          # 66 hours
    'Xe-133': 126.0,        # 5.2 days
    
    # Long-lived (years+) - Plausible in any sample
    'Cs-137': 264398000,    # 30.2 years
    'Co-60': 46180000,      # 5.27 years
    'Am-241': 3795840000,   # 432 years
    'Ra-226': 14071200000,  # 1600 years
    
    # Primordial/decay chain (billions of years) - Always plausible
    'U-238': 39471840000000000,  # 4.5 billion years
    'U-235': 6176160000000000,   # 704 million years  
    'Th-232': 123120000000000000, # 14 billion years
    'K-40': 11010240000000000,   # 1.25 billion years
}


def calculate_halflife_penalty(isotope: str, assumed_sample_age_hours: float = 168.0) -> float:
    """
    Calculate a confidence penalty based on isotope half-life.
    
    Short-lived isotopes are penalized because they cannot exist in
    aged environmental samples. This naturally filters out medical
    isotopes like F-18, Tc-99m without artificial suppression.
    
    Args:
        isotope: Isotope name (e.g., 'F-18')
        assumed_sample_age_hours: Assumed minimum sample age in hours (default: 1 week)
        
    Returns:
        Penalty multiplier (0.0-1.0, where 1.0 = no penalty)
    """
    half_life = ISOTOPE_HALF_LIVES.get(isotope)
    
    if half_life is None:
        # Unknown isotope - check if it's a decay chain member (plausible)
        decay_chain_isotopes = [
            'Th-234', 'Pa-234m', 'U-234', 'Th-230', 'Ra-226', 'Rn-222',
            'Po-218', 'Pb-214', 'Bi-214', 'Po-214', 'Pb-210', 'Bi-210', 'Po-210',
            'Ra-228', 'Ac-228', 'Th-228', 'Ra-224', 'Rn-220', 'Po-216',
            'Pb-212', 'Bi-212', 'Tl-208', 'Po-212'
        ]
        if isotope in decay_chain_isotopes:
            return 1.0  # Decay chain products are always plausible
        return 0.8  # Unknown isotope - slight penalty
    
    # Calculate how many half-lives have passed
    half_lives_passed = assumed_sample_age_hours / half_life
    
    if half_lives_passed < 1:
        # Isotope could still exist
        return 1.0
    elif half_lives_passed < 5:
        # Significantly decayed but possible
        return max(0.3, 1.0 - (half_lives_passed * 0.15))
    elif half_lives_passed < 10:
        # Very decayed - unlikely
        return 0.1
    else:
        # More than 10 half-lives = essentially impossible
        # (less than 0.1% remaining)
        return 0.01


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


def calculate_isotope_confidence(
    isotope: str,
    detected_energy: float,
    expected_energy: float,
    peak_data: Optional[Dict] = None,
    all_peaks: Optional[List[Dict]] = None,
    tolerance: float = 15.0
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
    peaks: List[Dict]
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
        matched_energy = ident.get('matched_energy', ident.get('energy', 0))
        expected_energy = ident.get('expected_energy', matched_energy)
        
        # Find matching peak data
        peak_data = None
        for peak in peaks:
            if abs(peak.get('energy', 0) - matched_energy) < 10:
                peak_data = peak
                break
        
        # Calculate enhanced confidence
        confidence, factors = calculate_isotope_confidence(
            isotope=isotope,
            detected_energy=matched_energy,
            expected_energy=expected_energy,
            peak_data=peak_data,
            all_peaks=peaks
        )
        
        # Create enhanced identification
        enhanced_ident = ident.copy()
        
        # IMPORTANT: Convert to 0-100 scale to match core.py filtering thresholds
        enhanced_confidence = round(confidence * 100, 1)
        
        # Preserve suppression from original identification
        # If the original identification was suppressed, apply the same reduction
        if ident.get('suppressed', False):
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
        
        enhanced.append(enhanced_ident)
    
    # Sort by confidence
    enhanced.sort(key=lambda x: x['confidence'], reverse=True)
    
    return enhanced
