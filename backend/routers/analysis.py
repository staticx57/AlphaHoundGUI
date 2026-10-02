import logging
logger = logging.getLogger(__name__)
from fastapi import APIRouter, File, UploadFile, HTTPException, Response
from pydantic import BaseModel, field_validator, Field
from typing import List, Optional, Dict
import math
from n42_parser import parse_n42
from radiacode_xml_parser import is_radiacode_xml, parse_radiacode_xml
from csv_parser import parse_csv_spectrum
from peak_detection import detect_peaks
from isotope_database import identify_isotopes, identify_decay_chains
from core import DEFAULT_SETTINGS, UPLOAD_SETTINGS, apply_abundance_weighting, apply_confidence_filtering
from spectral_analysis import fit_gaussian, calibrate_energy, subtract_background
from chn_spe_parser import parse_chn_file, parse_spe_file
from detector_efficiency import get_detector_names, calculate_mda, DETECTOR_DATABASE
from decay_calculator import predict_decay_chain

# Enhanced analysis modules (with fallback)
try:
    from peak_detection_enhanced import detect_peaks_enhanced
    from chain_detection_enhanced import identify_decay_chains_enhanced
    from confidence_scoring import enhance_isotope_identifications
    from multiplet_fitting import enhance_peaks_with_multiplet_fitting
    HAS_ENHANCED_ANALYSIS = True
    logger.info("[Analysis] Enhanced analysis modules loaded")
except ImportError as e:
    HAS_ENHANCED_ANALYSIS = False
    logger.warning(f"[Analysis] Enhanced modules not available: {e}")

from analysis_utils import analyze_spectrum_peaks, sanitize_for_json


# Constants for input validation
MAX_FILE_SIZE_MB = 10
# Extended file format support via SandiaSpecUtils
ALLOWED_EXTENSIONS = {
    # Native parsers (CSV, N42, CHN, SPE)
    '.n42', '.xml', '.csv', '.chn', '.spe',
    # SandiaSpecUtils extended formats (most common)
    '.spc',   # ORTEC SPC
    '.pcf',   # GADRAS PCF
    '.dat',   # Generic DAT
    '.txt',   # Text/ASCII
    '.mca',   # Amptek MCA
    '.iem',   # IEM
    '.gam',   # GAM
    '.cnf',   # Canberra CNF
    '.tka',   # TKA
    '.pks',   # PKS
    '.grd',   # GRD
    '.sal',   # SAL
    '.lis',   # LIS
    '.phd',   # PHD
    '.pmf',   # PMF
}
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


class BackgroundSubtractionRequest(BaseModel):
    """Request model for background subtraction."""
    source_counts: List[float] = Field(..., min_length=1)
    background_counts: List[float] = Field(..., min_length=1)
    scaling_factor: float = Field(default=1.0, ge=0.0, le=10.0)

class MLIdentifyRequest(BaseModel):
    """Request model for ML isotope identification."""
    counts: List[float] = Field(..., min_length=10, max_length=MAX_SPECTRUM_CHANNELS)
    # Channel energies (keV) of the spectrum: lets the model resample onto its own energy grid
    energies: Optional[List[float]] = Field(default=None, max_length=MAX_SPECTRUM_CHANNELS)

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
    acquisition_time_s: float = Field(..., ge=1, le=36000000)  # 1 sec to 10,000 hours
    source_type: Optional[str] = Field(default="auto")  # User-specified source type


class UraniumRatioRequest(BaseModel):
    """Request model for uranium enrichment analysis."""
    energies: List[float] = Field(..., min_length=10)
    counts: List[float] = Field(..., min_length=10)
    detector: str = Field(default="AlphaHound CsI(Tl)")
    acquisition_time_s: float = Field(..., ge=1, le=36000000)
    source_type: Optional[str] = Field(default="auto")  # User-specified source type


@router.get("/settings")
def get_settings():
    return DEFAULT_SETTINGS

