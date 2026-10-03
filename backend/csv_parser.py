import csv
import io
import os
import tempfile

# Try to import becquerel
try:
    import becquerel as bq
    HAS_BECQUEREL = True
except ImportError:
    HAS_BECQUEREL = False

import logging
logger = logging.getLogger(__name__)


def _split_comment_metadata(content: bytes):
    """Remove leading/inline '#' lines; return (content_without_comments, {key: float})."""
    text = content.decode("utf-8", errors="replace")
    meta, kept = {}, []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            parts = [p.strip() for p in stripped.lstrip("#").split(",", 1)]
            if len(parts) == 2:
                try:
                    meta[parts[0].lower()] = float(parts[1])
                except ValueError:
                    pass
            continue
        kept.append(line)
    if not meta and len(kept) == len(text.splitlines()):
        return content, meta  # nothing stripped: leave bytes untouched
    return ("\n".join(kept) + "\n").encode("utf-8"), meta


def _numeric_list(values, what):
    """Values as numbers; text where numbers belong means this is not a spectrum (ValueError, a client error)."""
    out = []
    for v in values:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            f = v
        else:
            try:
                f = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"The {what} column contains text that is not a number (for example {str(v)[:20]!r}). "
                                 "A spectrum CSV needs numeric counts (and optionally energies).")
        if f != f or f in (float("inf"), float("-inf")):
            raise ValueError(f"The {what} column contains a value that is not a finite number.")
        out.append(f)
    return out


_CALIBRATION_WORDS = ("calibration", "coeffs", "coefficients")


def _table_text(tmp_path: str) -> str:
    """
    The file's text without calibration lines in its first 25 lines ("Calibration: 2.0 3.1"): they are not part of the
    table (_try_parse_calibration_header reads them from the file), and as the first line they would be taken for the header.
    """
    with open(tmp_path, "r", encoding="utf-8-sig") as f:   # strict UTF-8, as pandas reads it; also drops an Excel BOM
        lines = f.read().splitlines()
    kept = [l for i, l in enumerate(lines) if not (i < 25 and any(w in l.lower() for w in _CALIBRATION_WORDS))]
    return "\n".join(kept) + "\n"


def _delimiter(text: str) -> str:
    """Comma, semicolon, tab or space. Letting pandas guess among all characters splits a one-column file on a letter."""
    try:
        return csv.Sniffer().sniff("\n".join(text.splitlines()[:50]), delimiters=",;\t ").delimiter
    except csv.Error:
        return ","


def _manual_columns(tmp_path: str):
    """
    Fallback when Becquerel cannot read the file: find the counts and energy columns with pandas (delimiter inferred,
    columns identified by name, then by position). Returns (counts, energies); energies may be empty.
    """
    import pandas as pd
    text = _table_text(tmp_path)
    sep = _delimiter(text)
    df = pd.read_csv(io.StringIO(text), sep=sep, engine='python')

    # Numeric column names mean a headerless file that was read with its first row as the header
    try:
        [float(c) for c in df.columns]
        df = pd.read_csv(io.StringIO(text), sep=sep, engine='python', header=None)
        df.columns = [str(c) for c in df.columns]
    except ValueError:  # pandas ParserError and EmptyDataError subclass ValueError
        pass

    df.columns = [str(c).lower().strip() for c in df.columns]
    columns_lower = list(df.columns)

    count_col_idx = next((i for i, c in enumerate(columns_lower) if any(x in c for x in ['count', 'cnt', 'data', 'cps'])), None)
    energy_col_idx = next((i for i, c in enumerate(columns_lower) if any(x in c for x in ['energy', 'kev', 'mev'])), None)
    channel_col_idx = next((i for i, c in enumerate(columns_lower) if any(x in c for x in ['channel', 'chan'])), None)

    counts = []
    energies = []

    if count_col_idx is not None:
        counts = df.iloc[:, count_col_idx].fillna(0).tolist()
    elif len(df.columns) >= 2:
        # Energy in column 1 means counts are column 0; otherwise the usual layout is (energy, counts)
        if energy_col_idx == 1:
            counts = df.iloc[:, 0].fillna(0).tolist()
        else:
            counts = df.iloc[:, 1].fillna(0).tolist()
    elif len(df.columns) == 1:
        counts = df.iloc[:, 0].fillna(0).tolist()

    if energy_col_idx is not None:
        energies = df.iloc[:, energy_col_idx].fillna(0).tolist()
    elif channel_col_idx is not None:
        energies = []   # channel numbers only: the caller falls back to channel indices
    elif len(df.columns) >= 2:
        # No energy column by name: the other one of the first two columns is the energy
        if counts == df.iloc[:, 1].fillna(0).tolist():
            energies = df.iloc[:, 0].fillna(0).tolist()
        elif counts == df.iloc[:, 0].fillna(0).tolist():
            energies = df.iloc[:, 1].fillna(0).tolist()

    if not counts:
        raise ValueError("Could not identify 'counts' column in CSV")
    return counts, energies


