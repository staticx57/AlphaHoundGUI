
import serial.tools.list_ports
try:
    ports = serial.tools.list_ports.comports()
    print(f"Found {len(ports)} ports:")
    for p in ports:
        print(f" - {p.device}: {p.description}")
except Exception as e:
    print(f"Error listing ports: {e}")
