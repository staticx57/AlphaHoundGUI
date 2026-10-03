"""
Decay calculation engines
=========================

One interface, three real engines, each with its own nuclear data:

  radioactivedecay   ICRP Publication 107 data, solved by the library (matrix exponential). The default when installed.
  curie              ENSDF half-lives and branching fractions read from Curie's database, solved with bateman.py.
  builtin            ICRP-107 data embedded in decay_data.py, solved with bateman.py: needs no optional package.

(An earlier version also listed a "PyNE" engine and a "Curie" engine that simply ran the built-in solver under another
name. They are gone: an engine that is not what its label says is worse than a missing one.)

Every engine returns the same shape: the nuclides that matter as full-length series (one activity per time point),
ordered along the decay chain, plus the engine, its data source and the nuclides left out for being negligible.
"""

import logging
import math
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from nuclides import bateman
from nuclides.decay_calculator import DecayInputError, GRAPH, TABLE_SOURCE, _rd_graph, normalize_isotope

logger = logging.getLogger(__name__)

try:
    import radioactivedecay as rd
    HAS_RADIOACTIVEDECAY = True
except Exception:
    rd = None
    HAS_RADIOACTIVEDECAY = False

from nuclides.curie_compat import CURIE_LOCK, make_curie_thread_safe

try:
    import curie
    HAS_CURIE = True
    make_curie_thread_safe(curie)       # Curie's SQLite connections would otherwise only work in the thread that opened them
except Exception:
    curie = None
    HAS_CURIE = False

# a nuclide is plotted if at any time it reaches this fraction of the starting activity
TRACE_FRACTION = 1e-3
MAX_DURATION_S = 1e24          # about 3e16 years: beyond the longest half-life in the data, and still finite in every engine
MIN_POINTS, MAX_POINTS = 2, 2000


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


def package_series(engine: "BaseDecayEngine", isotope: str, activity: float, duration_seconds: float, times: np.ndarray,
                   raw: Dict[str, Any], order: List[str]) -> Dict[str, Any]:
    """
    The one result shape. `raw` maps nuclide -> activity at every time point. Nuclides that never reach TRACE_FRACTION of the
    starting activity are left out (and listed), the rest keep ALL their points, ordered along the chain with the parent first.
    """
    full = {str(n): [float(x) for x in np.asarray(v, dtype=float)] for n, v in raw.items()}
    rank = {n: i for i, n in enumerate(order)}
    names = sorted(full, key=lambda n: (rank.get(n, len(rank)), n))
    keep = [n for n in names if n == isotope or max(full[n]) >= TRACE_FRACTION * activity]
    omitted = [n for n in names if n not in keep and max(full[n]) > 0]
    return {
        "isotope": isotope,
        "initial_activity": activity,
        "duration": duration_seconds,
        "time_points": [float(t) for t in times],
        "time_labels": format_time_labels(list(times), duration_seconds),
        "series": {n: full[n] for n in keep},
        "isotopes": keep,
        "omitted": omitted,
        "engine_used": engine.name,
        "engine_version": engine.version,
        "data_source": engine.data_source,
    }


class BaseDecayEngine(ABC):
    """Abstract Base Class for all radioactive decay engines."""

    available = True

    @property
    @abstractmethod
    def name(self) -> str:
        """The canonical name of the engine."""

    @property
    @abstractmethod
    def description(self) -> str:
        """A human-readable description of the engine."""

    @property
    def version(self) -> Optional[str]:
        return None

    @property
    def data_source(self) -> str:
        return ""

    @abstractmethod
    def get_half_life(self, isotope: str) -> Optional[float]:
        """Half-life in seconds; None for a stable or unknown nuclide."""

    @abstractmethod
    def predict_decay(self, isotope: str, activity: float, duration_seconds: float, points: int = 50) -> Dict[str, Any]:
        """
        Activity of the isotope and its progeny over time.
        Raises DecayInputError if the engine has no data for the isotope or it is stable.
        """


# ============================================================================
# Engine 1: built-in (embedded ICRP-107 table + Bateman solver)
# ============================================================================

