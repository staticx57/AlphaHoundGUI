"""
Radiacode Device Driver

Wrapper for the radiacode Python library to interface with Radiacode 103, 103G, and 110 devices.
Provides a consistent API matching the AlphaHound device pattern.

Supports:
- USB connection (all platforms)
- Bluetooth BLE connection (all platforms via bleak)

References:
- https://github.com/cdump/radiacode
- https://towardsdatascience.com/exploratory-data-analysis-gamma-spectroscopy-in-python/
"""

from typing import Optional, List, Tuple, Dict, Any
import threading
import platform

# Windows-specific libusb initialization
# PyUSB on Windows cannot find libusb-1.0.dll automatically.
# We must configure the backend using libusb_package BEFORE importing radiacode.
if platform.system() == 'Windows':
    try:
        import libusb_package
        import usb.backend.libusb1 as libusb1
        # Initialize the backend with explicit DLL path
        _libusb_backend = libusb1.get_backend(find_library=libusb_package.find_library)
        if _libusb_backend:
            # Patch usb.core.find to use our backend by default
            import usb.core
            _original_find = usb.core.find
            def _patched_find(*args, **kwargs):
                if 'backend' not in kwargs:
                    kwargs['backend'] = _libusb_backend
                return _original_find(*args, **kwargs)
            usb.core.find = _patched_find
    except ImportError:
        pass  # libusb_package not installed, will fail later with helpful error

# Try to import radiacode library
try:
    from radiacode import RadiaCode
    from radiacode.transports.usb import DeviceNotFound as RadiacodeNotFound
    from radiacode.types import RealTimeData, Spectrum
    HAS_RADIACODE = True
except ImportError:
    HAS_RADIACODE = False
    RadiaCode = None
    RadiacodeNotFound = Exception
    RealTimeData = None
    Spectrum = None

# Try to import bleak-based transport for cross-platform BLE
try:
    from radiacode_bleak_transport import BleakBluetooth, scan_radiacode_sync, HAS_BLEAK, DeviceNotFound as BleakDeviceNotFound
except ImportError:
    HAS_BLEAK = False
    BleakBluetooth = None
    scan_radiacode_sync = None
    BleakDeviceNotFound = Exception


