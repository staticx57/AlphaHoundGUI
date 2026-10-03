"""
Create a working ML workflow from scratch, avoiding get_dummy_seeds
"""
from riid.data.sampleset import SampleSet
from riid.models import MLPClassifier
import pandas as pd
import numpy as np

print("="*60)
print("Creating training data manually")
print("="*60)

# Create simple synthetic training data
# We'll create a few "isotopes" with characteristic peak patterns
isotopes = ['Cs137', 'Co60', 'K40', 'Background']
n_channels = 1024
n_samples_per_isotope = 10

all_spectra = []
all_labels = []

for isotope in isotopes:
    for i in range(n_samples_per_isotope):
        # Create spectrum with noise
        spectrum = np.random.poisson(5, n_channels).astype(float)
        
        # Add characteristic peaks for each isotope
        if isotope == 'Cs137':
            # 662 keV peak around channel 662 (assuming 1 keV/channel)
            peak_ch = min(662, n_channels-50)
            spectrum[peak_ch-5:peak_ch+5] += np.random.poisson(200, 10)
        elif isotope == 'Co60':
            # 1173 and 1332 keV peaks
            if n_channels > 1332:
                spectrum[1165:1180] += np.random.poisson(100, 15)
                spectrum[1325:1340] += np.random.poisson(100, 15)
        elif isotope == 'K40':
            # 1461 keV peak
            if n_channels > 1461:
                spectrum[1455:1465] += np.random.poisson(80, 10)
        # Background has no peaks, just noise
        
        all_spectra.append(spectrum)
        all_labels.append(isotope)

# Create DataFrame
train_df = pd.DataFrame({
    'live_time': [300.0] * len(all_spectra),
    'total_counts': [spec.sum() for spec in all_spectra],
    'counts': all_spectra,
    'Isotope': all_labels
})

print(f"Created {len(all_spectra)} training spectra")
print(f"Isotopes: {isotopes}")

# Create SampleSet
train_ss = SampleSet()
train_ss.spectra = train_df
train_ss.spectra_state = 2  # Gross counts

print(f"Training SampleSet:")
print(f"  n_samples: {train_ss.n_samples}")
print(f"  n_channels: {train_ss.n_channels}")
print(f"  spectra_type: {train_ss.spectra_type}")
print(f"  spectra_state: {train_ss.spectra_state}")

print("\n" + "="*60)
print("Training MLPClassifier")
print("="*60)

model = MLPClassifier()
print("Fitting model...")
try:
    history = model.fit(train_ss, epochs=5, verbose=False)
    print("✓ Training successful!")
except Exception as e:
    print(f"✗ Training failed: {e}")
    import traceback
    traceback.print_exc()
    import sys
    sys.exit(1)

print("\n" + "="*60)
print("Testing prediction")
print("="*60)

# Create test spectrum (Cs-137 like)
test_spectrum = np.random.poisson(5, n_channels).astype(float)
test_spectrum[657:667] += np.random.poisson(200, 10)  # Cs-137 peak

test_df = pd.DataFrame({
    'live_time': [300.0],
    'total_counts': [test_spectrum.sum()],
    'counts': [test_spectrum]
})

test_ss = SampleSet()
test_ss.spectra = test_df
test_ss.spectra_state = 2  # Same as training

print(f"Test SampleSet: n_samples={test_ss.n_samples}, n_channels={test_ss.n_channels}")

try:
    predictions = model.predict(test_ss)
    pred_df = predictions.get_predictions()
    
    print("✓ Prediction successful!")
    print(f"\nPredictions for Cs-137-like spectrum:")
    pred_values = pred_df.iloc[0]
    for isotope, prob in pred_values.nlargest(4).items():
        print(f"  {isotope}: {prob*100:.2f}%")
        
    print("\n" + "="*60)
    print("SUCCESS - Complete ML workflow working!")
    print("="*60)
    
except Exception as e:
    print(f"✗ Prediction failed: {e}")
    import traceback
    traceback.print_exc()
