import logging
logger = logging.getLogger(__name__)

# ========== IAEA DATA INTEGRATION ==========
# Load authoritative gamma data from IAEA NDS
# This provides intensity weights for better peak matching

try:
    from formats.iaea_parser import load_all_isotopes
    IAEA_DATA = load_all_isotopes(min_intensity=0.5, top_n=15)
    HAS_IAEA_DATA = True
    logger.info(f"Loaded IAEA data for {len(IAEA_DATA)} isotopes")
except ImportError:
    IAEA_DATA = {}
    HAS_IAEA_DATA = False
    logger.warning("IAEA parser not available, using built-in data only")
except Exception as e:
    IAEA_DATA = {}
    HAS_IAEA_DATA = False
    logger.warning(f"IAEA data load failed: {e}")

# ========== CURIE X-RAY DATA INTEGRATION ==========
# Provides characteristic X-ray emission lines for improved isotope ID
try:
    from nuclides.curie_integration import (
        get_element_xrays as _get_element_xrays,
        get_all_xrays_for_isotope as _get_all_xrays_for_isotope,
        HAS_CURIE
    )
    logger.info(f"Curie X-ray integration loaded (curie available: {HAS_CURIE})")
except ImportError:
    HAS_CURIE = False
    _get_element_xrays = lambda *args, **kwargs: []
    _get_all_xrays_for_isotope = lambda *args, **kwargs: []
    logger.warning("Curie integration not available")



def get_isotope_xrays(isotope_name: str):
    """
    Get characteristic X-ray emission lines for an isotope.
    
    These are X-rays from the daughter nucleus after decay, e.g.:
    - Cs-137 -> Ba-137m emits Ba X-rays (~32 keV)
    - Am-241 -> Np X-rays
    
    Args:
        isotope_name: Isotope name (e.g., "Cs-137")
        
    Returns:
        List of dicts with 'energy', 'element', 'shell', 'intensity' keys
    """
    return _get_all_xrays_for_isotope(isotope_name)



def get_gamma_intensity(isotope: str, energy: float) -> float:
    """Get relative intensity (0.0-1.0) for a gamma line from IAEA data.
    
    Returns 1.0 (full weight) if intensity data not available.
    """
    if not HAS_IAEA_DATA or isotope not in IAEA_DATA:
        return 1.0
    
    gammas = IAEA_DATA[isotope].get('gammas', [])
    if not gammas:
        return 1.0
    
    # Find matching gamma line (within 2 keV)
    for gamma_energy, intensity in gammas:
        if abs(gamma_energy - energy) < 2.0:
            # Normalize intensity (max is ~100%, convert to 0-1 scale)
            # Intensities above 10% get full weight, below are scaled
            return min(1.0, intensity / 10.0)
    
    return 0.5  # Default for unmatched lines


# ========== SIMPLE MODE DATABASE (Hobby-Focused) ==========
# Optimized for common hobby sources, background radiation, and basic medical/industrial
# IMPORTANT: Uranium detection uses daughter products for reliable identification
ISOTOPE_DATABASE_SIMPLE = {
    # Medical/Industrial calibration sources
    "Co-60": [1173.2, 1332.5],
    "Cs-137": [661.7],
    "Na-22": [511.0, 1274.5],
    "Am-241": [59.5],
    "Ba-133": [81.0, 276.4, 302.9, 356.0, 383.8],
    
    # Natural background
    "K-40": [1460.8],
    
    # U-238 Decay Chain (Uranium series) - Hobby sources
    # NOTE: U-238 itself has weak gammas, detected via daughter products
    "U-238": [49.55, 63.3, 92.4, 1001.0, 766.4],  # Includes Th-234, Pa-234m signatures
    "Th-234": [63.3, 92.5, 112.8],  # U-238 daughter - 63/93 keV doublet is characteristic
    "Pa-234m": [1001.0, 766.4],
    "U-234": [53.2],
    "Ra-226": [186.2],  # KEY: This is in U-238 chain, NOT U-235
    "Pb-214": [295.2, 351.9, 241.0],
    "Bi-214": [609.3, 1120.3, 1764.5],
    
    # Th-232 Decay Chain (Thorium series) - Lantern mantles, thoriated lenses
    # NOTE: Th-232 itself has very weak gammas (~4%), detected via chain daughters
    "Th-232": [63.8, 238.6, 583.2, 911.2, 2614.5],  # Chain signature peaks for identification
    "Ac-228": [338.3, 911.2, 968.9, 463.0],  # Characteristic Th-chain marker
    "Pb-212": [238.6, 300.1],  # Strong Th-chain marker
    "Bi-212": [727.0, 1620.5],
    "Tl-208": [583.2, 860.6, 2614.5],  # 2614 keV is highest natural gamma
    
    # U-235 Decay Chain (Actinium series)
    # NOTE: 185.7 keV REMOVED - overlaps with Ra-226 (186.2) from U-238 chain
    # Only use non-overlapping signatures
    "U-235": [143.8, 163.4, 205.3],  # Removed 185.7 to prevent false positives
    "Th-231": [84.2, 163.3],
    "Th-227": [236.0],
    "Ra-223": [144.2, 269.0, 324.0],
    
    # Common medical isotopes
    "I-131": [364.5],
    "Tc-99m": [140.5],
    "F-18": [511.0],
    "Tl-201": [135.0, 167.0],
}

