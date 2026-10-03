"""
AlphaHound Serial Command Probe
Tests various serial commands against the connected device and logs responses.
"""
import serial
import serial.tools.list_ports
import time
from datetime import datetime

# Commands to probe
COMMANDS = [
    ("G", "Get Gamma Spectrum"),
    ("D", "Get Dose Rate"),
    ("DA", "Get Dose Rate A"),
    ("DB", "Get Dose Rate B"),
    ("GA", "Get Gamma A"),
    ("GB", "Get Gamma B"),
    ("W", "Wipe/Clear Spectrum"),
    ("T", "Temperature?"),
    ("S", "Status?"),
    ("V", "Version?"),
    ("I", "Info?"),
    ("H", "Help?"),
    ("?", "Help?"),
    ("RA", "Reset A?"),
    ("RB", "Reset B?"),
    ("C", "Calibration query?"),
]

def list_ports():
    """List available serial ports."""
    ports = serial.tools.list_ports.comports()
    print("\n=== Available Serial Ports ===")
    for i, port in enumerate(ports):
        print(f"  [{i}] {port.device} - {port.description}")
    return [p.device for p in ports]

def probe_command(ser, cmd, description, timeout=3.0):
    """Send a command and capture response."""
    print(f"\n--- CMD: {cmd} ({description}) ---")
    
    # Clear any pending data
    ser.reset_input_buffer()
    
    # Send command
    ser.write(cmd.encode('utf-8'))
    
    # Wait and collect response
    start = time.time()
    response_lines = []
    spectrum_count = 0
    
    while (time.time() - start) < timeout:
        if ser.in_waiting:
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    # Check if it's spectrum data (count,energy format)
                    if ',' in line and '.' in line:
                        spectrum_count += 1
                        if spectrum_count <= 5:  # Show first 5 lines
                            response_lines.append(f"    {line}")
                        elif spectrum_count == 6:
                            response_lines.append("    ...")
                    else:
                        response_lines.append(f"    {line}")
            except:
                pass
        else:
            time.sleep(0.05)
    
    if spectrum_count > 5:
        response_lines.append(f"    (Total spectrum lines: {spectrum_count})")
    
    if response_lines:
        print("\n".join(response_lines))
    else:
        print("    (no response)")
    
    return response_lines

def main():
    print("=" * 60)
    print("  AlphaHound Serial Command Probe")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    ports = list_ports()
    if not ports:
        print("\nNo serial ports found!")
        return
    
    # Use COM8 for AlphaHound
    port = "COM8"
    
    print(f"\nUsing port: {port}")
    print("Press Ctrl+C to cancel\n")
    
    try:
        ser = serial.Serial(port, 9600, timeout=0.5)
        print(f"Connected to {port}")
        time.sleep(2)  # Wait for device to initialize
        
        # Clear any startup messages
        ser.reset_input_buffer()
        
        results = {}
        
        for cmd, desc in COMMANDS:
            try:
                response = probe_command(ser, cmd, desc, timeout=3.0 if cmd.startswith('G') else 1.5)
                results[cmd] = response
                time.sleep(0.5)  # Pause between commands
            except KeyboardInterrupt:
                print("\n\nProbe interrupted by user")
                break
            except Exception as e:
                print(f"    Error: {e}")
                results[cmd] = [f"Error: {e}"]
        
        ser.close()
        print("\n" + "=" * 60)
        print("  Probe Complete")
        print("=" * 60)
        
        # Summary
        print("\n=== Summary ===")
        for cmd, desc in COMMANDS:
            if cmd in results:
                has_response = len(results[cmd]) > 0 and results[cmd][0] != "    (no response)"
                status = "✓ Response" if has_response else "✗ No response"
                print(f"  {cmd:6} {status}")
        
    except serial.SerialException as e:
        print(f"\nCould not open port {port}: {e}")
    except KeyboardInterrupt:
        print("\n\nCancelled by user")

if __name__ == "__main__":
    main()
