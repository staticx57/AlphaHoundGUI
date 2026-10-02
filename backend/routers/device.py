from fastapi import APIRouter, HTTPException, WebSocket
from .analysis import sanitize_for_json
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
import asyncio
from datetime import datetime, timezone, timedelta
import re
from alphahound_serial import device as alphahound_device
from radiacode_driver import radiacode_device
from device_calibration import energies_from_device_spectrum, SOURCE_DEVICE
from analysis_utils import analyze_spectrum_peaks, sanitize_for_json

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
    is_connected = alphahound_device.is_connected()
    return {
        "connected": is_connected,
        "dose_rate": alphahound_device.get_dose_rate() if is_connected else None,
        "temperature": alphahound_device.get_temperature() if is_connected else None,
        "comp_factor": alphahound_device.get_comp_factor() if is_connected else None
    }

@router.get("/dose")
async def get_dose_rate():
    if not alphahound_device.is_connected():
        raise HTTPException(status_code=400, detail="Device not connected")
    return {"dose_rate": alphahound_device.get_dose_rate()}

@router.post("/display/{direction}")
async def change_display_mode(direction: str):
    """
    Cycle device display mode.
    - direction: 'next' or 'prev'
    - Sends 'E' command for next, 'Q' command for previous
    """
    if not alphahound_device.is_connected():
        raise HTTPException(status_code=400, detail="Device not connected")
    
    if direction == "next":
        alphahound_device.send_command("E")
        return {"status": "ok", "action": "display_next"}
    elif direction == "prev":
        alphahound_device.send_command("Q")
        return {"status": "ok", "action": "display_prev"}
    else:
        raise HTTPException(status_code=400, detail="Invalid direction. Use 'next' or 'prev'")

@router.post("/clear")
async def clear_spectrum():
    """
    Clear/reset the spectrum on the device (W command).
    This wipes all accumulated counts.
    """
    if not alphahound_device.is_connected():
        raise HTTPException(status_code=400, detail="Device not connected")
    
    alphahound_device.clear_spectrum()
    return {"status": "ok", "action": "spectrum_cleared"}

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
    # Use the device's own (nonlinear) energy axis; linear fallback only if it is unusable
    energies, energy_source = energies_from_device_spectrum(spectrum)
    
    # Use actual duration if provided, otherwise use count_minutes
    actual_duration_seconds = request.actual_duration_s if request.actual_duration_s else (count_minutes * 60)

    # Use common enhanced analysis pipeline
    result = {
        "counts": counts,
        "energies": energies,
        "metadata": {
            "source": "AlphaHound Device",
            "channels": len(counts),
            "energy_calibration": energy_source
        }
    }
    # A guessed linear fallback axis is not a calibration: identification is skipped with a warning
    result = analyze_spectrum_peaks(result, is_calibrated=(energy_source == SOURCE_DEVICE), live_time=float(actual_duration_seconds))
    
    # Extract results for backward compatibility in the response
    peaks = result.get("peaks", [])
    isotopes = result.get("isotopes", [])
    decay_chains = result.get("decay_chains", [])
    
    # Calculate acquisition timing for N42 export
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(seconds=actual_duration_seconds)
    
    return sanitize_for_json({
        "counts": counts,
        "energies": energies,
        "peaks": peaks,
        "isotopes": isotopes,
        "decay_chains": decay_chains,
        "metadata": {
            "source": "AlphaHound Device",
            "channels": len(counts),
            "energy_calibration": energy_source,
            "count_time_minutes": (actual_duration_seconds / 60),
            # N42 export fields
            "acquisition_time": actual_duration_seconds,
            "live_time": actual_duration_seconds,
            "real_time": actual_duration_seconds,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat()
        }
    })

# ============================================================
# Server-Side Acquisition Endpoints (Browser-Independent)
# ============================================================

from acquisition_manager import acquisition_manager


class ManagedAcquisitionRequest(BaseModel):
    """Request model for managed acquisition."""
    duration_minutes: float = Field(..., gt=0, le=MAX_ACQUISITION_MINUTES)
    device: Literal["alphahound", "radiacode"] = "alphahound"


UREM_TO_USV = 0.01  # AlphaHound reports dose rate in uRem/h (1 uRem = 0.01 uSv)


def alphahound_dose_rate_uSv_h():
    if not alphahound_device.is_connected():
        return None
    return alphahound_device.get_dose_rate() * UREM_TO_USV


class RadiacodeAcquisitionDevice:
    """Adapts the Radiacode driver to the acquisition manager's device interface."""

    calibration_source = "device"

    def is_connected(self):
        return radiacode_device.is_connected()

    def clear_spectrum(self):
        radiacode_device.clear_spectrum()

    def request_spectrum(self):
        pass  # Radiacode spectra are read on demand

    def dose_rate_uSv_h(self):
        return radiacode_device.get_dose_rate()  # already uSv/h

    device_duration_s = None  # accumulation time reported by the device itself

    def get_spectrum(self):
        counts, energies, meta = radiacode_device.get_spectrum()
        self.device_duration_s = (meta or {}).get('duration_s')
        self.calibration_source = (meta or {}).get("calibration_source", "device")
        return list(zip(counts, energies)) if counts else []


