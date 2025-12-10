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
import asyncio
import traceback
from typing import Optional, List, Dict, Callable

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
            print(f"[AlphaHound] Connecting to {port}...")
            self.serial_conn = serial.Serial(port, baudrate, timeout=1.0) # Increased timeout for safety
            self.stop_event.clear()
            self.read_thread = threading.Thread(target=self._read_worker, daemon=True)
            self.read_thread.start()
            print("[AlphaHound] Connected and thread started.")
            return True
        except Exception as e:
            print(f"[AlphaHound] Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from device"""
        print("[AlphaHound] Disconnecting...")
        self.stop_event.set()
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except:
                pass
        self.serial_conn = None
        self.current_dose = 0.0 # Reset dose to indicate disconnect
    
    def is_connected(self) -> bool:
        """Check if device is connected"""
        return self.serial_conn is not None and self.serial_conn.is_open
    
    def request_spectrum(self):
        """Request gamma spectrum download from device"""
        self.spectrum = []
        self.collecting_spectrum = True
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
    
    def _write(self, data: bytes):
        """Thread-safe write to serial port"""
        if not self.serial_conn:
            return
        try:
            with self.write_lock:
                self.serial_conn.write(data)
                # print(f"[TX] {data}") 
        except Exception as e:
            print(f"[AlphaHound] Write error: {e}")
            self.disconnect()
    
    def _read_worker(self):
        """Background thread for reading serial data"""
        buffer = b''
        spectrum_tmp = []
        expecting_spectrum = False
        last_dose_time = 0
        
        print("[AlphaHound] Read thread active")
        
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
                            
                        # Spectrum Start
                        if line == "Comp":
                            print("[AlphaHound] Spectrum start detected")
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
                                print(f"[AlphaHound] Spectrum complete: {len(spectrum_tmp)} channels")
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
                                    self.current_dose = dose
                                    # print(f"[Dose] {dose}") # Debug
                                    if self.dose_callback:
                                        self.dose_callback(dose)
                            except ValueError:
                                pass

                # 2. POLL LOOP
                curr = time.time()
                # Poll dose every 1.0s IF NOT collecting spectrum
                if not self.collecting_spectrum and (curr - last_dose_time >= 1.0):
                    self._write(b'D')
                    last_dose_time = curr
                
                time.sleep(0.05)
                
            except Exception as e:
                print(f"[AlphaHound] Read thread exception: {e}")
                break
        
        print("[AlphaHound] Read thread exiting")
        self.disconnect()

# Global device instance
device = AlphaHoundDevice()
