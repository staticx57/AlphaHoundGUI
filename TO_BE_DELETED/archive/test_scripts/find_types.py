"""
Find exact spectra_type mapping
"""
from riid.data.sampleset import SampleSet
import pandas as pd
import numpy as np

# Check SpectraType enum or constants
print("="*60)
print("Checking for SpectraType constants")
print("="*60)

# Check SampleSet for type constants
for attr in dir(SampleSet):
    if not attr.startswith('_'):
        val = getattr(SampleSet, attr)
        if isinstance(val, int) and attr.isupper():
            print(f"{attr} = {val}")

# Try importing riid.data to look for enums
try:
    import riid.data
    print("\nChecking riid.data for SpectraType:")
    for attr in dir(riid.data):
        if 'type' in attr.lower() or 'state' in attr.lower():
            print(f"  {attr}: {getattr(riid.data, attr)}")
except:
    pass

# Check if there's a SpectraType or SpectraState enum
try:
    from riid.data.sampleset import SpectraType
    print("\nFound SpectraType enum:")
    for item in SpectraType:
        print(f"  {item.name} = {item.value}")
except ImportError:
    print("\nNo SpectraType enum found")

try:
    from riid.data.sampleset import SpectraState  
    print("\nFound SpectraState enum:")
    for item in SpectraState:
        print(f"  {item.name} = {item.value}")
except ImportError:
    print("\nNo SpectraState enum found")

# Manual test - try all combinations
print("\n" + "="*60)
print("Testing different spectra_type + spectra_state combinations")
print("="*60)

test_spectrum = np.random.poisson(5, 1024).astype(float)
test_df = pd.DataFrame({
    'live_time': [300.0],
    'total_counts': [test_spectrum.sum()],
    'counts': [test_spectrum],
    'Isotope': ['Cs137']  # Add label
})

for stype in range(0, 10):
    for sstate in range(0, 5):
        try:
            ss = SampleSet()
            ss.spectra = test_df.copy()
            
            # Try setting both
            try:
                ss.spectra_type = stype
            except:
                pass
            try:
                ss.spectra_state = sstate
            except:
                pass
                
            actual_type = ss.spectra_type
            actual_state = ss.spectra_state
            
            # Only print if we got the values we wanted
            if actual_type == stype and actual_state == sstate:
                print(f"type={stype}, state={sstate}: Created (actual: type={actual_type}, state={actual_state})")
        except Exception as e:
            pass
