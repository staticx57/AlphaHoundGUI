"""
Deep dive into PyRIID API to understand training requirements
"""
from riid.data.synthetic import get_dummy_seeds
from riid.data.sampleset import SampleSet
import inspect

print("="*60)
print("Understanding get_dummy_seeds() output")
print("="*60)

seeds = get_dummy_seeds()
print(f"Type: {type(seeds)}")
print(f"Number of samples: {seeds.n_samples if hasattr(seeds, 'n_samples') else 'N/A'}")
print(f"Number of channels: {seeds.n_channels if hasattr(seeds, 'n_channels') else 'N/A'}")

print("\nSampleSet attributes:")
for attr in dir(seeds):
    if not attr.startswith('_'):
        val = getattr(seeds, attr)
        if not callable(val):
            print(f"  {attr}: {type(val).__name__}")

print("\n" + "="*60)
print("Examining seeds.spectra DataFrame")
print("="*60)
if hasattr(seeds, 'spectra') and seeds.spectra is not None:
    print(f"Shape: {seeds.spectra.shape}")
    print(f"\nColumns: {list(seeds.spectra.columns)}")
    print(f"\nFirst few rows:")
    print(seeds.spectra.head())
    
    # Check for label/target columns
    print(f"\n\nChecking for classification targets:")
    for col in seeds.spectra.columns:
        if 'label' in col.lower() or 'target' in col.lower() or 'isotope' in col.lower():
            print(f"  Found: {col}")
            print(f"  Unique values: {seeds.spectra[col].unique()}")

print("\n" + "="*60)
print("SampleSet methods")
print("="*60)
for attr in dir(seeds):
    if not attr.startswith('_'):
        val = getattr(seeds, attr)
        if callable(val):
            sig = inspect.signature(val)
            print(f"  {attr}{sig}")
