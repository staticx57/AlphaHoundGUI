"""
CHN/SPE File Parsers

Parsers for Ortec CHN and Maestro SPE spectrum file formats.
These are common formats from commercial MCA (Multi-Channel Analyzer) systems.
"""

import struct
import os
from datetime import datetime


def parse_chn_file(filepath):
    """
    Parse Ortec CHN binary spectrum file format.
    
    CHN files contain:
    - 32-byte header with metadata
    - Spectrum data as 32-bit integers
    - Optional 256-byte trailer with calibration
    
    Args:
        filepath: Path to .chn file
        
    Returns:
        dict with counts, metadata, and calibration info
    """
    with open(filepath, 'rb') as f:
        data = f.read()
    
    if len(data) < 32:
        raise ValueError("File too small to be a valid CHN file")
    
    # Parse 32-byte header
    # Byte 0-1: Format indicator (-1 = Ortec format)
    # Byte 2-3: MCA number
    # Byte 4-5: Segment number
    # Byte 6-7: Start seconds (ASCII)
    # Byte 8-11: Real time (20ms units)
    # Byte 12-15: Live time (20ms units)
    # Byte 16-23: Start date/time string
    # Byte 24-27: Channel offset
    # Byte 28-31: Number of channels
    
    format_id = struct.unpack('<h', data[0:2])[0]
    mca_num = struct.unpack('<h', data[2:4])[0]
    segment = struct.unpack('<h', data[4:6])[0]
    
    # Real and live time in 20ms units
    real_time_raw = struct.unpack('<I', data[8:12])[0]
    live_time_raw = struct.unpack('<I', data[12:16])[0]
    real_time = real_time_raw * 0.02  # Convert to seconds
    live_time = live_time_raw * 0.02
    
    # Date/time string (8 bytes)
    date_str = data[16:24].decode('ascii', errors='ignore').strip()
    
    # Channel info
    channel_offset = struct.unpack('<I', data[24:28])[0]
    num_channels = struct.unpack('<I', data[28:32])[0]
    
    # Parse spectrum data (32-bit integers)
    spectrum_start = 32
    spectrum_end = spectrum_start + num_channels * 4
    
    if len(data) < spectrum_end:
        raise ValueError(f"File truncated: expected {spectrum_end} bytes, got {len(data)}")
    
    counts = []
    for i in range(num_channels):
        offset = spectrum_start + i * 4
        count = struct.unpack('<I', data[offset:offset+4])[0]
        counts.append(count)
    
    # Try to parse calibration from trailer (if present)
    calibration = None
    trailer_start = spectrum_end
    if len(data) >= trailer_start + 256:
        # Calibration coefficients are at offset 0 and 4 in trailer
        try:
            cal_a = struct.unpack('<f', data[trailer_start:trailer_start+4])[0]
            cal_b = struct.unpack('<f', data[trailer_start+4:trailer_start+8])[0]
            cal_c = struct.unpack('<f', data[trailer_start+8:trailer_start+12])[0]
            
            if abs(cal_b) > 0.001:  # Sanity check
                calibration = {
                    'a': cal_a,  # offset
                    'b': cal_b,  # keV/channel
                    'c': cal_c   # quadratic term
                }
        except:
            pass
    
    # Generate energies if calibrated
    energies = list(range(num_channels))
    if calibration:
        energies = [calibration['a'] + calibration['b'] * i + calibration['c'] * i**2 
                   for i in range(num_channels)]
    
    return {
        'counts': counts,
        'energies': energies,
        'num_channels': num_channels,
        'live_time': live_time,
        'real_time': real_time,
        'calibration': calibration,
        'metadata': {
            'format': 'CHN (Ortec)',
            'mca_number': mca_num,
            'segment': segment,
            'date_string': date_str,
            'channel_offset': channel_offset
        }
    }


