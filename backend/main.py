from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from n42_parser import parse_n42
from csv_parser import parse_csv_spectrum
from peak_detection import detect_peaks
from isotope_database import identify_isotopes, identify_decay_chains
from alphahound_serial import device as alphahound_device
import numpy as np
import os
import asyncio

app = FastAPI()

# ========== Settings for Simple/Advanced Mode ==========
# Default settings for Simple mode
DEFAULT_SETTINGS = {
    "mode": "simple",
    "isotope_min_confidence": 30.0,
    "chain_min_confidence": 30.0,    # Reverted to 30% per user request (calibrated file)
    "energy_tolerance": 20.0,        # Reverted to 20.0 keV
    "chain_min_isotopes_medium": 3,  # Reverted to 3 to effectively filter random noise chains like U-235
    "chain_min_isotopes_high": 4,
    "max_isotopes": 5  # Limit for simple mode
}

# Settings for generic File Uploads (often uncalibrated/noisy)
UPLOAD_SETTINGS = DEFAULT_SETTINGS.copy()
UPLOAD_SETTINGS.update({
    "chain_min_confidence": 1.0,     # Loose 1% threshold for uploads
    "energy_tolerance": 30.0,        # Higher tolerance for uncalibrated drift
    "chain_min_isotopes_medium": 1   # Allow single-isotope structure (necessary for poor keys)
})

def apply_abundance_weighting(chains):
    """
    Apply natural abundance weighting to decay chain confidence scores.
    
    Based on authoritative sources (LBNL, NRC):
    - U-238: 99.274% of natural uranium (weight ~1.0)
    - U-235: 0.720% of natural uranium (weight ~0.007)  
    - Th-232: ~3.5× more abundant than U in Earth's crust
    
    This ensures U-238 always ranks higher than U-235 in natural samples,
    even when U-235 shows 100% of its (fewer) indicators.
    
    Args:
        chains: List of decay chain detections from identify_decay_chains()
    
    Returns:
        List of chains with weighted confidence scores
    """
    for chain in chains:
        # Get abundance weight from database (default 1.0)
        abundance_weight = chain.get('abundance_weight', 1.0)
        original_confidence = chain['confidence']
        
        # Apply logarithmic weighting to avoid over-correction
        # For U-238 (0.993): slight boost (~99%)
        # For U-235 (0.0072): strong penalty (~0.7%)
        # For Th-232 (1.0): no change
        import math
        
        if abundance_weight < 0.01:  # U-235 and similarly rare
            # Strong penalty for rare isotopes
            weighted_confidence = original_confidence * abundance_weight * 10
        elif abundance_weight > 0.9:  # U-238
            # Keep high, slight boost
            weighted_confidence = original_confidence * 1.05
        else:  # Th-232 and others
            weighted_confidence = original_confidence
        
        # Store both for transparency
        chain['confidence_unweighted'] = original_confidence
        chain['confidence'] = weighted_confidence
        chain['abundance_weight'] = abundance_weight
    
    return chains

def apply_confidence_filtering(isotopes, chains, settings):
    """
    Apply threshold filtering based on mode settings.
    isotope_database functions return ALL matches - this filters them.
    """
    # Filter isotopes by minimum confidence
    filtered_isotopes = [
        iso for iso in isotopes
        if iso['confidence'] >= settings.get('isotope_min_confidence', 40.0)
    ]
    
    # Limit number of isotopes in simple mode
    if settings.get('mode') == 'simple':
        filtered_isotopes = filtered_isotopes[:settings.get('max_isotopes', 5)]
    
    # Filter chains by minimum confidence and isotope count
    min_isotopes = settings.get('chain_min_isotopes_medium', 3)
    filtered_chains = []
    
    for chain in chains:
        # Calculate percentage of indicators found
        percentage = (chain['num_detected'] / chain['num_key_isotopes'] * 100) if chain['num_key_isotopes'] > 0 else 0
        
        # Improved confidence level logic using Settings
        high_threshold = settings.get('chain_min_isotopes_high', 4)
        med_threshold = settings.get('chain_min_isotopes_medium', 3)
        
        # HIGH: Meets high threshold OR ≥80% of indicators found
        # MEDIUM: Meets medium threshold OR ≥60% of indicators found
        if chain['num_detected'] >= high_threshold or percentage >= 80:
            chain['confidence_level'] = 'HIGH'
        elif chain['num_detected'] >= med_threshold or percentage >= 60:
            chain['confidence_level'] = 'MEDIUM'
        else:
            chain['confidence_level'] = 'LOW'
            
        # FORCE DOWNGRADE based on Weighted Confidence
        # This fixes the issue where U-235 (100% match but 0.72% abundance -> 7% score) shows as "HIGH"
        if chain['confidence'] < 15.0:
            chain['confidence_level'] = 'LOW'
        elif chain['confidence'] < 40.0 and chain['confidence_level'] == 'HIGH':
            chain['confidence_level'] = 'MEDIUM'
        
        # Apply filters (using WEIGHTED confidence)
        if chain['confidence'] >= settings.get('chain_min_confidence', 30.0) and chain['num_detected'] >= min_isotopes:
            filtered_chains.append(chain)
    
    # Re-sort by weighted confidence
    filtered_chains.sort(key=lambda x: x['confidence'], reverse=True)
    
    return filtered_isotopes, filtered_chains

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

