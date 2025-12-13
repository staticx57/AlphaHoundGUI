"""
Check if predict modifies in-place
"""
from riid.data.sampleset import SampleSet
from riid.models import MLPClassifier
import pandas as pd
import numpy as np

n_samples = 10
n_channels = 128
labels = ['Cs137'] * 4 + ['Co60'] * 3 + ['Background'] * 3

# Create training data
spectra_matrix = np.random.poisson(10, (n_samples, n_channels)).astype(float)
for i, label in enumerate(labels):
    if label == 'Cs137':
        spectra_matrix[i, 60:70] += 250

ss = SampleSet()
ss.spectra = pd.DataFrame(spectra_matrix)
ss.spectra_type = 3
ss.spectra_state = 1

# Sources
unique_labels = list(set(labels))
sources_data = {}
for iso in unique_labels:
    sources_data[('Radionuclide', iso, '')] = [1.0 if l == iso else 0.0 for l in labels]
sources_df = pd.DataFrame(sources_data)
sources_df.columns = pd.MultiIndex.from_tuples(sources_df.columns, names=SampleSet.SOURCES_MULTI_INDEX_NAMES)
ss.sources = sources_df

# Train
model = MLPClassifier()
model.fit(ss, epochs=3, target_level='Isotope', verbose=False)
print("✓ Training complete!")

# Create test with same structure
test_matrix = np.random.poisson(10, (1, n_channels)).astype(float)
test_matrix[0, 60:70] += 250  # Cs137 peak

test_ss = SampleSet()
test_ss.spectra = pd.DataFrame(test_matrix)
test_ss.spectra_type = 3
test_ss.spectra_state = 1

print(f"\nBefore predict:")
print(f"  test_ss.spectra columns: {list(test_ss.spectra.columns)}")
print(f"  test_ss has prediction_probas: {hasattr(test_ss, 'prediction_probas')}")

# Predict - check if modifies in-place
result = model.predict(test_ss)
print(f"\npredict() returned: {type(result)}")

print(f"\nAfter predict (check test_ss):")
print(f"  test_ss.spectra columns: {list(test_ss.spectra.columns)}")
if hasattr(test_ss, 'prediction_probas') and test_ss.prediction_probas is not None:
    print(f"  prediction_probas:\n{test_ss.prediction_probas}")

# Check for predictions attribute
try:
    preds_df = test_ss.get_predictions()
    if preds_df is not None and not preds_df.empty:
        print(f"\n✓ Predictions found!")
        print(f"Top predictions:")
        for iso, prob in preds_df.iloc[0].nlargest(3).items():
            print(f"  {iso}: {prob*100:.2f}%")
except Exception as e:
    print(f"get_predictions error: {e}")
