"""
AlphaHound Raw Serial Data Diagnostic Tool

This script reads raw serial data from the AlphaHound device to:
1. Understand the exact format of all messages
2. Identify all available fields for N42 export compliance
3. Capture timing and metadata information

Usage:
    python alphahound_raw_diagnostics.py COM3
    
    Replace COM3 with your AlphaHound's serial port.
"""

import serial
import serial.tools.list_ports
import sys
import time
from datetime import datetime
import json

class AlphaHoundDiagnostics:
    def __init__(self, port, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.capture_log = []
        self.session_start = None
        self.spectrum_data = []
        
    def list_available_ports(self):
        """List all available COM ports"""
        ports = serial.tools.list_ports.comports()
        print("\n=== Available Serial Ports ===")
        for p in ports:
            print(f"  {p.device}: {p.description}")
        print()
        
    def connect(self):
        """Connect to the AlphaHound device"""
        try:
            print(f"[{self.timestamp()}] Connecting to {self.port} at {self.baudrate} baud...")
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1.0)
            self.session_start = datetime.now()
            print(f"[{self.timestamp()}] ✓ Connected successfully\n")
            return True
        except Exception as e:
            print(f"[{self.timestamp()}] ✗ Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from device"""
        if self.serial_conn:
            self.serial_conn.close()
            print(f"\n[{self.timestamp()}] Disconnected from {self.port}")
    
    def timestamp(self):
        """Get current timestamp"""
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]
    
    def log_message(self, direction, data, parsed=None):
        """Log a message with timestamp and metadata"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_s": (datetime.now() - self.session_start).total_seconds(),
            "direction": direction,
            "raw_bytes": data.hex() if isinstance(data, bytes) else None,
            "decoded": data.decode('utf-8', errors='replace') if isinstance(data, bytes) else data,
            "parsed": parsed
        }
        self.capture_log.append(entry)
        
    def send_command(self, cmd):
        """Send a command to the device"""
        if isinstance(cmd, str):
            cmd = cmd.encode('utf-8')
        self.serial_conn.write(cmd)
        self.log_message("TX", cmd)
        print(f"[{self.timestamp()}] TX → {cmd.decode('utf-8', errors='replace')}")
    
    def analyze_line(self, line):
        """Analyze and categorize a received line"""
        line_stripped = line.strip()
        
        # Detect message type
        msg_type = "UNKNOWN"
        parsed_data = {}
        
        if line_stripped == "Comp":
            msg_type = "SPECTRUM_START"
        elif ',' in line_stripped:
            try:
                parts = line_stripped.split(',')
                if len(parts) >= 2:
                    count = float(parts[0])
                    energy = float(parts[1])
                    msg_type = "SPECTRUM_DATA"
                    parsed_data = {"count": count, "energy_keV": energy}
                    self.spectrum_data.append(parsed_data)
            except ValueError:
                msg_type = "UNKNOWN_CSV"
        elif line_stripped.replace('.', '', 1).replace('-', '', 1).isdigit():
            try:
                dose = float(line_stripped)
                msg_type = "DOSE_RATE"
                parsed_data = {"dose_uRem": dose}
            except ValueError:
                pass
        elif line_stripped.startswith("Full"):
            msg_type = "STATUS_MESSAGE"
            parsed_data = {"message": line_stripped}
        
        return msg_type, parsed_data
    
    def read_loop(self, duration_seconds=30):
        """Read raw serial data for specified duration"""
        print(f"=== Starting {duration_seconds}s capture ===\n")
        print("Commands will be sent automatically:")
        print("  D - Request dose rate (every 2s)")
        print("  G - Request spectrum (at 10s)")
        print("  W - Clear spectrum (at 15s)\n")
        
        buffer = b''
        start_time = time.time()
        last_dose_request = 0
        spectrum_requested = False
        spectrum_cleared = False
        
        try:
            while (time.time() - start_time) < duration_seconds:
                elapsed = time.time() - start_time
                
                # Auto-send commands for testing
                if elapsed - last_dose_request >= 2.0:
                    self.send_command(b'D')
                    last_dose_request = elapsed
                
                if not spectrum_requested and elapsed >= 10.0:
                    print(f"\n[{self.timestamp()}] >>> Requesting spectrum...\n")
                    self.send_command(b'G')
                    spectrum_requested = True
                
                if not spectrum_cleared and elapsed >= 15.0:
                    print(f"\n[{self.timestamp()}] >>> Clearing spectrum...\n")
                    self.send_command(b'W')
                    spectrum_cleared = True
                
                # Read available data
                if self.serial_conn.in_waiting:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    buffer += data
                    
                    # Process complete lines
                    while b'\n' in buffer:
                        line_bytes, buffer = buffer.split(b'\n', 1)
                        line = line_bytes.decode('utf-8', errors='replace')
                        
                        msg_type, parsed = self.analyze_line(line)
                        self.log_message("RX", line_bytes, parsed)
                        
                        # Print with color coding
                        if msg_type == "SPECTRUM_START":
                            print(f"[{self.timestamp()}] RX ← [{msg_type}] {line.strip()}")
                        elif msg_type == "SPECTRUM_DATA":
                            # Only print first few and summary
                            if len(self.spectrum_data) <= 5 or len(self.spectrum_data) >= 1024:
                                print(f"[{self.timestamp()}] RX ← [{msg_type}] Count={parsed['count']}, "
                                      f"Energy={parsed['energy_keV']} keV ({len(self.spectrum_data)}/1024)")
                        elif msg_type == "DOSE_RATE":
                            print(f"[{self.timestamp()}] RX ← [{msg_type}] {parsed['dose_uRem']} µRem/h")
                        else:
                            print(f"[{self.timestamp()}] RX ← [{msg_type}] {line.strip()}")
                
                time.sleep(0.05)
                
        except KeyboardInterrupt:
            print(f"\n[{self.timestamp()}] Capture interrupted by user")
    
    def save_results(self, filename="alphahound_diagnostics.json"):
        """Save capture log to JSON file"""
        results = {
            "session_info": {
                "port": self.port,
                "baudrate": self.baudrate,
                "start_time": self.session_start.isoformat(),
                "duration_s": (datetime.now() - self.session_start).total_seconds(),
                "total_messages": len(self.capture_log),
                "spectrum_channels_captured": len(self.spectrum_data)
            },
            "analysis": self.analyze_capture(),
            "raw_log": self.capture_log
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n[{self.timestamp()}] ✓ Results saved to: {filename}")
        return filename
    
    def analyze_capture(self):
        """Analyze the captured data for N42 export fields"""
        msg_types = {}
        for entry in self.capture_log:
            if entry['direction'] == 'RX' and entry['parsed']:
                msg_type = list(entry['parsed'].keys())[0] if entry['parsed'] else "unknown"
                msg_types[msg_type] = msg_types.get(msg_type, 0) + 1
        
        analysis = {
            "message_types": msg_types,
            "n42_fields_available": {
                "counts_array": len(self.spectrum_data) > 0,
                "energy_calibration": len(self.spectrum_data) > 0,
                "dose_rate": any('dose_uRem' in e.get('parsed', {}) for e in self.capture_log),
                "timestamps": "Device does NOT provide timestamps",
                "live_time": "NOT AVAILABLE - Device does not send",
                "real_time": "NOT AVAILABLE - Device does not send",
                "start_time": "NOT AVAILABLE - Must use system time",
                "instrument_info": "NOT AVAILABLE - Device does not send"
            },
            "n42_compliance_notes": [
                "✓ Spectrum data (counts + energies) available",
                "✓ Dose rate available",
                "✗ Acquisition timing must be tracked CLIENT-SIDE",
                "✗ No device-provided timestamps",
                "✗ No instrument identification from device",
                "⚠ LiveTime/RealTime must be calculated from acquisition duration"
            ]
        }
        
        return analysis
    
    def print_summary(self):
        """Print analysis summary"""
        analysis = self.analyze_capture()
        
        print("\n" + "="*60)
        print("=== ALPHAHOUND DATA ANALYSIS ===")
        print("="*60)
        
        print("\n📊 Message Statistics:")
        for msg_type, count in analysis['message_types'].items():
            print(f"  {msg_type}: {count} messages")
        
        print("\n📋 N42 Export Field Availability:")
        for field, status in analysis['n42_fields_available'].items():
            symbol = "✓" if status == True else ("✗" if status == False else "⚠")
            print(f"  {symbol} {field}: {status}")
        
        print("\n💡 N42 Compliance Notes:")
        for note in analysis['n42_compliance_notes']:
            print(f"  {note}")
        
        print("\n" + "="*60)


def main():
    print("\n" + "="*60)
    print(" AlphaHound Raw Serial Diagnostics Tool")
    print("="*60)
    
    diag = AlphaHoundDiagnostics(None)
    diag.list_available_ports()
    
    if len(sys.argv) < 2:
        print("Usage: python alphahound_raw_diagnostics.py <PORT>")
        print("Example: python alphahound_raw_diagnostics.py COM3")
        sys.exit(1)
    
    port = sys.argv[1]
    diag = AlphaHoundDiagnostics(port)
    
    if not diag.connect():
        sys.exit(1)
    
    try:
        diag.read_loop(duration_seconds=30)
        diag.print_summary()
        filename = diag.save_results()
        
        print(f"\n✓ Diagnostic complete!")
        print(f"  View detailed results in: {filename}")
        
    finally:
        diag.disconnect()


if __name__ == "__main__":
    main()
