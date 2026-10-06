"""
AlphaHound Serial Communication Module

Based on AlphaHound Python Interface by NuclearGeekETH
https://github.com/NuclearGeekETH/

Provides async serial communication with RadView Detection AlphaHound device
for dose rate monitoring and gamma spectrum acquisition.

Author: Integration by N42 Viewer
Original: NuclearGeekETH
Device: RadView Detection AlphaHound™
"""

import serial
import serial.tools.list_ports
import threading
import time
import math
import json
import os
from collections import deque
from typing import Optional, List, Dict, Callable

import logging
logger = logging.getLogger(__name__)

# Dose/CPS history kept for CSV download (about 27 h at one reading per second)
DOSE_LOG_MAX = 100_000
# Non-spectrum lines kept so a command's raw reply can be inspected (probe)
RAW_LINES_MAX = 300
# Read-only commands the probe may send. Others (A, B, RA, RB, ...) have unknown effects on the device.
PROBE_COMMANDS = ("D", "DA", "DB", "P")
# 'P' reply: CPS:<gamma>,<beta>,<alpha>[,<dose>]  (as used by the manufacturer's AlphaView page)
CPS_MAX_AGE_S = 5.0
# Current firmware streams a dose value (about 5 per second, uRem/h scale) on its own, with no polling.
# Replies to D / DA / DB (and the dose field of 'P') come back about 10x larger (nSv/h), so they must not
# be mixed into the streamed value. Polling DB is therefore only a fallback for firmware without the
# stream: it starts after this many seconds without any numeric line.
STREAM_DETECT_S = 3.0
STREAM_FRESH_S = 2.0
# One dose-log row per second (the mean of the readings in that second)
DOSE_LOG_INTERVAL_S = 1.0
# Window for the smoothed dose rate (single streamed readings are noisy: +-20 % or more)
DOSE_AVG_WINDOW_S = 5.0
# A spectrum normally arrives within about a second. If the device never answers, stop waiting after this
# long: otherwise the "collecting" flag stays set and all dose / CPS polling stops for good.
SPECTRUM_TIMEOUT_S = 10.0


def parse_cps_line(line: str) -> Optional[Dict[str, float]]:
    """Parse a 'CPS:gamma,beta,alpha[,dose]' line; None if it is not one or is malformed."""
    if not line.startswith('CPS:'):
        return None
    parts = [p.strip() for p in line[4:].split(',')]
    if len(parts) < 3:
        return None
    try:
        gamma, beta, alpha = (float(p) for p in parts[:3])
    except ValueError:
        return None
    if not all(math.isfinite(v) for v in (gamma, beta, alpha)):
        return None
    out = {'gamma': gamma, 'beta': beta, 'alpha': alpha}
    if len(parts) >= 4:
        try:
            dose = float(parts[3])
            if math.isfinite(dose):
                out['dose'] = dose
        except ValueError:
            pass
    return out


WRITE_TIMEOUT_S = 2.0  # a command is a few bytes: a write that takes this long means the link has stalled


