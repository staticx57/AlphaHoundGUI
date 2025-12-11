from fastapi import APIRouter, HTTPException, WebSocket
from pydantic import BaseModel
import asyncio
from alphahound_serial import device as alphahound_device
from peak_detection import detect_peaks
from isotope_database import identify_isotopes, identify_decay_chains
from core import DEFAULT_SETTINGS, apply_abundance_weighting, apply_confidence_filtering

router = APIRouter(prefix="/device", tags=["device"])

class SpectrumRequest(BaseModel):
    count_minutes: float = 0

@router.get("/ports")
async def list_serial_ports():
    try:
        ports = alphahound_device.list_ports()
        return {"ports": ports}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing ports: {str(e)}")

@router.post("/connect")
async def connect_device(request: dict):
    port = request.get("port")
    if not port:
        raise HTTPException(status_code=400, detail="Port required")
    
    if alphahound_device.is_connected():
        return {"status": "already_connected", "port": port}
    
    success = alphahound_device.connect(port)
    if success:
        return {"status": "connected", "port": port}
    else:
        raise HTTPException(status_code=500, detail="Failed to connect to device")

@router.post("/disconnect")
async def disconnect_device():
    alphahound_device.disconnect()
    return {"status": "disconnected"}

@router.get("/status")
async def device_status():
    return {
        "connected": alphahound_device.is_connected(),
        "dose_rate": alphahound_device.get_dose_rate() if alphahound_device.is_connected() else None
    }

@router.get("/dose")
async def get_dose_rate():
    if not alphahound_device.is_connected():
        raise HTTPException(status_code=400, detail="Device not connected")
    return {"dose_rate": alphahound_device.get_dose_rate()}

@router.post("/spectrum")
async def acquire_spectrum(request: SpectrumRequest):
    if not alphahound_device.is_connected():
        raise HTTPException(status_code=400, detail="Device not connected")
    
    count_minutes = request.count_minutes
    if count_minutes > 0:
        alphahound_device.clear_spectrum()
        wait_seconds = count_minutes * 60
        for i in range(int(wait_seconds)):
            await asyncio.sleep(1)
            
    alphahound_device.request_spectrum()
    max_wait = 5 if count_minutes == 0 else 30
    waited = 0
    while waited < max_wait:
        await asyncio.sleep(0.5)
        waited += 0.5
        spectrum = alphahound_device.get_spectrum()
        if len(spectrum) >= 1024:
            break
            
    spectrum = alphahound_device.get_spectrum()
    counts = [count for count, energy in spectrum]
    energies = [energy for count, energy in spectrum]
    
    peaks = detect_peaks(energies, counts)
    if peaks:
        all_isotopes = identify_isotopes(
            peaks, 
            energy_tolerance=DEFAULT_SETTINGS['energy_tolerance'],
            mode=DEFAULT_SETTINGS.get('mode', 'simple')
        )
        all_chains = identify_decay_chains(peaks, all_isotopes, energy_tolerance=DEFAULT_SETTINGS['energy_tolerance'])
        weighted_chains = apply_abundance_weighting(all_chains)
        isotopes, decay_chains = apply_confidence_filtering(all_isotopes, weighted_chains, DEFAULT_SETTINGS)
    else:
        isotopes = []
        decay_chains = []
    
    return {
        "counts": counts,
        "energies": energies,
        "peaks": peaks,
        "isotopes": isotopes,
        "decay_chains": decay_chains,
        "metadata": {
            "source": "AlphaHound Device",
            "channels": len(counts),
            "count_time_minutes": count_minutes
        }
    }

@router.post("/clear")
async def clear_device_spectrum():
    if not alphahound_device.is_connected():
        raise HTTPException(status_code=400, detail="Device not connected")
    alphahound_device.clear_spectrum()
    return {"status": "cleared"}

# Note: WebSocket endpoint cannot be easily moved to APIRouter in older FastAPI versions without issues,
# but in recent versions it works. We will try to include it here or keep it in main.
# It's safer to keep WS in main if we encounter issues, but let's try moving it.
# Actually, let's keep WS in main.py for maximum stability as some servers handle router WS differently.
# WAIT - Router supports WS. Let's do it cleanly.
