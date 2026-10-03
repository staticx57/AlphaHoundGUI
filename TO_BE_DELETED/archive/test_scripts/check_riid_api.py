"""
Check what's actually available in riid.data.synthetic
"""
import riid.data.synthetic as synthetic

print("Available in riid.data.synthetic:")
print()
for item in dir(synthetic):
    if not item.startswith('_'):
        print(f"  - {item}")

print("\n" + "="*50)
print("\nChecking riid.models:")
import riid.models as models
for item in dir(models):
    if not item.startswith('_'):
        print(f"  - {item}")

print("\n" + "="*50)
print("\nTrying to find the correct imports...")

# Check if there's documentation or examples
try:
    import riid
    print(f"\nriid version: {riid.__version__}")
    print(f"riid path: {riid.__file__}")
except:
    pass
