"""
Source-Specific Enhanced Analysis Module

Provides source-context insights when analyzing specific source types:
- Mass estimation (Ra-226, K, ThO₂)
- Dose rate estimation
- Comparison to standard activities
- Decay-corrected calculations

Each function returns a dictionary of enhanced analysis results to be
displayed alongside the standard ROI analysis output.
"""

from typing import Dict, Any, Optional
from datetime import datetime
import math

# Physical constants
RA226_SPECIFIC_ACTIVITY = 3.66e10  # Bq/g
TH232_SPECIFIC_ACTIVITY = 4070     # Bq/g  
K40_SPECIFIC_ACTIVITY = 31.4       # Bq/g of natural K (K-40 is 0.0117%)
CS137_HALF_LIFE_YEARS = 30.17
CO60_HALF_LIFE_YEARS = 5.27
AM241_STANDARD_ACTIVITY = 37000    # Bq (~1 µCi typical smoke detector)
HUMAN_BODY_K40 = 4400              # Bq K-40 in typical human body


def analyze_radium_dial(activity_bq: float) -> Dict[str, Any]:
    """
    Radium dial analysis: Ra-226 mass and dose rate estimation.
    
    Ra-226 activity equals Bi-214 activity in secular equilibrium.
    Dose rate estimate at 1 meter: ~8.25 µSv/hr per GBq.
    """
    if activity_bq <= 0:
        return {"error": "Invalid activity for Ra-226 analysis"}
    
    # Ra-226 mass estimation
    ra226_mass_ug = (activity_bq / RA226_SPECIFIC_ACTIVITY) * 1e6
    
    # Dose rate at 1 meter (approximate)
    dose_rate_uSv_hr_1m = activity_bq * 8.25e-9
    
    # Dose rate at contact (approx 10x higher)
    dose_rate_uSv_hr_contact = dose_rate_uSv_hr_1m * 10
    
    return {
        "source_type": "radium_dial",
        "insights": [
            {
                "label": "Ra-226 Mass",
                "value": f"{ra226_mass_ug:.3f} µg",
                "icon": "⚗️"
            },
            {
                "label": "Dose Rate (1m)",
                "value": f"{dose_rate_uSv_hr_1m:.2f} µSv/hr",
                "icon": "☢️"
            },
            {
                "label": "Dose Rate (Contact)",
                "value": f"{dose_rate_uSv_hr_contact:.1f} µSv/hr",
                "icon": "⚠️",
                "warning": dose_rate_uSv_hr_contact > 10
            }
        ]
    }


def analyze_smoke_detector(activity_bq: float) -> Dict[str, Any]:
    """
    Smoke detector (Am-241) analysis: Compare to standard activity.
    
    Standard ionization smoke detector contains ~1 µCi (37 kBq) of Am-241.
    """
    if activity_bq <= 0:
        return {"error": "Invalid activity for Am-241 analysis"}
    
    percent_of_standard = (activity_bq / AM241_STANDARD_ACTIVITY) * 100
    
    status = "Normal"
    if percent_of_standard < 50:
        status = "Low (may need replacement)"
    elif percent_of_standard > 150:
        status = "Higher than typical single detector"
    
    return {
        "source_type": "smoke_detector",
        "insights": [
            {
                "label": "% of Standard",
                "value": f"{percent_of_standard:.1f}%",
                "icon": "📊"
            },
            {
                "label": "Standard Activity",
                "value": "~37 kBq (1 µCi)",
                "icon": "ℹ️"
            },
            {
                "label": "Status",
                "value": status,
                "icon": "🔵" if 50 <= percent_of_standard <= 150 else "⚠️"
            }
        ]
    }


