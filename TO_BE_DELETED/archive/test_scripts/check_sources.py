"""
Check how labels should be stored in SampleSet
"""
from riid.data.sampleset import SampleSet
import pandas as pd
import numpy as np

# Create test data
test_counts = [np.random.poisson(10, 1024).astype(float) for _ in range(3)]
test_df = pd.DataFrame({
    'live_time': [300.0] * 3,
    'total_counts': [spec.sum() for spec in test_counts],
    'counts': test_counts
})

ss = SampleSet()
ss.spectra = test_df

print("SampleSet attributes related to labels/sources:")
for attr in ['sources', 'info', 'labels', 'prediction_probas']:
    if hasattr(ss, attr):
        val = getattr(ss, attr)
        print(f"\n{attr}:")
        print(f"  Type: {type(val)}")
        if val is not None:
            print(f"  Value: {val}")
            if hasattr(val, 'columns'):
                print(f"  Columns: {list(val.columns)}")

# Try setting sources
print("\n" + "="*60)
print("Trying to set sources:")
print("="*60)

# Create sources DataFrame
sources_df = pd.DataFrame({
    'Isotope': ['Cs137', 'Co60', 'K40']
})

ss.sources = sources_df
print(f"Set sources successfully")
print(f"ss.sources:\n{ss.sources}")

# Try with multi-index as shown in SOURCES_MULTI_INDEX_NAMES
print("\n" + "="*60)
print("Trying multi-index sources:")
print("="*60)
print(f"SOURCES_MULTI_INDEX_NAMES: {SampleSet.SOURCES_MULTI_INDEX_NAMES}")

# Create with proper multi-index
sources_data = {
    'Isotope': ['Cs137', 'Co60', 'K40']
}
sources_mi = pd.DataFrame(sources_data)
sources_mi.columns = pd.MultiIndex.from_tuples([('Isotope', '')], names=SampleSet.SOURCES_MULTI_INDEX_NAMES)

try:
    ss2 = SampleSet()
    ss2.spectra = test_df
    ss2.sources = sources_mi
    print(f"✓ Multi-index sources set successfully")
    print(f"ss2.sources:\n{ss2.sources}")
except Exception as e:
    print(f"✗ Error: {e}")
