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
    
    # If no data available yet (data_buf empty), return 0 instead of erroring
    if dose_rate is None:
        dose_rate = 0.0
    
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


# ============================================================
# Device Settings Endpoints (Radiacode-specific)
# ============================================================

class RadiacodeSettingsRequest(BaseModel):
    """Request model for device settings update."""
    brightness: Optional[int] = Field(default=None, ge=0, le=9, description="Display brightness 0-9")
    sound: Optional[bool] = Field(default=None, description="Sound alerts enabled")
    vibration: Optional[bool] = Field(default=None, description="Vibration alerts enabled")
    display_off_time: Optional[int] = Field(default=None, ge=0, description="Display auto-off seconds (0=never)")


@router.post("/settings")
async def update_radiacode_settings(request: RadiacodeSettingsRequest):
    """
    Update Radiacode device settings.
    
    Only provided fields will be updated.
    """
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    results = {}
    
    if request.brightness is not None:
        results["brightness"] = radiacode_device.set_brightness(request.brightness)
    
    if request.sound is not None:
        results["sound"] = radiacode_device.set_sound(request.sound)
    
    if request.vibration is not None:
        results["vibration"] = radiacode_device.set_vibration(request.vibration)
    
    if request.display_off_time is not None:
        results["display_off_time"] = radiacode_device.set_display_off_time(request.display_off_time)
    
    # Check if any settings failed
    failures = [k for k, v in results.items() if not v]
    if failures:
        return {
            "status": "partial_success",
            "results": results,
            "failed": failures,
            "last_error": radiacode_device.get_last_error()
        }
    
    return {"status": "success", "results": results}


@router.get("/configuration")
async def get_radiacode_configuration():
    """Get full device configuration dump (for debugging/advanced users)."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    config = radiacode_device.get_configuration()
    
    if config is None:
        error = radiacode_device.get_last_error() or "Failed to get configuration"
        raise HTTPException(status_code=500, detail=error)
    
    return {"configuration": config}


@router.get("/capabilities")
async def get_radiacode_capabilities():
    """
    Get device capabilities for UI feature gating.
    
    Returns which features are supported by the Radiacode device.
    """
    return {
        "device_type": "radiacode",
        "capabilities": {
            "timedAcquisition": True,
            "serverManagedAcquisition": True,
            "temperature": False,
            "displayModeToggle": False,
            "clearSpectrum": True,
            "doseReset": True,
            "deviceSettings": True,
            "bleConnection": radiacode_device.is_ble_available
        }
    }


# ============================================================
# Device Settings Endpoints
# ============================================================

@router.post("/settings/brightness")
async def set_radiacode_brightness(level: int):
    """Set Radiacode display brightness (0-9)."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    if radiacode_device.set_brightness(level):
        return {"status": "success", "brightness": level}
    else:
        error = radiacode_device.get_last_error() or "Failed to set brightness"
        raise HTTPException(status_code=500, detail=error)


@router.post("/settings/sound")
async def set_radiacode_sound(enabled: bool):
    """Enable or disable sound alerts."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    if radiacode_device.set_sound(enabled):
        return {"status": "success", "sound_enabled": enabled}
    else:
        error = radiacode_device.get_last_error() or "Failed to set sound"
        raise HTTPException(status_code=500, detail=error)


@router.post("/settings/vibration")
async def set_radiacode_vibration(enabled: bool):
    """Enable or disable vibration alerts."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    if radiacode_device.set_vibration(enabled):
        return {"status": "success", "vibration_enabled": enabled}
    else:
        error = radiacode_device.get_last_error() or "Failed to set vibration"
        raise HTTPException(status_code=500, detail=error)


@router.post("/settings/display-timeout")
async def set_radiacode_display_timeout(seconds: int):
    """Set display auto-off timeout."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    if radiacode_device.set_display_off_time(seconds):
        return {"status": "success", "timeout_seconds": seconds}
    else:
        error = radiacode_device.get_last_error() or "Failed to set display timeout"
        raise HTTPException(status_code=500, detail=error)


@router.post("/settings/language")
async def set_radiacode_language(language: str):
    """Set device language ('en' or 'ru')."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    if radiacode_device.set_language(language):
        return {"status": "success", "language": language}
    else:
        error = radiacode_device.get_last_error() or "Failed to set language"
        raise HTTPException(status_code=500, detail=error)


# ============================================================
# Phase 1: Quick Win Features
# ============================================================

@router.get("/spectrum/accumulated")
async def get_accumulated_spectrum(analyze: bool = True):
    """Get long-term accumulated spectrum from device memory (persists across clears)."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    spectrum = radiacode_device.get_accumulated_spectrum()
    
    if spectrum is None:
        error = radiacode_device.get_last_error() or "Failed to get accumulated spectrum"
        raise HTTPException(status_code=500, detail=error)
    
    # Transform to standard format for analysis
    # Generate energies from calibration coefficients
    energies = []
    for i in range(len(spectrum["counts"])):
        energies.append(spectrum["a0"] + spectrum["a1"] * i + spectrum["a2"] * i * i)
    
    result = {
        "counts": spectrum["counts"],
        "energies": energies,
        "duration": spectrum["duration"],
        "a0": spectrum["a0"],
        "a1": spectrum["a1"],
        "a2": spectrum["a2"],
        "is_calibrated": True
    }
    
    # Run analysis if requested (same as regular spectrum endpoint)
    if analyze and len(spectrum["counts"]) > 0:
        try:
            live_time = float(spectrum["duration"]) if spectrum["duration"] else 0.0
            result = analyze_spectrum_peaks(result, is_calibrated=True, live_time=live_time)
            print(f"[Radiacode] Accumulated analysis: {len(result.get('peaks', []))} peaks, {len(result.get('isotopes', []))} isotopes")
        except Exception as e:
            import traceback
            print(f"[Radiacode] Accumulated analysis error: {e}")
            traceback.print_exc()
            result["analysis_error"] = str(e)
    
    return result


@router.post("/settings/display-direction")
async def set_display_direction(direction: str):
    """Set device display orientation (normal/reversed/auto)."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    if radiacode_device.set_display_direction(direction):
        return {"status": "success", "direction": direction}
    else:
        error = radiacode_device.get_last_error() or "Failed to set display direction"
        raise HTTPException(status_code=500, detail=error)


