# Core settings and helper functions
DEFAULT_SETTINGS = {
    "mode": "simple",
    "isotope_min_confidence": 30.0,
    "chain_min_confidence": 30.0,
    "energy_tolerance": 20.0,
    "chain_min_isotopes_medium": 3,
    "chain_min_isotopes_high": 4,
    "max_isotopes": 5
}

UPLOAD_SETTINGS = DEFAULT_SETTINGS.copy()
UPLOAD_SETTINGS.update({
    "chain_min_confidence": 1.0,
    "energy_tolerance": 30.0,
    "chain_min_isotopes_medium": 1
})

def apply_abundance_weighting(chains):
    """
    Apply natural abundance weighting to decay chain confidence scores.
    """
    for chain in chains:
        abundance_weight = chain.get('abundance_weight', 1.0)
        original_confidence = chain['confidence']
        
        if abundance_weight < 0.01:
            weighted_confidence = original_confidence * abundance_weight * 10
        elif abundance_weight > 0.9:
            weighted_confidence = original_confidence * 1.05
        else:
            weighted_confidence = original_confidence
        
        chain['confidence_unweighted'] = original_confidence
        chain['confidence'] = weighted_confidence
        chain['abundance_weight'] = abundance_weight
    
    return chains

def apply_confidence_filtering(isotopes, chains, settings):
    """
    Apply threshold filtering based on mode settings.
    """
    filtered_isotopes = [
        iso for iso in isotopes
        if iso['confidence'] >= settings.get('isotope_min_confidence', 40.0)
    ]
    
    if settings.get('mode') == 'simple':
        filtered_isotopes = filtered_isotopes[:settings.get('max_isotopes', 5)]
    
    min_isotopes = settings.get('chain_min_isotopes_medium', 3)
    filtered_chains = []
    
    for chain in chains:
        percentage = (chain['num_detected'] / chain['num_key_isotopes'] * 100) if chain['num_key_isotopes'] > 0 else 0
        
        high_threshold = settings.get('chain_min_isotopes_high', 4)
        med_threshold = settings.get('chain_min_isotopes_medium', 3)
        
        if chain['num_detected'] >= high_threshold or percentage >= 80:
            chain['confidence_level'] = 'HIGH'
        elif chain['num_detected'] >= med_threshold or percentage >= 60:
            chain['confidence_level'] = 'MEDIUM'
        else:
            chain['confidence_level'] = 'LOW'
            
        if chain['confidence'] < 15.0:
            chain['confidence_level'] = 'LOW'
        elif chain['confidence'] < 40.0 and chain['confidence_level'] == 'HIGH':
            chain['confidence_level'] = 'MEDIUM'
        
        if chain['confidence'] >= settings.get('chain_min_confidence', 30.0) and chain['num_detected'] >= min_isotopes:
            filtered_chains.append(chain)
    
    filtered_chains.sort(key=lambda x: x['confidence'], reverse=True)
    return filtered_isotopes, filtered_chains
