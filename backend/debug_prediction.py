"""
Full working test with prediction fix
"""
from riid.data.sampleset import SampleSet
from riid.models import MLPClassifier
import pandas as pd
import numpy as np

n_samples = 10
n_channels = 128
isotopes = ['Cs137', 'Co60', 'Background']

# Create spectra as 2D matrix (rows=samples, cols=channels)
spectra_matrix = np.random.poisson(10, (n_samples, n_channels)).astype(float)

# Add peaks for different isotopes
labels = ['Cs137'] * 4 + ['Co60'] * 3 + ['Background'] * 3
for i, label in enumerate(labels):
    if label == 'Cs137':
        spectra_matrix[i, 60:70] += 250  # Peak at channel 65
    elif label == 'Co60':
        spectra_matrix[i, 80:90] += 150  # Peak at channel 85

# Create SampleSet with matrix spectra
ss = SampleSet()
ss.spectra = pd.DataFrame(spectra_matrix)
ss.spectra_type = 3
ss.spectra_state = 1

# Create sources with 3-level MultiIndex
unique_labels = list(set(labels))
sources_data = {}
for iso in unique_labels:
    col_key = ('Radionuclide', iso, '')
    sources_data[col_key] = [1.0 if label == iso else 0.0 for label in labels]

sources_df = pd.DataFrame(sources_data)
sources_df.columns = pd.MultiIndex.from_tuples(
    sources_df.columns,
    names=SampleSet.SOURCES_MULTI_INDEX_NAMES
)
ss.sources = sources_df

print(f"Training SampleSet:")
print(f"  n_samples: {ss.n_samples}")
print(f"  n_channels: {ss.n_channels}")

# Train
model = MLPClassifier()
model.fit(ss, epochs=3, target_level='Isotope', verbose=False)
print("✓ Training complete!")

# Test prediction  
test_matrix = np.random.poisson(10, (1, n_channels)).astype(float)
test_matrix[0, 60:70] += 250  # Cs137-like peak

test_ss = SampleSet()
test_ss.spectra = pd.DataFrame(test_matrix)
test_ss.spectra_type = 3
test_ss.spectra_state = 1

print("\nPredicting...")
preds = model.predict(test_ss)

# Check what predict returns
print(f"preds type: {type(preds)}")
if preds is not None:
    print(f"preds.spectra columns: {list(preds.spectra.columns)}")
    
    # Check for prediction probas directly 
    if hasattr(preds, 'prediction_probas') and preds.prediction_probas is not None:
        print(f"prediction_probas:\n{preds.prediction_probas}")
    
    # Try get_predictions
    try:
        pred_df = preds.get_predictions()
        if pred_df is not None:
            print(f"\nTop predictions:")
            for iso, prob in pred_df.iloc[0].nlargest(3).items():
                print(f"  {iso}: {prob*100:.2f}%")
    except Exception as e:
        print(f"get_predictions() error: {e}")
    
    # Alternative: check the returned spectra
    print(f"\nReturned spectra shape: {preds.spectra.shape}")
    print(f"Returned spectra:\n{preds.spectra}")
else:
    print("preds is None!")
