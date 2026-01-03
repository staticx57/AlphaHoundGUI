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
    from radiacode.types import RealTimeData, Spectrum, DisplayDirection, CTRL
    HAS_RADIACODE = True
except ImportError:
    HAS_RADIACODE = False
    RadiaCode = None
    RadiacodeNotFound = Exception
    RealTimeData = None
    Spectrum = None
    DisplayDirection = None
    CTRL = None

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
            # Serial number - call the method
            serial = None
            if hasattr(self._device, 'serial_number') and callable(self._device.serial_number):
                serial = self._device.serial_number()
            
            # Firmware version - call the method
            fw_version = None
            if hasattr(self._device, 'fw_version') and callable(self._device.fw_version):
                fw_version = self._device.fw_version()
            
            # Determine model from characteristics (heuristic)
            model = "Radiacode"  # Default
            
            return {
                "serial_number": serial,
                "firmware_version": fw_version,
                "model": model,
                "connection_type": self._connection_type or "USB"
            }
        except Exception as e:
            print(f"[Radiacode] Error fetching device info: {e}")
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
    
    # ============================================================
    # Device Settings (Radiacode-specific features)
    # ============================================================
    
    def set_brightness(self, level: int) -> bool:
        """
        Set display brightness (0-9).
        
        Args:
            level: Brightness level 0 (dimmest) to 9 (brightest)
            
        Returns:
            True if successful, False otherwise
        """
        if not self._device:
            return False
        
        level = max(0, min(9, level))  # Clamp to valid range
        
        with self._lock:
            try:
                self._device.set_display_brightness(level)
                return True
            except Exception as e:
                self._last_error = f"Failed to set brightness: {e}"
                return False
    
    def set_sound(self, enabled: bool) -> bool:
        """
        Enable or disable device sound alerts.
        
        Args:
            enabled: True to enable sound, False to disable
            
        Returns:
            True if successful, False otherwise
        """
        if not self._device:
            return False
        
        with self._lock:
            try:
                self._device.set_sound_on(enabled)
                return True
            except Exception as e:
                self._last_error = f"Failed to set sound: {e}"
                return False
    
    def set_vibration(self, enabled: bool) -> bool:
        """
        Enable or disable device vibration alerts.
        
        Args:
            enabled: True to enable vibration, False to disable
            
        Returns:
            True if successful, False otherwise
        """
        if not self._device:
            return False
        
        with self._lock:
            try:
                self._device.set_vibro_on(enabled)
                return True
            except Exception as e:
                self._last_error = f"Failed to set vibration: {e}"
                return False
    
    def set_display_off_time(self, seconds: int) -> bool:
        """
        Set display auto-off timeout.
        
        Args:
            seconds: Seconds until display turns off (0 = never)
            
        Returns:
            True if successful, False otherwise
        """
        if not self._device:
            return False
        
        with self._lock:
            try:
                self._device.set_display_off_time(seconds)
                return True
            except Exception as e:
                self._last_error = f"Failed to set display off time: {e}"
                return False
    
    def set_language(self, language: str) -> bool:
        """
        Set device language.
        
        Args:
            language: 'en' for English or 'ru' for Russian
            
        Returns:
            True if successful, False otherwise
        """
        if not self._device:
            self._last_error = "Device not connected"
            return False
        
        if language not in ['en', 'ru']:
            self._last_error = "Language must be 'en' or 'ru'"
            return False
        
        with self._lock:
            try:
                self._device.set_language(language)
                print(f"[Radiacode] Language set to {language}")
                return True
            except Exception as e:
                self._last_error = f"Failed to set language: {e}"
                print(f"[Radiacode] Error setting language: {e}")
                return False
    
    
    def get_accumulated_dose(self) -> Optional[float]:
        """
        Get total accumulated dose in μSv.
        
        NOTE: The radiacode library does not expose accumulated dose via data_buf().
        RealTimeData only provides dose_rate, not accumulated dose.
        This feature is not available.
        
        Returns:
            None - Feature not available in radiacode library
        """
        # Accumulated dose is not available from RealTimeData
        # The library only exposes dose_rate, not total accumulated dose
        return None
    
    def get_configuration(self) -> Optional[str]:
        """
        Get full device configuration dump.
        
        Returns:
            Configuration string or None if unavailable
        """
        if not self._device:
            return None
        
        with self._lock:
            try:
                return self._device.configuration()
            except Exception as e:
                self._last_error = f"Failed to get configuration: {e}"
                return None

    # ==================== Phase 1: Quick Win Features ====================

    def get_accumulated_spectrum(self) -> Optional[dict]:
        """
        Get accumulated spectrum data (long-term monitoring).
        
        Returns spectrum data accumulated over time, useful for isotope identification
        and long-term radiation monitoring.
        
        Returns:
            dict with spectrum data and metadata, or None if unavailable
        """
        if not self._device:
            return None
        
        with self._lock:
            try:
                spec = self._device.spectrum_accum()
                return {
                    'counts': spec.counts.tolist() if hasattr(spec.counts, 'tolist') else list(spec.counts),
                    'duration': spec.duration.total_seconds(),
                    'a0': spec.a0,
                    'a1': spec.a1,
                    'a2': spec.a2,
                    'channels': len(spec.counts)
                }
            except Exception as e:
                self._last_error = f"Failed to get accumulated spectrum: {e}"
                return None

    def set_display_direction(self, direction: str) -> bool:
        """
        Set the device display orientation.
        
        Args:
            direction: One of 'normal', 'reversed', or 'auto'
            
        Returns:
            True if successful, False otherwise
        """
        if not self._device:
            return False
        
        with self._lock:
            try:
                from radiacode.transports.usb import DisplayDirection
                
                direction_map = {
                    'normal': DisplayDirection.NORMAL,
                    'reversed': DisplayDirection.REVERSED,
                    'auto': DisplayDirection.AUTO
                }
                
                if direction.lower() not in direction_map:
                    self._last_error = f"Invalid direction: {direction}"
                    return False
                
                self._device.set_display_direction(direction_map[direction.lower()])
                return True
            except Exception as e:
                self._last_error = f"Failed to set display direction: {e}"
                return False

    def sync_device_time(self) -> bool:
        """
        Synchronize device clock with computer time.
        
        Returns:
            True if successful, False otherwise
        """
        if not self._device:
            return False
        
        with self._lock:
            try:
                import datetime
                self._device.set_local_time(datetime.datetime.now())
                return True
            except Exception as e:
                self._last_error = f"Failed to sync device time: {e}"
                return False

    def get_hw_serial_number(self) -> Optional[str]:
        """
        Get the hardware serial number.
        
        Returns detailed hardware serial number (distinct from software serial).
        
        Returns:
            Hardware serial number string, or None if unavailable
        """
        if not self._device:
            return None
        
        with self._lock:
            try:
                return self._device.hw_serial_number()
            except Exception as e:
                self._last_error = f"Failed to get hardware serial: {e}"
                return None

    # ============================================================
    # Phase 2: Advanced Controls
    # ============================================================

    def get_energy_calibration(self) -> Optional[Dict[str, float]]:
        """Get current energy calibration coefficients."""
        if not self._device:
            return None
        
        with self._lock:
            try:
                spec = self._device.spectrum()
                return {"a0": spec.a0, "a1": spec.a1, "a2": spec.a2}
            except Exception as e:
                print(f"[Radiacode] Error getting calibration: {e}")
                self._last_error = f"Failed to get calibration: {e}"
                return None

    def set_energy_calibration(self, a0: float, a1: float, a2: float) -> bool:
        """Set energy calibration coefficients (Energy = a0 + a1*ch + a2*ch^2)."""
        if not self._device:
            self._last_error = "Not connected"
            return False
        
        with self._lock:
            try:
                self._device.set_energy_calib([a0, a1, a2])
                print(f"[Radiacode] Set calibration: a0={a0}, a1={a1}, a2={a2}")
                return True
            except Exception as e:
                print(f"[Radiacode] Error setting calibration: {e}")
                self._last_error = f"Failed to set calibration: {e}"
                return False

    def set_sound_control(self, search: bool = False, detector: bool = False, clicks: bool = False) -> bool:
        """Set advanced sound control flags (search/detector/clicks)."""
        if not self._device:
            self._last_error = "Not connected"
            return False
        
        with self._lock:
            try:
                ctrls = []
                if search:
                    ctrls.append(CTRL.SEARCH)
                if detector:
                    ctrls.append(CTRL.DETECTOR)
                if clicks:
                    ctrls.append(CTRL.CLICKS)
                self._device.set_sound_ctrl(ctrls)
                return True
            except Exception as e:
                print(f"[Radiacode] Error setting sound control: {e}")
                self._last_error = f"Failed to set sound control: {e}"
                return False

    def set_vibration_control(self, search: bool = False, detector: bool = False) -> bool:
        """Set advanced vibration control flags (search/detector only, no clicks)."""
        if not self._device:
            self._last_error = "Not connected"
            return False
        
        with self._lock:
            try:
                ctrls = []
                if search:
                    ctrls.append(CTRL.SEARCH)
                if detector:
                    ctrls.append(CTRL.DETECTOR)
                self._device.set_vibro_ctrl(ctrls)
                return True
            except Exception as e:
                print(f"[Radiacode] Error setting vibration control: {e}")
                self._last_error = f"Failed to set vibration control: {e}"
                return False

    def power_off_device(self) -> bool:
        """Power off the device. User must manually power back on."""
        if not self._device:
            self._last_error = "Not connected"
            return False
        
        with self._lock:
            try:
                self._device.set_device_on(False)
                print("[Radiacode] Device power off sent")
                return True
            except Exception as e:
                print(f"[Radiacode] Error powering off: {e}")
                self._last_error = f"Failed to power off: {e}"
                return False

    # ============================================================
    # Phase 3: Info & Diagnostics
    # ============================================================

    def get_status_flags(self) -> Optional[str]:
        """Get device status flags."""
        if not self._device:
            return None
        
        with self._lock:
            try:
                return self._device.status()
            except Exception as e:
                print(f"[Radiacode] Error getting status: {e}")
                self._last_error = f"Failed to get status: {e}"
                return None

    def get_firmware_signature(self) -> Optional[str]:
        """Get firmware signature info."""
        if not self._device:
            return None
        
        with self._lock:
            try:
                return self._device.fw_signature()
            except Exception as e:
                print(f"[Radiacode] Error getting FW signature: {e}")
                self._last_error = f"Failed to get FW signature: {e}"
                return None

    def get_text_message(self) -> Optional[str]:
        """Get device text message/alert."""
        if not self._device:
            return None
        
        with self._lock:
            try:
                msg = self._device.text_message()
                return msg if msg else None
            except Exception as e:
                print(f"[Radiacode] Error getting text message: {e}")
                self._last_error = f"Failed to get text message: {e}"
                return None

    # ============================================================
    # Phase 4: System Features
    # ============================================================

    def get_available_commands(self) -> Optional[str]:
        """Get list of available SFR commands."""
        if not self._device:
            return None
        
        with self._lock:
            try:
                return self._device.commands()
            except Exception as e:
                print(f"[Radiacode] Error getting commands: {e}")
                self._last_error = f"Failed to get commands: {e}"
                return None

    def get_base_time(self) -> Optional[str]:
        """Get device base time reference for timestamp conversion."""
        if not self._device:
            return None
        
        with self._lock:
            try:
                # _base_time is set during device initialization
                return str(self._device._base_time) if hasattr(self._device, '_base_time') else None
            except Exception as e:
                print(f"[Radiacode] Error getting base time: {e}")
                self._last_error = f"Failed to get base time: {e}"
                return None


# Global singleton instance
radiacode_device = RadiacodeDevice()
