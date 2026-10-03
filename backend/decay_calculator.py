"""
Decay data and chain calculations that need nothing beyond the standard library.

The decay data (half-lives and branching fractions) is generated from ICRP Publication 107 into decay_data.py; the chain
mathematics is in bateman.py. This module ties them together for the rest of the app:

  - normalize_isotope()      "cs-137", "Cs137", "137Cs", "Tc99m" -> "Cs-137", "Cs-137", "Cs-137", "Tc-99m"
  - get_decay_constant(), HALF_LIVES, CHAINS   (the names older code imports)
  - predict_decay_chain()    activities of a parent and all its progeny over time (any parent in the table, with branching)
  - get_isotope_info(), get_decay_chain()   what /analyze/isotope-info returns
"""

import math
import re
from typing import Dict, List, Optional

import numpy as np

import bateman
from decay_data import DECAY_TABLE, SOURCE as TABLE_SOURCE

try:  # optional: a wider nuclide list for isotope information
    import radioactivedecay as _rd
except Exception:  # pragma: no cover - depends on the install
    _rd = None


class DecayInputError(ValueError):
    """The caller asked for something that cannot be computed (unknown isotope, negative duration, ...): a 400, not a 500."""


# nuclide -> (half-life in seconds | None, ((daughter, fraction), ...)); see decay_data.py
GRAPH = DECAY_TABLE

# kept for code that imported these names
HALF_LIVES: Dict[str, float] = {n: hl for n, (hl, _) in GRAPH.items() if hl}
CHAINS: Dict[str, List[str]] = {
    "U-238 Sequence": bateman.topological_order(GRAPH, "U-238"),
    "Th-232 Sequence": bateman.topological_order(GRAPH, "Th-232"),
}

_ALIASES = {"uranium": "U-238", "thorium": "Th-232", "radium": "Ra-226", "radon": "Rn-222", "potassium": "K-40", "cesium": "Cs-137",
            "caesium": "Cs-137", "cobalt": "Co-60", "strontium": "Sr-90", "americium": "Am-241"}
_META = {"m": "m", "m1": "m", "n": "n", "m2": "n"}


def normalize_isotope(name) -> str:
    """'cs-137' / 'Cs137' / '137Cs' / 'CS 137' -> 'Cs-137'; 'Tc99m' / '99mTc' -> 'Tc-99m'. Raises DecayInputError if unreadable."""
    text = str(name or "").strip()
    if not text:
        raise DecayInputError("No isotope given.")
    alias = _ALIASES.get(text.lower())
    if alias:
        return alias
    m = re.fullmatch(r"([A-Za-z]{1,2})\s*-?\s*(\d{1,3})\s*-?\s*([mMnN]\d?)?", text)
    if m:
        symbol, mass, meta = m.group(1), m.group(2), m.group(3)
    else:
        m = re.fullmatch(r"(\d{1,3})\s*([mMnN]\d?)?\s*-?\s*([A-Za-z]{1,2})", text)
        if not m:
            raise DecayInputError(f"Could not read the isotope name {text!r}. Use a form like Cs-137, Co60 or Tc-99m.")
        mass, meta, symbol = m.group(1), m.group(2), m.group(3)
    suffix = _META.get((meta or "").lower(), "") if meta else ""
    return f"{symbol[0].upper()}{symbol[1:].lower()}-{int(mass)}{suffix}"


def format_half_life(seconds: Optional[float]) -> str:
    """164.3e-6 -> '164.3 µs'; 9.5e8 -> '30.17 y'; None -> 'stable'."""
    if seconds is None or not math.isfinite(seconds) or seconds <= 0:
        return "stable"
    for limit, unit, scale in ((1e-3, "µs", 1e-6), (1.0, "ms", 1e-3), (60.0, "s", 1.0), (3600.0, "min", 60.0), (86400.0, "h", 3600.0),
                               (86400.0 * 365.25, "d", 86400.0)):
        if seconds < limit:
            return f"{seconds / scale:.4g} {unit}"
    years = seconds / (86400.0 * 365.25)
    return f"{years:.4g} y" if years < 1e6 else f"{years:.3e} y"


def get_decay_constant(isotope: str) -> float:
    """lambda = ln(2) / half-life in 1/s; 0.0 for a stable or unknown nuclide (callers must not mistake that for 'does not decay')."""
    try:
        hl = GRAPH.get(normalize_isotope(isotope), (None, ()))[0]
    except DecayInputError:
        return 0.0
    return math.log(2) / hl if hl else 0.0