@app.get("/")
def read_index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    filename = file.filename.lower()
    content = await file.read()
    
    if filename.endswith('.n42') or filename.endswith('.xml'):
        # Use custom parser for N42
        try:
            content_str = content.decode('utf-8')
            result = parse_n42(content_str)
            if "error" in result:
                 raise HTTPException(status_code=400, detail=result["error"])
            
            # Add peak detection
            if result.get("counts") and result.get("energies"):
                peaks = detect_peaks(result["energies"], result["counts"])
                result["peaks"] = peaks
                print(f"[DEBUG] Detected {len(peaks)} peaks")
                if peaks:
                    peak_energies = [p['energy'] for p in peaks]
                    print(f"[DEBUG] Peak energies: {peak_energies}")
                
                # Add isotope identification
                if peaks:
                    try:
                        # DYNAMIC SETTINGS SELECTION
                        # If file is calibrated (keV energies), use Strict settings (Default) to avoid false positives.
                        # If uncalibrated (Channels), use Robust settings (Upload) to find structure.
                        is_calibrated = result.get("is_calibrated", True) # Default to True (Strict) if unknown
                        
                        if is_calibrated:
                            current_settings = DEFAULT_SETTINGS
                            print(f"[DEBUG] File is CALIBRATED. Using STRICT settings.")
                        else:
                            current_settings = UPLOAD_SETTINGS
                            print(f"[DEBUG] File is UNCALIBRATED. Using ROBUST settings.")

                        # Get ALL isotopes and chains (no filtering at detection level) using selected settings
                        all_isotopes = identify_isotopes(
                            peaks, 
                            energy_tolerance=current_settings['energy_tolerance'],
                            mode=current_settings.get('mode', 'simple')
                        )
                        all_chains = identify_decay_chains(peaks, all_isotopes, energy_tolerance=current_settings['energy_tolerance'])
                        
                        # Apply abundance weighting (intermediate step)
                        weighted_chains = apply_abundance_weighting(all_chains)
                        
                        # Apply filtering based on selected settings
                        isotopes, decay_chains = apply_confidence_filtering(all_isotopes, weighted_chains, current_settings)
                        
                        result["isotopes"] = isotopes
                        result["decay_chains"] = decay_chains
                        
                        print(f"[DEBUG] Detected {len(all_isotopes)} total isotopes, filtered to {len(isotopes)}")
                        if isotopes:
                            for iso in isotopes[:3]:  # Show first 3
                                print(f"[DEBUG]   - {iso['isotope']}: {iso['confidence']:.0f}% confidence")
                        
                        print(f"[DEBUG] Detected {len(all_chains)} total chains, filtered to {len(decay_chains)}")
                        if decay_chains:
                            for chain in decay_chains:
                                print(f"[DEBUG]   - {chain['chain_name']}: {chain['confidence_level']} confidence")
                    except Exception as decay_error:
                        print(f"[ERROR] Decay chain detection failed: {str(decay_error)}")
                        import traceback
                        traceback.print_exc()
                        # Still return results without decay chains
                        result["isotopes"] = []
                        result["decay_chains"] = []
            
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error parsing N42: {str(e)}")

    elif filename.endswith('.csv'):
        # Use Becquerel for CSV if available
        try:
             result = parse_csv_spectrum(content, filename)
             
             # Perform full analysis (CSV parser only does basic isotope ID)
             if result.get("counts") and result.get("energies"):
                 # Re-detect peaks to be sure (or use parser's)
                 peaks = detect_peaks(result["energies"], result["counts"])
                 result["peaks"] = peaks
                 
                 if peaks:
                     try:
                         # DYNAMIC SETTINGS SELECTION
                         is_calibrated = result.get("is_calibrated", False) # Default to False for CSV if unknown
                         
                         if is_calibrated:
                             current_settings = DEFAULT_SETTINGS
                             print(f"[DEBUG] CSV is CALIBRATED. Using STRICT settings.")
                         else:
                             current_settings = UPLOAD_SETTINGS
                             print(f"[DEBUG] CSV is UNCALIBRATED. Using ROBUST settings.")

                         # Use selected settings
                         all_isotopes = identify_isotopes(
                             peaks, 
                             energy_tolerance=current_settings['energy_tolerance'],
                             mode=current_settings.get('mode', 'simple')
                         )
                         all_chains = identify_decay_chains(peaks, all_isotopes, energy_tolerance=current_settings['energy_tolerance'])
                         
                         # Apply weighting
                         weighted_chains = apply_abundance_weighting(all_chains)
                         
                         # Apply filtering with selected settings
                         isotopes, decay_chains = apply_confidence_filtering(all_isotopes, weighted_chains, current_settings)
                         
                         result["isotopes"] = isotopes
                         result["decay_chains"] = decay_chains
                         
                         print(f"[DEBUG] CSV Analysis: {len(isotopes)} isotopes, {len(decay_chains)} chains found with UPLOAD_SETTINGS")
                     except Exception as e:
                         print(f"[ERROR] CSV Analysis failed: {e}")
                         result["isotopes"] = []
                         result["decay_chains"] = []
                         
             return result
        except ImportError as e:
             raise HTTPException(status_code=501, detail=str(e))
        except ValueError as e:
             raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
             raise HTTPException(status_code=500, detail=str(e))

    else:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please use .n42 or .csv")


