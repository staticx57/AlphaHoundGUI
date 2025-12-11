"""
Test importing ml_analysis and see what the actual error is
"""
import sys
import traceback

print("Attempting to import ml_analysis module...")
print()

# Temporarily modify ml_analysis to show the actual import error
import importlib.util
spec = importlib.util.spec_from_file_location(
    "ml_analysis_test",
    r"c:\Users\stati\Desktop\Projects\AlphaHoundGUI\backend\ml_analysis.py"
)
module = importlib.util.module_from_spec(spec)

try:
    spec.loader.exec_module(module)
    print(f"HAS_RIID: {module.HAS_RIID}")
    
    if not module.HAS_RIID:
        print("\n⚠ Import failed during module load, but exception was caught")
        print("Let's try importing directly to see the actual error:")
        print()
        
        try:
            from riid.data.synthetic import SeedMixer, GrossCountSpectrum, get_dummy_seeds
            from riid.models import MLPClassifier
            print("✓ Direct import succeeded!")
            print("\nThis means the try/except block in ml_analysis.py is catching an error")
            print("that shouldn't prevent the import. Let's see what it is...")
        except Exception as e:
            print(f"✗ Direct import also failed: {e}")
            traceback.print_exc()
    else:
        print("✓ SUCCESS - HAS_RIID is True")
        
except Exception as e:
    print(f"✗ ERROR loading module: {e}")
    traceback.print_exc()
