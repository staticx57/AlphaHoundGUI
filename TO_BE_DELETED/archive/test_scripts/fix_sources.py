"""
Investigate the correct sources DataFrame structure by examining PyRIID internals
"""
from riid.data.sampleset import SampleSet
import pandas as pd
import numpy as np

print("="*60)
print("SampleSet.SOURCES_MULTI_INDEX_NAMES")
print("="*60)
print(SampleSet.SOURCES_MULTI_INDEX_NAMES)

print("\n" + "="*60)
print("Create proper multi-index sources")
print("="*60)

# Create sample data
n = 3
isotopes = ['Cs137', 'Co60', 'K40']

# Create multi-index columns based on SOURCES_MULTI_INDEX_NAMES
# According to PyRIID, sources uses a specific multi-index format
try:
    # SOURCES_MULTI_INDEX_NAMES likely = ('Category', 'Isotope') or similar
    names = SampleSet.SOURCES_MULTI_INDEX_NAMES
    print(f"Index names: {names}")
    
    # Try creating sources with multi-index columns where Isotope is a level
    if len(names) == 2:
        # Create columns like: (category, isotope_name)
        # Each unique isotope gets a column with 1.0 where that sample is that isotope
        unique_isotopes = list(set(isotopes))
        
        # Create one-hot encoded format
        data = {}
        for iso in unique_isotopes:
            data[('Isotope', iso)] = [1.0 if label == iso else 0.0 for label in isotopes]
        
        sources_df = pd.DataFrame(data)
        sources_df.columns = pd.MultiIndex.from_tuples(
            sources_df.columns,
            names=names
        )
        
        print(f"\nCreated sources DataFrame:")
        print(sources_df)
        print(f"\nColumns: {sources_df.columns.tolist()}")
        
        # Test with SampleSet
        test_counts = [np.random.poisson(10, 1024).astype(float) for _ in range(n)]
        test_df = pd.DataFrame({
            'live_time': [300.0] * n,
            'total_counts': [spec.sum() for spec in test_counts],
            'counts': test_counts
        })
        
        ss = SampleSet()
        ss.spectra = test_df
        ss.sources = sources_df
        ss.spectra_type = 3
        ss.spectra_state = 1
        
        print(f"\nSampleSet created successfully!")
        print(f"ss.sources.columns: {ss.sources.columns.tolist()}")
        
        # Now try training
        from riid.models import MLPClassifier
        print("\nAttempting to train MLPClassifier...")
        model = MLPClassifier()
        model.fit(ss, epochs=2, target_level='Isotope', verbose=True)
        print("\n✓ SUCCESS!")
        
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
