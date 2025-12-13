"""
Fix sources with correct 3-level multi-index: (Category, Isotope, Seed)
"""
from riid.data.sampleset import SampleSet
from riid.models import MLPClassifier
import pandas as pd
import numpy as np

print("="*60)
print("Creating sources with 3-level multi-index")
print("="*60)

# Training data
isotopes = ['Cs137', 'Co60', 'K40', 'Ra226', 'Background']
n_samples_per_isotope = 10
n_channels = 1024

all_spectra = []
all_labels = []

for isotope in isotopes:
    for i in range(n_samples_per_isotope):
        spectrum = np.random.poisson(8, n_channels).astype(float)
        if isotope == 'Cs137':
            spectrum[657:667] += np.random.poisson(250, 10)
        elif isotope == 'Co60':
            spectrum[500:515] += np.random.poisson(120, 15)
        all_spectra.append(spectrum)
        all_labels.append(isotope)

n_samples = len(all_spectra)
unique_isotopes = list(set(all_labels))
print(f"Training samples: {n_samples}")
print(f"Unique isotopes: {unique_isotopes}")

# Create spectra DataFrame
spectra_df = pd.DataFrame({
    'live_time': [300.0] * n_samples,
    'total_counts': [float(spec.sum()) for spec in all_spectra],
    'counts': all_spectra
})

# Create sources with 3-level MultiIndex: (Category, Isotope, Seed)
# One-hot encoding: each isotope is a column with 1.0 where that sample belongs to it
sources_data = {}
for iso in unique_isotopes:
    # Column tuple: (Category, Isotope name, Seed)
    # Category could be 'Radionuclide', Seed could be empty or '0'
    col_key = ('Radionuclide', iso, '')
    sources_data[col_key] = [1.0 if label == iso else 0.0 for label in all_labels]

sources_df = pd.DataFrame(sources_data)
sources_df.columns = pd.MultiIndex.from_tuples(
    sources_df.columns,
    names=SampleSet.SOURCES_MULTI_INDEX_NAMES  # ('Category', 'Isotope', 'Seed')
)

print(f"\nSources DataFrame:")
print(f"  Shape: {sources_df.shape}")
print(f"  Columns: {sources_df.columns.tolist()[:3]}...")

# Create SampleSet
ss = SampleSet()
ss.spectra = spectra_df
ss.sources = sources_df
ss.spectra_type = 3  # Gross
ss.spectra_state = 1  # Counts

print(f"\nSampleSet:")
print(f"  n_samples: {ss.n_samples}")
print(f"  n_channels: {ss.n_channels}")
print(f"  spectra_type: {ss.spectra_type}")

# Train
print("\n" + "="*60)
print("Training MLPClassifier...")
print("="*60)

try:
    model = MLPClassifier()
    history = model.fit(ss, epochs=5, target_level='Isotope', verbose=True)
    print("\n✓ Training SUCCESS!")
    
    # Test prediction
    test_spectrum = np.random.poisson(8, n_channels).astype(float)
    test_spectrum[657:667] += np.random.poisson(250, 10)  # Cs137-like
    
    test_df = pd.DataFrame({
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
    
    print("\n✓ Prediction SUCCESS!")
    print("\nTop predictions for Cs137-like spectrum:")
    for iso, prob in pred_df.iloc[0].nlargest(3).items():
        print(f"  {iso}: {prob*100:.2f}%")

    print("\n" + "="*60)
    print("COMPLETE SUCCESS! ML workflow working!")
    print("="*60)
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
