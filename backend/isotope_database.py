# ========== SIMPLE MODE DATABASE (Hobby-Focused) ==========
# Optimized for common hobby sources, background radiation, and basic medical/industrial
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
    "U-238": [49.55],
    "Th-234": [63.3],
    "Pa-234m": [1001.0, 766.4],
    "U-234": [53.2],
    "Ra-226": [186.2],
    "Pb-214": [295.2, 351.9, 241.0],
    "Bi-214": [609.3, 1120.3, 1764.5],
    
    # Th-232 Decay Chain (Thorium series) - Lantern mantles
    "Th-232": [63.8],
    "Ac-228": [338.3, 911.2, 968.9],
    "Pb-212": [238.6],
    "Bi-212": [727.0, 1621.0],
    "Tl-208": [583.2, 860.6, 2614.5],
    
    # U-235 Decay Chain (Actinium series)
    "U-235": [185.7, 143.8, 163.4, 205.3],
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

def get_isotope_database(mode='simple'):
    """
    Get the appropriate isotope database based on mode.
    
    Args:
        mode: 'simple' for hobby-focused (30 isotopes) or 'advanced' for comprehensive (100+ isotopes)
    
    Returns:
        Dictionary of isotope names to gamma energies
    """
    if mode == 'advanced':
        return ISOTOPE_DATABASE_ADVANCED
    return ISOTOPE_DATABASE_SIMPLE


# Decay chain definitions with key indicators
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
            "Bi-214": [609.3, 1120.3, 1764.5],  # Strongest indicator
            "Pb-214": [351.9, 295.2, 241.0],    # Major contributor
            "Pa-234m": [1001.0, 766.4],         # High energy
            "Th-234": [63.3],                   # Low energy
            "Ra-226": [186.2]                   # Parent
        },
        "applications": [
            "Uranium glass/vaseline glass",
            "Vintage Fiestaware ceramics",
            "Radium watch dials (pre-1970)",
            "Uranium minerals",
            "Natural background radiation"
        ],
        "abundance_weight": 0.993,  # U-238 is 99.3% of natural uranium
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
            "Tl-208": [2614.5, 583.2, 510.0],  # 2614 keV is DIAGNOSTIC
            "Ac-228": [911.2, 968.9],           # Significant peaks
            "Pb-212": [238.6]                   # Prominent
        },
        "applications": [
            "Gas lantern mantles (camping)",
            "Vintage camera lenses (1940s-1970s)",
            "Welding rods (thoriated tungsten)",
            "Thorium minerals"
        ],
        "abundance_weight": 1.0,  # Not in natural uranium, but common in mantles/ceramics
        "references": [
            {"name": "NNDC Th-232 Data", "url": "https://www.nndc.bnl.gov/nudat3/decaysearchdirect.jsp?nuc=232Th"},
            {"name": "Thorium Abundance (USGS)", "url": "https://pubs.usgs.gov/fs/2002/fs087-02/"},
            {"name": "Natural Series (Britannica)", "url": "https://www.britannica.com/science/thorium-series"}
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
            "U-235": [185.7, 143.8],  # Direct detection
            "Th-227": [236.0],         # For Ac-227
            "Ra-223": [144.2]          # Daughter
        },
        "applications": [
            "Natural uranium (0.72% abundance)",
            "Enriched uranium materials",
            "Old nuclear equipment"
        ],
        "abundance_weight": 0.0072,  # U-235 is only 0.72% of natural uranium  
        "references": [
            {"name": "NNDC U-235 Data", "url": "https://www.nndc.bnl.gov/nudat3/decaysearchdirect.jsp?nuc=235U"},
            {"name": "Isotopic Composition (NRC)", "url": "https://www.nrc.gov/reading-rm/doc-collections/fact-sheets/uranium.html"},
            {"name": "Actinium Series (Wikipedia)", "url": "https://en.wikipedia.org/wiki/Decay_chain#Actinium_series"}
        ],
        "notes": "Usually overshadowed by U-238 chain in natural samples. 185.7 keV overlaps with Ra-226 at 186.2 keV."
    }
}

