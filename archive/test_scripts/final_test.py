"""Final end-to-end test with detailed error reporting"""
from riid.data.sampleset import SampleSet
from riid.models import MLPClassifier
import pandas as pd
import numpy as np
import traceback

print("Creating training data...")
isotopes = ['Cs137', 'Co60', 'K40', 'Ra226', 'Background']
n_samples_per_isotope = 15
n_channels = 1024

all_spectra = []
all_labels = []

for isotope in isotopes:
    for i in range(n_samples_per_isotope):
        spectrum = np.random.poisson(8, n_channels).astype(float)
        if isotope == 'Cs137':
            peak_ch = 662
            spectrum[peak_ch-5:peak_ch+5] += np.random.poisson(250, 10)
        all_spectra.append(spectrum)
        all_labels.append(isotope)

# Create training data
train_df = pd.DataFrame({
    'live_time': [300.0] * len(all_spectra),
    'total_counts': [float(spec.sum()) for spec in all_spectra],
    'counts': all_spectra
})

labels_df = pd.DataFrame({
    'Isotope': all_labels
})

print(f"Train spectra shape: {train_df.shape}")
print(f"Train spectra columns: {list(train_df.columns)}")
print(f"Labels shape: {labels_df.shape}")
print(f"Labels columns: {list(labels_df.columns)}")
print(f"Labels unique values: {labels_df['Isotope'].unique()}")

# Create SampleSet
train_ss = SampleSet()
train_ss.spectra = train_df
train_ss.sources = labels_df
train_ss.spectra_type = 3
train_ss.spectra_state = 1

print(f"\nSampleSet created:")
print(f"  n_samples: {train_ss.n_samples}")
print(f"  n_channels: {train_ss.n_channels}")
print(f"  spectra_type: {train_ss.spectra_type}")
print(f"  spectra_state: {train_ss.spectra_state}")
print(f"  sources.shape: {train_ss.sources.shape}")
print(f"  sources.columns: {list(train_ss.sources.columns)}")

# Train
print("\nTraining...")
try:
    model = MLPClassifier()
    model.fit(train_ss, epochs=2, target_level='Isotope', verbose=True)
    print("✓ Training successful!")
    
    # Predict
    test_spectrum = np.random.poisson(8, n_channels).astype(float)
    test_spectrum[657:667] += np.random.poisson(250, 10)
    
    test_df =pd.DataFrame({
        'live_time': [300.0],
        'total_counts': [float(test_spectrum.sum())],
        'counts': [test_spectrum]
    })
    
    test_ss = SampleSet()
    test_ss.spectra = test_df
    test_ss.spectra_type = 3
    test_ss.spectra_state = 1
    
    print("\nPredicting...")
    preds = model.predict(test_ss)
    pred_df = preds.get_predictions()
    
    print("✓ Prediction successful!")
    print("\nTop predictions:")
    for iso, prob in pred_df.iloc[0].nlargest(3).items():
        print(f"  {iso}: {prob*100:.2f}%")
        
    print("\n" + "="*60)
    print("SUCCESS - Complete workflow works!")
    print("="*60)
    
except Exception as e:
    print(f"\n✗ ERROR: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
