"""
Check counts array format - should they be in a matrix not list of arrays?
"""
from riid.data.sampleset import SampleSet
from riid.models import MLPClassifier
import pandas as pd
import numpy as np

print("="*60)
print("Test different spectra formats")
print("="*60)

n_samples = 5
n_channels = 128  # Smaller for testing
isotopes = ['Cs137', 'Co60', 'Background']

# Method 1: spectra as 2D numpy array (matrix-style)
print("\nMethod 1: spectra as 2D matrix")
try:
    spectra_matrix = np.random.poisson(10, (n_samples, n_channels)).astype(float)
    
    ss1 = SampleSet()
    ss1.spectra = pd.DataFrame(spectra_matrix)  # Columns are channel indices
    ss1.spectra_type = 3
    ss1.spectra_state = 1
    
    print(f"  spectra shape: {ss1.spectra.shape}")
    print(f"  n_samples: {ss1.n_samples}")
    print(f"  n_channels: {ss1.n_channels}")
    print("  ✓ Method 1 works!")
    
    # Add sources with multi-index
    labels = ['Cs137'] * 2 + ['Co60'] * 2 + ['Background']
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
    
    ss1.sources = sources_df
    print(f"  sources shape: {ss1.sources.shape}")
    
    # Try training
    print("\n  Attempting to train...")
    model = MLPClassifier()
    model.fit(ss1, epochs=2, target_level='Isotope', verbose=False)
    print("  ✓ Training SUCCESS!")
    
    # Test prediction
    test_matrix = np.random.poisson(10, (1, n_channels)).astype(float)
    test_ss = SampleSet()
    test_ss.spectra = pd.DataFrame(test_matrix)
    test_ss.spectra_type = 3
    test_ss.spectra_state = 1
    
    preds = model.predict(test_ss)
    pred_df = preds.get_predictions()
    print("\n  ✓ Prediction SUCCESS!")
    print("  Top predictions:")
    for iso, prob in pred_df.iloc[0].nlargest(3).items():
        print(f"    {iso}: {prob*100:.2f}%")
    
    print("\n" + "="*60)
    print("SUCCESS! WORKING ML WORKFLOW!")
    print("="*60)
    
except Exception as e:
    print(f"  ✗ Error: {e}")
    import traceback
    traceback.print_exc()
