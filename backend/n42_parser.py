import xml.etree.ElementTree as ET
import numpy as np

def parse_n42(file_content: str):
    """
    Parses N42 XML content and returns a dictionary with spectrum data.
    """
    try:
        root = ET.fromstring(file_content)
        ns = {'n42': 'http://physics.nist.gov/N42/2006/N42'}
        
        # Helper to find elements with namespace
        def find_text(element, path):
            return element.find(path, ns).text if element.find(path, ns) is not None else None

        # Find Spectrum element (assuming single measurement for now)
        spectrum = root.find('.//n42:Spectrum', ns)
        if spectrum is None:
            # Try without namespace if it fails, or handle multiple namespaces
            # For this simple implementation, we stick to the provided file's namespace
            return {"error": "No Spectrum element found"}

        # Extract Counts
        channel_data_elem = spectrum.find('n42:ChannelData', ns)
        if channel_data_elem is None:
             return {"error": "No ChannelData found"}
        
        counts = np.fromstring(channel_data_elem.text, sep=' ', dtype=int)
        
        # Extract Energy Calibration
        energy_cal_elem = spectrum.find('n42:EnergyCalibration', ns)
        energies = []
        if energy_cal_elem is not None:
             channel_energies_elem = energy_cal_elem.find('n42:ChannelEnergies', ns)
             if channel_energies_elem is not None:
                 energies = np.fromstring(channel_energies_elem.text, sep=' ', dtype=float)
        
        # If no explicit energies, we might need coefficients, but for now let's use what we found
        # If energies array length matches counts, we are good.
        
        # Parse Duration (float)
        try:
             live_time_val = float(live_time) if live_time else 0.0
             real_time_val = float(real_time) if real_time else 0.0
        except:
             live_time_val = 0.0
             real_time_val = 0.0

        # Determine calibration status
        is_calibrated = len(energies) > 0 and len(energies) == len(counts)
        
        return {
            "counts": counts.tolist(),
            "energies": energies.tolist() if len(energies) > 0 else [],
            "is_calibrated": is_calibrated,
            "metadata": {
                "source": "N42 File",
                "live_time": live_time_val,
                "real_time": real_time_val
            }
        }

    except ET.ParseError as e:
        return {"error": f"XML Parse Error: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected Error: {str(e)}"}
