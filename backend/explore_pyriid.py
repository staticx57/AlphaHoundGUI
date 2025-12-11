"""
Find out how to actually use Synthesizer and MLPClassifier in PyRIID 2.2.0
"""
from riid.data.synthetic import Synthesizer, get_dummy_seeds
from riid.models import MLPClassifier
import inspect

print("=" * 60)
print("Synthesizer methods:")
print("=" * 60)
for method in dir(Synthesizer):
    if not method.startswith('_'):
        print(f"  - {method}")

print("\n" + "=" * 60)
print("MLPClassifier.fit signature:")
print("=" * 60)
print(inspect.signature(MLPClassifier.fit))

print("\n" + "=" * 60)
print("MLPClassifier.predict signature:")
print("=" * 60)
print(inspect.signature(MLPClassifier.predict))

print("\n" + "=" * 60)
print("Trying a simple workflow:")
print("=" * 60)

# Try the simple approach
seeds = get_dummy_seeds()
print(f"Got {len(seeds)} dummy seeds")
print(f"Seeds type: {type(seeds)}")

# Check if get_dummy_seeds returns something we can use directly
print(f"\nFirst seed type: {type(seeds[0]) if seeds else 'empty'}")

# Try creating synthesizer and using it
synth = Synthesizer()
print(f"\nSynthesizer created")

# Check what attributes/methods it has
print(f"\nSynth attributes that don't start with _:")
for attr in dir(synth):
    if not attr.startswith('_'):
        obj = getattr(synth, attr)
        if callable(obj):
            print(f"  METHOD: {attr}{inspect.signature(obj)}")
        else:
            print(f"  ATTR: {attr} = {type(obj).__name__}")
