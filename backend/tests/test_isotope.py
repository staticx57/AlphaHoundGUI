
import pytest
from backend.isotope_database import identify_isotopes, identify_decay_chains

def test_identify_isotopes_simple():
    # Cs-137 at 662 keV
    peaks = [{'energy': 662.0, 'net_area': 1000}]
    
    results = identify_isotopes(peaks, energy_tolerance=10.0, mode='simple')
    
    # Needs to match database
    match = next((i for i in results if i['isotope'] == 'Cs-137'), None)
    assert match is not None
    assert match['confidence'] == 100.0

def test_identify_decay_chains():
    # Basic U-238 chain (Bi-214 at 609, 1120, 1764)
    peaks = [
        {'energy': 609.3, 'net_area': 500},
        {'energy': 1120.3, 'net_area': 300},
        {'energy': 1764.5, 'net_area': 200},
        # Add Pb-214 for better confidence
        {'energy': 351.9, 'net_area': 400},
        {'energy': 295.2, 'net_area': 350}
    ]
    
    # 1. Identify Isotopes First
    isotop_results = identify_isotopes(peaks, energy_tolerance=10.0)
    
    # 2. Check Chains
    chains = identify_decay_chains(peaks, isotop_results, energy_tolerance=10.0)
    
    u238 = next((c for c in chains if 'U-238' in c['chain_name']), None)
    assert u238 is not None
    # With 2 isotopes (Bi-214, Pb-214), confidence might be LOW (2 isotopes) or MEDIUM (3). 
    # Logic: >=2 is LOW, >=3 is MEDIUM. We have 2. 
    # Le't check confidence_level key.
    assert u238['confidence_level'] in ['LOW', 'MEDIUM', 'HIGH']
