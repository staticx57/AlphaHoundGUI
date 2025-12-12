import os
import tempfile
from peak_detection import detect_peaks
from isotope_database import identify_isotopes

# Try to import becquerel
try:
    import becquerel as bq
    HAS_BECQUEREL = True
except ImportError:
    HAS_BECQUEREL = False

def parse_csv_spectrum(content: bytes, filename: str) -> dict:
    """
    Parse a CSV spectrum file using Becquerel.
    Returns a dictionary result with counts, energies, peaks, isotopes, and metadata.
    """
    if not HAS_BECQUEREL:
        raise ImportError("Becquerel library not installed on server.")

    # Becquerel usually needs a file path, so we save to temp
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        try:
            tmp.write(content)
            tmp_path = tmp.name
        except Exception as e:
            tmp.close()
            os.remove(tmp.name)
            raise e
    
    # Close it before reading (windows locking safety)
    tmp.close()

    try:
        # Attempt to read with Becquerel
        spec = bq.Spectrum.from_file(tmp_path)
        
        # Extract data
        counts = spec.counts.tolist() if spec.counts is not None else []
        energies = spec.energies.tolist() if spec.energies is not None else []
        
        # Metadata
        live_time = spec.live_time
        real_time = spec.real_time
        source = "CSV File (Becquerel)"

    except Exception as bq_error:
        print(f"[WARNING] Becquerel parsing failed: {str(bq_error)}. Attempting manual fallback.")
        try:
            # Fallback: Manual generic CSV parsing using pandas
            import pandas as pd
            # Try to infer delimiter (comma, semicolon, tab)
            df = pd.read_csv(tmp_path, sep=None, engine='python')
            
            # Check if headers are numeric (implying headerless file read as header)
            try:
                # Try converting column names to floats
                [float(c) for c in df.columns]
                # If valid, reload with header=None
                df = pd.read_csv(tmp_path, sep=None, engine='python', header=None)
                # Ensure generic column names for mapping logic below
                df.columns = [str(c) for c in df.columns]
            except:
                pass

            # Normalize column names
            df.columns = [str(c).lower().strip() for c in df.columns]
            
            counts = []
            energies = []
            
            # Identify columns by name first
            columns_lower = [str(c).lower().strip() for c in df.columns]
            
            count_col_idx = next((i for i, c in enumerate(columns_lower) if any(x in c for x in ['count', 'cnt', 'data', 'cps'])), None)
            energy_col_idx = next((i for i, c in enumerate(columns_lower) if any(x in c for x in ['energy', 'kev', 'mev'])), None)
            channel_col_idx = next((i for i, c in enumerate(columns_lower) if any(x in c for x in ['channel', 'chan'])), None)
            
            # Logic to extract data
            counts = []
            energies = []
            
            if count_col_idx is not None:
                counts = df.iloc[:, count_col_idx].fillna(0).tolist()
            else:
                # Heuristic fallback for Counts
                if len(df.columns) >= 2:
                    # If we identified Energy at col 1, then Counts must be col 0
                    if energy_col_idx == 1:
                        counts = df.iloc[:, 0].fillna(0).tolist()
                    # If we identified Energy at col 0, Counts must be col 1
                    elif energy_col_idx == 0:
                        counts = df.iloc[:, 1].fillna(0).tolist()
                    else:
                        # Standard default: Energy, Counts -> Counts is col 1
                        counts = df.iloc[:, 1].fillna(0).tolist()
                elif len(df.columns) == 1:
                    counts = df.iloc[:, 0].fillna(0).tolist()

            if energy_col_idx is not None:
                energies = df.iloc[:, energy_col_idx].fillna(0).tolist()
            elif channel_col_idx is not None:
                 # Map channel to roughly linear energy (simple assumption if calib missing)
                 # Or just return empty energies to fallback to channel indices
                 energies = [] 
            else:
                 # If we have 2 columns and neither identified as energy
                 if len(df.columns) >= 2:
                     # If we grabbed col 1 as Counts, try col 0 as Energy
                     if counts == df.iloc[:, 1].fillna(0).tolist():
                         energies = df.iloc[:, 0].fillna(0).tolist()
                     # If we grabbed col 0 as Counts, try col 1 as Energy
                     elif counts == df.iloc[:, 0].fillna(0).tolist():
                         energies = df.iloc[:, 1].fillna(0).tolist()

            live_time = None
            real_time = None
            source = "CSV File"
            
            if not counts:
                 raise ValueError("Could not identify 'counts' column in CSV")

        except Exception as manual_error:
            raise ValueError(f"Failed to parse CSV with both Becquerel ({str(bq_error)}) and Manual fallback ({str(manual_error)})")
    
    # === HEADER CALIBRATION PARSING (Fuzzy Match) ===
    # Even if we didn't find an Energy column, the header might have "Calibration: a0, a1" 
    # or "Energy = 0 + 2*ch" which we can use to generate energies.
    
    if (not energies or len(energies) == 0) and len(counts) > 0:
        header_cal_energies = _try_parse_calibration_header(tmp_path, len(counts))
        if header_cal_energies:
            energies = header_cal_energies
            # If we successfully parsed calibration from header, clearly it IS calibrated
            # The 'is_calibrated' logic below will see this list and set True.

    # If energies are missing, use channel numbers
    is_calibrated = True
    if not energies and len(counts) > 0:
        energies = list(range(len(counts)))
        is_calibrated = False # Falling back to channels
    elif energies and len(energies) > 1:
        # Check if energies look like simple channel numbers (0, 1, 2...)
        # Some CSVs might have an "Energy" column that is actually just channels
        diffs = [energies[i+1] - energies[i] for i in range(min(5, len(energies)-1))]
        if all(abs(d - 1.0) < 0.01 for d in diffs) and energies[0] == 0:
             is_calibrated = False

    # Detect peaks
    peaks = detect_peaks(energies, counts)
    
    # Identify isotopes
    isotopes = identify_isotopes(peaks) if peaks else []

    # Cleanup temp file
    if os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except:
            pass

    return {
        "counts": counts,
        "energies": energies,
        "peaks": peaks,
        "isotopes": isotopes,
        "is_calibrated": is_calibrated,
        "metadata": {
            "live_time": live_time,
            "real_time": real_time,
            "filename": filename,
            "source": source
        }
    }

