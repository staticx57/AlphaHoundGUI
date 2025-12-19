"""Parser for IAEA LiveChart API gamma radiation data.

Parses CSV files downloaded from IAEA NDS to extract gamma energies and intensities
for use in both peak matching and ML training.
"""
import os
import csv
from typing import Dict, List, Tuple, Optional

# Directory containing downloaded IAEA data
IAEA_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data', 'idb', 'isotopes')


def parse_iaea_csv(filepath: str, min_intensity: float = 0.01, min_energy: float = 20.0) -> Dict:
    """Parse an IAEA gamma radiation CSV file.
    
    Args:
        filepath: Path to the CSV file
        min_intensity: Minimum intensity threshold (%) to include
        min_energy: Minimum energy threshold (keV) - filters out X-ray lines
        
    Returns:
        Dict with 'gammas' list of (energy, intensity) tuples,
        'half_life' string, and 'isotope' name
    """
    gammas = []
    half_life = None
    isotope = None
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                # Extract energy and intensity
                try:
                    energy = float(row.get('energy', 0))
                    intensity_str = row.get('intensity', '')
                    
                    # Skip if no intensity data
                    if not intensity_str or intensity_str.strip() == '':
                        continue
                    
                    intensity = float(intensity_str)
                    
                    # Filter by minimum intensity
                    if intensity < min_intensity:
                        continue
                    
                    # Filter by minimum energy - excludes X-ray fluorescence lines
                    # that cause false positive matches (e.g., Co-60's 7-18 keV X-rays)
                    if energy < min_energy:
                        continue
                    
                    # Extract half-life (same for all rows of an isotope)
                    if half_life is None:
                        hl = row.get('half_life', '')
                        unit = row.get('unit_hl', '')
                        if hl and unit:
                            half_life = f"{hl} {unit}"
                    
                    # Extract isotope name (p_symbol = parent symbol, p_z = proton number)
                    if isotope is None:
                        symbol = row.get('p_symbol', '')
                        # The atomic mass can be derived from p_z + p_n
                        p_z = row.get('p_z', '')
                        p_n = row.get('p_n', '')
                        if symbol and p_z and p_n:
                            mass = int(p_z) + int(p_n)
                            isotope = f"{symbol}-{mass}"
                    
                    gammas.append((energy, intensity))
                    
                except (ValueError, TypeError):
                    continue
        
        # Sort by intensity (strongest first)
        gammas.sort(key=lambda x: -x[1])
        
    except Exception as e:
        print(f"[IAEA Parser] Error parsing {filepath}: {e}")
        return None
    
    return {
        'gammas': gammas,
        'half_life': half_life,
        'isotope': isotope,
        'source': 'IAEA NDS'
    }


def get_top_gammas(filepath: str, top_n: int = 10, min_intensity: float = 0.1) -> List[Tuple[float, float]]:
    """Get top N gamma lines by intensity from an IAEA CSV file.
    
    Args:
        filepath: Path to the CSV file
        top_n: Number of top gamma lines to return
        min_intensity: Minimum intensity threshold
        
    Returns:
        List of (energy, intensity) tuples, sorted by intensity
    """
    result = parse_iaea_csv(filepath, min_intensity)
    if result is None:
        return []
    return result['gammas'][:top_n]


def load_all_isotopes(min_intensity: float = 0.5, top_n: int = 15) -> Dict[str, Dict]:
    """Load all downloaded IAEA isotope data.
    
    Args:
        min_intensity: Minimum intensity threshold for gamma lines
        top_n: Maximum number of gamma lines per isotope
        
    Returns:
        Dict mapping isotope name to gamma data
    """
    isotopes = {}
    
    if not os.path.exists(IAEA_DATA_DIR):
        print(f"[IAEA Parser] Data directory not found: {IAEA_DATA_DIR}")
        return isotopes
    
    for filename in os.listdir(IAEA_DATA_DIR):
        if not filename.endswith('_gammas.csv'):
            continue
        
        # Extract isotope name from filename (e.g., "bi214_gammas.csv" -> "bi214")
        isotope_key = filename.replace('_gammas.csv', '')
        
        filepath = os.path.join(IAEA_DATA_DIR, filename)
        result = parse_iaea_csv(filepath, min_intensity)
        
        if result and result['gammas']:
            # Format isotope name properly (e.g., "bi214" -> "Bi-214")
            if result['isotope']:
                proper_name = result['isotope']
            else:
                # Fallback: parse from filename
                element = isotope_key.rstrip('0123456789').capitalize()
                mass = isotope_key[len(element.lower()):]
                proper_name = f"{element}-{mass}"
            
            # Keep only top N gammas
            result['gammas'] = result['gammas'][:top_n]
            isotopes[proper_name] = result
    
    print(f"[IAEA Parser] Loaded {len(isotopes)} isotopes from IAEA data")
    return isotopes


def get_isotope_gammas(isotope_name: str, min_intensity: float = 0.5) -> List[Tuple[float, float]]:
    """Get gamma lines for a specific isotope.
    
    Args:
        isotope_name: Isotope name (e.g., "Bi-214", "Cs-137")
        min_intensity: Minimum intensity threshold
        
    Returns:
        List of (energy, intensity) tuples
    """
    # Normalize isotope name to filename format
    normalized = isotope_name.lower().replace('-', '')
    filename = f"{normalized}_gammas.csv"
    filepath = os.path.join(IAEA_DATA_DIR, filename)
    
    if not os.path.exists(filepath):
        return []
    
    return get_top_gammas(filepath, top_n=15, min_intensity=min_intensity)


# Quick test
if __name__ == "__main__":
    print("Testing IAEA Parser...")
    
    # Test single isotope
    bi214_gammas = get_isotope_gammas("Bi-214")
    print(f"\nBi-214 top gamma lines ({len(bi214_gammas)} found):")
    for energy, intensity in bi214_gammas[:5]:
        print(f"  {energy:.1f} keV - {intensity:.2f}%")
    
    # Test loading all isotopes
    all_isotopes = load_all_isotopes()
    print(f"\nLoaded {len(all_isotopes)} isotopes from IAEA data")
    
    # Show sample
    for name, data in list(all_isotopes.items())[:5]:
        n_gammas = len(data['gammas'])
        top_energy = data['gammas'][0][0] if data['gammas'] else 0
        top_intensity = data['gammas'][0][1] if data['gammas'] else 0
        print(f"  {name}: {n_gammas} gammas, strongest {top_energy:.1f} keV @ {top_intensity:.2f}%")