class RadiacodeDevice:
    """
    Wrapper class for Radiacode device communication.
    
    Provides methods for connecting, reading dose rate, acquiring spectra,
    and controlling the device. Thread-safe for concurrent access.
    """
    
    def __init__(self):
        self._device: Optional[Any] = None
        self._bleak_transport: Optional[Any] = None  # For bleak-based BLE connections
        self._lock = threading.Lock()
        self._device_info: Dict[str, Any] = {}
        self._last_error: Optional[str] = None
        self._connection_type: str = ""  # "USB", "BLE", or "Bluetooth"
    
    @property
    def is_available(self) -> bool:
        """Check if radiacode library is installed."""
        return HAS_RADIACODE
    
    @property
    def is_ble_available(self) -> bool:
        """Check if bleak BLE transport is available."""
        return HAS_BLEAK
    
    @staticmethod
    def scan_ble_devices(timeout: float = 5.0) -> List[Dict[str, Any]]:
        """
        Scan for nearby Radiacode BLE devices.
        
        Args:
            timeout: Scan duration in seconds
            
        Returns:
            List of dicts with 'name', 'address', and 'rssi' for each device
        """
        if not HAS_BLEAK or scan_radiacode_sync is None:
            return []
        return scan_radiacode_sync(timeout)
    
    def connect(self, address: Optional[str] = None, use_bluetooth: bool = False) -> bool:
        """
        Connect to a Radiacode device.
        
        Args:
            address: Bluetooth MAC address or BLE address (required if use_bluetooth=True)
            use_bluetooth: Use Bluetooth/BLE instead of USB
            
        Returns:
            True if connection successful, False otherwise
        """
        if not HAS_RADIACODE:
            self._last_error = "Radiacode library not installed. Run: pip install radiacode"
            return False
        
        with self._lock:
            try:
                if use_bluetooth:
                    if not address:
                        self._last_error = "Bluetooth/BLE address required for wireless connection"
                        return False
                    
                    # On Windows/macOS, use bleak-based BLE transport
                    # On Linux, the upstream library's bluepy transport works
                    current_platform = platform.system()
                    
                    if current_platform in ('Windows', 'Darwin'):
                        # Use bleak for cross-platform BLE
                        if not HAS_BLEAK:
                            self._last_error = "bleak library not installed. Run: pip install bleak"
                            return False
                        
                        print(f"[Radiacode] Connecting via BLE (bleak) to {address}...")
                        self._bleak_transport = BleakBluetooth(address)
                        
                        # Create RadiaCode instance and manually set the connection
                        # We use __new__ to bypass __init__ which would try to create its own transport
                        self._device = RadiaCode.__new__(RadiaCode)
                        self._device._connection = self._bleak_transport
                        self._device._seq = 0
                        
                        # Perform initialization sequence from official library
                        import datetime
                        from radiacode.types import COMMAND, VS
                        print("[Radiacode] Initializing device (SET_EXCHANGE)...")
                        self._device.execute(COMMAND.SET_EXCHANGE, b'\x01\xff\x12\xff')
                        
                        print("[Radiacode] Syncing time...")
                        self._device.set_local_time(datetime.datetime.now())
                        self._device.device_time(0)
                        self._device._base_time = datetime.datetime.now() + datetime.timedelta(seconds=128)
                        
                        # Firmware and spectrum format check
                        print("[Radiacode] Fetching device configuration...")
                        self._device._spectrum_format_version = 0
                        try:
                            config = self._device.configuration()
                            for line in config.split('\n'):
                                if line.startswith('SpecFormatVersion'):
                                    self._device._spectrum_format_version = int(line.split('=')[1])
                                    break
                        except Exception as e:
                            print(f"[Radiacode] Warning: failed to parse SpecFormatVersion: {e}")
                        
                        self._connection_type = "BLE"
                        print(f"[Radiacode] BLE connected and initialized successfully")
                    else:
                        # Linux: use upstream library's bluepy transport
                        print(f"[Radiacode] Connecting via Bluetooth (bluepy) to {address}...")
                        self._device = RadiaCode(bluetooth_mac=address)
                        self._connection_type = "Bluetooth"
                else:
                    print("[Radiacode] Connecting via USB...")
                    self._device = RadiaCode()
                    self._connection_type = "USB"
                
                # Get device info
                self._device_info = self._fetch_device_info()
                self._last_error = None
                print(f"[Radiacode] Connected via {self._connection_type}")
                return True
                
            except RadiacodeNotFound:
                self._last_error = "Radiacode device not found. Check USB connection."
                self._device = None
                self._bleak_transport = None
                return False
            except BleakDeviceNotFound as e:
                self._last_error = f"BLE device not found: {str(e)}"
                self._device = None
                self._bleak_transport = None
                return False
            except Exception as e:
                self._last_error = f"Connection failed: {str(e)}"
                self._device = None
                self._bleak_transport = None
                return False
    
    def disconnect(self) -> None:
        """Disconnect from the device."""
        with self._lock:
            # Close bleak transport if used
            if self._bleak_transport:
                try:
                    self._bleak_transport.close()
                except Exception:
                    pass
                self._bleak_transport = None
            
            if self._device:
                try:
                    # Try to close the device's connection
                    if hasattr(self._device, '_connection') and hasattr(self._device._connection, 'close'):
                        self._device._connection.close()
                except Exception:
                    pass
                self._device = None
            
            self._device_info = {}
            self._connection_type = ""
            print("[Radiacode] Disconnected")
    
    def is_connected(self) -> bool:
        """Check if device is currently connected."""
        return self._device is not None
    
    def get_last_error(self) -> Optional[str]:
        """Get the last error message."""
        return self._last_error
    
    def _fetch_device_info(self) -> Dict[str, Any]:
        """Fetch device information from connected device."""
        if not self._device:
            return {}
        
        try:
            # Serial number
            serial = getattr(self._device, 'serial_number', None)
            
            # Firmware version (if available)
            fw_version = getattr(self._device, 'fw_version', None)
            
            # Determine model from characteristics (heuristic)
            # Model detection isn't directly exposed, use serial prefix or calibration data
            model = "Radiacode"  # Default
            
            return {
                "serial_number": serial,
                "firmware_version": fw_version,
                "model": model,
                "connection_type": self._connection_type or "USB"
            }
        except Exception:
            return {}
    
    def get_device_info(self) -> Dict[str, Any]:
        """Get cached device information."""
        return self._device_info.copy()
    
    def get_dose_rate(self) -> Optional[float]:
        """
        Get current dose rate in μSv/h.
        
        Returns:
            Dose rate in μSv/h, or None if unavailable
        """
        if not self._device:
            return None
        
        with self._lock:
                try:
                    data_records = self._device.data_buf()
                    for record in data_records:
                        if RealTimeData and isinstance(record, RealTimeData):
                            # RadiaCode library returns dose_rate in a unit requiring 10,000x multiplier for µSv/h
                            raw_val = float(record.dose_rate)
                            return raw_val * 10000
                    return None
                except Exception as e:
                    import traceback
                    print(f"[Radiacode] Error in get_dose_rate: {e}")
                    traceback.print_exc()
                    self._last_error = f"Failed to get dose rate: {e}"
                    return None
    
    def get_spectrum(self) -> Tuple[List[int], List[float], Dict[str, Any]]:
        """
        Get current accumulated spectrum with energy calibration.
        
        Returns:
            Tuple of (counts, energies, metadata)
            - counts: List of count values per channel
            - energies: List of calibrated energy values (keV)
            - metadata: Dict with duration, total_counts, etc.
        """
        if not self._device:
            return [], [], {}
        
        with self._lock:
            try:
                spectrum = self._device.spectrum()
                
                # Counts per channel
                counts = list(spectrum.counts) if spectrum.counts is not None else []
                
                # Get energy calibration coefficients
                # RadiaCode uses polynomial calibration: E = a0 + a1*ch + a2*ch^2
                try:
                    coeffs = self._device.energy_calib()
                    if len(coeffs) >= 2:
                        a0, a1 = coeffs[0], coeffs[1]
                        a2 = coeffs[2] if len(coeffs) > 2 else 0.0
                    else:
                        # Default calibration (~3 keV/channel)
                        a0, a1, a2 = 0.0, 3.0, 0.0
                except Exception:
                    a0, a1, a2 = 0.0, 3.0, 0.0
                
                # Calculate energies from calibration
                energies = [a0 + a1 * ch + a2 * ch**2 for ch in range(len(counts))]
                
                # Metadata
                # Handle duration - it may be a timedelta or a number
                raw_duration = getattr(spectrum, 'duration', 0)
                if hasattr(raw_duration, 'total_seconds'):
                    # It's a datetime.timedelta object
                    duration_s = raw_duration.total_seconds()
                elif raw_duration is not None:
                    duration_s = float(raw_duration)
                else:
                    duration_s = 0.0
                
                metadata = {
                    "duration_s": duration_s,
                    "total_counts": sum(counts),
                    "channels": len(counts),
                    "calibration": {"a0": a0, "a1": a1, "a2": a2},
                    "source": "Radiacode Device"
                }
                
                return counts, energies, metadata
                
            except Exception as e:
                import traceback
                print(f"[Radiacode] Error in get_spectrum: {e}")
                traceback.print_exc()
                self._last_error = f"Failed to get spectrum: {e}"
                return [], [], {}
    
    def clear_spectrum(self) -> bool:
        """
        Clear/reset accumulated spectrum on device.
        
        Returns:
            True if successful, False otherwise
        """
        if not self._device:
            return False
        
        with self._lock:
            try:
                self._device.spectrum_reset()
                return True
            except Exception as e:
                self._last_error = f"Failed to clear spectrum: {e}"
                return False
    
    def reset_dose(self) -> bool:
        """
        Reset dose accumulator on device.
        
        Returns:
            True if successful, False otherwise
        """
        if not self._device:
            return False
        
        with self._lock:
            try:
                self._device.dose_reset()
                return True
            except Exception as e:
                self._last_error = f"Failed to reset dose: {e}"
                return False


# Global singleton instance
radiacode_device = RadiacodeDevice()
