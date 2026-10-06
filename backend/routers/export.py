"""Export (PDF/N42/CSV/PCF/CHN) and N42 metadata endpoints."""
import os
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from formats.report_generator import generate_pdf_report

import logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["export"])


class ReportRequest(BaseModel):
    """Request model for PDF report generation."""
    filename: str = Field(..., min_length=1, max_length=255)
    metadata: dict = Field(default={})
    energies: List[float] = Field(default=[])
    counts: List[float] = Field(default=[])
    peaks: List[dict] = Field(default=[])
    isotopes: List[dict] = Field(default=[])
    decay_chains: List[dict] = Field(default=[])


class N42ExportRequest(BaseModel):
    """Request model for N42 XML export"""
    counts: List[float]
    energies: List[float]
    metadata: Optional[dict] = {}
    peaks: Optional[List[dict]] = []
    isotopes: Optional[List[dict]] = []
    filename: Optional[str] = "spectrum"


@router.post("/export/pdf")
def export_pdf(request: ReportRequest):
    try:
        pdf_bytes = generate_pdf_report(request.model_dump())
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


@router.post("/export/n42")
def export_n42(request: N42ExportRequest):
    """Export spectrum data as standards-compliant N42 XML file."""
    logger.info("Endpoint called")
    try:
        from formats.n42_exporter import generate_n42_xml
        
        # Convert Pydantic model to dict for exporter
        request_dict = request.model_dump()
        
        logger.info(f"Generating XML for {len(request.counts)} channels...")
        # Generate N42 XML
        xml_content = generate_n42_xml(request_dict)
        logger.info(f"XML generated: {len(xml_content)} chars")
        
        # Get filename from request or use default
        filename = request.filename.replace('.n42', '') + '.n42'
        logger.info(f"Filename: {filename}")
        
        # Encode XML string to bytes for Response
        xml_bytes = xml_content.encode('utf-8')
        logger.info(f"Encoded to {len(xml_bytes)} bytes, returning Response...")
        
        return Response(
            content=xml_bytes,
            media_type="application/xml",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "application/xml; charset=utf-8"
            }
        )
    except ValueError as e:
        logger.error(f"ValueError: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def _export_spectrum_file(request: N42ExportRequest, fmt: str) -> Response:
    """PCF (GADRAS) and CHN (Ortec) through SpecUtils; the calibration error of the fitted polynomial is reported in a header."""
    from formats.spectrum_export import export_spectrum, SpectrumExportError, SpecUtilsUnavailable
    try:
        result = export_spectrum(request.model_dump(), fmt)
    except SpectrumExportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SpecUtilsUnavailable as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        logger.error(f"{e}")
        raise HTTPException(status_code=500, detail=str(e))
    stem = os.path.splitext(request.filename or "spectrum")[0] or "spectrum"
    return Response(
        content=result["content"],
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{stem}{result["extension"]}"',
            "X-Calibration-Max-Error-keV": f'{result["calibration_max_error_kev"]:.4f}',
            "X-Calibration-Calibrated": "true" if result["calibrated"] else "false",
        },
    )


@router.post("/export/pcf")
def export_pcf(request: N42ExportRequest):
    """Export the spectrum as a GADRAS PCF file (opens in InterSpec and GADRAS)."""
    return _export_spectrum_file(request, "pcf")


@router.post("/export/chn")
def export_chn(request: N42ExportRequest):
    """Export the spectrum as an Ortec CHN file (a polynomial calibration only)."""
    return _export_spectrum_file(request, "chn")


@router.post("/export/csv-auto")
def export_csv_auto(request: dict):
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
        logger.error(f"CSV auto-save error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save CSV: {str(e)}")


