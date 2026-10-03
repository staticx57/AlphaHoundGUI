import sys
import os
import pytest
from n42_parser import parse_n42

# Add parent directory to path to import backend modules if needed, 
# although pytest usually handles this if run from the right place.

def test_parse_n42_valid_file():
    # Read the actual test.n42 file from the desktop
    n42_path = r"c:\Users\user\Desktop\N42 viewer\test.n42"
    with open(n42_path, 'r') as f:
        content = f.read()
    
    result = parse_n42(content)
    
    assert "error" not in result, f"Parser returned error: {result.get('error')}"
    assert "counts" in result
    assert "energies" in result
    assert "metadata" in result
    
    counts = result['counts']
    energies = result['energies']
    
    assert len(counts) > 0
    # Check for a known value from the file inspection
    # ChannelData... 0 0 0 0 1 2 ...
    assert counts[4] == 1
    
    # Check energies
    # 15.00000 16.68000 ...
    assert len(energies) > 0
    assert energies[0] == 15.0
    
    # Check live time
    assert result['metadata']['live_time'] == '1.0'

if __name__ == "__main__":
    # Allow running directly with python
    test_parse_n42_valid_file()
    print("Test passed!")
