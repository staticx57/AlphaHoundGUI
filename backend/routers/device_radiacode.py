"""
Radiacode Device API Router

FastAPI endpoints for Radiacode 103/103G/110 device control.
Mirrors the AlphaHound device API pattern for consistency.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from radiacode_driver import radiacode_device
from analysis_utils import analyze_spectrum_peaks

router = APIRouter(prefix="/radiacode", tags=["radiacode"])


class RadiacodeConnectRequest(BaseModel):
    """Request model for Radiacode connection."""
    use_bluetooth: bool = Field(default=False, description="Use Bluetooth/BLE instead of USB")
    bluetooth_mac: Optional[str] = Field(default=None, description="Bluetooth/BLE address (required if use_bluetooth=True)")


@router.get("/available")
async def check_radiacode_available():
    """Check if Radiacode library is installed and available."""
    return {
        "available": radiacode_device.is_available,
        "ble_available": radiacode_device.is_ble_available,
        "message": "Radiacode library available" if radiacode_device.is_available else "Radiacode library not installed. Run: pip install radiacode"
    }


@router.get("/scan-ble")
async def scan_radiacode_ble(timeout: float = 5.0) -> List[Dict[str, Any]]:
    """
    Scan for nearby Radiacode BLE devices.
    
    Args:
        timeout: Scan duration in seconds (default: 5.0)
        
    Returns:
        List of discovered devices with name, address, and rssi
    """
    if not radiacode_device.is_ble_available:
        raise HTTPException(
            status_code=501,
            detail="BLE not available. Install bleak: pip install bleak"
        )
    
    # Import and call the async scan function directly
    try:
        from radiacode_bleak_transport import scan_for_radiacode_devices
        devices = await scan_for_radiacode_devices(timeout=timeout)
        return devices
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"BLE scan failed: {str(e)}")


@router.post("/connect")
async def connect_radiacode(request: RadiacodeConnectRequest):
    """
    Connect to a Radiacode device.
    
    USB connection works on all platforms.
    Bluetooth/BLE works on all platforms (Windows, macOS, Linux) via bleak.
    """
    if not radiacode_device.is_available:
        raise HTTPException(
            status_code=501,
            detail="Radiacode library not installed. Run: pip install radiacode"
        )
    
    if radiacode_device.is_connected():
        return {"status": "already_connected", "device_info": radiacode_device.get_device_info()}
    
    success = radiacode_device.connect(
        address=request.bluetooth_mac,
        use_bluetooth=request.use_bluetooth
    )
    
    if not success:
        error = radiacode_device.get_last_error() or "Unknown connection error"
        raise HTTPException(status_code=400, detail=error)
    
    return {
        "status": "connected",
        "device_info": radiacode_device.get_device_info()
    }


@router.post("/disconnect")
async def disconnect_radiacode():
    """Disconnect from Radiacode device."""
    if not radiacode_device.is_connected():
        return {"status": "not_connected"}
    
    radiacode_device.disconnect()
    return {"status": "disconnected"}


@router.get("/status")
async def get_radiacode_status():
    """Get current Radiacode connection status and device info."""
    return {
        "connected": radiacode_device.is_connected(),
        "available": radiacode_device.is_available,
        "device_info": radiacode_device.get_device_info() if radiacode_device.is_connected() else None,
        "last_error": radiacode_device.get_last_error()
    }


@router.get("/dose")
async def get_radiacode_dose():
    """
    Get current dose rate from Radiacode device.
    
    Returns dose rate in μSv/h.
    """
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    dose_rate = radiacode_device.get_dose_rate()
    
    if dose_rate is None:
        raise HTTPException(status_code=500, detail="Failed to read dose rate")
    
    return {
        "dose_rate_uSv_h": dose_rate,
        "unit": "μSv/h"
    }


@router.get("/spectrum")
async def get_radiacode_spectrum(analyze: bool = True):
    """
    Get current spectrum from Radiacode device.
    
    Args:
        analyze: If True, run peak detection and isotope identification
        
    Returns:
        Spectrum data with counts, energies, and optional analysis
    """
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    counts, energies, metadata = radiacode_device.get_spectrum()
    
    if not counts:
        raise HTTPException(status_code=500, detail="Failed to read spectrum")
    
    result = {
        "counts": counts,
        "energies": energies,
        "metadata": metadata,
        "is_calibrated": True  # Radiacode provides calibration
    }
    
    print(f"[Radiacode] Fetched {len(counts)} channels, duration: {metadata.get('duration_s')}s")
    # Run analysis if requested
    if analyze and len(counts) > 0:
        try:
            # Use common enhanced analysis pipeline
            duration = metadata.get("duration_s")
            live_time = float(duration) if duration is not None else 0.0
            result = analyze_spectrum_peaks(result, is_calibrated=True, live_time=live_time)
            print(f"[Radiacode] Analysis complete: {len(result.get('peaks', []))} peaks, {len(result.get('isotopes', []))} isotopes")
        except Exception as e:
            import traceback
            print(f"[Radiacode] Analysis error: {e}")
            traceback.print_exc()
            # Return raw spectrum without analysis rather than failing
            result["analysis_error"] = str(e)
    
    return result


@router.post("/clear")
async def clear_radiacode_spectrum():
    """Clear/reset accumulated spectrum on Radiacode device."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    success = radiacode_device.clear_spectrum()
    
    if not success:
        error = radiacode_device.get_last_error() or "Failed to clear spectrum"
        raise HTTPException(status_code=500, detail=error)
    
    return {"status": "spectrum_cleared"}


@router.post("/reset-dose")
async def reset_radiacode_dose():
    """Reset dose accumulator on Radiacode device."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    success = radiacode_device.reset_dose()
    
    if not success:
        error = radiacode_device.get_last_error() or "Failed to reset dose"
        raise HTTPException(status_code=500, detail=error)
    
    return {"status": "dose_reset"}