# ========== AlphaHound Device Control Endpoints ==========
# Credit: Based on AlphaHound Python Interface by NuclearGeekETH
# Device: RadView Detection AlphaHound™

@app.get("/device/ports")
async def list_serial_ports():
    """List available serial ports for AlphaHound device"""
    try:
        ports = alphahound_device.list_ports()
        return {"ports": ports}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing ports: {str(e)}")


@app.post("/device/connect")
async def connect_device(request: dict):
    """Connect to AlphaHound device on specified port"""
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


@app.post("/device/disconnect")
async def disconnect_device():
    """Disconnect from AlphaHound device"""
    alphahound_device.disconnect()
    return {"status": "disconnected"}


@app.get("/device/status")
async def device_status():
    """Get device connection status"""
    return {
        "connected": alphahound_device.is_connected(),
        "dose_rate": alphahound_device.get_dose_rate() if alphahound_device.is_connected() else None
    }


@app.get("/device/dose")
async def get_dose_rate():
    """Get current dose rate from device"""
    if not alphahound_device.is_connected():
        raise HTTPException(status_code=400, detail="Device not connected")
    
    return {"dose_rate": alphahound_device.get_dose_rate()}


from pydantic import BaseModel

class SpectrumRequest(BaseModel):
    count_minutes: float = 0

@app.post("/device/spectrum")
async def acquire_spectrum(request: SpectrumRequest):
    """Request spectrum acquisition from device with optional timed count"""
    if not alphahound_device.is_connected():
        raise HTTPException(status_code=400, detail="Device not connected")
    
    count_minutes = request.count_minutes
    print(f"[API] Received count_minutes: {count_minutes}")
    
    if count_minutes > 0:
        # Timed acquisition: clear, wait, then download
        print(f"[API] Starting timed count: {count_minutes} minutes...")
        alphahound_device.clear_spectrum()
        
        # Wait for specified time
        wait_seconds = count_minutes * 60
        for i in range(int(wait_seconds)):
            await asyncio.sleep(1)
            if i % 10 == 0:
                print(f"[API] Counting... {i}/{int(wait_seconds)}s")
    
    # Request spectrum from device
    print(f"[API] Requesting spectrum... (instant: {count_minutes == 0})")
    alphahound_device.request_spectrum()
    
    # For instant snapshot (count_minutes=0), use shorter timeout
    max_wait = 5 if count_minutes == 0 else 30
    waited = 0
    while waited < max_wait:
        await asyncio.sleep(0.5)
        waited += 0.5
        spectrum = alphahound_device.get_spectrum()
        if len(spectrum) >= 1024:
            break
    
    spectrum = alphahound_device.get_spectrum()
    
    # For instant snapshots, return partial data even if not full
    if count_minutes == 0 and len(spectrum) < 1024:
        print(f"[API] Snapshot: {len(spectrum)} channels (partial)")
    elif len(spectrum) < 1024:
        raise HTTPException(status_code=408, detail=f"Spectrum acquisition timeout ({len(spectrum)} channels received)")
    
    # Convert to counts and energies arrays
    counts = [count for count, energy in spectrum]
    energies = [energy for count, energy in spectrum]
    
    # Perform analysis
    peaks = detect_peaks(energies, counts)
    
    if peaks:
        # Get ALL isotopes and chains
        all_isotopes = identify_isotopes(
            peaks, 
            energy_tolerance=DEFAULT_SETTINGS['energy_tolerance'],
            mode=DEFAULT_SETTINGS.get('mode', 'simple')
        )
        all_chains = identify_decay_chains(peaks, all_isotopes, energy_tolerance=DEFAULT_SETTINGS['energy_tolerance'])
        
        # Apply abundance weighting (intermediate step)
        weighted_chains = apply_abundance_weighting(all_chains)
        
        # Apply filtering (Simple mode by default)
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
            "device": "RadView Detection AlphaHound",
            "channels": len(counts),
            "count_time_minutes": count_minutes,
            "tool": "AlphaHound Live Acquisition"
        }
    }


