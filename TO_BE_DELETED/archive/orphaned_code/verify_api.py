import requests
import time
import subprocess
import sys
import os

# Server assumed to be running externally
print("Verifying API against running server...")
# proc = subprocess.Popen(...) # Handled by agent tool

time.sleep(2) # Short wait just in case

try:
    print("Testing N42 Upload...")
    n42_path = r"..\test.n42"
    with open(n42_path, 'rb') as f:
        files = {'file': ('test.n42', f, 'application/xml')}
        response = requests.post("http://127.0.0.1:8080/upload", files=files)
        
    if response.status_code == 200:
        data = response.json()
        print("Success! N42 Parsed.")
        print(f"Metadata: {data.get('metadata')}")
        print(f"Counts length: {len(data.get('counts'))}")
    else:
        print(f"Failed: {response.status_code} - {response.text}")

except requests.exceptions.ConnectionError:
    print("Connection refused. Server logs:")
    # Capture output
    try:
        outs, errs = proc.communicate(timeout=2)
        print(f"STDOUT: {outs.decode()}")
        print(f"STDERR: {errs.decode()}")
    except:
        print("Could not retrieve logs (process might be active).")


except Exception as e:
    print(f"Error: {e}")

finally:
    print("Killing server...")
    proc.terminate()
