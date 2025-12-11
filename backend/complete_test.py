"""
Complete training and prediction test
"""
from riid.data.synthetic import get_dummy_seeds
from riid.data.sampleset import SampleSet
from riid.models import MLPClassifier
import pandas as pd
import numpy as np

print("="*60)
print("Step 1: Get dummy seeds and examine structure")
print("="*60)

seeds = get_dummy_seeds()
print(f"Samples: {seeds.n_samples}, Channels: {seeds.n_channels}")
print(f"Columns: {list(seeds.spectra.columns)}")
print(f"\nFirst row (excluding counts):")
display_cols = [col for col in seeds.spectra.columns if col != 'counts']
print(seeds.spectra[display_cols].iloc[0])

print("\n" + "="*60)
print("Step 2: Train MLPClassifier")
print("="*60)

model = MLPClassifier()
print("Training...")
model.fit(seeds, epochs=2, verbose=False)
print("✓ Training complete!")

print("\n" + "="*60)
print("Step 3: Test prediction on seeds")
print("="*60)

predictions = model.predict(seeds)
pred_df = predictions.get_predictions()
print(f"Prediction columns: {list(pred_df.columns)}")
print(f"\nFirst prediction probabilities:")
print(pred_df.iloc[0])

print("\n" + "="*60)
print("Step 4: Create custom test SampleSet")
print("="*60)

# Create test spectrum matching the channel count
test_counts = np.random.poisson(10, seeds.n_channels).astype(float)

# Create DataFrame matching seeds structure
test_df = pd.DataFrame({
    'live_time': [300.0],
    'total_counts': [float(test_counts.sum())],
    'counts': [test_counts]
})

print(f"Created test DataFrame:")
print(f"  Shape: {test_df.shape}")
print(f"  Columns: {list(test_df.columns)}")
print(f"  Counts shape: {test_df['counts'].iloc[0].shape}")

# Create SampleSet using from_dataframe or similar
test_ss = SampleSet()
test_ss.spectra = test_df

print(f"\nTest SampleSet:")
print(f"  n_samples: {test_ss.n_samples}")  
print(f"  n_channels: {test_ss.n_channels}")

print("\n" + "="*60)
print("Step 5: Predict on custom SampleSet")
print("="*60)

try:
    test_predictions = model.predict(test_ss)
    test_pred_df = test_predictions.get_predictions()
    print("✓ Prediction successful!")
    print(f"\nTop 5 predictions:")
    top_5 = test_pred_df.iloc[0].nlargest(5)
    for isotope, prob in top_5.items():
        print(f"  {isotope}: {prob*100:.2f}%")
except Exception as e:
    print(f"✗ Prediction failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("SUCCESS - Complete workflow works!")
print("="*60)