# ========== ADVANCED MODE DATABASE (Comprehensive) ==========
# Includes all Simple isotopes + extended library for professional/research use
# Data sources: IAEA NDS, NNDC/ENSDF, CapGam
ISOTOPE_DATABASE_ADVANCED = {
    # All Simple mode isotopes
    **ISOTOPE_DATABASE_SIMPLE,
    
    # === FISSION PRODUCTS (Nuclear Reactor/Waste) ===
    "Ru-103": [497.1, 295.0, 443.8, 179.3],
    "Ru-106": [511.9],  # Via Rh-106 daughter
    "Zr-95": [724.2, 756.7],
    "Ce-141": [145.4],
    "Ce-144": [133.5, 696.5],  # Via Pr-144
    "La-140": [1596.2, 487.0],
    "Nb-95": [765.8],
    "Mo-99": [739.5, 777.9, 181.1],  # Precursor to Tc-99m
    "Xe-133": [81.0],
    "Te-132": [228.2],
    "Cs-134": [604.7, 795.9, 569.3],
    "Sr-89": [909.0],  # Weak gamma emitter
    "Y-91": [1204.7],
    
    # === ACTIVATION PRODUCTS ===
    "Sc-46": [889.3, 1120.5],
    "Cr-51": [320.1],
    "Mn-56": [846.8, 1811.2],
    "Co-57": [122.1, 136.5],
    "Co-58": [810.8, 511.0],  # 511 from positron
    "Ni-65": [1481.8, 1115.5],
    "Cu-64": [511.0],  # Annihilation only
    "Ag-108m": [433.9, 614.3, 722.9],
    "Ag-110m": [657.8, 884.7, 937.5],
    "Sb-124": [602.7, 1691.0, 645.9],
    "Sb-125": [427.9, 463.4, 600.6],
    "Mn-54": [834.8],
    "Zn-65": [1115.5, 511.0],
    "Fe-59": [1099.2, 1291.6, 192.3],
    
    # === EXTENDED MEDICAL/INDUSTRIAL ===
    "Ga-67": [93.3, 184.6, 300.2],
    "In-111": [171.3, 245.4],
    "Sm-153": [103.2],
    "Lu-177": [113.0, 208.4],
    "Sr-85": [514.0],
    "Cd-109": [88.0],
    "Se-75": [121.1, 136.0, 264.7, 279.5, 400.7],
    "Sn-113": [391.7],
    "Ir-192": [296.0, 308.0, 316.0, 468.0, 604.4],
    "Au-198": [411.8],
    "Hg-203": [279.2],
    "Tl-204": [],  # Beta only, but commonly encountered
    
    # === RARE EARTH ISOTOPES ===
    "Eu-152": [121.8, 244.7, 344.3, 778.9, 964.1, 1085.8, 1112.1, 1408.0],
    "Eu-154": [123.1, 723.3, 873.2, 1274.4, 1004.8],
    "Eu-155": [86.5, 105.3],
    "Gd-153": [97.4, 103.2],
    "Tb-160": [298.6, 879.4, 966.2],
    "Ho-166": [80.6],  # Weak gamma
    "Tm-170": [84.3],
    "Yb-169": [177.2, 198.0, 307.7],
    
    # === TRANSURANICS & ACTINIDES ===
    "Pu-238": [43.5, 99.9, 152.7],  # Weak gammas, primarily alpha
    "Pu-239": [51.6, 129.3, 375.0, 413.7],
    "Pu-240": [45.2, 104.2],
    "Pu-241": [148.6],  # Very weak, primarily beta
    "Np-237": [86.5, 143.2, 312.2],
    "Am-243": [74.7],
    "Cm-244": [42.9, 152.6],
    
    # === NATURAL SERIES EXTENSIONS ===
    "Pb-210": [46.5],
    "Bi-210": [],  # Beta only
    "Po-210": [803.0],  # Very weak, primarily alpha
    "Rn-222": [510.0],  # Very weak
    "Ac-227": [],  # Complex spectrum via daughters
    
    # === ADDITIONAL INDUSTRIAL/RESEARCH ===
    "Be-7": [477.6],
    "Na-24": [1368.6, 2754.0],
    "P-32": [],  # Pure beta
    "S-35": [],  # Pure beta
    "Ca-45": [],  # Pure beta
    "V-48": [983.5, 1312.1],
    "W-187": [479.5, 551.5, 618.4, 685.8],
    "Ta-182": [67.7, 100.1, 152.4, 156.4, 179.4, 198.4, 222.1, 229.3, 264.1, 1121.3, 1189.0, 1221.4],
    "Re-186": [137.2],
    "Os-191": [129.4],
}

