from fastapi import APIRouter, File, UploadFile, HTTPException, Response
from pydantic import BaseModel
from n42_parser import parse_n42
from csv_parser import parse_csv_spectrum
from peak_detection import detect_peaks
from isotope_database import identify_isotopes, identify_decay_chains
from core import DEFAULT_SETTINGS, UPLOAD_SETTINGS, apply_abundance_weighting, apply_confidence_filtering
from spectral_analysis import fit_gaussian, calibrate_energy, subtract_background
from report_generator import generate_pdf_report
from ml_analysis import get_ml_identifier

router = APIRouter(tags=["analysis"])

class AnalysisRequest(BaseModel):
    energies: list
    counts: list
    peaks: list 

class CalibrationRequest(BaseModel):
    channels: list
    known_energies: list

class ReportRequest(BaseModel):
    filename: str
    metadata: dict
    energies: list
    counts: list
    peaks: list = []
    isotopes: list = []
    isotopes: list = []
    decay_chains: list = []

class BackgroundSubtractionRequest(BaseModel):
    source_counts: list
    background_counts: list
    scaling_factor: float = 1.0

class MLIdentifyRequest(BaseModel):
    counts: list

@router.get("/settings")
async def get_settings():
    return DEFAULT_SETTINGS

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    filename = file.filename.lower()
    content = await file.read()
    
    if filename.endswith('.n42') or filename.endswith('.xml'):
        try:
            content_str = content.decode('utf-8')
            result = parse_n42(content_str)
            if "error" in result: raise HTTPException(status_code=400, detail=result["error"])
            
            if result.get("counts") and result.get("energies"):
                peaks = detect_peaks(result["energies"], result["counts"])
                result["peaks"] = peaks
                
                if peaks:
                    is_calibrated = result.get("is_calibrated", True)
                    live_time = float(result.get("metadata", {}).get("live_time", 0))
                    
                    if is_calibrated and live_time > 30.0:
                        current_settings = DEFAULT_SETTINGS
                    else:
                        current_settings = UPLOAD_SETTINGS
                    
                    all_isotopes = identify_isotopes(peaks, energy_tolerance=current_settings['energy_tolerance'], mode=current_settings.get('mode', 'simple'))
                    all_chains = identify_decay_chains(peaks, all_isotopes, energy_tolerance=current_settings['energy_tolerance'])
                    weighted_chains = apply_abundance_weighting(all_chains)
                    isotopes, decay_chains = apply_confidence_filtering(all_isotopes, weighted_chains, current_settings)
                    
                    result["isotopes"] = isotopes
                    result["decay_chains"] = decay_chains
                else:
                     result["isotopes"] = []
                     result["decay_chains"] = []
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error parsing N42: {str(e)}")

    elif filename.endswith('.csv'):
        try:
             result = parse_csv_spectrum(content, filename)
             if result.get("counts") and result.get("energies"):
                 peaks = detect_peaks(result["energies"], result["counts"])
                 result["peaks"] = peaks
                 
                 if peaks:
                     is_calibrated = result.get("is_calibrated", False)
                     current_settings = DEFAULT_SETTINGS if is_calibrated else UPLOAD_SETTINGS
                     
                     all_isotopes = identify_isotopes(peaks, energy_tolerance=current_settings['energy_tolerance'], mode=current_settings.get('mode', 'simple'))
                     all_chains = identify_decay_chains(peaks, all_isotopes, energy_tolerance=current_settings['energy_tolerance'])
                     weighted_chains = apply_abundance_weighting(all_chains)
                     isotopes, decay_chains = apply_confidence_filtering(all_isotopes, weighted_chains, current_settings)
                     
                     result["isotopes"] = isotopes
                     result["decay_chains"] = decay_chains
                 else:
                     result["isotopes"] = []
                     result["decay_chains"] = []
             return result
        except Exception as e:
             raise HTTPException(status_code=500, detail=str(e))
    else:
        raise HTTPException(status_code=400, detail="Unsupported format")

@router.post("/analyze/fit-peaks")
async def analyze_fit_peaks(request: AnalysisRequest):
    try:
        peak_centers = []
        for p in request.peaks:
            if isinstance(p, dict): peak_centers.append(p.get("energy", 0))
            elif isinstance(p, (int, float)): peak_centers.append(p)
        fits = fit_gaussian(request.energies, request.counts, peak_centers)
        return {"fits": fits}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze/calibrate")
async def analyze_calibrate(request: CalibrationRequest):
    try:
        calibrated_energies, params = calibrate_energy(request.channels, request.known_energies, request.channels)
        return {"calibrated_energies": calibrated_energies, "params": params}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/export/pdf")
async def export_pdf(request: ReportRequest):
    try:
        pdf_bytes = generate_pdf_report(request.dict())
        filename = f"{request.filename}_report.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_bytes))
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze/subtract-background")
async def analyze_subtract_background(request: BackgroundSubtractionRequest):
    try:
        net_counts = subtract_background(
            request.source_counts, 
            request.background_counts, 
            request.scaling_factor
        )
        return {"net_counts": net_counts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze/ml-identify")
async def ml_identify(request: MLIdentifyRequest):
    """Machine Learning isotope identification using PyRIID"""
    try:
        ml = get_ml_identifier()
        if ml is None:
            raise HTTPException(status_code=501, detail="PyRIID not installed")
        results = ml.identify(request.counts, top_k=5)
        return {"predictions": results}
    except ImportError as e:
        raise HTTPException(status_code=501, detail="PyRIID not installed")
    except Exception as e:
        print(f"[ML] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
