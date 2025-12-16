
"""
Verification script for 'curie' package.
Run this to check if the installation was successful.
"""
import sys

def verify_curie():
    print("Attempting to import curie...")
    try:
        import curie
        print(f"✅ SUCCESS: 'curie' package imported successfully.")
        print(f"Version: {getattr(curie, '__version__', 'unknown')}")
        
        # Try a simple calculation if possible
        # (This depends on the library's specific API, just testing import is usually enough)
        if hasattr(curie, 'Isotope'):
            i = curie.Isotope('U-238')
            print(f"✅ Functionality Test: Created Isotope object for {i.name}")
            
    except ImportError:
        print("❌ FAILURE: Could not import 'curie'.")
        print("Please check your installation (pip list) or try re-installing.")
        print(f"Python Executable: {sys.executable}")
    except Exception as e:
        print(f"⚠️ WARNING: Import worked but usage failed: {e}")

if __name__ == "__main__":
    verify_curie()
