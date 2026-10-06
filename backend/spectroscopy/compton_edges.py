"""
Peaks that are probably the Compton edge of a stronger line, not a line.

A photon of energy E that scatters once through ~180 degrees leaves the crystal with at most 2E^2 / (511 + 2E) keV (477 keV for Cs-137's 662 keV).
Below that the spectrum is a continuum; at it, a step. On a scintillator the step is smeared over about a resolution width, and a peak finder
reports the bump below it as a peak: the "471 keV" peak beside every Cs-137 line.

This only FLAGS such a peak (`compton_edge_of`: the energy of the line it may belong to) so the page can say so; identification still sees it, because
a real weak line can sit on an edge (Ac-228's 409 keV beside the edge of Tl-208's 583 keV) and the flag cannot tell. It is a hint with a hedge, never a
verdict. A peak is flagged when it lies from 1.5 widths below the edge to half a width above it, and the line it would belong to is at least twice
its area (a real line is not more than a Compton shelf of a much weaker one).
"""
import math
from typing import Dict, List, Optional

MIN_PARENT_ENERGY_KEV = 250.0   # below this the edge lies under ~100 keV, mixed with X-rays and backscatter: no clean step
BELOW_EDGE_WIDTHS = 1.5
ABOVE_EDGE_WIDTHS = 0.5
MIN_AREA_RATIO = 2.0            # the parent line's net area over the flagged peak's


def compton_edge_kev(energy_kev: float) -> float:
    """The highest energy a single Compton scatter leaves in the detector."""
    return 2.0 * energy_kev * energy_kev / (511.0 + 2.0 * energy_kev)


def _fwhm(r662: float, energy: float) -> float:
    return r662 * 662.0 * math.sqrt(max(energy, 1.0) / 662.0)


def _area(peak: Dict) -> float:
    return float(peak.get("net_area") or peak.get("area") or peak.get("counts") or 0.0)


def flag_compton_edges(peaks: List[Dict], r662: float) -> int:
    """Sets `compton_edge_of` (the parent line's energy, keV) on each peak that looks like an edge, and removes it from the others. Returns the count."""
    flagged = 0
    for peak in peaks:
        peak.pop("compton_edge_of", None)
        own = _area(peak)
        best: Optional[float] = None
        for parent in peaks:
            if parent is peak or parent["energy"] < MIN_PARENT_ENERGY_KEV or _area(parent) < MIN_AREA_RATIO * max(own, 1.0):
                continue
            edge = compton_edge_kev(parent["energy"])
            width = _fwhm(r662, edge)
            if edge - BELOW_EDGE_WIDTHS * width <= peak["energy"] <= edge + ABOVE_EDGE_WIDTHS * width:
                if best is None or _area(parent) > _area(next(p for p in peaks if p["energy"] == best)):
                    best = parent["energy"]
        if best is not None:
            peak["compton_edge_of"] = round(best, 1)
            flagged += 1
    return flagged
