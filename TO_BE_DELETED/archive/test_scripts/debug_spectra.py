"""
Debug spectra format issue
"""
from riid.data.sampleset import SampleSet
from riid.models import MLPClassifier
import pandas as pd
import numpy as np

print("="*60)
print("Creating training data with proper format")
print("="*60)

n_samples = 10
n_channels = 128
labels = ['Cs137'] * 5 + ['Background'] * 5

# Training spectra as 2D matrix
train_matrix = np.random.poisson(10, (n_samples, n_channels)).astype(float)
for i in range(5):  # Add Cs137 peaks to first 5
    train_matrix[i, 60:70] += 250

# Create training SampleSet
train_ss = SampleSet()
train_ss.spectra = pd.DataFrame(train_matrix)
train_ss.spectra_type = 3
train_ss.spectra_state = 1

print(f"Training spectra type: {type(train_ss.spectra)}")
print(f"Training spectra columns: {train_ss.spectra.columns[:5].tolist()}...")
print(f"Training spectra dtype: {train_ss.spectra.values.dtype}")

# Create sources
unique_labels = list(set(labels))
sources_data = {}
for iso in unique_labels:
    sources_data[('Radionuclide', iso, '')] = [1.0 if l == iso else 0.0 for l in labels]
sources_df = pd.DataFrame(sources_data)
sources_df.columns = pd.MultiIndex.from_tuples(sources_df.columns, names=SampleSet.SOURCES_MULTI_INDEX_NAMES)
train_ss.sources = sources_df

# Train
print("\nTraining...")
model = MLPClassifier()
model.fit(train_ss, epochs=3, target_level='Isotope', verbose=False)
print("✓ Training complete!")

# Create test spectrum - same way
print("\n" + "="*60)
print("Creating test data")
print("="*60)

test_spectrum = np.random.poisson(10, n_channels).astype(float)
test_spectrum[60:70] += 250  # Cs137 peak

# Reshape to 2D matrix like training
test_matrix = test_spectrum.reshape(1, -1)

test_ss = SampleSet()
test_ss.spectra = pd.DataFrame(test_matrix)
test_ss.spectra_type = 3
test_ss.spectra_state = 1

print(f"Test spectra type: {type(test_ss.spectra)}")
print(f"Test spectra columns: {test_ss.spectra.columns[:5].tolist()}...")
print(f"Test spectra dtype: {test_ss.spectra.values.dtype}")
print(f"Test spectra shape: {test_ss.spectra.shape}")

# Predict
print("\nPredicting...")
model.predict(test_ss)

# Check results
pred_df = test_ss.get_predictions()
print(f"\npred_df type: {type(pred_df)}")
print(f"pred_df shape: {pred_df.shape if pred_df is not None else 'None'}")
print(f"pred_df columns: {pred_df.columns.tolist() if pred_df is not None else 'None'}")
print(f"\npred_df:\n{pred_df}")

if pred_df is not None and not pred_df.empty:
    row = pred_df.iloc[0]
    print("\nPredictions:")
    for col_idx, confidence in enumerate(row):
        col_name = pred_df.columns[col_idx]
        isotope = col_name[1] if isinstance(col_name, tuple) else col_name
        print(f"  {isotope}: {float(confidence)*100:.2f}%")
