import requests
try:
    # First get ports to be sure
    r = requests.get('http://localhost:8081/device/ports')
    print("Ports:", r.json())
    ports = r.json().get('ports', [])
    if not ports:
        print("No ports found")
        exit()
        
    port = "COM8" # User specified
    print(f"Connecting to {port}...")
    
    r = requests.post('http://localhost:8081/device/connect', json={'port': port})
    print("Connect:", r.status_code, r.text)
except Exception as e:
    print(e)
