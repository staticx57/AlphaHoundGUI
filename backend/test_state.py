"""
Test with supported spectra states
"""
from riid.data.synthetic import get_dummy_seeds
from riid.data.sampleset import SampleSet
from riid.models import MLPClassifier
import pandas as pd
import numpy as np

print("="*60)
print("Testing with spectra_state instead of spectra_type")
print("="*60)

test_counts = np.random.poisson(10, 512).astype(float)
test_df = pd.DataFrame({
    'live_time': [300.0],
    'total_counts': [float(test_counts.sum())],
    'counts': [test_counts]
})

# Try state 1 (foreground/net) and state 2 (gross)
for state in [1, 2]:
    print(f"\nTesting spectra_state = {state}")
    try:
        test_ss = SampleSet()
        test_ss.spectra = test_df.copy()
        test_ss.spectra_state = state
        print(f"  Created SampleSet with state {state}")
        print(f"    spectra_type: {test_ss.spectra_type}")
        print(f"    spectra_state: {test_ss.spectra_state}")
        
        # Add some dummy labels for training
        # Check what columns seeds have
        seeds = get_dummy_seeds()
        seeds_cols = seeds.spectra.columns
        print(f"  Dummy seeds columns: {list(seeds_cols)}")
        
        # Try to mimic seeds structure
        for col in seeds_cols:
            if col not in test_df.columns and col != 'counts':
                if 'isotope' in col.lower():
                    test_ss.spectra[col] = 'Cs137'  # Dummy isotope
                elif 'categorical' in str(seeds.spectra[col].dtype):
                    test_ss.spectra[col] = seeds.spectra[col].iloc[0]
                    
        print(f"  Augmented test SampleSet columns: {list(test_ss.spectra.columns)}")
        
        # Now try training a fresh model
        model = MLPClassifier()
        print(f"  Attempting to fit model...")
        model.fit(test_ss, epochs=1, verbose=False)
        print(f"  ✓ Training SUCCESS with state {state}!")
        
        # Try prediction
        pred_ss = model.predict(test_ss)
        pred_df = pred_ss.get_predictions()
        print(f"  ✓ Prediction SUCCESS!")
        print(f"    Prediction columns: {list(pred_df.columns)[:5]}...")  # Show first 5
        break
        
    except Exception as e:
        print(f"  ✗ Error with state {state}: {e}")

print("\n" + "="*60)
print("Now testing simple approach: use get_dummy_seeds() directly")
print("="*60)

# The simplest approach: just use dummy seeds as-is, they're already trained
try:
    # Convert dummy seeds to a trainable state
    seeds = get_dummy_seeds()
    print(f"Original seeds spectra_state: {seeds.spectra_state}")
    
    #Convert to state 2 (gross)
    seeds.spectra_state = 2
    print(f"Modified seeds spectra_state: {seeds.spectra_state}")
    
    model = MLPClassifier()
    print("Training on modified seeds...")
    model.fit(seeds, epochs=2, verbose=False)
    print("✓ Training successful!")
    
    # Create test sample
    test_counts = np.random.poisson(10, seeds.n_channels).astype(float)
    test_df = pd.DataFrame({
        'live_time': [300.0],
        'total_counts': [float(test_counts.sum())],
        'counts': [test_counts]
    })
    
    test_ss = SampleSet()
    test_ss.spectra = test_df
    test_ss.spectra_state = 2
    
    print("\nPredicting...")
    predictions = model.predict(test_ss)
    pred_df = predictions.get_predictions()
    
    print("✓ Prediction successful!")
    print(f"\nTop 5 predictions:")
    if len(pred_df) > 0:
        top_5 = pred_df.iloc[0].nlargest(5)
        for isotope, prob in top_5.items():
            print(f"  {isotope}: {prob*100:.2f}%")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