# Default to Simple mode database for backward compatibility
ISOTOPE_DATABASE = ISOTOPE_DATABASE_SIMPLE

# Custom Isotope Persistence
CUSTOM_ISOTOPES_FILE = "custom_isotopes.json"
import logging
logger = logging.getLogger(__name__)
import json
import os

def load_custom_isotopes():
    if not os.path.exists(CUSTOM_ISOTOPES_FILE):
        return {}
    try:
        with open(CUSTOM_ISOTOPES_FILE, 'r') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

def save_custom_isotope(name, energies):
    custom = load_custom_isotopes()
    custom[name] = energies
    with open(CUSTOM_ISOTOPES_FILE, 'w') as f:
        json.dump(custom, f, indent=2)

def delete_custom_isotope(name):
    custom = load_custom_isotopes()
    if name in custom:
        del custom[name]
        with open(CUSTOM_ISOTOPES_FILE, 'w') as f:
            json.dump(custom, f, indent=2)
        return True
    return False

def get_isotope_database(mode='simple'):
    """
    Get the appropriate isotope database based on mode.
    Merges custom isotopes into the base database.
    
    Args:
        mode: 'simple' for hobby-focused (30 isotopes) or 'advanced' for comprehensive (100+ isotopes)
    
    Returns:
        Dictionary of isotope names to gamma energies
    """
    base_db = ISOTOPE_DATABASE_ADVANCED if mode == 'advanced' else ISOTOPE_DATABASE_SIMPLE
    
    # Merge custom isotopes (Custom overrides base if same name, or just adds)
    # create a copy to not mutate the global constant
    merged_db = base_db.copy()
    merged_db.update(load_custom_isotopes())
    
    return merged_db


# Decay chain definitions with key indicators
# Enhanced with required isotopes, intensity weighting, and exclusion rules
DECAY_CHAINS = {
    "U-238 Chain": {
        "parent": "U-238",
        "common_names": ["Uranium Series", "Radium Series"],
        "members": [
            "U-238", "Th-234", "Pa-234m", "U-234", "Th-230",
            "Ra-226", "Rn-222", "Po-218", "Pb-214", "Bi-214",
            "Po-214", "Pb-210", "Bi-210", "Po-210", "Pb-206"
        ],
        "key_indicators": {
            "Bi-214": {"energies": [609.3, 1120.3, 1764.5], "required": True, "weight": 1.0},  # Strongest, required
            "Pb-214": {"energies": [351.9, 295.2, 241.0], "required": False, "weight": 0.8},
            "Th-234": {"energies": [63.3, 92.4], "required": True, "weight": 0.9},  # Required for U-238 vs Ra-226
            "Pa-234m": {"energies": [1001.0, 766.4], "required": False, "weight": 0.7},
            "Ra-226": {"energies": [186.2], "required": False, "weight": 0.5}
        },
        "min_isotopes_required": 2,  # Need at least 2 isotopes to report chain
        "applications": [
            "Uranium glass/vaseline glass",
            "Vintage Fiestaware ceramics",
            "Radium watch dials (pre-1970)",
            "Uranium minerals",
            "Natural background radiation"
        ],
        "abundance_weight": 0.993,
        "references": [
            {"name": "NNDC Nuclear Data", "url": "https://www.nndc.bnl.gov/nudat3/decaysearchdirect.jsp?nuc=238U"},
            {"name": "IAEA Decay Data", "url": "https://www-nds.iaea.org/relnsd/vcharthtml/VChartHTML.html"},
            {"name": "Natural Abundance (LBNL)", "url": "https://www2.lbl.gov/abc/wallchart/chapters/03/2.html"}
        ],
        "notes": "Most common hobby source. Bi-214 at 609 keV is strongest peak."
    },
    
    "Th-232 Chain": {
        "parent": "Th-232",
        "common_names": ["Thorium Series"],
        "members": [
            "Th-232", "Ra-228", "Ac-228", "Th-228", "Ra-224",
            "Rn-220", "Po-216", "Pb-212", "Bi-212", "Tl-208",
            "Po-212", "Pb-208"
        ],
        "key_indicators": {
            "Tl-208": {"energies": [2614.5, 583.2], "required": False, "weight": 1.0},  # 2614 keV is DIAGNOSTIC
            "Ac-228": {"energies": [911.2, 968.9], "required": True, "weight": 0.9},  # Required indicator
            "Pb-212": {"energies": [238.6], "required": False, "weight": 0.6}
        },
        "min_isotopes_required": 2,
        "applications": [
            "Gas lantern mantles (camping)",
            "Vintage camera lenses (1940s-1970s)",
            "Welding rods (thoriated tungsten)",
            "Thorium minerals"
        ],
        "abundance_weight": 1.0,
        "references": [
            {"name": "NNDC Th-232 Data", "url": "https://www.nndc.bnl.gov/nudat3/decaysearchdirect.jsp?nuc=232Th"},
            {"name": "Thorium Abundance (USGS)", "url": "https://pubs.usgs.gov/fs/2002/fs087-02/"}
        ],
        "notes": "Tl-208 at 2614 keV is unique diagnostic peak, used for calibration."
    },
    
    "U-235 Chain": {
        "parent": "U-235",
        "common_names": ["Actinium Series"],
        "members": [
            "U-235", "Th-231", "Pa-231", "Ac-227", "Th-227",
            "Ra-223", "Rn-219", "Po-215", "Pb-211", "Bi-211",
            "Tl-207", "Pb-207"
        ],
        "key_indicators": {
            "U-235": {"energies": [185.7, 143.8], "required": True, "weight": 1.0},
            "Th-227": {"energies": [236.0], "required": False, "weight": 0.5},
            "Ra-223": {"energies": [144.2], "required": False, "weight": 0.5}
        },
        "min_isotopes_required": 2,
        "applications": [
            "Natural uranium (0.72% abundance)",
            "Enriched uranium materials"
        ],
        "abundance_weight": 0.0072,  # Strongly suppressed vs U-238
        "references": [
            {"name": "NNDC U-235 Data", "url": "https://www.nndc.bnl.gov/nudat3/decaysearchdirect.jsp?nuc=235U"}
        ],
        "notes": "Usually overshadowed by U-238 chain. 185.7 keV overlaps with Ra-226 at 186.2 keV."
    },
    
    # NOTE: Single-isotope sources (Am-241, Cs-137, Co-60) have been REMOVED.
    # They are NOT decay chains and should be handled via isotope identification.
    # Their presence here was causing false positive "chain" detections in natural spectra.
    
    "Ra-226 (Refined)": {
        "parent": "Ra-226",
        "common_names": ["Radium Dial", "Refined Radium"],
        "members": ["Ra-226", "Rn-222", "Pb-214", "Bi-214"],
        "key_indicators": {
            "Bi-214": {"energies": [609.3, 1120.3], "required": True, "weight": 1.0},
            "Pb-214": {"energies": [351.9, 295.2], "required": True, "weight": 0.9}
        },
        "exclusion_isotopes": ["Th-234", "Pa-234m"],  # Must NOT have these (would indicate U-238 ore)
        "min_isotopes_required": 2,
        "applications": ["Radium watch dials", "Radium clocks", "Industrial gauges"],
        "abundance_weight": 1.0,
        "references": [],
        "notes": "Refined Ra-226 separated from U ore. Should NOT have Th-234/Pa-234m."
    }
}

# Decay chain membership, used to tell a natural series from a man-made source
U238_CHAIN = ["U-238", "Th-234", "Pa-234m", "U-234", "Th-230", "Ra-226",
              "Rn-222", "Po-218", "Pb-214", "Bi-214", "Po-214", "Pb-210", "Bi-210", "Po-210"]
TH232_CHAIN = ["Th-232", "Ra-228", "Ac-228", "Th-228", "Ra-224",
               "Rn-220", "Po-216", "Pb-212", "Bi-212", "Tl-208", "Po-212"]
U235_CHAIN = ["U-235", "Th-231", "Pa-231", "Ac-227", "Th-227", "Ra-223", "Rn-219"]

# Natural abundance weights: rare isotopes are penalised
ABUNDANCE_WEIGHTS = {
    "U-238": 1.0,      # 99.3% of natural uranium
    "U-235": 0.01,     # 0.72% - strongly suppress
    "Th-231": 0.01,    # U-235 daughter
    "Ra-223": 0.01,    # U-235 chain
    "Th-227": 0.01,    # U-235 chain
}

# A chain counts as detected when one of its members reaches this weighted confidence. Stricter than "any match", so a weak
# single match (e.g. Pb-214 at 241 keV) does not flag a whole uranium series.
CHAIN_DETECTION_CONFIDENCE = 40.0


def _line_tolerance(energy, energy_tolerance, detector):
    """
    How far a peak may sit from a line and still match it: the configured tolerance, narrowed to what the detector can resolve (half its
    FWHM, a 4 % calibration error and a 5 keV floor, in quadrature) where that is smaller. A fixed 20-30 keV is wider than a whole peak below
    ~150 keV: Pb X-rays from a lead shield (74 keV) matched Am-241 (59.5 keV), and Am-241 itself matched Ba-133 (81 keV).
    """
    if not detector:
        return energy_tolerance
    try:
        from spectroscopy.source_templates import _match_tolerance
        return min(energy_tolerance, _match_tolerance(energy, detector))
    except Exception:
        return energy_tolerance


DETECTABLE_FRACTION = 0.2   # a line counts towards the required ones when its expected counts are this share of the strongest line's


def _detectable_lines(isotope, gamma_energies, detector):
    """
    How many of the listed lines a detector would show: emission probability times efficiency at least DETECTABLE_FRACTION of the
    strongest line's. None when an intensity is unknown (the validation rule then stands as it is). Requiring every listed line threw
    out Pb-212 (238.6 keV, 43.6 %) for lack of its 300.1 keV line (3.3 %), the strongest thorium line in every thoriated spectrum.
    """
    gammas = IAEA_DATA.get(isotope, {}).get('gammas', []) if HAS_IAEA_DATA else []
    weights = []
    for e in gamma_energies:
        intensity = next((i for g, i in gammas if abs(g - e) < 2.0), None)
        if intensity is None:
            return None
        try:
            from spectroscopy.detector_efficiency import interpolate_efficiency
            eff = interpolate_efficiency(detector or 'AlphaHound CsI(Tl)', e) or 0.0
        except Exception:
            eff = 1.0
        weights.append(intensity * eff)
    top = max(weights, default=0.0)
    return sum(1 for w in weights if top > 0 and w >= DETECTABLE_FRACTION * top) if weights else None


MIN_SINGLE_LINE_SIGNIFICANCE = 10.0     # standard errors: a peak of a single-line isotope has no second line to corroborate it
MIN_WIDTH_RATIO, MAX_WIDTH_RATIO = 0.6, 1.6   # its width against the detector's at that energy, in the gap the 41 measured matches leave


def _stands_alone(peak) -> bool:
    """
    Whether a peak can be the only evidence for an isotope. Measured on the 41 single-line matches of 33 labelled spectra at three axis offsets: the 37
    genuine ones had a significance of at least 18 and a width 0.70-1.37 times the detector's; the false ones were a 128 keV feature read as Tc-99m
    (significance 6.6, width 0.56), a 493 keV one read as F-18 (significance 3.0, width 0.45) and, on a Cs-137 spectrum drifted 10 %, a 380 keV
    Compton-edge bump read as I-131 (width 1.72; it had been hidden by a false Ra-226 match, width 2.03, until that was refused). The bounds sit in
    the gaps. A peak with no significance or width recorded (not every peak finder gives them) is not judged.
    """
    significance = peak.get('significance')
    if significance is not None and significance < MIN_SINGLE_LINE_SIGNIFICANCE:
        return False
    fwhm, expected = peak.get('fwhm'), peak.get('fwhm_expected')
    if fwhm and expected and not MIN_WIDTH_RATIO <= fwhm / expected <= MAX_WIDTH_RATIO:
        return False
    return True


def _score_isotope(isotope, gamma_energies, peaks, energy_tolerance, validation_rules, detector=None):
    """
    Match one isotope's gamma lines against the detected peaks and score it (intensity weighted, with the single-line,
    peak-count, intrinsic-validation and abundance adjustments). Returns the match record, or None if no line matched.
    """
    matches = 0
    matched_peaks = []
    total_intensity = 0.0
    matched_intensity = 0.0
    used = set()   # one peak is evidence for one line of this isotope: a bump between two lines used to "match" both

    # intensity weight (yield) from IAEA data; 1.0 if unavailable (falls back to simple counting). Strong lines claim their peak first.
    lines = sorted(((get_gamma_intensity(isotope, e), e) for e in gamma_energies), key=lambda t: -t[0])
    for intensity, gamma_energy in lines:
        total_intensity += intensity
        tolerance = _line_tolerance(gamma_energy, energy_tolerance, detector)
        candidates = [(abs(p['energy'] - gamma_energy), i) for i, p in enumerate(peaks)
                      if i not in used and abs(p['energy'] - gamma_energy) <= tolerance
                      and (len(gamma_energies) > 1 or _stands_alone(p))]
        if not candidates:
            continue
        energy_diff, i = min(candidates)
        used.add(i)
        matches += 1
        matched_intensity += intensity
        matched_peaks.append({
            'expected': gamma_energy,
            'observed': peaks[i]['energy'],
            'diff': energy_diff,
            'intensity': intensity
        })
    matched_peaks.sort(key=lambda m: m['expected'])

    if matches == 0:
        return None

    # If we have intensity data, the weighted score penalises missing strong lines
    if total_intensity > 0:
        base_confidence = (matched_intensity / total_intensity) * 100
    else:
        base_confidence = (matches / len(gamma_energies)) * 100

    # Single-line isotopes are capped at 60%: a 1/1 match is often coincidental
    if len(gamma_energies) == 1 and matches == 1:
        base_confidence = min(base_confidence, 60.0)

    # Peak count: a single match is penalised, 3 or more earn a bonus
    if matches == 1:
        base_confidence *= 0.7
    elif matches >= 3:
        base_confidence = min(base_confidence * 1.1, 100.0)

    # Physics-based rules for specific isotopes (required number of peaks, low-energy penalty)
    rules = validation_rules.get(isotope)
    cap = None
    if rules:
        required_peaks = rules.get("required_peaks", 1)
        detectable = _detectable_lines(isotope, gamma_energies, detector)
        if detectable is not None:
            required_peaks = max(1, min(required_peaks, detectable))
        min_conf_single = rules.get("min_confidence_single", 30.0)
        if matches < required_peaks:
            base_confidence = min(base_confidence, min_conf_single)
            cap = min_conf_single
            logger.info(f"[Intrinsic] {isotope}: {matches}/{required_peaks} peaks - capped at {min_conf_single}%")
        if rules.get("low_energy_penalty") and matches == 1:
            base_confidence *= 0.6
            logger.info(f"[Intrinsic] {isotope}: Low energy penalty applied")

    abundance_weight = ABUNDANCE_WEIGHTS.get(isotope, 1.0)
    return {
        'isotope': isotope,
        'confidence': base_confidence * abundance_weight,
        'raw_confidence': base_confidence,
        'matches': matches,
        'total_lines': len(gamma_energies),
        'matched_peaks': matched_peaks,
        'expected_peaks': [{'energy': e, 'intensity': get_gamma_intensity(isotope, e)} for e in gamma_energies],
        'abundance_weight': abundance_weight,
        'suppressed': False,
        # the ceiling the validation rules put on this match (too few of the required lines); later rescoring must keep it
        'validation_cap': cap,
    }


def _apply_contextual_rules(isotope_matches, chains_detected, peaks):
    """
    Adjust the confidences in place using what else is in the spectrum: suppress man-made isotopes that cannot coexist with
    a natural series (unless their line is among the strongest peaks), boost a man-made source that dominates the spectrum,
    and demote natural-series matches that are probably Compton continuum when a man-made source dominates.
    """
    try:
        from nuclides.isotope_validation import INCOMPATIBLE_WITH_NATURAL
    except ImportError:
        INCOMPATIBLE_WITH_NATURAL = ["Cs-137", "I-131", "F-18", "Tc-99m", "Co-60", "Sr-90", "Pu-239", "Np-237"]
    try:
        from nuclides.isotope_validation import MANMADE_SIGNATURES
    except ImportError:
        MANMADE_SIGNATURES = {'Cs-137': [661.7], 'Co-60': [1173.2, 1332.5], 'Am-241': [59.5]}

    any_chain_detected = chains_detected['u238'] or chains_detected['th232']

    # Top 5 peaks by counts (not only the dominant one: Cs-137 662 keV may be weaker than a Ba X-ray)
    sorted_peaks = sorted(peaks, key=lambda p: p.get('counts', p.get('area', 0)), reverse=True)
    top_peak_energies = [p.get('energy', 0) for p in sorted_peaks[:5]]

    # Which man-made sources have a characteristic line (25 keV tolerance) among the top peaks
    manmade_in_top_peaks = set()
    for peak_energy in top_peak_energies:
        for iso, energies in MANMADE_SIGNATURES.items():
            for e in energies:
                if abs(peak_energy - e) < 25:
                    manmade_in_top_peaks.add(iso)

    logger.debug(f"[Suppress] top_peak_energies={top_peak_energies} manmade_in_top_peaks={manmade_in_top_peaks} "
                 f"chains_detected={chains_detected}")

    if any_chain_detected:
        for iso in INCOMPATIBLE_WITH_NATURAL:
            if iso in isotope_matches:
                if iso in manmade_in_top_peaks:
                    logger.debug(f"[Suppress] bypassing suppression for {iso}")
                    continue
                logger.debug(f"[Suppress] suppressing {iso}")
                isotope_matches[iso]['confidence'] *= 0.1  # 90% reduction
                isotope_matches[iso]['suppressed'] = True
                isotope_matches[iso]['suppression_reason'] = 'incompatible_with_natural_chain'

    # Boost a dominant man-made source to 95% so it ranks above false multi-peak matches (and overrides the single-line
    # cap). Only when no natural chain is detected: otherwise coincidental energy matches become false positives.
    if not any_chain_detected:
        for iso in manmade_in_top_peaks:
            if iso in isotope_matches:
                old_conf = isotope_matches[iso]['confidence']
                isotope_matches[iso]['confidence'] = max(old_conf, 95.0)
                logger.debug(f"[Boost] {iso} from {old_conf:.1f}% to {isotope_matches[iso]['confidence']:.1f}%")
    else:
        logger.debug(f"[Boost] skipped, natural chain detected: {chains_detected}")

    # A man-made source dominates and no chain is detected: natural-series matches are likely Compton continuum
    if manmade_in_top_peaks and not any_chain_detected:
        for iso in isotope_matches:
            if iso in U238_CHAIN or iso in TH232_CHAIN:
                old_conf = isotope_matches[iso]['confidence']
                isotope_matches[iso]['confidence'] = min(old_conf, 40.0)
                isotope_matches[iso]['suppressed'] = True
                isotope_matches[iso]['suppression_reason'] = 'manmade_source_detected'
                logger.debug(f"[Demote] {iso} from {old_conf:.1f}% to {isotope_matches[iso]['confidence']:.1f}%")

    # With the U-238 series detected, U-235 series members are suppressed too
    if chains_detected['u238']:
        for iso in U235_CHAIN:
            if iso in isotope_matches and iso != "U-235":  # U-235 itself is handled by its abundance weight
                isotope_matches[iso]['confidence'] *= 0.2
                isotope_matches[iso]['suppressed'] = True
                isotope_matches[iso]['suppression_reason'] = 'u238_chain_dominant'


def identify_isotopes(peaks, energy_tolerance=20.0, mode='simple', detector=None):
    """
    Identify possible isotopes based on detected peaks.
    Returns ALL matches - filtering should be done at application layer.

    Args:
        peaks: List of detected peak dictionaries with 'energy' key
        energy_tolerance: Maximum energy difference for a match (keV)
        mode: 'simple' or 'advanced' - determines which database to use
        detector: detector profile name; when given, the tolerance narrows at low energy to what it can resolve

    Returns:
        List of identified isotopes with confidence scores (unfiltered)
    """
    if not peaks:
        return []

    database = get_isotope_database(mode)

    # Physics-based validation rules (single source of truth: isotope_validation.py)
    try:
        from nuclides.isotope_validation import generate_validation_rules
        validation_rules = generate_validation_rules(database)
    except ImportError:
        validation_rules = {}

    isotope_matches = {}
    chains_detected = {'u238': False, 'th232': False, 'u235': False}

    for isotope, gamma_energies in database.items():
        if not gamma_energies:
            continue
        match = _score_isotope(isotope, gamma_energies, peaks, energy_tolerance, validation_rules, detector)
        if match is None:
            continue
        isotope_matches[isotope] = match
        if match['confidence'] > CHAIN_DETECTION_CONFIDENCE:
            if isotope in U238_CHAIN:
                chains_detected['u238'] = True
            if isotope in TH232_CHAIN:
                chains_detected['th232'] = True
            if isotope in U235_CHAIN:
                chains_detected['u235'] = True

    _apply_contextual_rules(isotope_matches, chains_detected, peaks)

    # Sort by weighted confidence, then by number of matched lines
    return sorted(isotope_matches.values(), key=lambda x: (x['confidence'], x['matches']), reverse=True)


RELATIVE_PEAK_THRESHOLD = 0.05   # a peak counts for a chain only if it is at least 5% of the largest peak


def _peak_strength(peak) -> float:
    """A peak's size: its counts, else its area, else its height, else 0 (a peak without any is rejected)."""
    return peak.get('counts', peak.get('area', peak.get('height', 0)))


def _match_chain_indicators(chain_data, peaks, energy_tolerance, min_counts_threshold):
    """
    Check each key indicator isotope of one chain against the peaks.

    Returns (detected_members, required_found, required_missing, total_weight, matched_weight): the matched lines per
    detected isotope, the required isotopes found and missing, and the summed indicator weights (all, and matched).
    """
    detected_members = {}
    required_isotopes_found = []
    required_isotopes_missing = []
    total_weight = 0.0
    matched_weight = 0.0

    for isotope, indicator_config in chain_data["key_indicators"].items():
        # dict format (energies / required / weight), or the legacy plain list of energies
        if isinstance(indicator_config, dict):
            indicator_energies = indicator_config.get("energies", [])
            is_required = indicator_config.get("required", False)
            weight = indicator_config.get("weight", 1.0)
        else:
            indicator_energies = indicator_config
            is_required = False
            weight = 1.0

        total_weight += weight
        matched_energies = []

        for expected_energy in indicator_energies:
            for peak in peaks:
                energy_diff = abs(peak['energy'] - expected_energy)
                peak_area = _peak_strength(peak)
                # within tolerance AND above the relative threshold
                if energy_diff <= energy_tolerance and peak_area >= min_counts_threshold:
                    matched_energies.append({
                        'energy': expected_energy,
                        'observed': peak['energy'],
                        'diff': energy_diff,
                        'peak_area': peak_area
                    })
                    break

        if matched_energies:
            detected_members[isotope] = matched_energies
            matched_weight += weight
            if is_required:
                required_isotopes_found.append(isotope)
        elif is_required:
            required_isotopes_missing.append(isotope)

    return detected_members, required_isotopes_found, required_isotopes_missing, total_weight, matched_weight


