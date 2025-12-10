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
        
        # If energies are missing, use channel numbers
        if not energies and len(counts) > 0:
            energies = list(range(len(counts)))

        # Detect peaks
        peaks = detect_peaks(energies, counts)
        
        # Identify isotopes
        isotopes = identify_isotopes(peaks) if peaks else []

        return {
            "counts": counts,
            "energies": energies,
            "peaks": peaks,
            "isotopes": isotopes,
            "metadata": {
                "live_time": spec.live_time,
                "real_time": spec.real_time,
                "filename": filename,
                "tool": "Becquerel"
            }
        }
    except Exception as e:
        raise ValueError(f"Error parsing CSV with Becquerel: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass
