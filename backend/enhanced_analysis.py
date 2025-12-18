"""
Enhanced Analysis Integration Module

Provides a unified API that combines all enhanced analysis modules:
- Enhanced peak detection (CWT + Gaussian validation)
- Dynamic decay chain detection (radioactivedecay)
- Multi-peak fitting (overlapping peak deconvolution)
- Enhanced confidence scoring

This module is the main entry point for the enhanced analysis pipeline.
"""

from typing import List, Dict, Optional, Tuple
import numpy as np


def run_enhanced_analysis(
    energies: List[float],
    counts: List[int],
    options: Optional[Dict] = None
) -> Dict:
    """
    Run the complete enhanced analysis pipeline.
    
    Args:
        energies: Energy array (keV)
        counts: Count array
        options: Optional configuration dictionary
        
    Returns:
        Complete analysis results dictionary
    """
    options = options or {}
    
    results = {
        'peaks': [],
        'isotopes': [],
        'chains': [],
        'multiplet_regions': [],
        'analysis_version': '2.0',
        'modules_used': []
    }
    
    # Phase 1: Enhanced Peak Detection
    try:
        from peak_detection_enhanced import detect_peaks_enhanced
        
        peaks = detect_peaks_enhanced(
            energies, counts,
            min_energy=options.get('min_energy', 30.0),
            max_energy=options.get('max_energy', 3000.0),
            validate_fits=options.get('validate_fits', True)
        )
        results['peaks'] = peaks
        results['modules_used'].append('peak_detection_enhanced')
        
    except ImportError as e:
        print(f"[Enhanced Analysis] Peak detection module not available: {e}")
        # Fallback to simple detection
        from scipy.signal import find_peaks
        energies_arr = np.array(energies)
        counts_arr = np.array(counts)
        indices, _ = find_peaks(counts_arr, prominence=np.max(counts_arr) * 0.02)
        peaks = [{'energy': energies_arr[i], 'counts': counts_arr[i]} for i in indices]
        results['peaks'] = peaks
    
    # Phase 2: Dynamic Chain Detection
    try:
        from chain_detection_enhanced import identify_decay_chains_enhanced
        
        chains = identify_decay_chains_enhanced(
            peaks,
            energy_tolerance=options.get('energy_tolerance', 15.0),
            min_score=options.get('min_chain_score', 0.25)
        )
        results['chains'] = chains
        results['modules_used'].append('chain_detection_enhanced')
        
    except ImportError as e:
        print(f"[Enhanced Analysis] Chain detection module not available: {e}")
        results['chains'] = []
    
    # Phase 3: Multiplet Fitting (for known overlap regions)
    try:
        from multiplet_fitting import enhance_peaks_with_multiplet_fitting
        
        enhanced_peaks = enhance_peaks_with_multiplet_fitting(energies, counts, peaks)
        results['peaks'] = enhanced_peaks
        results['modules_used'].append('multiplet_fitting')
        
        # Check for specific deconvolution results
        for peak in enhanced_peaks:
            if peak.get('multiplet_result'):
                results['multiplet_regions'].append({
                    'energy': peak.get('energy'),
                    'result': peak.get('multiplet_result')
                })
                
    except ImportError as e:
        print(f"[Enhanced Analysis] Multiplet fitting module not available: {e}")
    
    # Phase 4: Enhanced Confidence Scoring (if isotopes identified)
    try:
        from confidence_scoring import enhance_isotope_identifications
        
        # If we have isotope identifications, enhance them
        if results.get('isotopes'):
            results['isotopes'] = enhance_isotope_identifications(
                results['isotopes'],
                results['peaks']
            )
            results['modules_used'].append('confidence_scoring')
            
    except ImportError as e:
        print(f"[Enhanced Analysis] Confidence scoring module not available: {e}")
    
    return results


