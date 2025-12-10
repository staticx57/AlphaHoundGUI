# Database of common isotopes and their gamma-ray energies (keV)
# Format: isotope_name: [list of primary gamma energies]

ISOTOPE_DATABASE = {
    # Medical/Industrial isotopes
    "Co-60": [1173.2, 1332.5],
    "Cs-137": [661.7],
    "Na-22": [511.0, 1274.5],
    "Am-241": [59.5],
    "Ba-133": [81.0, 276.4, 302.9, 356.0, 383.8],
    
    # Natural background
    "K-40": [1460.8],
    "Tl-208": [583.2, 860.6, 2614.5],
    "Bi-214": [609.3, 1120.3, 1764.5],
    "Pb-214": [295.2, 351.9],
    "Ac-228": [338.3, 911.2, 968.9],
    
    # Fission products
    "I-131": [364.5],
    "Te-132": [228.2],
    "Cs-134": [604.7, 795.9],
    
    # Activation products
    "Mn-54": [834.8],
    "Co-58": [810.8],
    "Zn-65": [1115.5],
    "Fe-59": [1099.2, 1291.6],
    
    # X-ray sources
    "Cd-109": [88.0],
    "Sr-85": [514.0],
    
    # Uranium/Thorium series
    "U-235": [185.7],
    "Th-232": [238.6],
    "Ra-226": [186.2],
    "Pb-210": [46.5],
}

def identify_isotopes(peaks, energy_tolerance=5.0):
    """
    Identify possible isotopes based on detected peaks.
    
    Args:
        peaks: List of detected peak dictionaries with 'energy' key
        energy_tolerance: Maximum energy difference for a match (keV)
    
    Returns:
        List of identified isotopes with confidence scores
    """
    if not peaks:
        return []
    
    isotope_matches = {}
    
    # For each isotope in database
    for isotope, gamma_energies in ISOTOPE_DATABASE.items():
        matches = 0
        matched_peaks = []
        
        # Check how many of its gamma energies match detected peaks
        for gamma_energy in gamma_energies:
            for peak in peaks:
                energy_diff = abs(peak['energy'] - gamma_energy)
                if energy_diff <= energy_tolerance:
                    matches += 1
                    matched_peaks.append({
                        'expected': gamma_energy,
                        'observed': peak['energy'],
                        'diff': energy_diff
                    })
                    break
        
        # Calculate confidence score
        if matches > 0:
            # Confidence based on fraction of characteristic peaks found
            confidence = (matches / len(gamma_energies)) * 100
            
            isotope_matches[isotope] = {
                'isotope': isotope,
                'confidence': confidence,
                'matches': matches,
                'total_lines': len(gamma_energies),
                'matched_peaks': matched_peaks
            }
    
    # Sort by confidence
    identified = sorted(isotope_matches.values(), 
                       key=lambda x: (x['matches'], x['confidence']), 
                       reverse=True)
    
    # Return top 5 most likely isotopes
    return identified[:5]
