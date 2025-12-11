"""
Debug script to check PyRIID import status
"""
import sys

print("Python Information:")
print(f"Version: {sys.version}")
print(f"Executable: {sys.executable}")
print()

print("Attempting to import PyRIID components...")
print()

try:
    print("1. Importing riid.data.synthetic...")
    from riid.data.synthetic import SeedMixer, GrossCountSpectrum, get_dummy_seeds
    print("   ✓ SUCCESS")
except ImportError as e:
    print(f"   ✗ FAILED: {e}")
except Exception as e:
    print(f"   ✗ ERROR: {e}")

try:
    print("2. Importing riid.models...")
    from riid.models import MLPClassifier
    print("   ✓ SUCCESS")
except ImportError as e:
    print(f"   ✗ FAILED: {e}")
except Exception as e:
    print(f"   ✗ ERROR: {e}")

print()
print("3. Testing ml_analysis module...")
try:
    from ml_analysis import get_ml_identifier, HAS_RIID
    print(f"   HAS_RIID = {HAS_RIID}")
    
    if HAS_RIID:
        ml = get_ml_identifier()
        print(f"   ML Identifier: {ml}")
        print("   ✓ ML module ready")
    else:
        print("   ⚠ HAS_RIID is False (import failed during module load)")
except Exception as e:
    print(f"   ✗ ERROR: {e}")

print()
print("4. Checking installed packages...")
import subprocess
result = subprocess.run(
    [sys.executable, "-m", "pip", "list"],
    capture_output=True,
    text=True
)
if "riid" in result.stdout.lower():
    print("   ✓ riid found in pip list")
    for line in result.stdout.split('\n'):
        if 'riid' in line.lower():
            print(f"   {line}")
else:
    print("   ✗ riid NOT found in pip list")
