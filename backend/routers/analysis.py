from fastapi import APIRouter, File, UploadFile, HTTPException, Response
from pydantic import BaseModel, field_validator, Field
from typing import List, Optional
from n42_parser import parse_n42
from csv_parser import parse_csv_spectrum
from peak_detection import detect_peaks
from isotope_database import identify_isotopes, identify_decay_chains
from core import DEFAULT_SETTINGS, UPLOAD_SETTINGS, apply_abundance_weighting, apply_confidence_filtering
from spectral_analysis import fit_gaussian, calibrate_energy, subtract_background
from report_generator import generate_pdf_report
from ml_analysis import get_ml_identifier

# Constants for input validation
MAX_FILE_SIZE_MB = 10
ALLOWED_EXTENSIONS = {'.n42', '.xml', '.csv'}
MAX_SPECTRUM_CHANNELS = 16384

router = APIRouter(tags=["analysis"])

class AnalysisRequest(BaseModel):
    """Request model for spectrum analysis."""
    energies: List[float] = Field(..., max_length=MAX_SPECTRUM_CHANNELS)
    counts: List[float] = Field(..., max_length=MAX_SPECTRUM_CHANNELS)
    peaks: List[dict] = Field(default=[])

    @field_validator('energies', 'counts')
    @classmethod
    def validate_spectrum_data(cls, v):
        if len(v) == 0:
            raise ValueError('Spectrum data cannot be empty')
        return v

class CalibrationRequest(BaseModel):
    """Request model for energy calibration."""
    channels: List[float] = Field(..., min_length=2)
    known_energies: List[float] = Field(..., min_length=2)

    @field_validator('known_energies')
    @classmethod
    def validate_energies_positive(cls, v):
        if any(e < 0 for e in v):
            raise ValueError('Energies must be positive')
        return v

class ReportRequest(BaseModel):
    """Request model for PDF report generation."""
    filename: str = Field(..., min_length=1, max_length=255)
    metadata: dict = Field(default={})
    energies: List[float] = Field(default=[])
    counts: List[float] = Field(default=[])
    peaks: List[dict] = Field(default=[])
    isotopes: List[dict] = Field(default=[])
    decay_chains: List[dict] = Field(default=[])

class BackgroundSubtractionRequest(BaseModel):
    """Request model for background subtraction."""
    source_counts: List[float] = Field(..., min_length=1)
    background_counts: List[float] = Field(..., min_length=1)
    scaling_factor: float = Field(default=1.0, ge=0.0, le=10.0)

class MLIdentifyRequest(BaseModel):
    """Request model for ML isotope identification."""
    counts: List[float] = Field(..., min_length=10, max_length=MAX_SPECTRUM_CHANNELS)

    @field_validator('counts')
    @classmethod
    def validate_counts_non_negative(cls, v):
        if any(c < 0 for c in v):
            raise ValueError('Counts must be non-negative')
        return v

class ROIAnalysisRequest(BaseModel):
    """Request model for ROI analysis."""
    energies: List[float] = Field(..., min_length=10)
    counts: List[float] = Field(..., min_length=10)
    isotope: str = Field(..., min_length=1)
    detector: str = Field(default="AlphaHound CsI(Tl)")
    acquisition_time_s: float = Field(..., ge=1, le=86400)  # 1 sec to 24 hours

class UraniumRatioRequest(BaseModel):
    """Request model for uranium enrichment analysis."""
    energies: List[float] = Field(..., min_length=10)
    counts: List[float] = Field(..., min_length=10)
    detector: str = Field(default="AlphaHound CsI(Tl)")
    acquisition_time_s: float = Field(..., ge=1, le=86400)

@router.get("/settings")
async def get_settings():
    return DEFAULT_SETTINGS

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload and analyze a spectrum file (N42/XML/CSV)."""
    # Validate file extension
    filename = file.filename.lower()
    ext = '.' + filename.split('.')[-1] if '.' in filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Read and validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE_MB}MB"
        )
    
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

@router.post("/export/csv-auto")
async def export_csv_auto(request: dict):
    """Auto-save spectrum to CSV with timestamped filename"""
    try:
        import os
        from datetime import datetime
        import csv
        
        # Create acquisitions directory if it doesn't exist
        save_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'acquisitions')
        os.makedirs(save_dir, exist_ok=True)
        
        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"spectrum_{timestamp}.csv"
        filepath = os.path.join(save_dir, filename)
        
        # Write CSV
        energies = request.get('energies', [])
        counts = request.get('counts', [])
        
        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Energy (keV)', 'Counts'])
            for energy, count in zip(energies, counts):
                writer.writerow([energy, count])
        
        return {
            "success": True,
            "filename": filename,
            "path": filepath,
            "message": f"Spectrum saved: {filename}"
        }
    except Exception as e:
        print(f"CSV auto-save error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save CSV: {str(e)}")

# === ROI Analysis Endpoints ===

@router.post("/analyze/roi")
async def analyze_roi_endpoint(request: ROIAnalysisRequest):
    """
    Perform ROI (Region-of-Interest) analysis for a specific isotope.
    
    Calculates net counts, activity (Bq/μCi), and uncertainty.
    Designed for AlphaHound AB+G detectors.
    """
    try:
        from roi_analysis import analyze_roi
        from isotope_roi_database import get_roi_isotope_names
        
        # Validate isotope exists
        valid_isotopes = get_roi_isotope_names()
        if request.isotope not in valid_isotopes:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown isotope: {request.isotope}. Valid: {valid_isotopes}"
            )
        
        result = analyze_roi(
            energies=request.energies,
            counts=[int(c) for c in request.counts],
            isotope_name=request.isotope,
            detector_name=request.detector,
            acquisition_time_s=request.acquisition_time_s
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[ROI] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze/uranium-ratio")
async def analyze_uranium_ratio_endpoint(request: UraniumRatioRequest):
    """
    Analyze uranium enrichment using 186 keV / 93 keV peak ratio.
    
    Determines if sample is Natural, Depleted, or Enriched uranium.
    Designed for AlphaHound AB+G detectors.
    """
    try:
        from roi_analysis import analyze_uranium_enrichment
        
        result = analyze_uranium_enrichment(
            energies=request.energies,
            counts=[int(c) for c in request.counts],
            detector_name=request.detector,
            acquisition_time_s=request.acquisition_time_s
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[ROI] Uranium ratio error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analyze/roi-isotopes")
async def get_roi_isotopes():
    """Get list of available isotopes for ROI analysis."""
    try:
        from isotope_roi_database import get_roi_isotope_names, ISOTOPE_ROI_DATABASE
        
        isotopes = []
        for name in get_roi_isotope_names():
            data = ISOTOPE_ROI_DATABASE[name]
            isotopes.append({
                "name": name,
                "isotope": data["isotope"],
                "energy_keV": data["energy_keV"],
                "roi_window": data["roi_window"]
            })
        
        return {"isotopes": isotopes}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analyze/detectors")
async def get_detectors():
    """Get list of available AlphaHound AB+G detector configurations."""
    try:
        from detector_efficiency import DETECTOR_DATABASE
        
        detectors = []
        for name, data in DETECTOR_DATABASE.items():
            # Only include AlphaHound detectors
            if "AlphaHound" in name:
                detectors.append({
                    "name": name,
                    "type": data["type"],
                    "description": data["description"],
                    "volume_cm3": data["volume_cm3"],
                    "sensitivity_cps_uSv_h": data.get("cs137_sensitivity_cps_per_uSv_h"),
                    "resolution_662keV": data.get("energy_resolution_662keV")
                })
        
        return {"detectors": detectors}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
