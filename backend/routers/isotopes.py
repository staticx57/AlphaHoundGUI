from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from isotope_database import load_custom_isotopes, save_custom_isotope, delete_custom_isotope

router = APIRouter()

class IsotopeModel(BaseModel):
    name: str
    energies: List[float]

@router.get("/isotopes/custom")
async def get_custom_isotopes():
    return load_custom_isotopes()

@router.post("/isotopes/custom")
async def add_custom_isotope(isotope: IsotopeModel):
    if not isotope.name:
        raise HTTPException(status_code=400, detail="Name required")
    save_custom_isotope(isotope.name, isotope.energies)
    return {"status": "success", "name": isotope.name}

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
async def import_custom_isotopes(data: Dict[str, List[float]]):
    """Import custom isotopes from JSON. Merges with existing."""
    if not data:
        raise HTTPException(status_code=400, detail="No isotopes provided")
    
    imported = 0
    for name, energies in data.items():
        if isinstance(energies, list) and all(isinstance(e, (int, float)) for e in energies):
            save_custom_isotope(name, energies)
            imported += 1
    
    return {"status": "success", "imported": imported}