class AlphaHoundDevice:
    """Manager for AlphaHound serial communication"""
    
    def __init__(self):
        self.serial_conn: Optional[serial.Serial] = None
        self.read_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.write_lock = threading.Lock()
        
        # Data storage
        self.current_dose: float = 0.0
        self.spectrum: List[tuple] = []  # [(count, energy), ...]
        self.collecting_spectrum = False
        self.temperature: Optional[float] = None  # Device temperature in °C
        self.comp_factor: Optional[float] = None  # Temperature compensation factor

        # Per-channel count rates from the 'P' command (gamma / beta / alpha, counts per second)
        self.cps: Optional[Dict[str, float]] = None
        self.cps_time: float = 0.0
        self.cps_callback: Optional[Callable] = None
        self.poll_cps: bool = True

        # Connection diagnostics and history
        self.last_error: Optional[str] = None
        self.port_busy: bool = False
        self.port: Optional[str] = None
        self.baudrate: Optional[int] = None
        self.user_disconnected: bool = False   # True after a deliberate disconnect: a watchdog must not undo it
        self.connected_since: Optional[float] = None
        self._log_lock = threading.Lock()
        self._last_numeric_time: float = 0.0   # wall clock of the last bare-number (dose) line
        self._spectrum_requested_at: float = 0.0
        self._log_sum = 0.0
        self._log_n = 0
        self._log_last = 0.0
        self._dose_recent = deque(maxlen=400)   # (wall time, uRem/h) of the latest readings, for the average
        self._log_path: Optional[str] = None    # persistent dose log (JSON lines), see enable_log_persistence
        self.dose_log = deque(maxlen=DOSE_LOG_MAX)
        self._raw_lines = deque(maxlen=RAW_LINES_MAX)
        self._poll_paused = threading.Event()
        
        # Callbacks for real-time updates
        self.dose_callback: Optional[Callable] = None
        self.spectrum_callback: Optional[Callable] = None
    
    @staticmethod
    def list_ports() -> List[Dict[str, str]]:
        """Get list of available serial ports"""
        ports = serial.tools.list_ports.comports()
        return [{"device": p.device, "description": p.description} for p in ports]
    
    def connect(self, port: str, baudrate: int = 115200) -> bool:
        """Connect to AlphaHound device"""
        try:
            logger.info(f"Connecting to {port}...")
            self.last_error = None
            self.port_busy = False
            # write_timeout: without it a stalled USB link blocks write() for good (_write retries, then disconnects)
            self.serial_conn = serial.Serial(port, baudrate, timeout=1.0, write_timeout=WRITE_TIMEOUT_S)
            self.stop_event.clear()
            self.read_thread = threading.Thread(target=self._read_worker, daemon=True)
            self.read_thread.start()
            self.port = port
            self.baudrate = baudrate
            self.user_disconnected = False
            self.connected_since = time.time()
            logger.info("Connected and thread started.")
            return True
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.serial_conn = None
            text = str(e)
            if isinstance(e, PermissionError) or 'PermissionError' in text or 'Access is denied' in text \
                    or 'Permission denied' in text or 'busy' in text.lower():
                self.port_busy = True
                self.last_error = (f"Port {port} is in use by another program (or was only just released). "
                                   "Close any other program using it and try again in a few seconds.")
            else:
                self.last_error = f"Could not open {port}: {text}"
            return False
    
    def disconnect(self, user: bool = False):
        """Disconnect from device. user=True marks a deliberate disconnect (the watchdog then leaves it alone)."""
        logger.info("Disconnecting...")
        if user:
            self.user_disconnected = True
        self.stop_event.set()
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except (OSError, serial.SerialException):
                logger.debug('serial close failed', exc_info=True)
        self.serial_conn = None
        self.current_dose = 0.0 # Reset dose to indicate disconnect
        self.cps = None
        self.port = None
        self.connected_since = None
    
    def is_connected(self) -> bool:
        """Check if device is connected"""
        return self.serial_conn is not None and self.serial_conn.is_open
    
    def request_spectrum(self):
        """Request gamma spectrum download from device"""
        self.spectrum = []
        self.collecting_spectrum = True
        self._spectrum_requested_at = time.time()
        self._write(b'G')
    
    def clear_spectrum(self):
        """Clear spectrum on device"""
        self._write(b'W')
        self.spectrum = []
    
    def get_dose_rate(self) -> float:
        """Get current dose rate"""
        return self.current_dose
    
    def get_spectrum(self) -> List[tuple]:
        """Get latest spectrum data"""
        return self.spectrum.copy()
    
    def get_temperature(self) -> Optional[float]:
        """Get device temperature in °C (updated when spectrum is requested)"""
        return self.temperature
    
    def get_comp_factor(self) -> Optional[float]:
        """Get temperature compensation factor (updated when spectrum is requested)"""
        return self.comp_factor
    
    def get_cps(self, max_age_s: float = CPS_MAX_AGE_S) -> Optional[Dict[str, float]]:
        """Latest per-channel count rates (gamma/beta/alpha/total CPS, optional dose); None if stale or unseen."""
        cps = self.cps
        if not cps:
            return None
        age = time.monotonic() - self.cps_time
        if age > max_age_s:
            return None
        return {**cps, 'total': cps['gamma'] + cps['beta'] + cps['alpha'], 'age_s': round(age, 2)}

    def get_dose_rate_avg(self, window_s: float = DOSE_AVG_WINDOW_S) -> Optional[float]:
        """Mean of the dose readings of the last window_s seconds (uRem/h), None when there are none."""
        cutoff = time.time() - window_s
        vals = [v for t, v in list(self._dose_recent) if t >= cutoff]
        return sum(vals) / len(vals) if vals else None

    def get_last_error(self) -> Optional[str]:
        return self.last_error

    def get_health(self) -> Dict[str, Optional[float]]:
        """Is the link alive? Ages are seconds since the last dose / CPS line (None = never seen)."""
        now = time.time()
        connected = self.is_connected()
        return {
            "connected": connected,
            "port": self.port,
            "user_disconnected": self.user_disconnected,
            "connected_for_s": round(now - self.connected_since, 1) if connected and self.connected_since else None,
            "data_age_s": round(now - self._last_numeric_time, 1) if connected and self._last_numeric_time else None,
            "cps_age_s": round(time.monotonic() - self.cps_time, 1) if connected and self.cps_time else None,
            "last_error": self.last_error,
        }

    # ------------------------------------------------------------ persistent dose log
    def enable_log_persistence(self, path: str) -> int:
        """Keep the dose log in a JSON-lines file so it survives a server restart.

        Loads the newest DOSE_LOG_MAX rows already in the file, trims it when it has grown well past
        that, and appends every new row from now on. Returns the number of rows loaded.
        """
        rows: List[Dict] = []
        try:
            with open(path, encoding='utf-8') as f:
                for line in f:
                    try:
                        row = json.loads(line)
                        if isinstance(row, dict) and 'time' in row and 'dose_rate' in row:
                            rows.append(row)
                    except ValueError:
                        continue          # a half-written last line after a crash
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning(f"Could not read the dose log {path}: {e}")
        total = len(rows)
        rows = rows[-DOSE_LOG_MAX:]
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            if total > DOSE_LOG_MAX * 1.2:   # rewrite once, so the file cannot grow without bound
                with open(path, 'w', encoding='utf-8') as f:
                    f.writelines(json.dumps(r) + '\n' for r in rows)
        except OSError as e:
            logger.warning(f"Dose log persistence disabled: {e}")
            return 0
        with self._log_lock:
            self.dose_log.clear()
            self.dose_log.extend(rows)
            self._log_path = path
        logger.info(f"Dose log: {len(rows)} earlier readings loaded from {path}")
        return len(rows)

    def _persist_row(self, row: Dict):
        path = self._log_path
        if not path:
            return
        try:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(row) + '\n')
        except OSError as e:
            logger.warning(f"Dose log persistence disabled: {e}")
            self._log_path = None

    def get_dose_log(self) -> List[Dict[str, Optional[float]]]:
        """Dose-rate history: [{time (epoch s), dose_rate (uRem/h), gamma/beta/alpha (cps or None)}, ...]."""
        with self._log_lock:
            return list(self.dose_log)

    def clear_dose_log(self) -> int:
        with self._log_lock:
            n = len(self.dose_log)
            self.dose_log.clear()
            self._log_sum, self._log_n = 0.0, 0
            path = self._log_path
        if path:
            try:
                open(path, 'w', encoding='utf-8').close()
            except OSError as e:
                logger.warning(f"Could not clear the dose log file: {e}")
        return n

    def _log_dose(self, dose: float, now: Optional[float] = None):
        """Accumulate dose readings and append one row per DOSE_LOG_INTERVAL_S holding their mean."""
        now = time.time() if now is None else now
        with self._log_lock:
            self._log_sum += dose
            self._log_n += 1
            if now - self._log_last < DOSE_LOG_INTERVAL_S:
                return
            mean = self._log_sum / self._log_n
            self._log_sum, self._log_n, self._log_last = 0.0, 0, now
        cps = self.get_cps()
        row = {'time': now, 'dose_rate': mean,
               'gamma': cps['gamma'] if cps else None,
               'beta': cps['beta'] if cps else None,
               'alpha': cps['alpha'] if cps else None}
        with self._log_lock:
            self.dose_log.append(row)
        self._persist_row(row)

    def probe(self, command: str, wait_s: float = 1.2) -> List[str]:
        """Send one read-only command (D, DA, DB, P) and return the raw lines the device answers with.

        Dose/CPS polling is paused meanwhile so replies cannot be mistaken for each other.
        Blocking: call from a worker thread.
        """
        if command not in PROBE_COMMANDS:
            raise ValueError(f"Command {command!r} is not allowed (use one of {', '.join(PROBE_COMMANDS)})")
        if not self.is_connected():
            raise RuntimeError("Device not connected")
        self._poll_paused.set()
        try:
            time.sleep(0.4)  # let a reply to an in-flight poll arrive first
            start = time.monotonic()
            self._write(command.encode('utf-8'))
            time.sleep(wait_s)
            with self._log_lock:
                return [line for t, line in self._raw_lines if t >= start]
        finally:
            self._poll_paused.clear()

    def send_command(self, cmd: str):
        """Send a raw command string to the device (e.g., 'E' for display next, 'Q' for display prev)"""
        self._write(cmd.encode('utf-8'))
    
    def _write(self, data: bytes):
        """Thread-safe write to serial port with retry logic"""
        if not self.serial_conn:
            return
        
        from datetime import datetime
        
        for attempt in range(3):
            try:
                with self.write_lock:
                    self.serial_conn.write(data)
                return  # Success
            except Exception as e:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.error(f"[{timestamp}] [AlphaHound] Write error (attempt {attempt+1}/3): {e}")
                if attempt < 2:
                    time.sleep(0.5)  # Brief pause before retry
        
        # All retries failed
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.warning(f"[{timestamp}] [AlphaHound] Write failed after 3 attempts, disconnecting")
        self.disconnect()
    
    def _read_worker(self):
        """Background thread for reading serial data"""
        buffer = b''
        spectrum_tmp = []
        expecting_spectrum = False
        last_dose_time = 0
        last_cps_time = 0
        started = time.time()
        initial_spectrum_requested = False
        
        logger.info("Read thread active")
        
        while not self.stop_event.is_set() and self.serial_conn and self.serial_conn.is_open:
            try:
                # 1. READ LOOP
                if self.serial_conn.in_waiting:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    buffer += data
                    
                    # Process lines
                    while b'\n' in buffer:
                        line_bytes, buffer = buffer.split(b'\n', 1)
                        line = line_bytes.decode(errors='ignore').strip()
                        
                        if not line:
                            continue
                        
                        if not expecting_spectrum:
                            with self._log_lock:
                                self._raw_lines.append((time.monotonic(), line))

                        # Per-channel count rates (reply to 'P')
                        cps = parse_cps_line(line)
                        if cps is not None:
                            self.cps = cps
                            self.cps_time = time.monotonic()
                            if self.cps_callback:
                                try:
                                    self.cps_callback(self.get_cps())
                                except Exception as e:
                                    logger.error(f"CPS callback error: {e}")
                            continue

                        # Parse temperature from spectrum metadata
                        if line.startswith('Temp:'):
                            try:
                                self.temperature = float(line.split(':')[1])
                            except ValueError:
                                pass
                        
                        # Parse compensation factor from spectrum metadata
                        if line.startswith('CompFactor:'):
                            try:
                                self.comp_factor = float(line.split(':')[1])
                            except ValueError:
                                pass
                            
                        # Spectrum Start
                        if line == "Comp":
                            logger.info("Spectrum start detected")
                            spectrum_tmp = []
                            expecting_spectrum = True
                        
                        # Spectrum Data (format: count,energy)
                        elif expecting_spectrum and ',' in line:
                            try:
                                parts = line.split(',')
                                if len(parts) >= 2:
                                    count = float(parts[0])
                                    energy = float(parts[1])
                                    spectrum_tmp.append((count, energy))
                            except ValueError:
                                pass
                            
                            # Check completion
                            if len(spectrum_tmp) >= 1024:
                                logger.info(f"Spectrum complete: {len(spectrum_tmp)} channels")
                                self.spectrum = spectrum_tmp.copy()
                                self.collecting_spectrum = False
                                expecting_spectrum = False
                                if self.spectrum_callback:
                                    self.spectrum_callback(self.spectrum)

                        # Dose Rate (simple float)
                        elif not expecting_spectrum:
                            # It might be "Full 1024..." or other messages, so be careful
                            try:
                                # Simple check: is it a float?
                                if line.replace('.','',1).isdigit():
                                    dose = float(line)
                                    self._last_numeric_time = time.time()
                                    # While a probe is running, a D/DA/DB reply (nSv/h scale) is among the
                                    # numbers: leave the dose value alone for that moment
                                    if not self._poll_paused.is_set():
                                        self.current_dose = dose
                                        self._dose_recent.append((self._last_numeric_time, dose))
                                        self._log_dose(dose)
                                        # print(f"[Dose] {dose}") # Debug
                                        if self.dose_callback:
                                            self.dose_callback(dose)
                            except ValueError:
                                pass

                # 2. POLL LOOP
                curr = time.time()
                # Poll dose every 1.0s IF NOT collecting spectrum
                # Using 'DB' command which matches the device display (discovered via probing)
                if self.collecting_spectrum and curr - self._spectrum_requested_at > SPECTRUM_TIMEOUT_S:
                    logger.warning("Spectrum request timed out; resuming polling")
                    self.collecting_spectrum = False
                    expecting_spectrum = False

                if (not initial_spectrum_requested and curr - started >= 1.0
                        and not self.collecting_spectrum and not self._poll_paused.is_set()):
                    # Temperature and compensation factor are only reported along with a spectrum, so take
                    # one right after connecting: the details panel then has them without anyone asking
                    initial_spectrum_requested = True
                    self.request_spectrum()

                if not self.collecting_spectrum and not self._poll_paused.is_set():
                    streaming = (curr - self._last_numeric_time) < STREAM_FRESH_S
                    # DB is only a fallback for firmware that does not stream the dose by itself
                    if (not streaming and curr - started >= STREAM_DETECT_S and curr - last_dose_time >= 1.0
                            and curr - last_cps_time >= 0.5):
                        self._write(b'DB')
                        last_dose_time = curr
                    # 'P' (gamma/beta/alpha CPS) and 'DB' are never written within half a second of each
                    # other, so the two single-letter commands are not written back to back
                    elif self.poll_cps and curr - last_cps_time >= 1.0 and curr - last_dose_time >= 0.5:
                        self._write(b'P')
                        last_cps_time = curr
                
                time.sleep(0.05)
                
            except Exception as e:
                logger.error(f"Read thread exception: {e}")
                break
        
        logger.info("Read thread exiting")
        self.disconnect()

# Global device instance
device = AlphaHoundDevice()
