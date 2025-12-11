import sys
import os
import time

# Add backend to path to allow imports
sys.path.append(os.path.join(os.getcwd(), 'backend'))

try:
    from alphahound_serial import device as alpha_device
except ImportError:
    # Try alternate path if running from root
    sys.path.append(os.getcwd())
    from backend.alphahound_serial import device as alpha_device

def run_debug():
    print("Searching for AlphaHound ports...")
    ports = alpha_device.list_ports()
    print(f"Available ports: {ports}")
    
    if not ports:
        print("No ports found. Please connect the device.")
        return

    # Try the first port (usually there's only one relevant one)
    target_port = ports[0]['device']
    print(f"Attempting connection to {target_port}...")
    
    if alpha_device.connect(target_port):
        print("--- CONNECTION SUCCESSFUL ---")
        print("Listening for 15 seconds. raw data should appear below...")
        print("-------------------------------------------------------")
        
        # Keep main thread alive while background read thread works
        for i in range(15):
            time.sleep(1)
            # Optional: send a 'D' poll command to see how it responds
            # alpha_device._write(b'D') 
        
        print("-------------------------------------------------------")
        print("Disconnecting...")
        alpha_device.disconnect()
        print("Done.")
    else:
        print("--- CONNECTION FAILED ---")
        print("Ensure the device is not in use by another app (like the GUI backend).")

if __name__ == "__main__":
    run_debug()