@router.get("/spectrum/current")
async def get_current_spectrum():
    """
    Get the current cumulative spectrum from the device WITHOUT clearing.
    
    The AlphaHound device internally accumulates counts continuously.
    This endpoint downloads whatever is currently on the device,
    useful for checking accumulation or resuming from a browser disconnect.
    
    Returns:
        Same format as /device/spectrum but doesn't affect device state
    """
    if not alphahound_device.is_connected():
        raise HTTPException(status_code=400, detail="Device not connected")
    
    alphahound_device.request_spectrum()
    max_wait = 10
    waited = 0
    while waited < max_wait:
        await asyncio.sleep(0.5)
        waited += 0.5
        spectrum = alphahound_device.get_spectrum()
        if len(spectrum) >= 1024:
            break
    
    spectrum = alphahound_device.get_spectrum()
    if len(spectrum) < 1024:
        raise HTTPException(status_code=500, detail="Failed to get spectrum from device")
    
    counts = [count for count, energy in spectrum]
    energies, energy_source = energies_from_device_spectrum(spectrum)
    
    # Use common enhanced analysis pipeline
    result = {
        "counts": counts,
        "energies": energies,
        "metadata": {
            "source": "AlphaHound Device (Current Cumulative)",
            "channels": len(counts),
            "note": "This is the device's internal accumulation - not time-stamped",
            "energy_calibration": energy_source
        }
    }
    result["is_calibrated"] = (energy_source == SOURCE_DEVICE)
    result = analyze_spectrum_peaks(result, is_calibrated=(energy_source == SOURCE_DEVICE))
    return result


@router.post("/acquisition/start")
async def start_managed_acquisition(request: ManagedAcquisitionRequest):
    """
    Start a server-managed acquisition.
    
    The acquisition runs independently of the browser - timing, checkpoints,
    and auto-save are all handled server-side. This survives browser tab
    throttling, display sleep, or even tab closure.
    
    Args:
        duration_minutes: How long to acquire (1 minute to 24 hours)
        
    Returns:
        Status dict with success flag
    """
    if request.device == "radiacode":
        from routers.device_radiacode import radiacode_identity
        ident = radiacode_identity()
        rc_dev = RadiacodeAcquisitionDevice()
        result = await acquisition_manager.start(request.duration_minutes, rc_dev,
                                                 source_name=f"Radiacode Device ({ident['instrument_model']})",
                                                 dose_rate_fn=rc_dev.dose_rate_uSv_h, instrument=ident)
    else:
        result = await acquisition_manager.start(request.duration_minutes, alphahound_device,
                                                 dose_rate_fn=alphahound_dose_rate_uSv_h,
                                                 instrument={"instrument_model": "AlphaHound"})
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/acquisition/status")
async def get_acquisition_status():
    """
    Get current acquisition status.
    
    Returns:
        State dict including:
        - status: 'idle', 'acquiring', 'finalizing', 'complete', 'stopped', 'error'
        - is_active: bool
        - elapsed_seconds: float
        - remaining_seconds: float
        - progress_percent: float
        - last_checkpoint: ISO timestamp
        - final_filename: str (when complete)
    """
    state = acquisition_manager.get_state()
    
    # Include latest spectrum data if acquisition is active
    if state.get("is_active"):
        data = acquisition_manager.get_latest_data()
        if data:
            state["spectrum_data"] = data
    
    return state


@router.post("/acquisition/stop")
async def stop_managed_acquisition():
    """
    Stop current acquisition and finalize.
    
    The acquisition will save its final spectrum to a timestamped N42 file
    and clean up the checkpoint file.
    
    Returns:
        Status dict with final_filename
    """
    result = await acquisition_manager.stop()
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/acquisition/data")
async def get_acquisition_data():
    """
    Get latest spectrum data from active acquisition.
    
    Use this for UI updates without affecting acquisition timing.
    
    Returns:
        Spectrum data dict (counts, energies, peaks, isotopes)
    """
    data = acquisition_manager.get_latest_data()
    if not data:
        raise HTTPException(status_code=404, detail="No acquisition data available")
    return data


@router.get("/capabilities")
async def get_device_capabilities():
    """
    Get device capabilities for UI feature gating.
    
    Returns which features are supported by the AlphaHound device.
    """
    return {
        "device_type": "alphahound",
        "capabilities": {
            "timedAcquisition": True,
            "serverManagedAcquisition": True,
            "temperature": True,
            "displayModeToggle": True,
            "clearSpectrum": True,
            "doseReset": False,
            "deviceSettings": False,
            "bleConnection": False
        }
    }