class BuiltinEngine(BaseDecayEngine):
    @property
    def name(self) -> str:
        return "builtin"

    @property
    def description(self) -> str:
        return "Built-in solver (ICRP-107 data embedded; needs no extra package)"

    @property
    def data_source(self) -> str:
        return TABLE_SOURCE

    def get_half_life(self, isotope: str) -> Optional[float]:
        try:
            return GRAPH.get(normalize_isotope(isotope), (None, ()))[0]
        except DecayInputError:
            return None

    def predict_decay(self, isotope: str, activity: float, duration_seconds: float, points: int = 50) -> Dict[str, Any]:
        parent = normalize_isotope(isotope)
        if parent not in GRAPH:
            raise DecayInputError(
                f"The built-in engine has no decay data for {parent}: it covers {len(GRAPH)} nuclides from {len(bateman_parents())} "
                "parents (the natural series, common sources and medical isotopes). Try the radioactivedecay engine.")
        if not bateman.is_radioactive(GRAPH, parent):
            raise DecayInputError(f"{parent} is stable: it does not decay.")
        times = np.linspace(0, duration_seconds, points)
        raw = bateman.solve_chain(GRAPH, parent, activity, times)
        return package_series(self, parent, activity, duration_seconds, times, raw, list(raw))


def bateman_parents() -> Tuple[str, ...]:
    from nuclides.decay_data import PARENTS
    return PARENTS


# ============================================================================
# Engine 2: radioactivedecay (ICRP-107, matrix exponential)
# ============================================================================

class RadioactiveDecayEngine(BaseDecayEngine):
    available = HAS_RADIOACTIVEDECAY

    @property
    def name(self) -> str:
        return "radioactivedecay"

    @property
    def description(self) -> str:
        return "radioactivedecay library (ICRP-107 data, matrix exponential; all nuclides and metastables)"

    @property
    def version(self) -> Optional[str]:
        return rd.__version__ if rd else None

    @property
    def data_source(self) -> str:
        return f"ICRP Publication 107 (radioactivedecay {rd.__version__})" if rd else ""

    def get_half_life(self, isotope: str) -> Optional[float]:
        if not HAS_RADIOACTIVEDECAY:
            return None
        try:
            hl = rd.Nuclide(normalize_isotope(isotope)).half_life("s")
            return float(hl) if not isinstance(hl, str) and math.isfinite(float(hl)) else None
        except Exception:
            return None

    def predict_decay(self, isotope: str, activity: float, duration_seconds: float, points: int = 50) -> Dict[str, Any]:
        if not HAS_RADIOACTIVEDECAY:
            raise RuntimeError("radioactivedecay package is not installed.")
        parent = normalize_isotope(isotope)
        try:
            rd.Nuclide(parent)
        except Exception:
            raise DecayInputError(f"radioactivedecay does not know the isotope {parent}.")
        if self.get_half_life(parent) is None:
            raise DecayInputError(f"{parent} is stable: it does not decay.")

        times = np.linspace(0, duration_seconds, points)
        inventory = rd.Inventory({parent: activity}, "Bq")
        raw: Dict[str, np.ndarray] = {}
        for idx, t in enumerate(times):
            for nuclide, value in inventory.decay(float(t), "s").activities("Bq").items():
                raw.setdefault(str(nuclide), np.zeros(len(times)))[idx] = float(value)   # every series gets every point
        graph = _rd_graph(parent)
        order = bateman.topological_order(graph, parent) if graph else [parent]
        return package_series(self, parent, activity, duration_seconds, times, raw, order)


# ============================================================================
# Engine 3: Curie (ENSDF half-lives and branching, Bateman solver)
# ============================================================================

_CURIE_NAME = re.compile(r"(\d+)([A-Z]{1,2})(g|m\d*)")   # Curie writes the element in capitals and the state in lower case: 138Ig, 137BAm1
MIN_BRANCH = 1e-6    # Curie lists thousands of spontaneous-fission fragments (fractions down to 1e-25) for U-238 and friends: ignore branches below this


def _from_curie(name: str) -> Optional[str]:
    """Curie's '137BAm1' / '60NIg' -> 'Ba-137m' / 'Ni-60'; None if the string is not a nuclide (e.g. a fission label)."""
    m = _CURIE_NAME.fullmatch(name)
    if not m:
        return None
    mass, symbol, state = m.group(1), m.group(2), m.group(3)
    meta = "" if state == "g" else ("m" if state in ("m", "m1") else "n")
    return f"{symbol[0].upper()}{symbol[1:].lower()}-{int(mass)}{meta}"