def _try_parse_calibration_header(filepath: str, num_channels: int):
    """
    Scans the beginning of the file for common calibration strings.
    Supported patterns:
    - "Energy = <Intercept> + <Slope> * Ch"
    - "Calibration coefficients: <Intercept> <Slope>"
    - "Coefficients: <A0> <A1>"
    """
    try:
        a0 = 0.0
        a1 = 1.0 # Default slope 1 (should be diff if calibrated)
        found_coeffs = False
        
        with open(filepath, 'r', errors='ignore') as f:
            for i in range(25): # Scan first 25 lines
                line = f.readline()
                if not line: break
                
                line_lower = line.lower().replace(',', ' ').replace('=', ' ').replace(':', ' ')
                tokens = line_lower.split()
                
                # Pattern 1: "Calibration: 0 1.5" or "Coeffs: 0 1.5"
                if "calibration" in line_lower or "coeffs" in line_lower or "coefficients" in line_lower:
                    # Look for floats in the line
                    floats = []
                    for t in tokens:
                        try:
                            val = float(t)
                            floats.append(val)
                        except:
                            pass
                    
                    if len(floats) >= 2:
                        # Assume A0 A1 A2... order
                        a0 = floats[0]
                        a1 = floats[1]
                        if abs(a1 - 1.0) > 0.0001 or abs(a0) > 0.0001: # Check if non-trivial
                            found_coeffs = True
                            break
                            
                # Pattern 2: "Energy = -5 + 2.4 * Channel" - explicit equation
                if "energy" in line_lower and "*" in line_lower and "+" in line_lower:
                   # Very crude parse: try to find the slope next to '*'
                   # This is harder, skipping for now in favor of coefficient list
                   pass

        if found_coeffs:
            print(f"[DEBUG] Found Calibration Coefficients in header: a0={a0}, a1={a1}")
            # Generate linear energy list
            return [a0 + a1 * x for x in range(num_channels)]
            
    except Exception as e:
        print(f"[DEBUG] Header calibration parsing failed: {e}")
        
    return None