def get_enhanced_peaks(
    energies: List[float],
    counts: List[int],
    validate: bool = True
) -> List[Dict]:
    """
    Get enhanced peak detection results only.
    
    Args:
        energies: Energy array
        counts: Count array
        validate: Whether to validate peaks with Gaussian fitting
        
    Returns:
        List of peak dictionaries
    """
    try:
        from peak_detection_enhanced import detect_peaks_enhanced
        return detect_peaks_enhanced(energies, counts, validate_fits=validate)
    except ImportError:
        # Fallback
        from scipy.signal import find_peaks
        energies_arr = np.array(energies)
        counts_arr = np.array(counts)
        indices, _ = find_peaks(counts_arr, prominence=np.max(counts_arr) * 0.02)
        return [{'energy': energies_arr[i], 'counts': counts_arr[i]} for i in indices]


def get_enhanced_chains(
    peaks: List[Dict],
    energy_tolerance: float = 15.0
) -> List[Dict]:
    """
    Get dynamic chain detection results only.
    
    Args:
        peaks: List of detected peaks
        energy_tolerance: Matching tolerance (keV)
        
    Returns:
        List of detected chain dictionaries
    """
    try:
        from chain_detection_enhanced import identify_decay_chains_enhanced
        return identify_decay_chains_enhanced(peaks, energy_tolerance=energy_tolerance)
    except ImportError:
        return []


def deconvolve_186_region(
    energies: List[float],
    counts: List[int]
) -> Optional[Dict]:
    """
    Deconvolve the U-235/Ra-226 overlap at 186 keV.
    
    Args:
        energies: Energy array
        counts: Count array
        
    Returns:
        Deconvolution result or None
    """
    try:
        from multiplet_fitting import fit_186_kev_region
        return fit_186_kev_region(energies, counts)
    except ImportError:
        return None


def calculate_confidence(
    isotope: str,
    detected_energy: float,
    expected_energy: float,
    peak_data: Optional[Dict] = None,
    all_peaks: Optional[List[Dict]] = None
) -> Tuple[float, str]:
    """
    Calculate enhanced confidence for an isotope identification.
    
    Args:
        isotope: Isotope name
        detected_energy: Detected energy (keV)
        expected_energy: Expected energy (keV)
        peak_data: Peak properties
        all_peaks: All detected peaks
        
    Returns:
        Tuple of (confidence_score, confidence_label)
    """
    try:
        from confidence_scoring import calculate_isotope_confidence, get_confidence_label
        score, factors = calculate_isotope_confidence(
            isotope, detected_energy, expected_energy,
            peak_data, all_peaks
        )
        return score, get_confidence_label(score)
    except ImportError:
        # Fallback to simple scoring
        diff = abs(detected_energy - expected_energy)
        if diff < 5:
            return 0.9, 'HIGH'
        elif diff < 10:
            return 0.6, 'MEDIUM'
        else:
            return 0.3, 'LOW'


# Module availability check
def check_modules() -> Dict[str, bool]:
    """
    Check which enhanced modules are available.
    
    Returns:
        Dictionary of module name -> availability
    """
    modules = {}
    
    try:
        import peak_detection_enhanced
        modules['peak_detection_enhanced'] = True
    except ImportError:
        modules['peak_detection_enhanced'] = False
    
    try:
        import chain_detection_enhanced
        modules['chain_detection_enhanced'] = True
    except ImportError:
        modules['chain_detection_enhanced'] = False
    
    try:
        import multiplet_fitting
        modules['multiplet_fitting'] = True
    except ImportError:
        modules['multiplet_fitting'] = False
    
    try:
        import confidence_scoring
        modules['confidence_scoring'] = True
    except ImportError:
        modules['confidence_scoring'] = False
    
    try:
        import radioactivedecay
        modules['radioactivedecay'] = True
    except ImportError:
        modules['radioactivedecay'] = False
    
    return modules


if __name__ == '__main__':
    # Quick test
    print("Enhanced Analysis Module Check")
    print("=" * 40)
    
    modules = check_modules()
    for name, available in modules.items():
        status = "✓" if available else "✗"
        print(f"  {status} {name}")
    
    print()
    print("Ready for enhanced analysis!" if all(modules.values()) else "Some modules missing")
