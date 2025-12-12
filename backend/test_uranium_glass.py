"""
Test the new multi-isotope mixture training
"""
import sys
sys.path.insert(0, '.')

from ml_analysis import get_ml_identifier
import numpy as np

print("="*60)
print("TESTING MULTI-ISOTOPE MIXTURE TRAINING")
print("="*60)

# Get ML identifier (will trigger training)
ml = get_ml_identifier()

print("\n[1] Training model with multi-isotope mixtures...")
ml.lazy_train()

print("\n[2] Creating synthetic UraniumGlass spectrum...")
# Create a uranium glass spectrum manually
# Should have: U-238, Th-234, Bi-214 (strongest), Pb-214, Ra-226
counts = np.random.poisson(5, 1024).astype(int)

# U-238 peak at 49 keV
counts[int(49/3)] += 50
# Th-234 peak at 63 keV
counts[int(63/3)] += 70
# Bi-214 peaks (strongest)
counts[int(609/3)] += 300  # 609 keV - STRONGEST
counts[int(1120/3)] += 150  # 1120 keV
counts[int(1764/3)] += 80   # 1764 keV
# Pb-214 peaks
counts[int(352/3)] += 180
counts[int(295/3)] += 120
# Ra-226 peak
counts[int(186/3)] += 100

counts_list = counts.tolist()

print(f"   Total counts: {sum(counts_list)}")
print(f"   Peak at 609 keV (Bi-214): channel {int(609/3)}")

print("\n[3] Running ML identification...")
results = ml.identify(counts_list, top_k=5)

print("\n" + "="*60)
print("RESULTS")
print("="*60)
if results:
    for i, pred in enumerate(results, 1):
        marker = " ✓✓✓ CORRECT!" if pred['isotope'] == 'UraniumGlass' else ""
        marker2 = " (U-238 chain)" if pred['isotope'] in ['U-238', 'Bi-214', 'Pb-214', 'Ra-226', 'Th-234'] else ""
        print(f"{i}. {pred['isotope']}: {pred['confidence']:.1f}%{marker}{marker2}")
else:
    print("No results!")

print("="*60)