def bateman_solution(chain_isotopes: List[str], initial_activity: float, time_points_s: List[float]) -> Dict[str, List[float]]:
    """Activities along a plain A -> B -> C chain (every branching fraction 1), for callers that pass their own list."""
    graph = {}
    for i, n in enumerate(chain_isotopes):
        nxt = chain_isotopes[i + 1:i + 2]
        graph[n] = (GRAPH.get(n, (None, ()))[0], tuple((d, 1.0) for d in nxt))
    return bateman.solve_chain(graph, chain_isotopes[0], initial_activity, time_points_s) if chain_isotopes else {}


def predict_decay_chain(parent_isotope: str, initial_activity_bq: float, duration_days: float, steps: int = 50) -> Optional[Dict]:
    """
    Activity of `parent_isotope` and every nuclide below it over `duration_days`, with branching (any parent in the table).
    Returns None when the table has no decay data for the parent.
    """
    try:
        parent = normalize_isotope(parent_isotope)
    except DecayInputError:
        return None
    if not bateman.is_radioactive(GRAPH, parent):
        return None
    times = np.linspace(0, duration_days * 86400.0, steps).tolist()
    activities = bateman.solve_chain(GRAPH, parent, initial_activity_bq, times)
    return {"isotopes": list(activities), "time_points_days": [t / 86400.0 for t in times], "activities": activities}


# ----------------------------------------------------------------------------------------------- isotope information

def _rd_graph(parent: str) -> Optional[Dict]:
    """The decay graph below `parent` from radioactivedecay (a wider list than the table), or None."""
    if _rd is None:
        return None
    graph, todo = {}, [parent]
    try:
        while todo:
            name = todo.pop()
            if name in graph:
                continue
            nuc = _rd.Nuclide(name)
            hl = nuc.half_life("s")
            if isinstance(hl, str) or hl is None or not math.isfinite(float(hl)):
                graph[name] = (None, ())
                continue
            products = tuple((str(p), float(b)) for p, b in zip(nuc.progeny(), nuc.branching_fractions()) if b > 0 and p != "SF")
            graph[name] = (float(hl), products)
            todo.extend(p for p, _ in products)
    except Exception:
        return None
    return graph


def _graph_for(isotope: str) -> Dict:
    if isotope in GRAPH:
        return GRAPH
    graph = _rd_graph(isotope)
    if graph is None:
        raise DecayInputError(f"No decay data for {isotope}.")
    return graph


def get_isotope_info(isotope: str) -> Dict:
    """Half-life, what it decays to (with branching) and which named series it belongs to."""
    name = normalize_isotope(isotope)
    graph = _graph_for(name)
    hl, products = graph.get(name, (None, ()))
    modes: List[Dict] = []
    source = TABLE_SOURCE
    if _rd is not None:
        try:
            nuc = _rd.Nuclide(name)
            modes = [{"mode": str(m), "daughter": str(p), "branching": float(b)}
                     for m, p, b in zip(nuc.decay_modes(), nuc.progeny(), nuc.branching_fractions())]
            source = f"ICRP Publication 107 (radioactivedecay {_rd.__version__})"
        except Exception:
            modes = []
    series = [label for label, members in CHAINS.items() if name in members]
    return {
        "isotope": name,
        "half_life_s": hl,
        "half_life_readable": format_half_life(hl),
        "stable": hl is None,
        "daughters": [{"isotope": d, "branching": b} for d, b in products],
        "decay_modes": modes,
        "series": series[0] if series else None,
        "data_source": source,
    }


def get_decay_chain(isotope: str) -> List[Dict]:
    """Every nuclide the isotope passes through, in decay order, ending with the stable ones."""
    name = normalize_isotope(isotope)
    graph = _graph_for(name)
    order = bateman.topological_order(graph, name) if bateman.is_radioactive(graph, name) else [name]
    chain = [{"isotope": n, "half_life_s": graph.get(n, (None, ()))[0], "half_life_readable": format_half_life(graph.get(n, (None, ()))[0]),
              "stable": False} for n in order]
    ends: List[str] = []
    for n in order:
        for d, _ in graph.get(n, (None, ()))[1]:
            if not bateman.is_radioactive(graph, d) and d not in ends:
                ends.append(d)
    chain.extend({"isotope": n, "half_life_s": None, "half_life_readable": "stable", "stable": True} for n in ends)
    if not bateman.is_radioactive(graph, name):
        chain[0]["stable"] = True
    return chain