def _to_curie(name: str) -> str:
    m = re.fullmatch(r"([A-Za-z]{1,2})-(\d+)([mn]?)", name)
    symbol, mass, meta = m.group(1), m.group(2), m.group(3)
    return f"{mass}{symbol.upper()}{'g' if not meta else ('m1' if meta == 'm' else 'm2')}"


@lru_cache(maxsize=64)
def _curie_graph(parent: str) -> Dict[str, Tuple[Optional[float], Tuple[Tuple[str, float], ...]]]:
    """The decay graph below `parent` from Curie's ENSDF database (cached)."""
    graph: Dict[str, Tuple[Optional[float], Tuple[Tuple[str, float], ...]]] = {}
    todo: List[Tuple[str, float]] = [(parent, 1.0)]
    with CURIE_LOCK:                                  # Curie's SQLite connection is shared: one thread at a time
        while todo:
            name, fraction_in = todo.pop()
            if name in graph:
                continue
            try:
                iso = curie.Isotope(_to_curie(name))
            except Exception as exc:
                logger.warning("Curie lookup of %s failed: %r", name, exc)
                if name != parent and fraction_in < 1e-4:     # a negligible branch Curie has no entry for (fission fragments)
                    graph[name] = (None, ())
                    continue
                raise DecayInputError(f"Curie does not know the isotope {name}.")
            if iso.stable:
                graph[name] = (None, ())
                continue
            hl = iso.half_life("s")
            if hl is None or not math.isfinite(float(hl)) or float(hl) <= 0:
                raise DecayInputError(f"Curie has no half-life for {name}.")
            products = []
            for product, fraction in (iso.decay_products or {}).items():
                canonical = _from_curie(product)
                if canonical and fraction and fraction >= MIN_BRANCH:
                    products.append((canonical, float(fraction)))
            graph[name] = (float(hl), tuple(products))
            todo.extend(products)
    return graph


def _curie_ready() -> bool:
    if not HAS_CURIE:
        return False
    try:
        with CURIE_LOCK:
            return float(curie.Isotope("Cs-137").half_life("s")) > 0
    except Exception:
        return False


class CurieEngine(BaseDecayEngine):
    available = _curie_ready()

    @property
    def name(self) -> str:
        return "curie"

    @property
    def description(self) -> str:
        return "Curie library (ENSDF half-lives and branching, Bateman solver)"

    @property
    def version(self) -> Optional[str]:
        return getattr(curie, "__version__", None) if curie else None

    @property
    def data_source(self) -> str:
        return "ENSDF via Curie" + (f" {self.version}" if self.version else "")

    def get_half_life(self, isotope: str) -> Optional[float]:
        if not self.available:
            return None
        try:
            with CURIE_LOCK:
                iso = curie.Isotope(_to_curie(normalize_isotope(isotope)))
                return None if iso.stable else float(iso.half_life("s"))
        except Exception:
            return None

    def predict_decay(self, isotope: str, activity: float, duration_seconds: float, points: int = 50) -> Dict[str, Any]:
        if not self.available:
            raise RuntimeError("curie is not installed or its nuclear data is missing.")
        parent = normalize_isotope(isotope)
        graph = _curie_graph(parent)
        if not bateman.is_radioactive(graph, parent):
            raise DecayInputError(f"{parent} is stable: it does not decay.")
        times = np.linspace(0, duration_seconds, points)
        raw = bateman.solve_chain(graph, parent, activity, times)
        return package_series(self, parent, activity, duration_seconds, times, raw, list(raw))


# ============================================================================
# Result normalization
# ============================================================================

