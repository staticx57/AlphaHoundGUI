"""Download gamma radiation data from IAEA LiveChart API for priority isotopes."""
import urllib.request
import os
import time

# IAEA LiveChart API base URL
BASE_URL = "https://www-nds.iaea.org/relnsd/v1/data"

# Priority isotopes for AlphaHound training
PRIORITY_ISOTOPES = [
    # U-238 decay chain
    "u238", "th234", "pa234m", "u234", "th230", "ra226", "rn222", "po218", 
    "pb214", "bi214", "po214", "pb210", "bi210", "po210",
    # Th-232 decay chain
    "th232", "ra228", "ac228", "th228", "ra224", "rn220", "po216", 
    "pb212", "bi212", "po212", "tl208",
    # U-235 decay chain
    "u235", "th231", "pa231", "ac227", "th227", "ra223", "rn219",
    # Common calibration sources
    "cs137", "co60", "am241", "ba133", "na22", "co57", "eu152",
    # Natural background
    "k40",
    # Medical isotopes
    "i131", "tc99m", "f18", "tl201", "in111", "ga67",
    # Industrial
    "ir192", "se75", "yb169",
]

# Output directory
OUTPUT_DIR = "backend/data/idb/isotopes"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def download_gamma_data(isotope):
    """Download gamma radiation data for a single isotope."""
    # API endpoint for gamma decay radiations
    url = f"{BASE_URL}?fields=decay_rads&nuclides={isotope}&rad_types=g"
    
    # Add user agent header
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode('utf-8')
            
            # Save to file
            output_file = os.path.join(OUTPUT_DIR, f"{isotope}_gammas.csv")
            with open(output_file, 'w') as f:
                f.write(content)
            
            # Count lines (excluding header)
            lines = len([l for l in content.strip().split('\n') if l and not l.startswith('energy')])
            return lines
    except Exception as e:
        return f"ERROR: {e}"

# Download all isotopes
print("="*60)
print("DOWNLOADING IAEA GAMMA DATA")
print("="*60)

success_count = 0
total_gammas = 0

for isotope in PRIORITY_ISOTOPES:
    result = download_gamma_data(isotope)
    if isinstance(result, int):
        print(f"  {isotope:10} - {result:4} gamma lines")
        success_count += 1
        total_gammas += result
    else:
        print(f"  {isotope:10} - {result}")
    
    # Rate limiting - be nice to IAEA servers
    time.sleep(0.5)

print("="*60)
print(f"SUCCESS: {success_count}/{len(PRIORITY_ISOTOPES)} isotopes downloaded")
print(f"TOTAL: {total_gammas} gamma lines")
print(f"OUTPUT: {OUTPUT_DIR}/")
