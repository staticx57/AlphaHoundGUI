"""Test with the actual demo file"""
import sys
sys.path.insert(0, '.')

from ml_analysis import get_ml_identifier

# Exact counts from demo_uranium_chain.n42 at line 13
demo_counts = [5]*21 + [35, 120, 200, 80, 20] + [5]*37 + [10, 80, 350, 600, 350, 80, 10] + [5]*8 + \
              [10, 85, 420, 680, 420, 85, 10] + [5]*14 + [10, 120, 650, 950, 650, 120, 10] + [5]*11 + \
              [15, 150, 850, 1200, 850, 150, 15] + [5]*45 + \
              [25, 250, 1500, 3200, 1500, 250, 25] + [5]*82 + \
              [10, 120, 650, 950, 650, 120, 10] + [5]*70 + \
              [15, 180, 1100, 1650, 1100, 180, 15] + [5]*324 + \
              [20, 220, 1450, 2100, 1450, 220, 20] + [5]*368

print(f"Demo file channels: {len(demo_counts)}")

ml = get_ml_identifier()
ml.lazy_train()

print("\nRunning ML on demo_uranium_chain.n42 counts...")
results = ml.identify(demo_counts, top_k=5)

print("\n" + "="*60)
print("RESULTS")
print("="*60)
for i, pred in enumerate(results, 1):
    marker = " ✓✓✓ MATCH!" if pred['isotope'] == 'UraniumGlass' else ""
    print(f"{i}. {pred['isotope']}: {pred['confidence']:.1f}%{marker}")