@app.post("/device/clear")
async def clear_device_spectrum():
    """Clear spectrum on device"""
    if not alphahound_device.is_connected():
        raise HTTPException(status_code=400, detail="Device not connected")
    
    alphahound_device.clear_spectrum()
    return {"status": "cleared"}


@app.get("/settings")
async def get_settings():
    """Get current default settings for Simple/Advanced mode"""
    return DEFAULT_SETTINGS


@app.websocket("/ws/dose")
async def websocket_dose_stream(websocket: WebSocket):
    """WebSocket endpoint for real-time dose rate streaming"""
    await websocket.accept()
    
    try:
        while True:
            if alphahound_device.is_connected():
                dose = alphahound_device.get_dose_rate()
                await websocket.send_json({"dose_rate": dose})
            else:
                await websocket.send_json({"dose_rate": None, "status": "disconnected"})
            
            await asyncio.sleep(1)  # Update every second
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()



from spectral_analysis import fit_gaussian, calibrate_energy

class AnalysisRequest(BaseModel):
    energies: list
    counts: list
    peaks: list # List of approximate peak centers

@app.post("/analyze/fit-peaks")
async def analyze_fit_peaks(request: AnalysisRequest):
    """Fit Gaussian profiles to peaks"""
    try:
        # Extract peak centers from the request (assuming request.peaks is list of dicts or floats)
        # If it's the structure returned by detect_peaks, it might be list of dicts
        peak_centers = []
        for p in request.peaks:
            if isinstance(p, dict):
                peak_centers.append(p.get("energy", 0))
            elif isinstance(p, (int, float)):
                peak_centers.append(p)
                
        fits = fit_gaussian(request.energies, request.counts, peak_centers)
        return {"fits": fits}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class CalibrationRequest(BaseModel):
    channels: list
    known_energies: list
    
@app.post("/analyze/calibrate")
async def analyze_calibrate(request: CalibrationRequest):
    """Perform energy calibration"""
    try:
        # channels = current peak indices or energies acting as uncalibrated values
        # known_energies = user entered true values
        calibrated_energies, params = calibrate_energy(request.channels, request.known_energies, request.channels)
        return {
            "calibrated_energies": calibrated_energies,
            "params": params
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



from reportlab.pdfgen import canvas
from fastapi.responses import Response
from report_generator import generate_pdf_report

class ReportRequest(BaseModel):
    filename: str
    metadata: dict
    energies: list
    counts: list
    peaks: list = []
    isotopes: list = []
    decay_chains: list = []  # Added for decay chain reporting

@app.post("/export/pdf")
async def export_pdf(request: ReportRequest):
    """Generate and download PDF report"""
    try:
        print(f"[PDF] Generating PDF for: {request.filename}")
        print(f"[PDF] Request data keys: {request.dict().keys()}")
        
        # Convert Pydantic model to dict for the generator
        data = request.dict()
        print(f"[PDF] Calling PDF generator...")
        pdf_bytes = generate_pdf_report(data)
        print(f"[PDF] Generated {len(pdf_bytes)} bytes")
        
        filename = f"{request.filename}_report.pdf"
        print(f"[PDF] Sending file: {filename}")
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_bytes))
            }
        )
    except Exception as e:
        print(f"[PDF] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
