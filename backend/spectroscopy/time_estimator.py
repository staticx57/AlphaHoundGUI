"""
Acquisition Time Estimator

Estimates acquisition time from spectrum count rates when the device
(like AlphaHound) doesn't provide timestamps.

Theory:
- Total counts = Activity × Efficiency × BranchingRatio × Time
- Time = TotalCounts / (Activity × Efficiency × BranchingRatio)

For known sources, we can estimate the expected count rate and
back-calculate the acquisition time.
"""

import math
from typing import Dict, Optional, List

# Expected gross count rates for typical sources at contact distance
# Units: counts per second for 1 kBq activity with AlphaHound CsI(Tl)
# These are empirical values based on detector sensitivity
EXPECTED_COUNT_RATES = {
    # Natural background (gross CPM in typical environment)
    'background': 50 / 60,  # ~50 CPM gross
    
    # Calibration sources (per kBq at contact)
    'Cs-137': 15.0,     # Strong gamma emitter
    'Co-60': 25.0,      # Two strong gammas
    'Am-241': 8.0,      # Low energy
    
    # Natural sources (gross CPM for typical samples)
    'uranium_glass': 200 / 60,      # ~200 CPM typical uranium glass
    'thoriated_lens': 300 / 60,     # ~300 CPM thoriated Takumar
    'radium_dial': 500 / 60,        # ~500 CPM radium dial watch
    'granite': 100 / 60,            # ~100 CPM granite countertop
    'potassium_salt': 80 / 60,      # ~80 CPM K-rich salt substitute
}

# AlphaHound CsI(Tl) sensitivity: 48 cps per µSv/h
ALPHAHOUND_SENSITIVITY_CPS_PER_USV_H = 48.0


def estimate_acquisition_time(
    total_counts: int,
    source_type: Optional[str] = None,
    peak_channel_counts: Optional[int] = None,
    estimated_activity_bq: Optional[float] = None,
    detected_dose_rate_usv_h: Optional[float] = None
) -> Dict:
    """
    Estimate acquisition time from spectrum statistics.
    
    Methods (in priority order):
    1. If dose rate known: Time = TotalCounts / (Sensitivity × DoseRate)
    2. If source type known: Time = TotalCounts / ExpectedCountRate
    3. Fallback: Estimate from total counts assuming background
    
    Args:
        total_counts: Total counts in spectrum
        source_type: Known source type (e.g., 'uranium_glass')
        peak_channel_counts: Counts in strongest peak
        estimated_activity_bq: Pre-estimated activity if available
        detected_dose_rate_usv_h: Dose rate from device if available
        
    Returns:
        Dict with:
            - estimated_time_s: Estimated acquisition seconds
            - estimated_time_readable: Human-readable format
            - confidence: HIGH/MEDIUM/LOW
            - method: Which estimation method was used
    """
    result = {
        'estimated_time_s': None,
        'estimated_time_readable': None,
        'confidence': 'LOW',
        'method': None,
        'valid': False
    }
    
    if total_counts <= 0:
        return result
    
    estimated_time_s = None
    confidence = 'LOW'
    method = None
    
    # Method 1: Use dose rate if available
    if detected_dose_rate_usv_h is not None and detected_dose_rate_usv_h > 0:
        expected_cps = ALPHAHOUND_SENSITIVITY_CPS_PER_USV_H * detected_dose_rate_usv_h
        estimated_time_s = total_counts / expected_cps
        confidence = 'HIGH'
        method = 'dose_rate'
    
    # Method 2: Use known source type
    elif source_type and source_type in EXPECTED_COUNT_RATES:
        expected_cps = EXPECTED_COUNT_RATES[source_type]
        estimated_time_s = total_counts / expected_cps
        confidence = 'MEDIUM'
        method = 'source_type'
    
    # Method 3: Estimate from peak prominence (heuristic)
    elif peak_channel_counts is not None and peak_channel_counts > 100:
        # Strong peaks suggest radioactive source
        # Assume moderately active source ~5 cps
        estimated_cps = 5.0
        estimated_time_s = total_counts / estimated_cps
        confidence = 'LOW'
        method = 'peak_heuristic'
    
    # Method 4: Fallback - assume background
    else:
        expected_cps = EXPECTED_COUNT_RATES['background']
        estimated_time_s = total_counts / expected_cps
        confidence = 'LOW'
        method = 'background_fallback'
    
    if estimated_time_s is None or estimated_time_s <= 0:
        return result
    
    result['estimated_time_s'] = float(estimated_time_s)
    result['confidence'] = confidence
    result['method'] = method
    result['valid'] = True
    
    # Format readable time
    if estimated_time_s < 60:
        result['estimated_time_readable'] = f"{estimated_time_s:.0f} seconds"
    elif estimated_time_s < 3600:
        minutes = estimated_time_s / 60
        result['estimated_time_readable'] = f"{minutes:.1f} minutes"
    elif estimated_time_s < 86400:
        hours = estimated_time_s / 3600
        result['estimated_time_readable'] = f"{hours:.1f} hours"
    else:
        days = estimated_time_s / 86400
        result['estimated_time_readable'] = f"{days:.1f} days"
    
    return result


def estimate_time_from_spectrum(
    counts: List[int],
    source_type: Optional[str] = None
) -> Dict:
    """
    Convenience function to estimate time from raw spectrum counts.
    
    Args:
        counts: Channel counts array
        source_type: Optional known source type
        
    Returns:
        Estimation result dict
    """
    total_counts = sum(counts)
    peak_counts = max(counts) if counts else 0
    
    return estimate_acquisition_time(
        total_counts=total_counts,
        source_type=source_type,
        peak_channel_counts=peak_counts
    )
