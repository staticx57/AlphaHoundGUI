"""Quick test of peak detection on 6hr uranium glass file."""
import sys
sys.path.insert(0, 'backend')

from csv_parser import parse_csv_spectrum

# Load the spectrum file
with open('backend/data/acquisitions/spectrum_2025-12-12_08-41-27.csv', 'rb') as f:
    content = f.read()

# Parse with CSV parser (same as upload endpoint)
result = parse_csv_spectrum(content, 'test.csv')

print(f"\n=== CSV PARSER RESULTS ===")
print(f"Counts: {len(result['counts'])} channels")
print(f"Energies: {len(result['energies'])} values")
print(f"Is calibrated: {result['is_calibrated']}")
print(f"\n=== PEAKS DETECTED: {len(result['peaks'])} ===")

# Show all peaks
for i, p in enumerate(result['peaks'][:20]):
    print(f"  {i+1}. {p['energy']:.1f} keV, {p['counts']:.0f} counts")

print(f"\n=== TOP 5 ISOTOPES ===")
for i, iso in enumerate(result['isotopes'][:5]):
    print(f"  {i+1}. {iso['isotope']}: {iso['confidence']:.1f}%")