def analyze_cesium137(activity_bq: float, manufacture_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Cesium-137 analysis: Decay calculation, half-life remaining.
    
    Half-life: 30.17 years
    """
    if activity_bq <= 0:
        return {"error": "Invalid activity for Cs-137 analysis"}
    
    insights = [
        {
            "label": "Current Activity",
            "value": f"{activity_bq:.1f} Bq",
            "icon": "🟡"
        },
        {
            "label": "Half-life",
            "value": f"{CS137_HALF_LIFE_YEARS} years",
            "icon": "⏱️"
        }
    ]
    
    if manufacture_date:
        try:
            mfg = datetime.strptime(manufacture_date, "%Y-%m-%d")
            years_elapsed = (datetime.now() - mfg).days / 365.25
            decay_factor = 0.5 ** (years_elapsed / CS137_HALF_LIFE_YEARS)
            original_activity = activity_bq / decay_factor
            insights.append({
                "label": "Original Activity",
                "value": f"{original_activity:.1f} Bq",
                "icon": "📅"
            })
        except:
            pass
    
    return {
        "source_type": "cesium_source",
        "insights": insights
    }


def analyze_cobalt60(activity_bq: float, manufacture_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Cobalt-60 analysis: Age estimation important due to short half-life.
    
    Half-life: 5.27 years
    """
    if activity_bq <= 0:
        return {"error": "Invalid activity for Co-60 analysis"}
    
    insights = [
        {
            "label": "Current Activity",
            "value": f"{activity_bq:.1f} Bq",
            "icon": "🔴"
        },
        {
            "label": "Half-life",
            "value": f"{CO60_HALF_LIFE_YEARS} years",
            "icon": "⏱️"
        }
    ]
    
    if manufacture_date:
        try:
            mfg = datetime.strptime(manufacture_date, "%Y-%m-%d")
            years_elapsed = (datetime.now() - mfg).days / 365.25
            decay_factor = 0.5 ** (years_elapsed / CO60_HALF_LIFE_YEARS)
            original_activity = activity_bq / decay_factor
            insights.append({
                "label": "Original Activity",
                "value": f"{original_activity:.1f} Bq",
                "icon": "📅"
            })
            insights.append({
                "label": "Years Since Manufacture",
                "value": f"{years_elapsed:.1f} years",
                "icon": "📆"
            })
        except:
            pass
    
    return {
        "source_type": "cobalt_source",
        "insights": insights
    }


def analyze_potassium40(activity_bq: float) -> Dict[str, Any]:
    """
    Potassium-40 analysis: K mass estimation and body equivalent.
    
    K-40 is 0.0117% of natural potassium.
    Human body contains ~4,400 Bq K-40.
    """
    if activity_bq <= 0:
        return {"error": "Invalid activity for K-40 analysis"}
    
    # Mass of natural potassium
    k_mass_g = activity_bq / K40_SPECIFIC_ACTIVITY
    
    # Human body equivalent
    body_equivalent = (activity_bq / HUMAN_BODY_K40) * 100
    
    return {
        "source_type": "natural_background",
        "insights": [
            {
                "label": "Potassium Mass",
                "value": f"{k_mass_g:.1f} g",
                "icon": "🧪"
            },
            {
                "label": "Human Body Equiv.",
                "value": f"{body_equivalent:.0f}%",
                "icon": "🧍"
            },
            {
                "label": "Body K-40 Reference",
                "value": "~4,400 Bq",
                "icon": "ℹ️"
            }
        ]
    }


def analyze_thoriated_lens(activity_bq: float) -> Dict[str, Any]:
    """
    Thoriated lens analysis: ThO₂ mass estimation from Th-234 activity.
    
    Th-234 activity equals Th-232 activity in secular equilibrium.
    """
    if activity_bq <= 0:
        return {"error": "Invalid activity for Th-232 analysis"}
    
    # Th-232 mass from activity
    th232_mass_mg = (activity_bq / TH232_SPECIFIC_ACTIVITY) * 1000
    
    # ThO₂ mass (MW ratio: ThO₂/Th = 264/232 = 1.138)
    tho2_mass_mg = th232_mass_mg * 1.138
    
    return {
        "source_type": "thoriated_lens",
        "insights": [
            {
                "label": "ThO₂ Mass",
                "value": f"{tho2_mass_mg:.1f} mg",
                "icon": "📷"
            },
            {
                "label": "Th-232 Mass",
                "value": f"{th232_mass_mg:.1f} mg",
                "icon": "⚗️"
            }
        ]
    }


def analyze_uranium_source(activity_bq: float, source_type: str = "uranium_glass") -> Dict[str, Any]:
    """
    Uranium source analysis: Activity context for uranium glass/ore.
    """
    if activity_bq <= 0:
        return {"error": "Invalid activity for uranium analysis"}
    
    source_label = "Uranium Glass" if source_type == "uranium_glass" else "Uranium Ore"
    
    return {
        "source_type": source_type,
        "insights": [
            {
                "label": "U-235 Activity",
                "value": f"{activity_bq:.1f} Bq",
                "icon": "⚛️"
            },
            {
                "label": "Source Type",
                "value": source_label,
                "icon": "🟢" if source_type == "uranium_glass" else "🪨"
            }
        ]
    }


def get_enhanced_analysis(source_type: str, activity_bq: float, 
                         manufacture_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Main entry point: Get enhanced analysis based on source type.
    
    Args:
        source_type: The selected source type (e.g., 'radium_dial')
        activity_bq: Calculated activity in Bq
        manufacture_date: Optional manufacture date for decay calculations
        
    Returns:
        Dictionary with enhanced analysis insights, or None if not applicable
    """
    if source_type == "radium_dial":
        return analyze_radium_dial(activity_bq)
    elif source_type == "smoke_detector":
        return analyze_smoke_detector(activity_bq)
    elif source_type == "cesium_source":
        return analyze_cesium137(activity_bq, manufacture_date)
    elif source_type == "cobalt_source":
        return analyze_cobalt60(activity_bq, manufacture_date)
    elif source_type == "natural_background":
        return analyze_potassium40(activity_bq)
    elif source_type in ["thoriated_lens", "takumar_lens"]:
        return analyze_thoriated_lens(activity_bq)
    elif source_type in ["uranium_glass", "uranium_ore"]:
        return analyze_uranium_source(activity_bq, source_type)
    
    return None
