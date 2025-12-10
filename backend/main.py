from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from n42_parser import parse_n42
from csv_parser import parse_csv_spectrum
from peak_detection import detect_peaks
from isotope_database import identify_isotopes
from alphahound_serial import device as alphahound_device
import numpy as np
import os
import asyncio

app = FastAPI()

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
                
                # Add isotope identification
                if peaks:
                    isotopes = identify_isotopes(peaks)
                    result["isotopes"] = isotopes
            
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error parsing N42: {str(e)}")

    elif filename.endswith('.csv'):
        # Use Becquerel for CSV if available
        try:
             result = parse_csv_spectrum(content, filename)
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
    
    print("[API] Requesting spectrum from device...")
    alphahound_device.request_spectrum()
    
    # Wait for spectrum (with longer timeout for device response)
    max_wait = 30  # seconds
    waited = 0
    while waited < max_wait:
        await asyncio.sleep(0.5)
        waited += 0.5
        spectrum = alphahound_device.get_spectrum()
        print(f"[API] Waiting... {waited}s, spectrum length: {len(spectrum)}")
        if len(spectrum) >= 1024:
            break
    
    spectrum = alphahound_device.get_spectrum()
    if len(spectrum) < 1024:
        raise HTTPException(status_code=408, detail=f"Spectrum acquisition timeout ({len(spectrum)} channels received)")
    
    # Convert to counts and energies arrays
    counts = [count for count, energy in spectrum]
    energies = [energy for count, energy in spectrum]
    
    # Perform analysis
    peaks = detect_peaks(energies, counts)
    isotopes = identify_isotopes(peaks) if peaks else []
    
    return {
        "counts": counts,
        "energies": energies,
        "peaks": peaks,
        "isotopes": isotopes,
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

@app.post("/export/pdf")
async def export_pdf(request: ReportRequest):
    """Generate and download PDF report"""
    try:
        # Convert Pydantic model to dict for the generator
        data = request.dict()
        pdf_bytes = generate_pdf_report(data)
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={request.filename}_report.pdf"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
