"""
Core settings and utilities for analysis routers.
Contains default settings and filtering functions.
"""

# Default settings for Simple mode
DEFAULT_SETTINGS = {
    "mode": "simple",
    "isotope_min_confidence": 30.0,
    "chain_min_confidence": 10.0,  # Lowered from 30 to allow natural chains with abundance weighting
    "energy_tolerance": 20.0,
    "chain_min_isotopes_medium": 2,  # Lowered from 3 to work with enhanced detection
    "chain_min_isotopes_high": 3,    # Lowered from 4
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
    
    DISABLED: Abundance weighting was causing Th-232 to be artificially 
    penalized even in actual thorium sources (like thoriated glass).
    Detection-based confidence is now used directly.
    
    The original logic was:
    - U-238: 99.274% of natural uranium (weight ~1.0)
    - U-235: 0.720% of natural uranium (weight ~0.007)  
    - Th-232: ~3.5× more abundant than U in Earth's crust (weight 0.35)
    
    But this is inappropriate for dedicated radioactive sources.
    """
    # DISABLED - return chains unchanged
    # Detection-based confidence is more appropriate for general-purpose analysis
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
    print(f"[DEBUG Isotopes] Filtering {len(isotopes)} isotopes with threshold={isotope_threshold}")
    
    for iso in isotopes[:5]:  # Show first 5 for debugging
        print(f"[DEBUG Iso] {iso.get('isotope', 'Unknown')}: conf={iso.get('confidence', 0)}")
    
    filtered_isotopes = [
        iso for iso in isotopes 
        if iso.get('confidence', 0) >= isotope_threshold
    ]
    
    print(f"[DEBUG Isotopes] After filtering: {len(filtered_isotopes)} isotopes remain")
    
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
    
    print(f"[DEBUG Chains] Filtering {len(chains)} chains with threshold={chain_threshold}, min_isotopes={min_isotopes}")
    
    filtered_chains = []
    for chain in chains:
        print(f"[DEBUG Chain] {chain.get('chain_name', 'Unknown')}: conf={chain.get('confidence', 0)}, num_detected={chain.get('num_detected', 0)}, num_key={chain.get('num_key_isotopes', 0)}")
        
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
        passes = chain['confidence'] >= chain_threshold and chain['num_detected'] >= min_isotopes
        print(f"[DEBUG Chain] -> passes filter: {passes}")
        if passes:
            filtered_chains.append(chain)
    
    print(f"[DEBUG Chains] After filtering: {len(filtered_chains)} chains remain")
    
    # Re-sort by weighted confidence
    filtered_chains.sort(key=lambda x: x['confidence'], reverse=True)
    
    return filtered_isotopes, filtered_chains
