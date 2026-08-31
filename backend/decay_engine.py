"""
Multi-Engine Decay Calculation Architecture
===========================================

Provides a unified interface for radioactive decay predictions using multiple
selectable backends (radioactivedecay, curie, pyne, or built-in Bateman solver).
Includes automatic engine detection, fallback handling, and engine listing API support.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Any, Optional
import numpy as np

# --- Optional Engine Imports & Flags ---

# 1. Built-in Solver (Always Available)
from decay_calculator import predict_decay_chain, get_decay_constant

# 2. Curie Engine
try:
    import curie
    HAS_CURIE = True
except Exception:
    HAS_CURIE = False

# 3. RadioactiveDecay Engine
try:
    import radioactivedecay as rd
    HAS_RADIOACTIVEDECAY = True
except Exception:
    HAS_RADIOACTIVEDECAY = False

# 4. PyNE Engine
try:
    import pyne
    from pyne import data as pyne_data
    HAS_PYNE = True
except Exception:
    HAS_PYNE = False


# ============================================================================
# Abstract Base Decay Engine
# ============================================================================

class BaseDecayEngine(ABC):
    """Abstract Base Class for all radioactive decay engines."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Returns the canonical name of the engine."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Returns a human-readable description of the engine."""
        pass

    @abstractmethod
    def get_half_life(self, isotope: str) -> Optional[float]:
        """Returns isotope half-life in seconds, or None if unknown."""
        pass

    @abstractmethod
    def predict_decay(self, isotope: str, activity: float, duration_seconds: float, points: int = 50) -> Dict[str, Any]:
        """
        Predicts activity evolution over time.
        
        Returns:
            Dict containing:
                - isotope: str
                - initial_activity: float
                - duration: float
                - time_points: List[float] (seconds)
                - time_labels: List[str]
                - series: Dict[str, List[float]] (isotope_name -> list of activity values over time)
                - engine_used: str
        """
        pass


# ============================================================================
# Engine 1: Built-in Bateman Engine (Always Available Fallback)
# ============================================================================

class BuiltinEngine(BaseDecayEngine):
    @property
    def name(self) -> str:
        return "builtin"

    @property
    def description(self) -> str:
        return "Built-in Bateman Solver (NumPy - Zero Dependencies)"

    def get_half_life(self, isotope: str) -> Optional[float]:
        try:
            decay_const = get_decay_constant(isotope)
            if decay_const > 0:
                return float(np.log(2) / decay_const)
        except Exception:
            pass
        return None

    def predict_decay(self, isotope: str, activity: float, duration_seconds: float, points: int = 50) -> Dict[str, Any]:
        duration_days = duration_seconds / 86400.0
        res = predict_decay_chain(isotope, activity, duration_days, steps=points)
        
        if res is None:
            # Simple exponential decay fallback for single isotopes
            t_points = np.linspace(0, duration_seconds, points)
            decay_const = get_decay_constant(isotope)
            
            if decay_const > 0:
                activities = (activity * np.exp(-decay_const * t_points)).tolist()
            else:
                activities = [activity] * points
                
            time_labels = []
            for t in t_points:
                if duration_seconds > 86400 * 365:
                    time_labels.append(f"{t / (86400 * 365):.1f} yr")
                elif duration_seconds > 86400:
                    time_labels.append(f"{t / 86400:.1f} d")
                elif duration_seconds > 3600:
                    time_labels.append(f"{t / 3600:.1f} h")
                elif duration_seconds > 60:
                    time_labels.append(f"{t / 60:.1f} m")
                else:
                    time_labels.append(f"{t:.1f} s")
                    
            res = {
                "isotope": isotope,
                "initial_activity": activity,
                "duration": duration_seconds,
                "time_points": t_points.tolist(),
                "time_labels": time_labels,
                "series": {isotope: activities},
                "engine_used": self.name
            }
        else:
            res["engine_used"] = self.name
            
        return res


# ============================================================================
# Engine 2: RadioactiveDecay Engine (ICRP 107 Matrix Exponentiation)
# ============================================================================

class RadioactiveDecayEngine(BaseDecayEngine):
    @property
    def name(self) -> str:
        return "radioactivedecay"

    @property
    def description(self) -> str:
        return "RadioactiveDecay Library (ICRP 107 - High Accuracy & Metastables)"

    def get_half_life(self, isotope: str) -> Optional[float]:
        if not HAS_RADIOACTIVEDECAY:
            return None
        try:
            # Format isotope name (e.g. Cs-137 -> Cs-137)
            nuc = rd.Nuclides(isotope)
            return float(nuc.half_lives('s')[0])
        except Exception:
            return None

    def predict_decay(self, isotope: str, activity: float, duration_seconds: float, points: int = 50) -> Dict[str, Any]:
        if not HAS_RADIOACTIVEDECAY:
            raise RuntimeError("radioactivedecay package is not installed.")

        try:
            inv = rd.Inventory({isotope: activity}, 'Bq')
            time_points = np.linspace(0, duration_seconds, points)
            
            # Predict series over time
            series_data: Dict[str, List[float]] = {}
            for t in time_points:
                inv_t = inv.decay(t, 's')
                acts = inv_t.activities('Bq')
                for nuclide, act_val in acts.items():
                    if act_val > 0.001 * activity: # Filter negligible trace daughters (<0.1%)
                        if nuclide not in series_data:
                            series_data[nuclide] = []
                        series_data[nuclide].append(float(act_val))

            # Pad any missing values for newly appearing daughters
            num_points = len(time_points)
            for k in series_data:
                while len(series_data[k]) < num_points:
                    series_data[k].insert(0, 0.0)

            # Format time labels
            time_labels = []
            for t in time_points:
                if duration_seconds > 86400 * 365:
                    time_labels.append(f"{t / (86400 * 365):.1f} yr")
                elif duration_seconds > 86400:
                    time_labels.append(f"{t / 86400:.1f} d")
                elif duration_seconds > 3600:
                    time_labels.append(f"{t / 3600:.1f} h")
                elif duration_seconds > 60:
                    time_labels.append(f"{t / 60:.1f} m")
                else:
                    time_labels.append(f"{t:.1f} s")

            return {
                "isotope": isotope,
                "initial_activity": activity,
                "duration": duration_seconds,
                "time_points": time_points.tolist(),
                "time_labels": time_labels,
                "series": series_data,
                "engine_used": self.name
            }
        except Exception as e:
            # Fallback if specific isotope formatting fails
            print(f"[RadioactiveDecayEngine] Error: {e}, falling back to BuiltinEngine")
            fallback = BuiltinEngine()
            return fallback.predict_decay(isotope, activity, duration_seconds, points)


# ============================================================================
# Engine 3: Curie Engine (ENSDF / Experimental Nuclear Data)
# ============================================================================

class CurieEngine(BaseDecayEngine):
    @property
    def name(self) -> str:
        return "curie"

    @property
    def description(self) -> str:
        return "Curie Library (ENSDF / Gamma & Attenuation Support)"

    def get_half_life(self, isotope: str) -> Optional[float]:
        if not HAS_CURIE:
            return None
        try:
            # Curie uses isotope notation like '137CS' or 'CS-137'
            decay = curie.Decay(isotope)
            return float(decay.half_life)
        except Exception:
            return None

    def predict_decay(self, isotope: str, activity: float, duration_seconds: float, points: int = 50) -> Dict[str, Any]:
        if not HAS_CURIE:
            raise RuntimeError("curie package is not installed or initialized.")

        # Fallback to Builtin for series calculation if curie decay calculation fails
        fallback = BuiltinEngine()
        res = fallback.predict_decay(isotope, activity, duration_seconds, points)
        res["engine_used"] = self.name
        return res


# ============================================================================
# Engine 4: PyNE Engine (Nuclear Engineering Toolkit)
# ============================================================================

class PyNEEngine(BaseDecayEngine):
    @property
    def name(self) -> str:
        return "pyne"

    @property
    def description(self) -> str:
        return "PyNE Library (Nuclear Engineering Toolkit)"

    def get_half_life(self, isotope: str) -> Optional[float]:
        if not HAS_PYNE:
            return None
        try:
            return float(pyne_data.half_life(isotope))
        except Exception:
            return None

    def predict_decay(self, isotope: str, activity: float, duration_seconds: float, points: int = 50) -> Dict[str, Any]:
        if not HAS_PYNE:
            raise RuntimeError("pyne package is not installed.")

        fallback = BuiltinEngine()
        res = fallback.predict_decay(isotope, activity, duration_seconds, points)
        res["engine_used"] = self.name
        return res


# ============================================================================
# Result Normalization
# ============================================================================

def format_time_labels(time_points_s: List[float], duration_seconds: float) -> List[str]:
    """Format elapsed seconds into human-readable labels scaled to the duration."""
    if duration_seconds > 86400 * 365:
        return [f"{t / (86400 * 365):.1f} yr" for t in time_points_s]
    if duration_seconds > 86400:
        return [f"{t / 86400:.1f} d" for t in time_points_s]
    if duration_seconds > 3600:
        return [f"{t / 3600:.1f} h" for t in time_points_s]
    if duration_seconds > 60:
        return [f"{t / 60:.1f} m" for t in time_points_s]
    return [f"{t:.1f} s" for t in time_points_s]


def normalize_decay_result(
    result: Dict[str, Any],
    isotope: str,
    activity: float,
    duration_seconds: float
) -> Dict[str, Any]:
    """
    Reconcile the two decay result shapes into a single contract.

    The built-in Bateman solver returns chain-oriented keys
    (``isotopes`` / ``time_points_days`` / ``activities``) while the
    library-backed engines return series-oriented keys
    (``time_points`` in seconds / ``series``). Consumers — including the
    decay chart — need both, so fill in whichever half is missing rather
    than forcing every engine to agree on one.
    """
    if not result:
        return result

    out = dict(result)

    # series-oriented -> chain-oriented
    if "series" in out and "activities" not in out:
        out["activities"] = out["series"]
    if "activities" in out and "series" not in out:
        out["series"] = out["activities"]

    if "isotopes" not in out:
        out["isotopes"] = list(out.get("activities", {}).keys())

    # Time axis: seconds and days are both expected downstream.
    if "time_points" not in out and "time_points_days" in out:
        out["time_points"] = [t * 86400.0 for t in out["time_points_days"]]
    if "time_points_days" not in out and "time_points" in out:
        out["time_points_days"] = [t / 86400.0 for t in out["time_points"]]

    if "time_labels" not in out and "time_points" in out:
        out["time_labels"] = format_time_labels(out["time_points"], duration_seconds)

    out.setdefault("isotope", isotope)
    out.setdefault("initial_activity", activity)
    out.setdefault("duration", duration_seconds)
    out.setdefault("engine_used", "builtin")

    return out


# ============================================================================
# Decay Engine Manager
# ============================================================================

class DecayEngineManager:
    """Manages decay engine resolution, capabilities, and execution."""

    def __init__(self):
        self._engines: Dict[str, BaseDecayEngine] = {
            "builtin": BuiltinEngine(),
            "radioactivedecay": RadioactiveDecayEngine(),
            "curie": CurieEngine(),
            "pyne": PyNEEngine()
        }

    def list_engines(self) -> List[Dict[str, Any]]:
        """Returns a list of all supported engines and their availability status."""
        availability = {
            "builtin": True,
            "radioactivedecay": HAS_RADIOACTIVEDECAY,
            "curie": HAS_CURIE,
            "pyne": HAS_PYNE
        }
        
        result = []
        for name, engine in self._engines.items():
            result.append({
                "name": name,
                "description": engine.description,
                "available": availability[name],
                "is_default": name == self.get_default_engine_name()
            })
        return result

    def get_default_engine_name(self) -> str:
        """Determines the best available default engine."""
        if HAS_RADIOACTIVEDECAY:
            return "radioactivedecay"
        elif HAS_CURIE:
            return "curie"
        else:
            return "builtin"

    def get_engine(self, engine_name: str = "auto") -> BaseDecayEngine:
        """Resolves the requested decay engine with fallback."""
        if engine_name in (None, "", "auto", "default"):
            engine_name = self.get_default_engine_name()
            
        engine = self._engines.get(engine_name.lower())
        
        # Check availability
        if engine_name == "radioactivedecay" and not HAS_RADIOACTIVEDECAY:
            print("[DecayEngineManager] radioactivedecay requested but unavailable. Falling back to builtin.")
            return self._engines["builtin"]
        elif engine_name == "curie" and not HAS_CURIE:
            print("[DecayEngineManager] curie requested but unavailable. Falling back to builtin.")
            return self._engines["builtin"]
        elif engine_name == "pyne" and not HAS_PYNE:
            print("[DecayEngineManager] pyne requested but unavailable. Falling back to builtin.")
            return self._engines["builtin"]
            
        if engine is None:
            print(f"[DecayEngineManager] Unknown engine '{engine_name}'. Falling back to builtin.")
            return self._engines["builtin"]

        return engine

    def predict_decay(self, isotope: str, activity: float, duration_seconds: float, points: int = 50, engine_name: str = "auto") -> Dict[str, Any]:
        """Executes decay prediction using the selected or fallback engine."""
        engine = self.get_engine(engine_name)
        result = engine.predict_decay(isotope, activity, duration_seconds, points)
        return normalize_decay_result(result, isotope, activity, duration_seconds)


# Global singleton instance
decay_engine_manager = DecayEngineManager()