@router.post("/export/n42-auto")
def export_n42_auto(request: dict):
    """Auto-save spectrum to N42 with timestamped filename (default format)"""
    try:
        import os
        from datetime import datetime
        from formats.n42_exporter import generate_n42_xml
        
        # Create acquisitions directory if it doesn't exist
        save_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'acquisitions')
        os.makedirs(save_dir, exist_ok=True)
        
        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"spectrum_{timestamp}.n42"
        filepath = os.path.join(save_dir, filename)
        
        # Generate N42 XML
        n42_content = generate_n42_xml(request)
        
        # Write N42 file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(n42_content)
        
        return {
            "success": True,
            "filename": filename,
            "path": filepath,
            "message": f"Spectrum saved: {filename}"
        }
    except Exception as e:
        logger.error(f"N42 auto-save error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save N42: {str(e)}")


@router.post("/export/n42-checkpoint")
def export_n42_checkpoint(request: dict):
    """Save spectrum to overwriting checkpoint file during acquisition.
    
    This provides crash recovery - if acquisition fails, the most recent
    checkpoint can be recovered from data/acquisitions/acquisition_in_progress.n42
    """
    try:
        import os
        from datetime import datetime
        from formats.n42_exporter import generate_n42_xml
        
        save_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'acquisitions')
        os.makedirs(save_dir, exist_ok=True)
        
        # Single overwriting checkpoint file
        filepath = os.path.join(save_dir, "acquisition_in_progress.n42")
        n42_content = generate_n42_xml(request)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(n42_content)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[{timestamp}] Checkpoint saved: {filepath}")
        
        return {"success": True, "message": "Checkpoint saved"}
    except Exception as e:
        logger.error(f"Checkpoint save error: {e}")
        # Don't fail the acquisition for checkpoint failures
        return {"success": False, "message": str(e)}


@router.delete("/export/n42-checkpoint")
def delete_n42_checkpoint():
    """Delete checkpoint file after successful acquisition completion"""
    try:
        import os
        filepath = os.path.join(os.path.dirname(__file__), '..', 'data', 'acquisitions', 'acquisition_in_progress.n42')
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Checkpoint file cleaned up: {filepath}")
        return {"success": True}
    except Exception as e:
        logger.error(f"Checkpoint cleanup error: {e}")
        return {"success": False, "message": str(e)}


class N42MetadataRequest(BaseModel):
    xml_content: str
    metadata: Dict = None


@router.post("/n42/metadata")
def get_n42_metadata(request: N42MetadataRequest):
    """Get current metadata from an N42 file."""
    try:
        from formats.n42_metadata_editor import N42MetadataEditor
        editor = N42MetadataEditor(request.xml_content)
        return {"metadata": editor.get_current_metadata()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class N42UpdateRequest(BaseModel):
    xml_content: str
    start_time: Optional[str] = None
    live_time_s: Optional[float] = None
    real_time_s: Optional[float] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    sample_description: Optional[str] = None
    remarks: Optional[List[str]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@router.post("/n42/update-metadata")
def update_n42_metadata(request: N42UpdateRequest):
    """Update metadata in an N42 file and return modified XML."""
    try:
        from formats.n42_metadata_editor import N42MetadataEditor
        from datetime import datetime
        
        editor = N42MetadataEditor(request.xml_content)
        
        if request.start_time:
            try:
                ts = datetime.fromisoformat(request.start_time.replace('Z', '+00:00'))
                editor.set_timestamp(ts)
            except (ValueError, AttributeError):
                editor.set_timestamp(datetime.now())
        
        if request.live_time_s:
            editor.set_live_time(request.live_time_s)
        
        if request.real_time_s:
            editor.set_real_time(request.real_time_s)
            
        if request.manufacturer or request.model or request.serial_number:
            editor.set_instrument_info(
                manufacturer=request.manufacturer,
                model=request.model,
                serial_number=request.serial_number
            )
        
        if request.sample_description:
            editor.set_sample_description(request.sample_description)
        
        if request.remarks:
            for remark in request.remarks:
                editor.add_remark(remark)
        
        if request.latitude is not None and request.longitude is not None:
            editor.set_geolocation(request.latitude, request.longitude)
        
        return {"xml_content": editor.to_xml()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
