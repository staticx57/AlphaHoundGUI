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
    try:
        from radiacode.types import RareData
    except ImportError:
        RareData = None
    try:
        from radiacode.types import VSFR
    except ImportError:
        VSFR = None
    try:
        from radiacode.types import Event
    except ImportError:
        Event = None
    HAS_RADIACODE = True
except ImportError:
    HAS_RADIACODE = False
    RadiaCode = None
    RadiacodeNotFound = Exception
    RealTimeData = None
    RareData = None
    VSFR = None
    Event = None
    Spectrum = None
    DisplayDirection = None
    CTRL = None

# Try to import bleak-based transport for cross-platform BLE
try:
    from devices.radiacode_bleak_transport import BleakBluetooth, scan_radiacode_sync, HAS_BLEAK, DeviceNotFound as BleakDeviceNotFound
except ImportError:
    HAS_BLEAK = False
    BleakBluetooth = None
    scan_radiacode_sync = None
    BleakDeviceNotFound = Exception

import logging
import time
logger = logging.getLogger(__name__)


CALIBRATION_DEVICE = "device"
CALIBRATION_FALLBACK = "fallback_linear_3.0_keV_per_channel"


def _valid_coeffs(coeffs):
    try:
        vals = [float(c) for c in coeffs]
    except (TypeError, ValueError):
        return None
    if len(vals) < 2 or not all(v == v and abs(v) != float("inf") for v in vals):
        return None
    if vals[1] <= 0:  # a1 is the slope in keV/channel; must be positive
        return None
    return (vals[0], vals[1], vals[2] if len(vals) > 2 else 0.0)