def parse_spe_file(filepath):
    """
    Parse Maestro SPE ASCII spectrum file format.
    
    SPE files are text-based with sections:
    - $SPEC_ID: Spectrum identifier
    - $DATE_MEA: Measurement date
    - $MEAS_TIM: Live and real time
    - $DATA: Channel data start/end and counts
    - $MCA_CAL: Energy calibration coefficients
    
    Args:
        filepath: Path to .spe file
        
    Returns:
        dict with counts, metadata, and calibration info
    """
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    counts = []
    live_time = 0
    real_time = 0
    calibration = None
    spec_id = ""
    date_mea = ""
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if line == '$SPEC_ID:':
            i += 1
            if i < len(lines):
                spec_id = lines[i].strip()
        
        elif line == '$DATE_MEA:':
            i += 1
            if i < len(lines):
                date_mea = lines[i].strip()
        
        elif line == '$MEAS_TIM:':
            i += 1
            if i < len(lines):
                parts = lines[i].strip().split()
                if len(parts) >= 2:
                    live_time = float(parts[0])
                    real_time = float(parts[1])
        
        elif line == '$DATA:':
            i += 1
            if i < len(lines):
                # First line is "start_channel end_channel"
                parts = lines[i].strip().split()
                start_ch = int(parts[0])
                end_ch = int(parts[1])
                
                # Following lines are channel counts
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('$'):
                    val = lines[i].strip()
                    if val:
                        counts.append(int(val))
                    i += 1
                continue  # Don't increment i again
        
        elif line == '$MCA_CAL:':
            i += 1
            if i < len(lines):
                # First line is number of coefficients
                num_coeffs = int(lines[i].strip())
                i += 1
                if i < len(lines):
                    # Second line is coefficients
                    coeffs = [float(x) for x in lines[i].strip().split()]
                    if len(coeffs) >= 2:
                        calibration = {
                            'a': coeffs[0],  # offset
                            'b': coeffs[1],  # keV/channel
                            'c': coeffs[2] if len(coeffs) > 2 else 0.0
                        }
        
        i += 1
    
    num_channels = len(counts)
    
    # Generate energies if calibrated
    energies = list(range(num_channels))
    if calibration:
        energies = [calibration['a'] + calibration['b'] * i + calibration['c'] * i**2 
                   for i in range(num_channels)]
    
    return {
        'counts': counts,
        'energies': energies,
        'num_channels': num_channels,
        'live_time': live_time,
        'real_time': real_time,
        'calibration': calibration,
        'metadata': {
            'format': 'SPE (Maestro)',
            'spec_id': spec_id,
            'date': date_mea
        }
    }


def parse_spectrum_file(filepath):
    """
    Auto-detect file type and parse spectrum.
    
    Native support: .chn, .spe
    Extended support via SandiaSpecUtils: 100+ additional formats
    """
    ext = os.path.splitext(filepath)[1].lower()
    
    # Native parsers for common formats
    if ext == '.chn':
        return parse_chn_file(filepath)
    elif ext == '.spe':
        return parse_spe_file(filepath)
    else:
        # Try SandiaSpecUtils for 100+ other formats
        try:
            from specutils_parser import parse_with_specutils, is_specutils_available
            if is_specutils_available():
                result = parse_with_specutils(filepath)
                # Normalize output format
                return {
                    'counts': result['counts'],
                    'energies': result['energies'],
                    'num_channels': len(result['counts']),
                    'live_time': result['metadata'].get('live_time', 0),
                    'real_time': result['metadata'].get('real_time', 0),
                    'calibration': None,  # SpecUtils handles calibration internally
                    'metadata': result['metadata']
                }
        except ImportError:
            pass
        except Exception as e:
            print(f"[SpecUtils] Failed to parse {filepath}: {e}")
        
        raise ValueError(f"Unsupported file type: {ext}. Install SandiaSpecUtils for extended format support.")


if __name__ == '__main__':
    # Test with sample files if available
    import sys
    if len(sys.argv) > 1:
        result = parse_spectrum_file(sys.argv[1])
        print(f"Channels: {result['num_channels']}")
        print(f"Live time: {result['live_time']:.1f}s")
        print(f"Real time: {result['real_time']:.1f}s")
        print(f"Calibration: {result['calibration']}")
        print(f"Total counts: {sum(result['counts'])}")
