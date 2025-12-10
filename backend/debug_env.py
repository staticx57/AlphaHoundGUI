import sys
import os

print(f"Python executable: {sys.executable}")
print(f"CWD: {os.getcwd()}")

try:
    import uvicorn
    print(f"Uvicorn version: {uvicorn.__version__}")
except ImportError:
    print("FATAL: uvicorn not found!")

try:
    from main import app
    print("Main app imported successfully.")
except Exception as e:
    print(f"FATAL: Could not import main app: {e}")