def normalize_decay_result(result: Dict[str, Any], isotope: str, activity: float, duration_seconds: float) -> Dict[str, Any]:
    """
    Reconcile the chain-oriented keys (isotopes / time_points_days / activities) and the series-oriented keys
    (time_points in seconds / series) into one contract: the decay chart needs both, so fill in whichever half is missing.
    """
    if not result:
        return result
    out = dict(result)
    if "series" in out and "activities" not in out:
        out["activities"] = out["series"]
    if "activities" in out and "series" not in out:
        out["series"] = out["activities"]
    if "isotopes" not in out:
        out["isotopes"] = list(out.get("activities", {}).keys())
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
    """Resolves the requested engine, validates the request and runs it."""

    PREFERENCE = ("radioactivedecay", "curie", "builtin")     # what "auto" tries, in order

    def __init__(self):
        self._engines: Dict[str, BaseDecayEngine] = {
            "builtin": BuiltinEngine(),
            "radioactivedecay": RadioactiveDecayEngine(),
            "curie": CurieEngine(),
        }

    def list_engines(self) -> List[Dict[str, Any]]:
        default = self.get_default_engine_name()
        return [{
            "name": name,
            "description": engine.description,
            "available": bool(engine.available),
            "is_default": name == default,
            "version": engine.version,
            "data_source": engine.data_source,
        } for name, engine in self._engines.items()]

    def list_isotopes(self) -> List[Dict[str, Any]]:
        """The parents the built-in engine (and so every engine) can start from, for the isotope picker: name and half-life."""
        from nuclides.decay_calculator import format_half_life
        names = sorted(bateman_parents(), key=lambda n: (re.sub(r"[^A-Za-z]", "", n), int(re.sub(r"\D", "", n) or 0)))
        return [{"name": n, "half_life": format_half_life(GRAPH.get(n, (None, ()))[0])} for n in names if bateman.is_radioactive(GRAPH, n)]

    def get_default_engine_name(self) -> str:
        """The first available engine in PREFERENCE."""
        for name in self.PREFERENCE:
            if self._engines[name].available:
                return name
        return "builtin"

    def get_engine(self, engine_name: str = "auto") -> BaseDecayEngine:
        """Resolves the requested engine; an unknown or unavailable one falls back (with a log line) to the built-in solver."""
        if engine_name in (None, "", "auto", "default"):
            engine_name = self.get_default_engine_name()
        engine = self._engines.get(str(engine_name).lower())
        if engine is None:
            logger.warning("Unknown decay engine %r: using builtin", engine_name)
            return self._engines["builtin"]
        if not engine.available:
            logger.warning("Decay engine %r is unavailable: using builtin", engine_name)
            return self._engines["builtin"]
        return engine

    @staticmethod
    def _validate(isotope, activity, duration_seconds, points) -> None:
        if not isinstance(activity, (int, float)) or not math.isfinite(activity) or activity <= 0:
            raise DecayInputError("The starting activity must be a positive number of becquerels.")
        if not isinstance(duration_seconds, (int, float)) or not math.isfinite(duration_seconds) or duration_seconds <= 0:
            raise DecayInputError("The duration must be a positive amount of time.")
        if duration_seconds > MAX_DURATION_S:
            raise DecayInputError(f"The duration is too long: the limit is {MAX_DURATION_S / (86400 * 365.25):.1e} years.")
        if not isinstance(points, int) or not (MIN_POINTS <= points <= MAX_POINTS):
            raise DecayInputError(f"points must be between {MIN_POINTS} and {MAX_POINTS}.")

    def predict_decay(self, isotope: str, activity: float, duration_seconds: float, points: int = 50,
                      engine_name: str = "auto") -> Dict[str, Any]:
        """
        Run a prediction. Raises DecayInputError for input that cannot be computed. A named engine that is unavailable is
        replaced by the default one and the result says so in `warnings`; with "auto" the engines are tried in order until one
        has data for the isotope.
        """
        self._validate(isotope, activity, duration_seconds, points)
        parent = normalize_isotope(isotope)
        requested = (engine_name or "auto").lower()
        if requested in ("default", ""):
            requested = "auto"
        if requested != "auto" and requested not in self._engines:
            raise DecayInputError(f"Unknown decay engine {engine_name!r}. Available: auto, " + ", ".join(self._engines) + ".")

        warnings: List[str] = []
        if requested == "auto":
            candidates = [n for n in self.PREFERENCE if self._engines[n].available]
        elif self._engines[requested].available:
            candidates = [requested]
        else:
            fallback = self.get_default_engine_name()
            warnings.append(f"The {requested} engine is not available here; the {fallback} engine was used instead.")
            candidates = [fallback]

        first_error: Optional[DecayInputError] = None
        for name in candidates:
            try:
                result = self._engines[name].predict_decay(parent, float(activity), float(duration_seconds), int(points))
            except DecayInputError as error:
                first_error = first_error or error
                continue
            result["engine_requested"] = requested
            result["warnings"] = warnings
            return normalize_decay_result(result, parent, activity, duration_seconds)
        raise first_error or DecayInputError(f"No engine could predict the decay of {parent}.")


# Global singleton instance
decay_engine_manager = DecayEngineManager()
