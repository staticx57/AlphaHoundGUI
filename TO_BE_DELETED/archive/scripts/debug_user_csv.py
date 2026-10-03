import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from csv_parser import parse_csv_spectrum
from peak_detection import detect_peaks
from isotope_database import identify_isotopes, identify_decay_chains
from main import DEFAULT_SETTINGS, apply_abundance_weighting, apply_confidence_filtering

filename = "community_spectrum_b83c9ae0_Ologoto.csv"

if not os.path.exists(filename):
    print(f"File {filename} not found!")
    sys.exit(1)

print(f"Processing {filename}...")

with open(filename, 'rb') as f:
    content = f.read()

try:
    # 1. Parse
    result = parse_csv_spectrum(content, filename)
    counts = result['counts']
    energies = result['energies']
    print(f"Parsed: {len(counts)} channels")
    print(f"First 5 energies: {energies[:5]}")
    print(f"First 5 counts: {counts[:5]}")
    
    # Check for linear bug
    if energies == counts:
         print("WARNING: Energies == Counts! Linear plot bug active.")
    
    # 2. Peaks
    peaks = detect_peaks(energies, counts)
    print(f"Detected {len(peaks)} peaks: {[p['energy'] for p in peaks]}")
    
    # 3. Isotopes
    all_isotopes = identify_isotopes(peaks, energy_tolerance=DEFAULT_SETTINGS['energy_tolerance'], mode='simple')
    print(f"Identified {len(all_isotopes)} potential isotopes")
    
    # 4. Chains
    all_chains = identify_decay_chains(peaks, all_isotopes, energy_tolerance=DEFAULT_SETTINGS['energy_tolerance'])
    print(f"Identified {len(all_chains)} potential chains")
    
    # 5. Weighting & Filtering
    weighted_chains = apply_abundance_weighting(all_chains)
    filtered_isotopes, filtered_chains = apply_confidence_filtering(all_isotopes, weighted_chains, DEFAULT_SETTINGS)
    
    print(f"\n--- FINAL RESULTS ---")
    print(f"Isotopes: {len(filtered_isotopes)}")
    for Iso in filtered_isotopes:
        print(f"  {Iso['isotope']}: {Iso['confidence']}%")
        
    print(f"Decay Chains: {len(filtered_chains)}")
    for chain in filtered_chains:
        print(f"  {chain['chain_name']} ({chain['confidence_level']}): {chain['num_detected']} isotopes detected")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
