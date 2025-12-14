import xml.etree.ElementTree as ET
import numpy as np
import re

def parse_iso8601_duration(duration_str: str) -> float:
    """
    Parse ISO 8601 duration format (e.g., 'PT60.000S') to seconds.
    Returns 0.0 if parsing fails.
    """
    if not duration_str:
        return 0.0
    try:
        # Handle direct numeric values
        return float(duration_str)
    except ValueError:
        pass
    
    # Parse ISO 8601 duration format: PT[hours]H[minutes]M[seconds]S
    match = re.match(r'PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?', duration_str)
    if match:
        hours = float(match.group(1) or 0)
        minutes = float(match.group(2) or 0)
        seconds = float(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds
    return 0.0

def parse_n42(file_content: str):
    """
    Parses N42 XML content and returns a dictionary with spectrum data.
    Gracefully handles both standards-compliant and legacy/partial formats.
    """
    try:
        root = ET.fromstring(file_content)
        
        # Try multiple namespace configurations
        namespaces = [
            {'n42': 'http://physics.nist.gov/N42/2006/N42'},
            {'n42': 'http://physics.nist.gov/N42/2011/N42'},
            {},  # No namespace fallback
        ]
        
        def find_element(element, paths, ns):
            """Try multiple paths to find an element."""
            for path in paths if isinstance(paths, list) else [paths]:
                if ns:
                    result = element.find(path, ns)
                else:
                    # For no-namespace, strip the prefix
                    clean_path = path.replace('n42:', '')
                    result = element.find(clean_path)
                    if result is None:
                        # Also try with .//* pattern
                        result = element.find('.//' + clean_path.split('/')[-1])
                if result is not None:
                    return result
            return None
        
        def find_text(element, paths, ns):
            """Try multiple paths to find element text."""
            elem = find_element(element, paths, ns)
            return elem.text if elem is not None else None
        
        # Try each namespace configuration
        for ns in namespaces:
            # Find Spectrum element
            spectrum = find_element(root, ['.//n42:Spectrum', './/Spectrum'], ns)
            if spectrum is not None:
                break
        
        if spectrum is None:
            return {"error": "No Spectrum element found"}

        # Find RadMeasurement element (parent of Spectrum)
        rad_measurement = find_element(root, ['.//n42:RadMeasurement', './/RadMeasurement'], ns)

        # Extract Counts - try multiple locations
        channel_data_elem = find_element(spectrum, ['n42:ChannelData', 'ChannelData'], ns)
        if channel_data_elem is None:
            channel_data_elem = find_element(root, ['.//n42:ChannelData', './/ChannelData'], ns)
        
        if channel_data_elem is None:
            return {"error": "No ChannelData found"}
        
        counts = np.fromstring(channel_data_elem.text, sep=' ', dtype=int)
        
        # Extract Energy Calibration - try multiple locations
        energy_cal_elem = find_element(spectrum, ['n42:EnergyCalibration', 'EnergyCalibration'], ns)
        if energy_cal_elem is None:
            energy_cal_elem = find_element(root, ['.//n42:EnergyCalibration', './/EnergyCalibration'], ns)
        
        energies = []
        if energy_cal_elem is not None:
            # Try ChannelEnergies first (list format)
            channel_energies_elem = find_element(energy_cal_elem, ['n42:ChannelEnergies', 'ChannelEnergies'], ns)
            if channel_energies_elem is not None:
                energies = np.fromstring(channel_energies_elem.text, sep=' ', dtype=float)
            else:
                # Try coefficient-based calibration
                coefs_elem = find_element(energy_cal_elem, ['n42:CoefficientValues', 'CoefficientValues', 'n42:Coefficients', 'Coefficients'], ns)
                if coefs_elem is not None:
                    coefs = np.fromstring(coefs_elem.text, sep=' ', dtype=float)
                    if len(coefs) >= 2:
                        # Generate energy array from coefficients (polynomial)
                        channels = np.arange(len(counts))
                        energies = sum(c * (channels ** i) for i, c in enumerate(coefs))
        
        # Parse LiveTime - try multiple locations
        live_time_str = find_text(spectrum, ['n42:LiveTime', 'LiveTime'], ns)
        if not live_time_str and rad_measurement is not None:
            live_time_str = find_text(rad_measurement, ['n42:LiveTime', 'LiveTime'], ns)
        live_time_val = parse_iso8601_duration(live_time_str)
        
        # Parse RealTime - try multiple locations  
        real_time_str = None
        if rad_measurement is not None:
            real_time_str = find_text(rad_measurement, ['n42:RealTime', 'RealTime'], ns)
        if not real_time_str:
            real_time_str = find_text(spectrum, ['n42:RealTime', 'RealTime'], ns)
        if not real_time_str:
            real_time_str = find_text(root, ['.//n42:RealTime', './/RealTime'], ns)
        real_time_val = parse_iso8601_duration(real_time_str)
        
        # Parse StartTime - try multiple locations
        start_time = None
        if rad_measurement is not None:
            start_time = find_text(rad_measurement, ['n42:StartTime', 'StartTime'], ns)
        if not start_time:
            start_time = find_text(root, ['.//n42:StartTime', './/StartTime', './/n42:MeasurementTime', './/MeasurementTime'], ns)

        # Extract Instrument Information for source name
        instrument_elem = find_element(spectrum, ['n42:InstrumentInformation', 'InstrumentInformation'], ns)
        if instrument_elem is None:
            instrument_elem = find_element(root, ['.//n42:InstrumentInformation', './/InstrumentInformation', 
                                                  './/n42:RadInstrumentInformation', './/RadInstrumentInformation'], ns)
        
        source = "N42 File"
        manufacturer = None
        model = None
        if instrument_elem is not None:
            manufacturer = find_text(instrument_elem, ['n42:Manufacturer', 'Manufacturer', 
                                                       'n42:RadInstrumentManufacturerName', 'RadInstrumentManufacturerName'], ns)
            model = find_text(instrument_elem, ['n42:Model', 'Model', 
                                                'n42:RadInstrumentModelName', 'RadInstrumentModelName'], ns)
            # Build source string from instrument info
            if model:
                source = model
                if manufacturer:
                    source = f"{manufacturer} {model}"
            elif manufacturer:
                source = manufacturer

        # Determine calibration status
        is_calibrated = len(energies) > 0 and len(energies) == len(counts)
        
        # If no energies found, create default channel-based array
        if len(energies) == 0:
            energies = np.arange(len(counts)).tolist()
        
        return {
            "counts": counts.tolist(),
            "energies": energies.tolist() if isinstance(energies, np.ndarray) else energies,
            "is_calibrated": is_calibrated,
            "metadata": {
                "source": source,
                "live_time": live_time_val,
                "real_time": real_time_val,
                "start_time": start_time,
                "channels": len(counts),
                "manufacturer": manufacturer,
                "model": model
            }
        }

    except ET.ParseError as e:
        return {"error": f"XML Parse Error: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected Error: {str(e)}"}