def resolve_energy_calibration(device, spectrum):
    """
    Return ((a0, a1, a2), source) for E = a0 + a1*ch + a2*ch^2.

    Tries the device's energy_calib(), then the coefficients attached to the spectrum
    object, and only then a 3.0 keV/channel assumption (source == CALIBRATION_FALLBACK).
    """
    try:
        coeffs = _valid_coeffs(device.energy_calib())
        if coeffs:
            return coeffs, CALIBRATION_DEVICE
    except Exception:
        pass
    coeffs = _valid_coeffs([getattr(spectrum, n, None) for n in ("a0", "a1", "a2")])
    if coeffs:
        return coeffs, CALIBRATION_DEVICE
    return (0.0, 3.0, 0.0), CALIBRATION_FALLBACK



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
        self._last_dose_rate: Optional[float] = None
        self._last_dose_rate_time: float = 0.0
        self._last_rare_dose_raw: Optional[float] = None  # RareData.dose (device dose counter)
        self._last_rare_duration_s: Optional[float] = None  # RareData.duration (s since dose reset)
        self._last_rare_time: Optional[float] = None
        self._record_type_counts: Dict[str, int] = {}  # data_buf record types seen since connect
        self._events: List[Dict[str, Any]] = []  # device Event records seen since connect (bounded)
        self._event_seq = 0
        self._dsur_warned = False
        self._session_reset()
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
        
        t0 = time.monotonic()

        def lap(step: str) -> None:
            logger.info(f"[Radiacode] connect: {step} done at +{time.monotonic() - t0:.1f}s")

        with self._lock:
            lap("lock acquired")
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
                        
                        logger.info(f"[Radiacode] Connecting via BLE (bleak) to {address}...")
                        self._bleak_transport = BleakBluetooth(address)
                        lap("BLE transport (link + GATT discovery)")
                        
                        # Create RadiaCode instance and manually set the connection
                        # We use __new__ to bypass __init__ which would try to create its own transport
                        self._device = RadiaCode.__new__(RadiaCode)
                        self._device._connection = self._bleak_transport
                        self._device._seq = 0
                        # radiacode>=0.4.0 close() calls self._finalizer() (normally set in __init__)
                        import weakref
                        self._device._finalizer = weakref.finalize(self._device, self._bleak_transport.close)
                        
                        # Perform initialization sequence from official library
                        import datetime
                        from radiacode.types import COMMAND, VS
                        logger.info("[Radiacode] Initializing device (SET_EXCHANGE)...")
                        self._device.execute(COMMAND.SET_EXCHANGE, b'\x01\xff\x12\xff')
                        
                        lap("SET_EXCHANGE")
                        logger.info("[Radiacode] Syncing time...")
                        self._device.set_local_time(datetime.datetime.now())
                        self._device.device_time(0)
                        self._device._base_time = datetime.datetime.now() + datetime.timedelta(seconds=128)
                        
                        lap("time sync")
                        # Firmware and spectrum format check
                        logger.info("[Radiacode] Fetching device configuration...")
                        self._device._spectrum_format_version = 0
                        try:
                            config = self._device.configuration()
                            for line in config.split('\n'):
                                if line.startswith('SpecFormatVersion'):
                                    self._device._spectrum_format_version = int(line.split('=')[1])
                                    break
                        except Exception as e:
                            logger.warning(f"[Radiacode] Warning: failed to parse SpecFormatVersion: {e}")
                        
                        lap("configuration")
                        self._connection_type = "BLE"
                        logger.info(f"[Radiacode] BLE connected and initialized successfully")
                    else:
                        # Linux: use upstream library's bluepy transport
                        logger.info(f"[Radiacode] Connecting via Bluetooth (bluepy) to {address}...")
                        self._device = RadiaCode(bluetooth_mac=address)
                        self._connection_type = "Bluetooth"
                else:
                    logger.info("[Radiacode] Connecting via USB...")
                    self._device = RadiaCode()
                    self._connection_type = "USB"
                
                # Get device info
                self._device_info = self._fetch_device_info()
                lap("device info")
                self._last_error = None
                logger.info(f"[Radiacode] Connected via {self._connection_type}")
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
            self._dsur_warned = False
            logger.info("[Radiacode] Disconnected")
    
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
            logger.error(f"[Radiacode] Error fetching device info: {e}")
            return {}
    
    def get_device_info(self) -> Dict[str, Any]:
        """Get cached device information."""
        return self._device_info.copy()
    
    DOSE_RATE_CACHE_S = 10.0
    DOSE_SCALE = 10000.0  # library raw units -> uSv (dose) and uSv/h (dose rate)

    MAX_EVENTS = 200
    ALARM_EVENT_PREFIXES = ("DOSE_RATE_ALARM", "DOSE_ALARM", "COUNT_RATE_ALARM", "DOSE_RATE_OFFSCALE",
                            "DOSE_OFFSCALE", "COUNT_RATE_OFFSCALE", "BATTERY_EMPTY_ALARM",
                            "LOW_BATTERY_SHUTOWN", "TEMPERATURE_TOO_")

    def _log_event(self, record) -> None:
        """Remember a device Event record (caller holds the lock)."""
        ev = getattr(record, "event", None)
        name = getattr(ev, "name", None) or str(ev)
        dt = getattr(record, "dt", None)
        self._event_seq += 1
        self._events.append({
            "id": self._event_seq,
            "name": name,
            "alarm": name.startswith(self.ALARM_EVENT_PREFIXES),
            "time": dt.isoformat() if hasattr(dt, "isoformat") else None,
            "param": getattr(record, "event_param1", None),
        })
        del self._events[:-self.MAX_EVENTS]

    def get_events(self, since_id: int = 0) -> List[Dict[str, Any]]:
        """Device events (alarms, power, dose reset...) with id > since_id."""
        with self._lock:
            return [e for e in self._events if e["id"] > since_id]

    def get_alarm_limits(self) -> Optional[Dict[str, Any]]:
        """
        The device's alarm thresholds, in the units configured on the device, or None.

        Registers are read one at a time: the library's single 8-register batch read is rejected
        over BLE ("Invalid Attribute Value Length"). A register this firmware will not serve is None.
        """
        if not self._device or VSFR is None:
            return None

        def read(name):
            reg = getattr(VSFR, name, None)
            if reg is None:
                return None
            try:
                return self._device._batch_read_vsfrs([reg])[0]
            except Exception as e:
                logger.warning(f"[Radiacode] Could not read {name}: {e}")
                return None

        with self._lock:
            raw = {n: read(n) for n in ("CR_LEV1_cp10s", "CR_LEV2_cp10s", "DR_LEV1_uR_h", "DR_LEV2_uR_h",
                                         "DS_LEV1_uR", "DS_LEV2_uR", "DS_UNITS", "CR_UNITS")}
        if all(v is None for v in raw.values()):
            self._last_error = "Failed to read alarm limits: no alarm register could be read"
            return None
        dose_mult = 100 if raw["DS_UNITS"] else 1
        count_mult = 60 if raw["CR_UNITS"] else 1

        def scaled(name, div):
            return None if raw[name] is None else raw[name] / div

        return {
            "l1_count_rate": scaled("CR_LEV1_cp10s", 10 / count_mult),
            "l2_count_rate": scaled("CR_LEV2_cp10s", 10 / count_mult),
            "count_unit": "cpm" if raw["CR_UNITS"] else "cps",
            "l1_dose_rate": scaled("DR_LEV1_uR_h", dose_mult),
            "l2_dose_rate": scaled("DR_LEV2_uR_h", dose_mult),
            "l1_dose": scaled("DS_LEV1_uR", 1e6 * dose_mult),
            "l2_dose": scaled("DS_LEV2_uR", 1e6 * dose_mult),
            "dose_unit": "Sv" if raw["DS_UNITS"] else "R",
        }

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
                # data_buf() drains the device buffer, so several callers (UI dose poll, acquisition
                # exposure) would otherwise steal readings from each other: keep the NEWEST reading
                # and serve it from a short-lived cache when a call finds no new records.
                newest = None
                for record in self._device.data_buf():
                    name = type(record).__name__
                    self._record_type_counts[name] = self._record_type_counts.get(name, 0) + 1
                    if RealTimeData and isinstance(record, RealTimeData):
                        newest = record
                    elif Event and isinstance(record, Event):
                        self._log_event(record)
                    elif RareData and isinstance(record, RareData):
                        # Periodic record carrying the device's cumulative dose counter
                        self._last_rare_dose_raw = float(record.dose)
                        self._last_rare_duration_s = float(getattr(record, "duration", 0) or 0)
                        self._last_rare_time = time.monotonic()
                if newest is not None:
                    # RadiaCode library returns dose_rate in a unit requiring 10,000x multiplier for uSv/h
                    self._last_dose_rate = float(newest.dose_rate) * self.DOSE_SCALE
                    self._last_dose_rate_time = time.monotonic()
                    self._integrate_session_dose(self._last_dose_rate, self._last_dose_rate_time)
                    return self._last_dose_rate
                if (self._last_dose_rate is not None and
                        time.monotonic() - self._last_dose_rate_time <= self.DOSE_RATE_CACHE_S):
                    return self._last_dose_rate
                return None
            except Exception as e:
                import traceback
                logger.error(f"[Radiacode] Error in get_dose_rate: {e}")
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
                
                # RadiaCode uses polynomial calibration: E = a0 + a1*ch + a2*ch^2
                (a0, a1, a2), calibration_source = resolve_energy_calibration(self._device, spectrum)
                if calibration_source != CALIBRATION_DEVICE:
                    logger.warning("[Radiacode] Could not read energy calibration from device; "
                                   "assuming 3.0 keV/channel. Peak energies may be wrong.")
                
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
                    "calibration_source": calibration_source,
                    "source": "Radiacode Device"
                }
                
                return counts, energies, metadata
                
            except Exception as e:
                import traceback
                logger.error(f"[Radiacode] Error in get_spectrum: {e}")
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
                self._session_reset()
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
                logger.info(f"[Radiacode] Language set to {language}")
                return True
            except Exception as e:
                self._last_error = f"Failed to set language: {e}"
                logger.error(f"[Radiacode] Error setting language: {e}")
                return False
    
    
    def get_accumulated_dose(self) -> Optional[float]:
        """
        Get the device's cumulative dose counter in uSv.

        The device sends it in periodic RareData records within data_buf(), which are
        consumed by get_dose_rate(); the latest value is cached there. The raw value is
        scaled like dose_rate (x10,000), the same factor that yields correct uSv/h.
        UNVERIFIED on hardware: compare with the dose shown on the device's own screen.

        Returns:
            Dose in uSv, or None until a RareData record has been received.
        """
        if self._last_rare_dose_raw is None:
            return None
        return self._last_rare_dose_raw * self.DOSE_SCALE

    UR_PER_USV = 100.0  # 1 uSv = 100 uR (same convention as the library's dose-rate examples)

    SESSION_MAX_GAP_S = 10.0  # do not integrate across longer gaps in readings

    def _session_reset(self):
        self._session_dose_uSv = 0.0
        self._session_covered_s = 0.0
        self._session_start = time.time()
        self._session_prev: Optional[tuple] = None  # (rate uSv/h, monotonic time)

    def _integrate_session_dose(self, rate_uSv_h: float, now_s: float):
        """Trapezoid-integrate dose rate into the session dose (uSv)."""
        prev = self._session_prev
        if prev is not None:
            dt = now_s - prev[1]
            if 0 < dt <= self.SESSION_MAX_GAP_S:
                self._session_dose_uSv += 0.5 * (prev[0] + rate_uSv_h) * dt / 3600.0
                self._session_covered_s += dt
        self._session_prev = (rate_uSv_h, now_s)

    def get_session_dose(self) -> Dict[str, Any]:
        """Dose accumulated by this app since connect or the last Reset Dose, from dose-rate readings."""
        return {
            "dose_uSv": round(self._session_dose_uSv, 6),
            "covered_seconds": round(self._session_covered_s, 1),
            "since": self._session_start,
            "method": "integrated instrument dose rate (app-side; device counter unavailable)",
        }

    def probe_vsfrs(self) -> Dict[str, Any]:
        """Read selected registers one at a time to see which this firmware/transport serves."""
        if not self._device or VSFR is None:
            return {}
        out = {}
        for name in ('DS_uR', 'DS_UNITS', 'DS_LEV1_uR', 'DS_LEV2_uR', 'DR_LEV1_uR_h', 'CR_LEV1_cp10s', 'CPS',
                     'DEVICE_LANG', 'DISP_BRT'):
            reg = getattr(VSFR, name, None)
            if reg is None:
                out[name] = 'not in library'
                continue
            with self._lock:
                try:
                    out[name] = self._device._batch_read_vsfrs([reg])[0]
                except Exception as e:
                    out[name] = f'error: {e}'
        return out

    def get_record_type_counts(self) -> Dict[str, int]:
        return dict(self._record_type_counts)

    def read_dose_register_uR(self) -> Optional[int]:
        """Read the device's accumulated-dose register DS_uR (uint32, micro-roentgen).

        This is the counter that Reset Dose clears. Unlike RareData it can be read on demand,
        and its unit is explicit in the register name.
        """
        if not self._device or VSFR is None or not hasattr(VSFR, 'DS_uR'):
            return None
        with self._lock:
            try:
                return int(self._device._batch_read_vsfrs([VSFR.DS_uR])[0])
            except Exception as e:
                # Firmware 4.14 never serves this register over BLE: warn once per connection, not per poll
                level = logging.DEBUG if self._dsur_warned else logging.WARNING
                self._dsur_warned = True
                logger.log(level, f'[Radiacode] Could not read DS_uR dose register: {e}')
                return None

    def get_dose_counter_info(self) -> Dict[str, Any]:
        """Dose counter with a self-check: dose / duration should equal the mean dose rate.

        The library documents both dose and dose_rate only as "device protocol units"; its own
        examples convert dose_rate x10,000 -> uSv/h (x1e6 -> uR/h), i.e. roentgen. If dose uses
        the same unit, implied_mean_rate_uSv_h is close to the readings seen over that period.
        """
        register_uR = self.read_dose_register_uR()
        rare_dose = self.get_accumulated_dose()
        dose = (register_uR / self.UR_PER_USV) if register_uR is not None else rare_dose
        dur = self._last_rare_duration_s
        info = {
            "session": self.get_session_dose(),
            "dose_uSv": dose,
            "source": "DS_uR register" if register_uR is not None else ("RareData" if rare_dose is not None else None),
            "register_uR": register_uR,
            "raredata_dose_uSv": rare_dose,
            "dose_raw": self._last_rare_dose_raw,
            "accumulation_seconds": dur,
            "record_age_seconds": (round(time.monotonic() - self._last_rare_time, 1)
                                   if self._last_rare_time is not None else None),
            "implied_mean_rate_uSv_h": None,
            "current_dose_rate_uSv_h": self._last_dose_rate,
        }
        if dose is not None and dur and dur > 0:
            info["implied_mean_rate_uSv_h"] = dose / (dur / 3600.0)
        return info

    def get_accumulated_dose_raw(self) -> Optional[float]:
        """Unscaled RareData.dose, for verifying the scale against the device display."""
        return self._last_rare_dose_raw
    
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
                # DisplayDirection comes from radiacode.types (module import); the old import from
                # transports.usb and the NORMAL/REVERSED members never existed, so this always failed.
                
                direction_map = {
                    'auto': DisplayDirection.AUTO,
                    'right': DisplayDirection.RIGHT,
                    'left': DisplayDirection.LEFT,
                    # legacy UI values
                    'normal': DisplayDirection.RIGHT,
                    'reversed': DisplayDirection.LEFT,
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
                logger.error(f"[Radiacode] Error getting calibration: {e}")
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
                logger.info(f"[Radiacode] Set calibration: a0={a0}, a1={a1}, a2={a2}")
                return True
            except Exception as e:
                logger.error(f"[Radiacode] Error setting calibration: {e}")
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
                logger.error(f"[Radiacode] Error setting sound control: {e}")
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
                logger.error(f"[Radiacode] Error setting vibration control: {e}")
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
                logger.info("[Radiacode] Device power off sent")
                return True
            except Exception as e:
                logger.error(f"[Radiacode] Error powering off: {e}")
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
                logger.error(f"[Radiacode] Error getting status: {e}")
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
                logger.error(f"[Radiacode] Error getting FW signature: {e}")
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
                logger.error(f"[Radiacode] Error getting text message: {e}")
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
                logger.error(f"[Radiacode] Error getting commands: {e}")
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
                logger.error(f"[Radiacode] Error getting base time: {e}")
                self._last_error = f"Failed to get base time: {e}"
                return None


# Global singleton instance
radiacode_device = RadiacodeDevice()