@router.get("/detectors")
def get_detectors():
    """Get list of available detector profiles."""
    return {"detectors": get_detector_names()}

@router.post("/analyze/mda")
def analyze_mda(request: dict):
    """
    Calculate Minimum Detectable Activity (MDA) for a specific ROI.
    """
    try:
        # Extract params
        bg_counts = float(request.get('background_counts', 0))
        energy = float(request.get('energy_keV', 662))
        branching = float(request.get('branching_ratio', 0.85))
        live_time = float(request.get('live_time_s', 60))
        detector = request.get('detector', 'AlphaHound CsI(Tl)')
        
        result = calculate_mda(
            background_counts=bg_counts,
            energy_keV=energy,
            branching_ratio=branching,
            live_time_s=live_time,
            detector_name=detector
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
            # RadiaCode/BecqMoni exports are .xml but not N42
            result = parse_radiacode_xml(content_str) if is_radiacode_xml(content_str) else parse_n42(content_str)
            if "error" in result: 
                raise HTTPException(status_code=400, detail=result["error"])
            
            # Use common analysis pipeline
            is_calibrated = result.get("is_calibrated", True)
            live_time = float(result.get("metadata", {}).get("live_time", 0))
            result = analyze_spectrum_peaks(result, is_calibrated, live_time)
            return result
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error parsing N42: {str(e)}")


    elif filename.endswith('.csv'):
        try:
            result = parse_csv_spectrum(content, filename)
            logger.info(f"[CSV Upload] Parsed: {len(result.get('counts', []))} counts, {len(result.get('energies', []))} energies")
            logger.info(f"[CSV Upload] is_calibrated: {result.get('is_calibrated', False)}")
            
            # Use common analysis pipeline
            is_calibrated = result.get("is_calibrated", False)
            result = analyze_spectrum_peaks(result, is_calibrated)
            
            logger.info(f"[CSV Upload] After analysis: peaks={len(result.get('peaks', []))}, isotopes={len(result.get('isotopes', []))}")
            if result.get('peaks'):
                peak_energies = [p.get('energy', 0) for p in result['peaks'][:5]]
                logger.info(f"[CSV Upload] First 5 peak energies: {peak_energies}")
            return result
        except ValueError as e:
            # Unparseable CSV is a client error, not a server fault
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"[CSV Upload] Error: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    elif filename.endswith('.chn') or filename.endswith('.spe'):
        try:
            # Save temp file for binary parsing
            import tempfile
            import os
            ext = '.chn' if filename.endswith('.chn') else '.spe'
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            
            try:
                if filename.endswith('.chn'):
                    result = parse_chn_file(tmp_path)
                else:
                    result = parse_spe_file(tmp_path)
                
                result['filename'] = file.filename
                result['source'] = 'CHN File' if filename.endswith('.chn') else 'SPE File'
                result['is_calibrated'] = result.get('calibration') is not None
                
                # Use common analysis pipeline
                is_calibrated = result.get('is_calibrated', False)
                result = analyze_spectrum_peaks(result, is_calibrated)
                return result
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error parsing CHN/SPE: {str(e)}")
            
    else:
        # Try generic parser (SandiaSpecUtils) for all other allowed extensions
        try:
            from specutils_parser import parse_spectrum_generic
            import tempfile
            import os
            
            # SpecUtils often requires a file path
            ext = os.path.splitext(filename)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
                
            try:
                result = parse_spectrum_generic(tmp_path)
                
                if not result or not result.get("counts"):
                    raise ValueError("Could not parse file structure or empty counts")
                
                result['filename'] = file.filename
                result['source'] = 'Generic Spectrum'
                
                # Determine calibration status
                cal = result.get('energy_calibration', {})
                is_calibrated = (cal.get('slope', 1) != 1) or (cal.get('intercept', 0) != 0)
                result['is_calibrated'] = is_calibrated
                
                # Expand energies if not present but calibration exists
                if is_calibrated and not result.get('energies'):
                    result['energies'] = []
                    slope = cal.get('slope', 1)
                    intercept = cal.get('intercept', 0)
                    quad = cal.get('quadratic', 0)
                    for i in range(len(result['counts'])):
                        # E = A + B*x + C*x^2
                        e = intercept + slope * i + quad * (i**2)
                        result['energies'].append(e)
                elif not result.get('energies'):
                    # Default linear 1 keV/ch
                     result['energies'] = list(range(len(result['counts'])))

                # Use common analysis pipeline
                live_time = result.get('live_time', 0.0)
                result = analyze_spectrum_peaks(result, is_calibrated, live_time)
                return result
                
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    
        except ImportError:
            raise HTTPException(status_code=501, detail="SandiaSpecUtils support not available (module missing)")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Generic parser error: {str(e)}")

@router.post("/analyze/fit-peaks")
def analyze_fit_peaks(request: AnalysisRequest):
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
def analyze_calibrate(request: CalibrationRequest):
    try:
        calibrated_energies, params = calibrate_energy(request.channels, request.known_energies, request.channels)
        return {"calibrated_energies": calibrated_energies, "params": params}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/subtract-background")
def analyze_subtract_background(request: BackgroundSubtractionRequest):
    try:
        # Returns {net_counts: [...], background, gross_counts, algorithm, iterations}
        return subtract_background(
            request.source_counts,
            request.background_counts,
            request.scaling_factor
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/ml-identify")
def ml_identify(request: MLIdentifyRequest):
    """
    Machine Learning isotope identification (scikit-learn MLP trained on synthetic spectra).
    
    Includes:
    - Confidence thresholding (top result must be >20% to show)
    - Hybrid filtering with Peak Matching results
    - Anomaly flagging for low confidence predictions
    """
    try:
        # Lazy import: the model is trained on first use
        from ml_analysis import get_ml_identifier
        
        ml = get_ml_identifier()
        if ml is None:
            raise HTTPException(status_code=501, detail="scikit-learn not installed")
        
        raw_results = ml.identify(request.counts, top_k=5, energies=request.energies)
        
        # ========== CONFIDENCE THRESHOLDING ==========
        # Only keep predictions with meaningful confidence
        min_confidence = 5.0  # Minimum to show at all
        results = [r for r in raw_results if r['confidence'] >= min_confidence]
        
        # ========== HYBRID FILTERING ==========
        # If Peak Matching results provided, suppress conflicting ML predictions
        peak_isotopes = getattr(request, 'peak_isotopes', None)
        if peak_isotopes and len(results) > 0:
            # Get HIGH confidence isotopes from Peak Matching
            high_conf_peaks = [iso for iso in peak_isotopes 
                              if iso.get('confidence', 0) > 70]
            high_conf_names = {iso['isotope'] for iso in high_conf_peaks}
            
            # If Peak Matching has HIGH confidence for natural chains,
            # boost ML predictions that match and suppress conflicts
            NATURAL_CHAIN_ISOTOPES = {
                'U-238', 'Bi-214', 'Pb-214', 'Ra-226', 'Th-234', 'Pa-234m',
                'Th-232', 'Tl-208', 'Ac-228', 'Pb-212'
            }
            
            if high_conf_names & NATURAL_CHAIN_ISOTOPES:
                # Natural chain detected by Peak Matching - suppress conflicts
                MEDICAL_ISOTOPES = {'Cs-137', 'I-131', 'F-18', 'Tc-99m', 'Co-60',
                                    'Tc-99m + I-131 + Mo-99', 'Cs-137 + Co-60'}
                for r in results:
                    if r['isotope'] in MEDICAL_ISOTOPES:
                        r['confidence'] *= 0.1
                        r['suppressed'] = True
                        r['suppression_reason'] = 'conflict_with_peak_matching'
                
                # Re-sort after suppression
                results.sort(key=lambda x: x['confidence'], reverse=True)
        
        # ========== QUALITY FLAGGING ==========
        quality = 'good'
        if len(results) == 0:
            quality = 'no_match'
        elif results[0]['confidence'] < 30:
            quality = 'low_confidence'
        elif results[0]['confidence'] < 60:
            quality = 'moderate'
        
        return {
            "predictions": results,
            "quality": quality,
            "top_confidence": results[0]['confidence'] if results else 0
        }
    except ImportError as e:
        raise HTTPException(status_code=501, detail="scikit-learn not installed")
    except Exception as e:
        logger.error(f"[ML] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === SNIP Background Subtraction ===

@router.post("/analyze/snip-background")
def snip_background_endpoint(request: dict):
    """
    Apply SNIP (Sensitive Nonlinear Iterative Peak) background estimation.
    
    This removes the Compton continuum and environmental background from
    gamma spectra, making peaks more visible for isotope identification.
    
    Args (JSON body):
        counts: List of spectrum counts
        iterations: SNIP iterations (8-24, default 24, higher = smoother)
        reanalyze: If true, also re-run peak detection and isotope ID
        energies: Required if reanalyze=True
    
    Returns:
        net_counts: Background-subtracted spectrum
        background: Estimated background curve
        algorithm: "SNIP"
        peaks: (optional) Re-detected peaks on net counts
        isotopes: (optional) Re-identified isotopes
    """
    try:
        from spectral_analysis import subtract_background, snip_background
        
        counts = request.get('counts', [])
        iterations = int(request.get('iterations', 24))
        energies = request.get('energies', [])
        reanalyze = request.get('reanalyze', False)
        
        if not counts:
            raise HTTPException(status_code=400, detail="counts is required")
        
        # Apply SNIP background subtraction
        result = subtract_background(counts, use_snip=True, snip_iterations=iterations)
        
        response = {
            'net_counts': result['net_counts'],
            'background': result['background'],
            'algorithm': result['algorithm'],
            'iterations': iterations
        }
        
        # Optionally re-run analysis on net counts
        if reanalyze and energies:
            # Detect peaks on background-subtracted data
            peaks = detect_peaks(energies, result['net_counts'])
            
            # Re-identify isotopes
            isotopes = identify_isotopes(peaks)
            isotopes = apply_abundance_weighting(isotopes)
            
            # Decay chains
            chains = identify_decay_chains(peaks, isotopes)
            
            # Apply confidence filtering with proper settings
            settings = {
                'isotope_min_confidence': UPLOAD_SETTINGS['isotope_min_confidence'],
                'max_isotopes': UPLOAD_SETTINGS['max_isotopes'],
                'chain_min_confidence': UPLOAD_SETTINGS['chain_min_confidence'],
                'chain_min_isotopes_medium': 3,
                'chain_min_isotopes_high': 4,
                'mode': 'simple'
            }
            isotopes, chains = apply_confidence_filtering(isotopes, chains, settings)
            
            response['peaks'] = peaks
            response['isotopes'] = isotopes
            response['decay_chains'] = chains
        
        return response
        
    except Exception as e:
        logger.error(f"SNIP background error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === ROI Analysis Endpoints ===

@router.post("/analyze/roi")
def analyze_roi_endpoint(request: ROIAnalysisRequest):
    """
    Perform ROI (Region-of-Interest) analysis for a specific isotope.
    
    Calculates net counts, activity (Bq/μCi), and uncertainty.
    Designed for AlphaHound AB+G detectors.
    """
    try:
        from roi_analysis import analyze_roi
        from isotope_roi_database import get_roi_isotope_names
        from source_analysis import get_enhanced_analysis
        
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
            acquisition_time_s=request.acquisition_time_s,
            source_type=request.source_type
        )
        
        from dataclasses import asdict
        logger.debug(f"[DEBUG] Analyze ROI Result Type: {type(result)}")
        # If it's already a dict, just return it. If dataclass, convert.
        if isinstance(result, dict):
            response = result
        else:
            response = asdict(result)
        
        # Add enhanced analysis if source type specified
        source_type = request.source_type
        if source_type and source_type not in ["auto", "unknown"]:
            activity_bq = response.get("activity_bq", 0)
            if activity_bq and activity_bq > 0:
                enhanced = get_enhanced_analysis(source_type, activity_bq)
                if enhanced:
                    response["enhanced_analysis"] = enhanced
                    logger.info(f"[ROI] Added enhanced analysis for {source_type}")
        
        return response
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[ROI] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze/uranium-ratio")
def analyze_uranium_ratio_endpoint(request: UraniumRatioRequest):
    """
    Analyze uranium enrichment using 186 keV / 93 keV peak ratio.
    
    Determines if sample is Natural, Depleted, or Enriched uranium.
    Designed for AlphaHound AB+G detectors.
    """
    try:
        from roi_analysis import analyze_uranium_enrichment
        
        # Check if source_type implies uranium context
        source_type = "auto"
        if hasattr(request, "source_type"):
            source_type = request.source_type
        
        result = analyze_uranium_enrichment(
            energies=request.energies,
            counts=[int(c) for c in request.counts],
            detector_name=request.detector,
            acquisition_time_s=request.acquisition_time_s,
            source_type=source_type
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[ROI] Uranium ratio error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analyze/roi-isotopes")
def get_roi_isotopes():
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


@router.post("/analyze/identify-source")
def identify_source_endpoint(request: UraniumRatioRequest):
    """
    Identify the source type based on spectral signatures.
    
    Recognizes common radioactive sources:
    - Uranium Glass (Vaseline Glass)
    - Thoriated Camera Lenses
    - Radium Dial Watches/Clocks
    - Smoke Detectors (Am-241)
    - Natural Background (K-40)
    
    If no match is found, returns the raw isotope detection data.
    """
    try:
        from source_identification import identify_source_type
        
        result = identify_source_type(
            energies=request.energies,
            counts=[int(c) for c in request.counts],
            detector_name=request.detector,
            acquisition_time_s=request.acquisition_time_s
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Source ID] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze/source-types")
def get_source_types():
    """Get list of known source types for the dropdown selector."""
    try:
        from source_identification import SOURCE_SIGNATURES
        
        source_types = [
            {
                "id": "auto",
                "name": "Auto-detect",
                "description": "Automatically identify source type from spectrum"
            }
        ]
        
        for source_id, signature in SOURCE_SIGNATURES.items():
            source_types.append({
                "id": source_id,
                "name": signature.name,
                "description": signature.description,
                "notes": signature.notes
            })
        
        source_types.append({
            "id": "unknown",
            "name": "Unknown / Other",
            "description": "Just show raw isotope detection data without assumptions"
        })
        
        return {"source_types": source_types}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze/detectors")
def get_detectors():
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


# === Model Export Endpoints ===

@router.post("/analyze/export-model")
def export_model_endpoint(request: dict):
    """
    Export trained ML model to ONNX (needs the optional skl2onnx package).
    
    Args (JSON body):
        format: 'onnx'
        model_type: 'hobby' or 'comprehensive'
    
    Returns:
        File download or error message
    """
    try:
        from ml_analysis import get_ml_identifier
        import tempfile
        import os
        
        format = request.get('format', 'onnx').lower()
        model_type = request.get('model_type', 'hobby')
        
        if format != 'onnx':
            raise HTTPException(status_code=400, detail="Format must be 'onnx'")
        
        identifier = get_ml_identifier(model_type)
        if not identifier:
            raise HTTPException(status_code=500, detail="ML model not available")
        
        # Export to temp file
        ext = '.onnx'
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp_path = tmp.name
        
        result = identifier.export_model(tmp_path, format)
        
        if not result.get('success'):
            raise HTTPException(status_code=500, detail=result.get('error', 'Export failed'))
        
        # Read file and return as response
        with open(result['path'], 'rb') as f:
            content = f.read()
        
        os.unlink(result['path'])
        
        filename = f"radtrace_model_{model_type}{ext}"
        return Response(
            content=content,
            media_type='application/octet-stream',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Spectrum Algebra Endpoints ===

@router.post("/analyze/spectrum-algebra")
def spectrum_algebra_endpoint(request: dict):
    """
    Perform spectrum algebra operations.
    
    Args (JSON body):
        operation: 'add', 'subtract', 'normalize', 'compare'
        spectra: List of spectrum counts arrays
        options: Operation-specific options
    """
    try:
        from spectrum_algebra import add_spectra, subtract_spectra, normalize_spectrum, compare_spectra
        
        operation = request.get('operation', 'add')
        spectra = request.get('spectra', [])
        options = request.get('options', {})
        
        if operation == 'add':
            weights = options.get('weights')
            return add_spectra(spectra, weights)
        
        elif operation == 'subtract':
            if len(spectra) < 2:
                raise HTTPException(status_code=400, detail="Need at least 2 spectra for subtraction")
            return subtract_spectra(
                spectra[0], spectra[1],
                source_time=options.get('source_time', 1.0),
                bg_time=options.get('bg_time', 1.0)
            )
        
        elif operation == 'normalize':
            if not spectra:
                raise HTTPException(status_code=400, detail="Need spectrum to normalize")
            return normalize_spectrum(
                spectra[0],
                method=options.get('method', 'l1'),
                live_time=options.get('live_time')
            )
        
        elif operation == 'compare':
            if len(spectra) < 2:
                raise HTTPException(status_code=400, detail="Need 2 spectra to compare")
            return compare_spectra(spectra[0], spectra[1])
        
        else:
            raise HTTPException(status_code=400, detail=f"Unknown operation: {operation}")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Anomaly Detection Endpoint ===

@router.post("/analyze/anomaly-detection")
def anomaly_detection_endpoint(request: dict):
    """
    Detect anomalous spectra that don't match expected patterns.
    
    Uses multiple heuristics to flag unusual spectra:
    - ML confidence too low (unknown source)
    - Unusual peak patterns
    - Unexpected isotope combinations
    
    Args (JSON body):
        counts: Spectrum counts
        energies: Energy axis
    
    Returns:
        Anomaly score and flags
    """
    try:
        from ml_analysis import get_ml_identifier
        import numpy as np
        
        counts = request.get('counts', [])
        energies = request.get('energies', [])
        
        if not counts:
            raise HTTPException(status_code=400, detail="counts is required")
        
        anomalies = []
        anomaly_score = 0.0
        
        # Check 1: ML confidence
        identifier = get_ml_identifier('hobby')
        if identifier:
            try:
                predictions = identifier.identify(counts, top_k=3)
                if predictions:
                    top_conf = predictions[0]['confidence']
                    if top_conf < 30:
                        anomalies.append({
                            'type': 'low_ml_confidence',
                            'message': f'Top ML prediction only {top_conf}% confident',
                            'severity': 'warning'
                        })
                        anomaly_score += 0.3
                    if top_conf < 10:
                        anomaly_score += 0.2
                else:
                    anomalies.append({
                        'type': 'no_ml_prediction',
                        'message': 'ML model returned no predictions',
                        'severity': 'info'
                    })
            except:
                pass
        
        # Check 2: Total counts
        arr = np.array(counts, dtype=float)
        total = arr.sum()
        if total < 100:
            anomalies.append({
                'type': 'low_counts',
                'message': f'Very low total counts ({total:.0f})',
                'severity': 'warning'
            })
            anomaly_score += 0.2
        
        # Check 3: Peak-to-background ratio
        if len(arr) > 50:
            bg_estimate = np.percentile(arr, 25)
            peak_estimate = np.percentile(arr, 99)
            if bg_estimate > 0:
                ratio = peak_estimate / bg_estimate
                if ratio < 2:
                    anomalies.append({
                        'type': 'flat_spectrum',
                        'message': f'Very flat spectrum (peak/bg ratio: {ratio:.1f})',
                        'severity': 'warning'
                    })
                    anomaly_score += 0.2
        
        # Check 4: Unusual spectral shape (entropy)
        if total > 0:
            probs = arr / total
            probs = probs[probs > 0]
            entropy = -np.sum(probs * np.log2(probs + 1e-10))
            max_entropy = np.log2(len(arr))
            normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0
            
            if normalized_entropy > 0.95:
                anomalies.append({
                    'type': 'high_entropy',
                    'message': 'Spectrum appears random/noise-like',
                    'severity': 'warning'
                })
                anomaly_score += 0.3
        
        return {
            'anomaly_score': min(1.0, anomaly_score),
            'is_anomalous': anomaly_score > 0.5,
            'anomalies': anomalies,
            'total_counts': float(total)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Phase 1B & 2: Activity Calculator & Decay Predictions ===


@router.post("/analyze/multiplet")
def analyze_multiplet_endpoint(request: dict):
    """
    Deconvolve overlapping peaks using multiplet fitting.
    
    Fits multiple Gaussian peaks simultaneously on a linear baseline.
    Useful for resolving overlapping peaks (e.g., U-235 + Ra-226 at 186 keV).
    
    Args (JSON body):
        energies: List of energy values (keV)
        counts: List of counts
        centroids: List of peak centroids to fit (keV)
        roi_width: Optional width of ROI around peaks (default: 50 keV)
        
    Returns:
        Fitted peak parameters for each centroid including:
        - amplitude, centroid, sigma, fwhm, net_area, uncertainty
        - r_squared for overall fit quality
    """
    try:
        from fitting_engine import AdvancedFittingEngine
        import numpy as np
        
        energies = request.get('energies', [])
        counts = request.get('counts', [])
        centroids = request.get('centroids', [])
        roi_width = request.get('roi_width', 50.0)
        
        if not energies or not counts or not centroids:
            raise HTTPException(status_code=400, detail="energies, counts, and centroids are required")
        
        if len(centroids) < 2:
            raise HTTPException(status_code=400, detail="At least 2 centroids required for multiplet fitting")
        
        engine = AdvancedFittingEngine()
        results, r_squared = engine.fit_multiplet(
            energies=np.array(energies),
            counts=np.array(counts),
            centroids=centroids,
            roi_width_kev=roi_width
        )
        
        if results is None:
            return {
                "success": False,
                "error": "Multiplet fit failed",
                "peaks": []
            }
        
        # Format results
        peaks = []
        for i, result in enumerate(results):
            peaks.append({
                "centroid_requested": centroids[i],
                "centroid_fitted": round(result.centroid, 2),
                "amplitude": round(result.amplitude, 1),
                "sigma": round(result.sigma, 2),
                "fwhm": round(result.fwhm, 2),
                "resolution_percent": round(result.resolution, 2),
                "net_area": round(result.net_area, 1),
                "uncertainty": round(result.uncertainty, 1),
            })
        
        return {
            "success": True,
            "r_squared": round(r_squared, 4),
            "peaks": peaks,
            "notes": f"Deconvolved {len(peaks)} overlapping peaks"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Multiplet] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# === N42 Metadata Editor Endpoints ===


# === Acquisition Time Estimator ===

class TimeEstimatorRequest(BaseModel):
    counts: List[float]
    source_type: Optional[str] = None

@router.post("/analyze/estimate-time")
def estimate_acquisition_time_endpoint(request: TimeEstimatorRequest):
    """Estimate acquisition time from spectrum counts."""
    try:
        from time_estimator import estimate_time_from_spectrum
        result = estimate_time_from_spectrum(
            counts=[int(c) for c in request.counts],
            source_type=request.source_type
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Dose Rate Calculator ===