def _chain_confidence_level(num_detected: int) -> str:
    if num_detected >= 4:
        return "HIGH"
    if num_detected >= 3:
        return "MEDIUM"
    if num_detected >= 2:
        return "LOW"
    return "SINGLE"


def identify_decay_chains(peaks, identified_isotopes=None, energy_tolerance=20.0):
    """
    Identify radioactive decay chains based on detected peaks and isotopes.

    Uses required isotopes, intensity weighting, a minimum isotope count and exclusion rules.

    Args:
        peaks: List of detected peak dictionaries with 'energy' key
        identified_isotopes: Optional list from identify_isotopes() (for the exclusion check)
        energy_tolerance: Maximum energy difference for a match (keV)

    Returns:
        List of detected decay chains with confidence scores (filtered by min requirements)
    """
    if not peaks:
        return []

    # Relative rather than absolute threshold (a fraction of the largest peak): works for strong spectra and for
    # weak ones from short acquisitions
    max_peak_counts = max([0] + [_peak_strength(p) for p in peaks])
    min_counts_threshold = max_peak_counts * RELATIVE_PEAK_THRESHOLD
    logger.debug(f"[Chain] max_peak_counts={max_peak_counts}, min_threshold={min_counts_threshold}, "
                 f"peak energies={[p.get('energy', 0) for p in peaks[:6]]}")

    # Confidently detected isotope names, for the exclusion check
    detected_isotope_names = set()
    if identified_isotopes:
        for iso in identified_isotopes:
            if iso.get('confidence', 0) > 30:
                detected_isotope_names.add(iso.get('isotope', ''))

    chain_detections = []

    for chain_name, chain_data in DECAY_CHAINS.items():
        (detected_members, required_isotopes_found, required_isotopes_missing,
         total_weight, matched_weight) = _match_chain_indicators(chain_data, peaks, energy_tolerance, min_counts_threshold)

        # Some chains exclude an isotope (e.g. Ra-226 Refined excludes Th-234)
        exclusion_violated = any(excl in detected_isotope_names for excl in chain_data.get("exclusion_isotopes", []))

        # Skip chains below the minimum isotope count, with a required isotope missing, or with an exclusion violated
        min_required = chain_data.get("min_isotopes_required", 1)
        num_detected = len(detected_members)
        if num_detected < min_required or required_isotopes_missing or exclusion_violated:
            continue

        # Confidence: mean of isotope coverage and weighted coverage, scaled by the chain's abundance weight
        num_key_isotopes = len(chain_data["key_indicators"])
        isotope_coverage = (num_detected / num_key_isotopes) * 100 if num_key_isotopes > 0 else 0
        weight_coverage = (matched_weight / total_weight) * 100 if total_weight > 0 else 0
        abundance_weight = chain_data.get('abundance_weight', 1.0)
        confidence = (isotope_coverage + weight_coverage) / 2 * abundance_weight

        chain_detections.append({
            'chain_name': chain_name,
            'parent': chain_data['parent'],
            'confidence': confidence,
            'confidence_level': _chain_confidence_level(num_detected),
            'detected_members': detected_members,
            'num_detected': num_detected,
            'num_key_isotopes': num_key_isotopes,
            'required_found': required_isotopes_found,
            'abundance_weight': abundance_weight,
            'suppress_when_natural': chain_data.get('suppress_when_natural', False),
            'applications': chain_data.get('applications', []),
            'references': chain_data.get('references', []),
            'notes': chain_data.get('notes', '')
        })

    # With a natural chain (U-238 or Th-232) detected, drop man-made chains marked for suppression: they are
    # usually Compton continuum matching Cs-137 / Co-60
    if any(c['chain_name'] in ['U-238 Chain', 'Th-232 Chain'] for c in chain_detections):
        chain_detections = [c for c in chain_detections if not c.get('suppress_when_natural', False)]

    chain_detections.sort(key=lambda x: x['confidence'], reverse=True)
    return chain_detections