def _resolve_energies(energies: list, counts: list, tmp_path: str, comment_meta: dict):
    """
    The energy axis to report and whether it is a real calibration: the file's own energy column, else a calibration
    written in the header or in '# calib_a0..a2' comment metadata, else channel numbers (uncalibrated).
    """
    # Even without an energy column the header may say "Calibration: a0, a1" (or "Energy = 0 + 2*ch")
    if not energies:
        header_cal_energies = _try_parse_calibration_header(tmp_path, len(counts))
        if header_cal_energies:
            energies = header_cal_energies

    # Calibration coefficients from '# calib_a0..a2' metadata, if no energy column was found
    if not energies and comment_meta.get("calib_a1"):
        a0, a1, a2 = (comment_meta.get(k, 0.0) for k in ("calib_a0", "calib_a1", "calib_a2"))
        energies = [a0 + a1 * ch + a2 * ch * ch for ch in range(len(counts))]

    is_calibrated = True
    if not energies:
        energies = list(range(len(counts)))
        is_calibrated = False   # falling back to channels
    elif len(energies) > 1:
        # An "Energy" column that is really channel numbers (0, 1, 2, ...) is not a calibration
        diffs = [energies[i + 1] - energies[i] for i in range(min(5, len(energies) - 1))]
        if all(abs(d - 1.0) < 0.01 for d in diffs) and energies[0] == 0:
            is_calibrated = False
    return energies, is_calibrated


def parse_csv_spectrum(content: bytes, filename: str) -> dict:
    """
    Parse a CSV spectrum file using Becquerel, with a pandas fallback.
    Returns a dictionary result with counts, energies, peaks, isotopes, and metadata.
    """
    if not HAS_BECQUEREL:
        raise ImportError("Becquerel library not installed on server.")

    # Some exporters (e.g. RadiaCode tools) prefix '# key,value' metadata lines; strip them
    # so the tabular parser sees only the header + data, but keep what they tell us.
    content, comment_meta = _split_comment_metadata(content)

    # Becquerel needs a file path, so the content goes to a temp file, removed whatever happens next
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp_path = tmp.name
        try:
            tmp.write(content)
        except Exception:
            tmp.close()
            os.remove(tmp_path)
            raise
    try:
        return _parse_csv_file(tmp_path, filename, comment_meta)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _parse_csv_file(tmp_path: str, filename: str, comment_meta: dict) -> dict:
    try:
        spec = bq.Spectrum.from_file(tmp_path)
        counts = spec.counts.tolist() if spec.counts is not None else []
        energies = spec.energies.tolist() if spec.energies is not None else []
        live_time = spec.live_time
        real_time = spec.real_time
        source = "CSV File (Becquerel)"
    except Exception as bq_error:
        logger.error(f"[WARNING] Becquerel parsing failed: {str(bq_error)}. Attempting manual fallback.")
        try:
            counts, energies = _manual_columns(tmp_path)
        except Exception as manual_error:
            raise ValueError(f"Failed to parse CSV with both Becquerel ({str(bq_error)}) and Manual fallback ({str(manual_error)})")
        live_time = None
        real_time = None
        source = "CSV File"

    counts = _numeric_list(counts, "counts")
    energies = _numeric_list(energies, "energy") if energies else energies
    if not counts:
        raise ValueError("No spectrum data found in the CSV")

    energies, is_calibrated = _resolve_energies(energies, counts, tmp_path, comment_meta)
    if live_time is None and comment_meta.get("duration_s"):
        live_time = comment_meta["duration_s"]

    return {
        "counts": counts,
        "energies": energies,
        "peaks": [],  # filled by analyze_spectrum_peaks()
        "isotopes": [],
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
                        except ValueError:
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
            logger.debug(f"[DEBUG] Found Calibration Coefficients in header: a0={a0}, a1={a1}")
            # Generate linear energy list
            return [a0 + a1 * x for x in range(num_channels)]
            
    except Exception as e:
        logger.debug(f"[DEBUG] Header calibration parsing failed: {e}")
        
    return None
