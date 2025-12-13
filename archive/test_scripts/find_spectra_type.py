"""
Investigate spectra_type issue
"""
from riid.data.synthetic import get_dummy_seeds
from riid.data.sampleset import SampleSet
from riid.models import MLPClassifier
import inspect

print("="*60)
print("Checking spectra_type on dummy seeds")
print("="*60)

seeds = get_dummy_seeds()
print(f"spectra_type: {seeds.spectra_type}")
print(f"spectra_state: {seeds.spectra_state}")

print("\n" + "="*60)
print("Looking for supported spectra types in MLPClassifier")
print("="*60)

# Check MLPClassifier source for supported types
model = MLPClassifier()

# Check if there's documentation
print(f"MLPClassifier.fit docstring:")
print(model.fit.__doc__)

print("\n" + "="*60)
print("Checking SampleSet.spectra_type options")
print("="*60)

# Check if SampleSet has enum or constant for types
for attr in dir(SampleSet):
    if 'TYPE' in attr.upper() or 'STATE' in attr.upper():
        val = getattr(SampleSet, attr)
        if not callable(val):
            print(f"  {attr}: {val}")

print("\n" + "="*60)  
print("Trying to create SampleSet with different spectra_type")
print("="*60)

# Try creating with spectra_type = 0 (likely gross counts)
import pandas as pd
import numpy as np

test_counts = np.random.poisson(10, 512).astype(float)
test_df = pd.DataFrame({
    'live_time': [300.0],
    'total_counts': [float(test_counts.sum())],
    'counts': [test_counts]
})

test_ss = SampleSet()
test_ss.spectra = test_df

print(f"Default spectra_type: {test_ss.spectra_type}")
print(f"Default spectra_state: {test_ss.spectra_state}")

# Try setting spectra_type
for test_type in [0, 1, 2, 3]:
    try:
        test_ss_copy = SampleSet()
        test_ss_copy.spectra = test_df.copy()
        test_ss_copy.spectra_type = test_type
        print(f"  spectra_type {test_type}: ✓ can be set")
        
        # Try training with it
        try:
            model_test = MLPClassifier()
            model_test.fit(test_ss_copy, epochs=1, verbose=False)
            print(f"    Training with type {test_type}: ✓ SUCCESS")
            break  #  Found working type!
        except ValueError as e:
            print(f"    Training with type {test_type}: ✗ {e}")
    except Exception as e:
        print(f"  spectra_type {test_type}: ✗ {e}")
