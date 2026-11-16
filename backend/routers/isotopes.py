from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List
from nuclides.isotope_database import load_custom_isotopes, save_custom_isotope, delete_custom_isotope

router = APIRouter()

class IsotopeModel(BaseModel):
    name: str
    energies: List[float]

@router.get("/isotopes/custom")
async def get_custom_isotopes():
    return load_custom_isotopes()

@router.post("/isotopes/custom")
async def add_custom_isotope(isotope: IsotopeModel):
    try:
        name = save_custom_isotope(isotope.name, isotope.energies)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "name": name}

@router.delete("/isotopes/custom/{name}")
async def remove_custom_isotope(name: str):
    if delete_custom_isotope(name):
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Isotope not found")

@router.get("/isotopes/custom/export")
async def export_custom_isotopes():
    """Export all custom isotopes as JSON for download."""
    isotopes = load_custom_isotopes()
    return {"isotopes": isotopes, "count": len(isotopes)}

@router.post("/isotopes/custom/import")
async def import_custom_isotopes(data: Dict[str, Any]):
    """Import custom isotopes from JSON ({name: [energies]}). Merges with existing; an entry whose name or energies
    are not acceptable is left out and listed under 'skipped' with the reason."""
    if not data:
        raise HTTPException(status_code=400, detail="No isotopes provided")
    if len(data) > 2000:
        raise HTTPException(status_code=400, detail="Too many entries in one file")
    
    imported = 0
    skipped = []
    for name, energies in data.items():
        try:
            save_custom_isotope(name, energies)
            imported += 1
        except ValueError as e:
            skipped.append({"name": str(name)[:80], "reason": str(e)})
    
    return {"status": "success", "imported": imported, "skipped": skipped}
