from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from ..isotope_database import load_custom_isotopes, save_custom_isotope, delete_custom_isotope

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
