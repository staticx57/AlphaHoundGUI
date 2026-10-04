"""
CHN/SPE File Parsers

Parsers for Ortec CHN and Maestro SPE spectrum file formats.
These are common formats from commercial MCA (Multi-Channel Analyzer) systems.
"""

import struct

import logging
logger = logging.getLogger(__name__)


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
    
    # 32-byte header (little endian), as written by Maestro and by SpecUtils/InterSpec:
    #   0 int16 -1 (format), 2 int16 MCA number, 4 int16 segment, 6 char[2] start seconds,
    #   8 int32 real time and 12 int32 live time (20 ms units), 16 char[8] start date DDMMMYY + century flag,
    #   24 char[4] start time HHMM, 28 uint16 first channel, 30 uint16 number of channels
    format_id, mca_num, segment = struct.unpack('<3h', data[0:6])
    if format_id != -1:
        raise ValueError("Not an Ortec CHN file (the format marker is not -1)")

    real_time_raw, live_time_raw = struct.unpack('<2I', data[8:16])
    real_time = real_time_raw * 0.02
    live_time = live_time_raw * 0.02

    date_str = (data[16:24].decode('ascii', errors='ignore') + ' ' + data[24:28].decode('ascii', errors='ignore')).strip()

    channel_offset, num_channels = struct.unpack('<2H', data[28:32])

    # 32-bit counts follow the header
    spectrum_start = 32
    spectrum_end = spectrum_start + num_channels * 4

    if num_channels == 0 or len(data) < spectrum_end:
        raise ValueError(f"File truncated: expected {spectrum_end} bytes, got {len(data)}")

    counts = list(struct.unpack(f'<{num_channels}I', data[spectrum_start:spectrum_end]))

    # Optional trailer: int16 -102 (type), int16 length, then float32 energy calibration a0, a1, a2
    calibration = None
    trailer = data[spectrum_end:]
    if len(trailer) >= 16 and struct.unpack('<h', trailer[:2])[0] == -102:
        cal_a, cal_b, cal_c = struct.unpack('<3f', trailer[4:16])
        if abs(cal_b) > 0.001:  # Sanity check
            calibration = {
                'a': cal_a,  # offset
                'b': cal_b,  # keV/channel
                'c': cal_c   # quadratic term
            }

    # Generate energies if calibrated
    energies = list(range(num_channels))
    if calibration:
        calibrated = [calibration['a'] + calibration['b'] * i + calibration['c'] * i**2
                      for i in range(num_channels)]
        # all-zero coefficients (how digiBASE/GammaVision write "not calibrated") give no axis: keep channel numbers
        if all(b > a for a, b in zip(calibrated, calibrated[1:])):
            energies = calibrated
        else:
            calibration = None

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
                    # Second line is coefficients, in GammaVision files followed by their unit ("... 0.000000E+000 keV")
                    coeffs = [float(x) for x in lines[i].strip().split()[:num_coeffs]]
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
        calibrated = [calibration['a'] + calibration['b'] * i + calibration['c'] * i**2
                      for i in range(num_channels)]
        # all-zero coefficients (how digiBASE/GammaVision write "not calibrated") give no axis: keep channel numbers
        if all(b > a for a, b in zip(calibrated, calibrated[1:])):
            energies = calibrated
        else:
            calibration = None

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
