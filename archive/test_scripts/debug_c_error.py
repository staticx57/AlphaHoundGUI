"""
Debug the 'C' error
"""
from riid.data.sampleset import SampleSet
from riid.models import MLPClassifier
import pandas as pd
import numpy as np

n_samples = 10
n_channels = 128
labels = ['Cs137'] * 5 + ['Background'] * 5

# Training spectra
train_matrix = np.random.poisson(10, (n_samples, n_channels)).astype(float)
for i in range(5):
    train_matrix[i, 60:70] += 250

train_ss = SampleSet()
# Use explicit integer column names
train_ss.spectra = pd.DataFrame(train_matrix, columns=range(n_channels))
train_ss.spectra_type = 3
train_ss.spectra_state = 1

print(f"Training columns (first 5): {list(train_ss.spectra.columns[:5])}")

# Sources
unique_labels = list(set(labels))
sources_data = {}
for iso in unique_labels:
    sources_data[('Radionuclide', iso, '')] = [1.0 if l == iso else 0.0 for l in labels]
sources_df = pd.DataFrame(sources_data)
sources_df.columns = pd.MultiIndex.from_tuples(sources_df.columns, names=SampleSet.SOURCES_MULTI_INDEX_NAMES)
train_ss.sources = sources_df

print("Training...")
model = MLPClassifier()
model.fit(train_ss, epochs=3, target_level='Isotope', verbose=False)
print("✓ Training complete!")

# Test spectrum
test_spectrum = np.random.poisson(10, n_channels).astype(float)
test_spectrum[60:70] += 250

test_ss = SampleSet()
# IMPORTANT: Use same column structure as training!
test_ss.spectra = pd.DataFrame(test_spectrum.reshape(1, -1), columns=range(n_channels))
test_ss.spectra_type = 3
test_ss.spectra_state = 1

print(f"Test columns (first 5): {list(test_ss.spectra.columns[:5])}")

print("Predicting...")
model.predict(test_ss)

# Get predictions - handle Series/DataFrame differences
preds = test_ss.get_predictions()
print(f"\nPredictions type: {type(preds)}")

if isinstance(preds, pd.Series):
    print(f"Series index: {list(preds.index)}")
    for idx, val in preds.items():
        isotope = idx[1] if isinstance(idx, tuple) else idx
        print(f"  {isotope}: {float(val)*100:.2f}%")
elif isinstance(preds, pd.DataFrame):
    print(f"DataFrame columns: {list(preds.columns)}")
    row = preds.iloc[0]
    for col_idx, val in enumerate(row):
        col = preds.columns[col_idx]
        isotope = col[1] if isinstance(col, tuple) else col
        print(f"  {isotope}: {float(val)*100:.2f}%")
else:
    print(f"Unknown type: {preds}")

print("\n✓ SUCCESS!")
