"""
Safer deep dive into SampleSet structure
"""
from riid.data.synthetic import get_dummy_seeds
from riid.data.sampleset import SampleSet
from riid.models import MLPClassifier
import pandas as pd
import numpy as np

print("="*60)
print("Examining dummy seeds SampleSet")
print("="*60)

seeds = get_dummy_seeds()
print(f"Type: {type(seeds)}")
print(f"Number of samples: {seeds.n_samples}")
print(f"Number of channels: {seeds.n_channels}")
print(f"Classified by: {seeds.classified_by}")

print("\n" + "="*60)
print("Examining spectra DataFrame")
print("="*60)
print(f"Shape: {seeds.spectra.shape}")
print(f"\nColumns: {list(seeds.spectra.columns)}")

print("\n" + "="*60)
print("Sample data (first 3 rows, excluding 'counts'):")
print("="*60)
display_cols = [col for col in seeds.spectra.columns if col != 'counts']
print(seeds.spectra[display_cols].head(3))

print("\n" + "="*60)
print("Testing MLPClassifier.fit()")
print("="*60)

try:
    model = MLPClassifier()
    print(f"MLPClassifier created")
    print(f"Attempting to fit on seeds...")
    model.fit(seeds, epochs=2, verbose=True)
    print("✓ Training succeeded!")
    
    print("\n" + "="*60)
    print("Testing prediction")
    print("="*60)
    
    # Try predicting on the same seeds
    predictions = model.predict(seeds)
    print(f"Predictions type: {type(predictions)}")
    print(f"Predictions shape: {predictions.spectra.shape if hasattr(predictions, 'spectra') else 'N/A'}")
    
    # Get prediction columns
    pred_df = predictions.get_predictions()
    print(f"\nPrediction columns: {list(pred_df.columns)}")
    print(f"\nFirst prediction:")
    print(pred_df.iloc[0])
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("Testing with custom SampleSet")
print("="*60)

try:
    # Create a simple test spectrum
    test_counts = np.random.poisson(10, seeds.n_channels)
    
    test_df = pd.DataFrame({
        'live_time': [300.0],
        'total_counts': [test_counts.sum()]
    })
    test_df['counts'] = [test_counts]
    
    test_ss = SampleSet()
    test_ss.spectra = test_df
    test_ss.n_samples = 1
    test_ss.n_channels = seeds.n_channels
    
    print(f"Created test SampleSet:")
    print(f"  Samples: {test_ss.n_samples}")
    print(f"  Channels: {test_ss.n_channels}")
    print(f"  Columns: {list(test_ss.spectra.columns)}")
    
except Exception as e:
    print(f"✗ Error creating test SampleSet: {e}")
    import traceback
    traceback.print_exc()
