"""
Use Synthesizer properly to generate trainable data
"""
from riid.data.synthetic import get_dummy_seeds, Synthesizer
from riid.data.sampleset import SampleSet
from riid.models import MLPClassifier

print("="*60)
print("Step 1: Get seeds for synthesizer")
print("="*60)

seeds = get_dummy_seeds()
print(f"Seeds: type={seeds.spectra_type}, state={seeds.spectra_state}")
print(f"Seeds n_samples: {seeds.n_samples}")

print("\n" + "="*60)
print("Step 2: Create Synthesizer and generate training data")
print("="*60)

syn = Synthesizer(
    bg_cps=300,
    long_bg_live_time=120,
    apply_poisson_noise=True,
    return_fg=True,  # Return foreground (net) spectra
    return_gross=False  # Don't return gross
)

print(f"Synthesizer created")
print(f"  return_fg: {syn.return_fg}")
print(f"  return_gross: {syn.return_gross}")

# Generate synthetic training data from seeds
print("\nGenerating synthetic spectra...")
try:
    # Check if synthesize method exists
    if hasattr(syn, 'synthesize'):
        print("Using syn.synthesize()")
        training_ss = syn.synthesize(seeds, n_samples=50)
    elif hasattr(seeds, 'generate'):
        print("Using seeds.generate() with synthesizer")
        training_ss = seeds.generate(syn, n_samples=50)
    else:
        # Try calling synthesizer
        print("Trying syn(seeds)")
        training_ss = syn(seeds, n_samples=50)
        
    print(f"Generated training data:")
    print(f"  type={training_ss.spectra_type}, state={training_ss.spectra_state}")
    print(f"  n_samples: {training_ss.n_samples}")
    print(f"  n_channels: {training_ss.n_channels}")
    
except Exception as e:
    print(f"✗ Generation failed: {e}")
    import traceback
    traceback.print_exc()
    
    # Try a different approach - look for methods
    print("\nAvailable methods on Synthesizer:")
    for method in dir(syn):
        if not method.startswith('_') and callable(getattr(syn, method)):
            print(f"  - {method}")
    
    print("\nAvailable methods on SampleSet:")
    for method in dir(seeds):
        if not method.startswith('_') and callable(getattr(seeds, method)) and 'syn' in method.lower():
            print(f"  - {method}")