def identify_isotopes(peaks, energy_tolerance=20.0, mode='simple'):
    """
    Identify possible isotopes based on detected peaks.
    Returns ALL matches - filtering should be done at application layer.
    
    Args:
        peaks: List of detected peak dictionaries with 'energy' key
        energy_tolerance: Maximum energy difference for a match (keV)
        mode: 'simple' or 'advanced' - determines which database to use
    
    Returns:
        List of identified isotopes with confidence scores (unfiltered)
    """
    if not peaks:
        return []
    
    # Get appropriate database for mode
    database = get_isotope_database(mode)
    
    isotope_matches = {}
    
    # For each isotope in database
    for isotope, gamma_energies in database.items():
        # Skip isotopes with no gamma emissions
        if not gamma_energies:
            continue
            
        matches = 0
        matched_peaks = []
        
        # Check how many of its gamma energies match detected peaks
        for gamma_energy in gamma_energies:
            for peak in peaks:
                energy_diff = abs(peak['energy'] - gamma_energy)
                if energy_diff <= energy_tolerance:
                    matches += 1
                    matched_peaks.append({
                        'expected': gamma_energy,
                        'observed': peak['energy'],
                        'diff': energy_diff
                    })
                    break
        
        # Calculate confidence score
        if matches > 0:
            # Confidence based on fraction of characteristic peaks found
            confidence = (matches / len(gamma_energies)) * 100
            
            # Return ALL matches - application layer will filter
            isotope_matches[isotope] = {
                'isotope': isotope,
                'confidence': confidence,
                'matches': matches,
                'total_lines': len(gamma_energies),
                'matched_peaks': matched_peaks
            }
    
    # Sort by confidence
    identified = sorted(isotope_matches.values(), 
                       key=lambda x: (x['matches'], x['confidence']), 
                       reverse=True)
    
    # Return all matches (no top 5 limit for flexibility)
    return identified


def identify_decay_chains(peaks, identified_isotopes=None, energy_tolerance=20.0):
    """
    Identify radioactive decay chains based on detected peaks and isotopes.
    Returns ALL matches - filtering should be done at application layer.
    
    Args:
        peaks: List of detected peak dictionaries with 'energy' key
        identified_isotopes: Optional list from identify_isotopes() (for optimization)
        energy_tolerance: Maximum energy difference for a match (keV)
    
    Returns:
        List of detected decay chains with confidence scores (unfiltered)
    """
    if not peaks:
        return []
    
    chain_detections = []
    
    for chain_name, chain_data in DECAY_CHAINS.items():
        detected_members = {}
        total_indicator_peaks = 0
        matched_indicator_peaks = 0
        
        # Check each key indicator isotope in this chain
        for isotope, indicator_energies in chain_data["key_indicators"].items():
            total_indicator_peaks += len(indicator_energies)
            matched_energies = []
            
            # Check if any of this isotope's peaks are detected
            for expected_energy in indicator_energies:
                for peak in peaks:
                    energy_diff = abs(peak['energy'] - expected_energy)
                    if energy_diff <= energy_tolerance:
                        matched_indicator_peaks += 1
                        matched_energies.append({
                            'energy': expected_energy,
                            'observed': peak['energy'],
                            'diff': energy_diff
                        })
                        break
            
            # If we detected at least one peak from this isotope, mark it as detected
            if matched_energies:
                detected_members[isotope] = matched_energies
        
        # Calculate confidence based on how many key indicators were found
        num_detected_isotopes = len(detected_members)
        num_key_isotopes = len(chain_data["key_indicators"])
        
        # Return ALL detections, even with 0 isotopes - let application layer filter
        if num_detected_isotopes >= 0:
            # Confidence scoring
            isotope_coverage = (num_detected_isotopes / num_key_isotopes) * 100 if num_key_isotopes > 0 else 0
            peak_coverage = (matched_indicator_peaks / total_indicator_peaks) * 100 if total_indicator_peaks > 0 else 0
            confidence = (isotope_coverage + peak_coverage) / 2
            
            # Determine confidence level for reference (not used for filtering here)
            if num_detected_isotopes >= 4:
                confidence_level = "HIGH"
            elif num_detected_isotopes >= 3:
                confidence_level = "MEDIUM"
            elif num_detected_isotopes >= 2:
                confidence_level = "LOW"
            else:
                confidence_level = "NONE"
            
            # Add all detections - application layer will filter
            chain_detections.append({
                'chain_name': chain_name,
                'parent': chain_data['parent'],
                'confidence': confidence,
                'confidence_level': confidence_level,
                'detected_members': detected_members,
                'num_detected': num_detected_isotopes,
                'num_key_isotopes': num_key_isotopes,
                'abundance_weight': chain_data.get('abundance_weight', 1.0),  # Pass from database
                'applications': chain_data['applications'],
                'references': chain_data.get('references', []),  # Pass authoritative sources
                'notes': chain_data['notes']
            })
    
    # Sort by confidence (highest first)
    chain_detections.sort(key=lambda x: x['confidence'], reverse=True)
    
    return chain_detections
