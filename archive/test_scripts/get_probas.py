"""
Get prediction probabilities correctly
"""
from riid.data.sampleset import SampleSet
from riid.models import MLPClassifier
import pandas as pd
import numpy as np

n_samples = 10
n_channels = 128
labels = ['Cs137'] * 5 + ['Background'] * 5

# Training
train_matrix = np.random.poisson(10, (n_samples, n_channels)).astype(float)
for i in range(5):
    train_matrix[i, 60:70] += 250

train_ss = SampleSet()
train_ss.spectra = pd.DataFrame(train_matrix, columns=range(n_channels))
train_ss.spectra_type = 3
train_ss.spectra_state = 1

sources_data = {}
for iso in set(labels):
    sources_data[('Radionuclide', iso, '')] = [1.0 if l == iso else 0.0 for l in labels]
sources_df = pd.DataFrame(sources_data)
sources_df.columns = pd.MultiIndex.from_tuples(sources_df.columns, names=SampleSet.SOURCES_MULTI_INDEX_NAMES)
train_ss.sources = sources_df

model = MLPClassifier()
model.fit(train_ss, epochs=3, target_level='Isotope', verbose=False)
print("✓ Training complete!")

# Test
test_spectrum = np.random.poisson(10, n_channels).astype(float)
test_spectrum[60:70] += 250

test_ss = SampleSet()
test_ss.spectra = pd.DataFrame(test_spectrum.reshape(1, -1), columns=range(n_channels))
test_ss.spectra_type = 3
test_ss.spectra_state = 1

model.predict(test_ss)

# Check prediction_probas - this should have probabilities!
print(f"\ntest_ss.prediction_probas type: {type(test_ss.prediction_probas)}")
print(f"test_ss.prediction_probas:\n{test_ss.prediction_probas}")

# The get_predictions() gives class labels
preds = test_ss.get_predictions()
print(f"\ntest_ss.get_predictions() type: {type(preds)}")
print(f"test_ss.get_predictions():\n{preds}")

# So we should use prediction_probas for confidence
if test_ss.prediction_probas is not None and not test_ss.prediction_probas.empty:
    print("\n" + "="*60)
    print("Extracted predictions with probabilities:")
    print("="*60)
    
    probas = test_ss.prediction_probas
    for col in probas.columns:
        isotope = col[1] if isinstance(col, tuple) else col
        prob = float(probas[col].iloc[0])
        print(f"  {isotope}: {prob*100:.2f}%")
    
    print("\n✓ SUCCESS!")