@router.post("/time/sync")
async def sync_device_time():
    """Synchronize device clock with computer time."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    if radiacode_device.sync_device_time():
        return {"status": "success", "message": "Device time synchronized"}
    else:
        error = radiacode_device.get_last_error() or "Failed to sync device time"
        raise HTTPException(status_code=500, detail=error)


@router.get("/info/hw-serial")
async def get_hw_serial():
    """Get hardware serial number."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    hw_serial = radiacode_device.get_hw_serial_number()
    
    if hw_serial is None:
        error = radiacode_device.get_last_error() or "Failed to get hardware serial"
        raise HTTPException(status_code=500, detail=error)
    
    return {"hw_serial_number": hw_serial}


# ============================================================
# Phase 2: Advanced Controls
# ============================================================

@router.get("/calibration/energy")
async def get_energy_calibration():
    """Get current energy calibration coefficients."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    calibration = radiacode_device.get_energy_calibration()
    
    if calibration is None:
        error = radiacode_device.get_last_error() or "Failed to get calibration"
        raise HTTPException(status_code=500, detail=error)
    
    return calibration


@router.post("/calibration/energy")
async def set_energy_calibration(a0: float, a1: float, a2: float):
    """Set energy calibration coefficients (Energy = a0 + a1*channel + a2*channel^2)."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    if radiacode_device.set_energy_calibration(a0, a1, a2):
        return {"status": "success", "a0": a0, "a1": a1, "a2": a2}
    else:
        error = radiacode_device.get_last_error() or "Failed to set calibration"
        raise HTTPException(status_code=500, detail=error)


@router.post("/settings/sound-control")
async def set_sound_control(search: bool = False, detector: bool = False, clicks: bool = False):
    """Set advanced sound control flags."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    if radiacode_device.set_sound_control(search, detector, clicks):
        return {"status": "success", "search": search, "detector": detector, "clicks": clicks}
    else:
        error = radiacode_device.get_last_error() or "Failed to set sound control"
        raise HTTPException(status_code=500, detail=error)


@router.post("/settings/vibration-control")
async def set_vibration_control(search: bool = False, detector: bool = False):
    """Set advanced vibration control flags (clicks not supported for vibration)."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    if radiacode_device.set_vibration_control(search, detector):
        return {"status": "success", "search": search, "detector": detector}
    else:
        error = radiacode_device.get_last_error() or "Failed to set vibration control"
        raise HTTPException(status_code=500, detail=error)


@router.post("/power/off")
async def power_off_device():
    """Power off the Radiacode device. User must manually power back on."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    if radiacode_device.power_off_device():
        # Device is powering off, disconnect locally
        radiacode_device.disconnect()
        return {"status": "success", "message": "Device powering off"}
    else:
        error = radiacode_device.get_last_error() or "Failed to power off device"
        raise HTTPException(status_code=500, detail=error)



@router.get("/info/extended")
async def get_radiacode_extended_info():
    """
    Get extended device information including accumulated dose and configuration.
    
    Returns:
        Extended device info with accumulated dose, configuration, etc.
    """
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    accumulated_dose = radiacode_device.get_accumulated_dose()
    configuration = radiacode_device.get_configuration()
    
    return {
        "accumulated_dose_uSv": accumulated_dose,
        "configuration": configuration,
        "device_info": radiacode_device.get_device_info()
    }


# ============================================================
# Phase 3: Info & Diagnostics
# ============================================================

@router.get("/status/flags")
async def get_status_flags():
    """Get device status flags (battery, alarms, etc.)."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    flags = radiacode_device.get_status_flags()
    return {"status_flags": flags}


@router.get("/info/fw-signature")
async def get_firmware_signature():
    """Get firmware signature info."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    signature = radiacode_device.get_firmware_signature()
    return {"fw_signature": signature}


@router.get("/messages")
async def get_text_message():
    """Get device text message/alert."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    message = radiacode_device.get_text_message()
    return {"message": message, "has_message": message is not None and len(message) > 0}


# ============================================================
# Phase 4: System Features
# ============================================================

@router.get("/capabilities/commands")
async def get_available_commands():
    """Get list of supported SFR commands (for auto-detection)."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    commands = radiacode_device.get_available_commands()
    return {"commands": commands}


@router.get("/info/base-time")
async def get_base_time():
    """Get device time reference for timestamp conversion."""
    if not radiacode_device.is_connected():
        raise HTTPException(status_code=400, detail="Radiacode not connected")
    
    base_time = radiacode_device.get_base_time()
    return {"base_time": base_time}




@router.get("/capabilities")
async def get_radiacode_capabilities():
    """
    Get device capabilities for UI feature gating.
    
    Returns which features are supported by the Radiacode device.
    """
    return {
        "device_type": "radiacode",
        "capabilities": {
            "timedAcquisition": True,
            "serverManagedAcquisition": True,
            "temperature": False,
            "displayModeToggle": False,
            "clearSpectrum": True,
            "doseReset": True,
            "deviceSettings": True,
            "bleConnection": radiacode_device.is_ble_available
        }
    }
