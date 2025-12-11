"""
Core settings and utilities for analysis routers.
Contains default settings and filtering functions.
"""

# Default settings for Simple mode
DEFAULT_SETTINGS = {
    "mode": "simple",
    "isotope_min_confidence": 30.0,
    "chain_min_confidence": 30.0,
    "energy_tolerance": 20.0,
    "chain_min_isotopes_medium": 3,
    "chain_min_isotopes_high": 4,
    "max_isotopes": 5
}

# Settings for generic File Uploads (often uncalibrated/noisy)
UPLOAD_SETTINGS = DEFAULT_SETTINGS.copy()
UPLOAD_SETTINGS.update({
    "chain_min_confidence": 1.0,
    "energy_tolerance": 30.0,
    "chain_min_isotopes_medium": 1
})

def apply_abundance_weighting(chains):
    """
    Apply natural abundance weighting to decay chain confidence scores.
    
    Based on authoritative sources (LBNL, NRC):
    - U-238: 99.274% of natural uranium (weight ~1.0)
    - U-235: 0.720% of natural uranium (weight ~0.007)  
    - Th-232: ~3.5× more abundant than U in Earth's crust
    """
    abundance_weights = {
        'U-238': 1.0,
        'U-235': 0.007,
        'Th-232': 0.35
    }
    
    for chain in chains:
        chain_name = chain.get('chain_name', '')
        
        # Apply abundance weight
        for key, weight in abundance_weights.items():
            if key in chain_name:
                original_conf = chain.get('confidence', 0)
                weighted_conf = original_conf * weight
                chain['confidence'] = weighted_conf
                chain['original_confidence'] = original_conf
                break
    
    return chains

def apply_confidence_filtering(isotopes, chains, settings):
    """
    Apply confidence filtering to isotopes and chains based on settings.
    
    Args:
        isotopes: List of identified isotopes
        chains: List of identified decay chains
        settings: Settings dictionary with thresholds
        
    Returns:
        Tuple of (filtered_isotopes, filtered_chains)
    """
    # Filter isotopes
    isotope_threshold = settings.get('isotope_min_confidence', 30.0)
    filtered_isotopes = [
        iso for iso in isotopes 
        if iso.get('confidence', 0) >= isotope_threshold
    ]
    
    # Limit isotopes if in simple mode
    max_isotopes = settings.get('max_isotopes', 999)
    if settings.get('mode') == 'simple' and len(filtered_isotopes) > max_isotopes:
        filtered_isotopes = sorted(
            filtered_isotopes, 
            key=lambda x: x.get('confidence', 0), 
            reverse=True
        )[:max_isotopes]
    
    # Filter chains
    chain_threshold = settings.get('chain_min_confidence', 30.0)
    min_isotopes = settings.get('chain_min_isotopes_medium', 3)
    
    filtered_chains = []
    for chain in chains:
        # Calculate confidence level
        percentage = (chain['num_detected'] / chain['num_key_isotopes'] * 100) if chain['num_key_isotopes'] > 0 else 0
        
        high_threshold = settings.get('chain_min_isotopes_high', 4)
        med_threshold = settings.get('chain_min_isotopes_medium', 3)
        
        if chain['num_detected'] >= high_threshold or percentage >= 80:
            chain['confidence_level'] = 'HIGH'
        elif chain['num_detected'] >= med_threshold or percentage >= 60:
            chain['confidence_level'] = 'MEDIUM'
        else:
            chain['confidence_level'] = 'LOW'
            
        # Force downgrade based on weighted confidence
        if chain['confidence'] < 15.0:
            chain['confidence_level'] = 'LOW'
        elif chain['confidence'] < 40.0 and chain['confidence_level'] == 'HIGH':
            chain['confidence_level'] = 'MEDIUM'
        
        # Apply filter
        if chain['confidence'] >= chain_threshold and chain['num_detected'] >= min_isotopes:
            filtered_chains.append(chain)
    
    # Re-sort by weighted confidence
    filtered_chains.sort(key=lambda x: x['confidence'], reverse=True)
    
    return filtered_isotopes, filtered_chains
