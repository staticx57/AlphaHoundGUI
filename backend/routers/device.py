from fastapi import APIRouter, HTTPException, WebSocket
from pydantic import BaseModel, Field, field_validator
from typing import Optional
import asyncio
import re
from alphahound_serial import device as alphahound_device
from peak_detection import detect_peaks
from isotope_database import identify_isotopes, identify_decay_chains
from core import DEFAULT_SETTINGS, apply_abundance_weighting, apply_confidence_filtering

router = APIRouter(prefix="/device", tags=["device"])

# Validation constants
MAX_ACQUISITION_MINUTES = 1440  # 24 hours max - supports overnight acquisitions
PORT_PATTERN = re.compile(r'^(COM\d+|/dev/tty[A-Za-z0-9]+)$')

class ConnectRequest(BaseModel):
    """Request model for device connection."""
    port: str = Field(..., min_length=3, max_length=50)
    
    @field_validator('port')
    @classmethod
    def validate_port(cls, v):
        # Allow common port patterns: COM1-COM99, /dev/ttyUSB0, /dev/ttyACM0, etc.
        if not PORT_PATTERN.match(v):
            raise ValueError('Invalid port format. Expected COM# or /dev/tty*')
        return v

class SpectrumRequest(BaseModel):
    """Request model for spectrum acquisition."""
    count_minutes: float = Field(default=0, ge=0, le=MAX_ACQUISITION_MINUTES)
    actual_duration_s: Optional[float] = Field(default=None, ge=0, le=MAX_ACQUISITION_MINUTES * 60)

@router.get("/ports")
async def list_serial_ports():
    try:
        ports = alphahound_device.list_ports()
        return {"ports": ports}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing ports: {str(e)}")

@router.post("/connect")
async def connect_device(request: ConnectRequest):
    """Connect to AlphaHound device on specified port."""
    port = request.port
    
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
    
    # Calculate acquisition timing for N42 export
    from datetime import datetime, timezone, timedelta
    
    # Use actual duration if provided, otherwise use count_minutes
    actual_duration_seconds = request.actual_duration_s if request.actual_duration_s else (count_minutes * 60)
    
    # Calculate start time (current time minus acquisition duration)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(seconds=actual_duration_seconds)
    
    return {
        "counts": counts,
        "energies": energies,
        "peaks": peaks,
        "isotopes": isotopes,
        "decay_chains": decay_chains,
        "metadata": {
            "source": "AlphaHound Device",
            "channels": len(counts),
            "count_time_minutes": (actual_duration_seconds / 60),
            # N42 export fields
            "acquisition_time": actual_duration_seconds,
            "live_time": actual_duration_seconds,  # AlphaHound has no dead-time correction
            "real_time": actual_duration_seconds,   # AlphaHound has no dead-time correction
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat()
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
