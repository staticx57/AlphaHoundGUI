"""Nuclear data, decay prediction and dose-rate endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

import logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["nuclear"])


class DoseRateRequest(BaseModel):
    """Request model for dose rate calculation."""
    isotope: str = Field(..., min_length=2, max_length=20)
    activity_bq: float = Field(..., ge=0)
    distance_m: float = Field(default=1.0, ge=0.01, le=1000)


class DecayPredictionRequest(BaseModel):
    """Request model for decay chain prediction."""
    parent_isotope: Optional[str] = None
    isotope: Optional[str] = None
    initial_activity_bq: float = Field(default=1000.0, ge=0)
    time_hours: Optional[float] = None
    duration_days: Optional[float] = None
    engine: Optional[str] = Field(default="auto", description="Decay engine to use (auto, radioactivedecay, curie, pyne, builtin)")


class IsotopeInfoRequest(BaseModel):
    """Request model for isotope information lookup."""
    isotope: str = Field(..., min_length=2, max_length=20)


@router.get("/analyze/decay-engines")
def get_decay_engines_endpoint():
    """
    Get available radioactive decay calculation engines and current system defaults.
    """
    try:
        from decay_engine import decay_engine_manager
        return {
            "engines": decay_engine_manager.list_engines(),
            "default": decay_engine_manager.get_default_engine_name()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/decay-prediction")
def predict_decay_endpoint(request: DecayPredictionRequest):
    """
    Predict decay chain activity evolution over time.
    Supports multi-engine selection (radioactivedecay, curie, pyne, builtin).
    """
    try:
        from decay_engine import decay_engine_manager
        
        target_isotope = request.isotope or request.parent_isotope or "Cs-137"
        
        # Calculate duration in seconds
        if request.duration_days is not None:
            duration_s = request.duration_days * 86400
        elif request.time_hours is not None:
            duration_s = request.time_hours * 3600
        else:
            duration_s = 24 * 3600 # 1 day default

        engine_name = request.engine or "auto"
        result = decay_engine_manager.predict_decay(
            isotope=target_isotope,
            activity=request.initial_activity_bq,
            duration_seconds=duration_s,
            engine_name=engine_name
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Decay Prediction] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/isotope-info")
def get_isotope_info_endpoint(request: IsotopeInfoRequest):
    """
    Get comprehensive information about an isotope.
    
    Returns half-life, decay mode, daughter isotope, and decay chain membership.
    """
    try:
        from decay_calculator import get_isotope_info, get_decay_chain
        
        info = get_isotope_info(request.isotope)
        info['decay_chain'] = get_decay_chain(request.isotope)
        
        return info
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Isotope Info] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze/gamma-constants")
def get_gamma_constants():
    """
    Get list of isotopes with known gamma dose constants.
    
    Returns dictionary of isotope names to gamma constants (μSv·m²/h per MBq).
    """
    try:
        from activity_calculator import GAMMA_DOSE_CONSTANTS as GAMMA_CONSTANTS
        
        return {
            "constants": GAMMA_CONSTANTS,
            "units": "μSv·m²/h per MBq",
            "description": "Gamma dose rate constants at 1 meter per MBq activity"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze/search-gamma")
def search_gamma_line_endpoint(
    energy: float,
    delta: float = 5.0,
    intensity_min: Optional[float] = None
):
    """
    Search for gamma-emitting isotopes near a given energy.
    
    Args:
        energy: Target energy in keV
        delta: Search window ±keV (default: 5)
        intensity_min: Minimum intensity % to include (optional)
        
    Returns:
        List of matching gamma lines sorted by proximity
    """
    try:
        from nuclear_data import search_gamma_line
        
        results = search_gamma_line(
            energy=energy,
            delta=delta,
            intensity_threshold=intensity_min
        )
        
        return {
            "query_energy_keV": energy,
            "search_window_keV": delta,
            "matches": results,
            "count": len(results)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze/search-xray")
def search_xray_line_endpoint(
    energy: float,
    delta: float = 2.0
):
    """
    Search for X-ray fluorescence lines near a given energy.
    Useful for identifying elements in XRF analysis.
    
    Args:
        energy: Target energy in keV
        delta: Search window ±keV (default: 2)
        
    Returns:
        List of matching X-ray lines sorted by proximity
    """
    try:
        from nuclear_data import search_xray_line
        
        results = search_xray_line(energy=energy, delta=delta)
        
        return {
            "query_energy_keV": energy,
            "search_window_keV": delta,
            "matches": results,
            "count": len(results)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze/decay-chain")
def decay_chain_spectrum_endpoint(
    parent: str,
    intensity_min: float = 1.0
):
    """
    Get all gamma lines from a decay chain.
    
    Args:
        parent: Parent isotope (e.g., "U-238", "Th-232", "U-235")
        intensity_min: Minimum intensity % to include (default: 1%)
        
    Returns:
        Complete decay chain with all gamma-emitting daughters
    """
    try:
        from nuclear_data import decay_chain_spectrum
        
        result = decay_chain_spectrum(
            parent=parent,
            intensity_threshold=intensity_min
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze/isotope-lines")
def get_isotope_lines_endpoint(
    isotope: str,
    intensity_min: Optional[float] = None
):
    """
    Get all gamma lines for a specific isotope.
    
    Args:
        isotope: Isotope name (e.g., "Cs-137", "Am-241")
        intensity_min: Minimum intensity % to include (optional)
        
    Returns:
        List of gamma lines for that isotope, sorted by intensity
    """
    try:
        from nuclear_data import get_isotope_gamma_lines
        
        results = get_isotope_gamma_lines(
            isotope=isotope,
            intensity_threshold=intensity_min
        )
        
        return {
            "isotope": isotope,
            "lines": results,
            "count": len(results)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/dose-rate")
def calculate_dose_rate_endpoint(request: DoseRateRequest):
    """Calculate gamma dose rate at specified distance."""
    try:
        from activity_calculator import calculate_dose_rate
        result = calculate_dose_rate(
            activity_bq=request.activity_bq,
            isotope=request.isotope,
            distance_m=request.distance_m
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
