"""
ML-based isotope identification: a small MLP (scikit-learn) trained on synthetic spectra built from
the isotope database (plus any labelled real spectra found in data/acquisitions).

Uses isotope data from isotope_database.py which is sourced from:
- IAEA Nuclear Data Services (NDS)
- NNDC/ENSDF (National Nuclear Data Center)
- CapGam capture gamma-ray database

Spectra are resampled onto the model's fixed energy grid before classification, so the device's
own energy calibration is honoured (a Radiacode channel is ~2.4 keV, an AlphaHound's ~3 keV).
"""
import logging
import os
logger = logging.getLogger(__name__)
import numpy as np
from typing import List, Dict, Optional

# scikit-learn provides the classifier. PyRIID is deliberately not used: it pins numpy 1.26 /
# scipy 1.13 / TensorFlow 2.16, which cannot coexist with this app's dependencies, and here it was
# only a thin MLP wrapper (the spectrum synthesis below is this project's own code).
try:
    from sklearn.neural_network import MLPClassifier
    HAS_ML = True
except ImportError as e:
    HAS_ML = False
    MLPClassifier = None
    logger.error(f"[WARNING] scikit-learn not available. ML identification disabled. Error: {e}")

# Import the authoritative isotope database and IAEA intensity data
try:
    from isotope_database import ISOTOPE_DATABASE_ADVANCED, get_gamma_intensity, HAS_IAEA_DATA, IAEA_DATA
    HAS_ISOTOPE_DB = True
    logger.info(f"[ML] Loaded {len(ISOTOPE_DATABASE_ADVANCED)} isotopes from database")
except ImportError:
    HAS_ISOTOPE_DB = False
    HAS_IAEA_DATA = False
    IAEA_DATA = {}
    ISOTOPE_DATABASE_ADVANCED = {}
    def get_gamma_intensity(isotope, energy): return 1.0
    logger.warning("[WARNING] Isotope database not found, using fallback isotopes")

# Import real spectrum loader for training data augmentation
try:
    from ml_data_loader import load_real_training_data
    HAS_REAL_DATA_LOADER = True
    logger.info("[ML] Real spectrum loader available")
except ImportError:
    HAS_REAL_DATA_LOADER = False
    load_real_training_data = None
    logger.warning("[WARNING] Real spectrum loader not available")



# =========================================================
# SELECTABLE ML MODEL TYPES
# Hobby: ~35 common isotopes for hobby use (uranium glass, mantles, etc.)
# Comprehensive: All 95+ isotopes for advanced/research use
# =========================================================

HOBBY_ISOTOPES = [
    # Calibration sources
    "Co-60", "Cs-137", "Na-22", "Am-241", "Ba-133",
    # Natural background
    "K-40",
    # U-238 decay chain (uranium glass, Fiestaware, radium watches)
    "U-238", "Th-234", "Pa-234m", "U-234", "Ra-226", "Pb-214", "Bi-214",
    # Th-232 decay chain (lantern mantles, welding rods)
    "Th-232", "Ac-228", "Pb-212", "Bi-212", "Tl-208",
    # U-235 chain (rare, but needed for completeness)
    "U-235", "Th-231", "Th-227", "Ra-223",
    # Common medical (may encounter from medical waste)
    "I-131", "Tc-99m", "F-18", "Tl-201",
    # Industrial (gauges, sources)
    "Ir-192", "Se-75", "Co-57", "Eu-152",
    # Background placeholder
    "Background"
]

ML_MODEL_TYPES = {
    "hobby": {
        "name": "Hobby (35 isotopes)",
        "description": "Common sources: uranium glass, mantles, radium, calibration",
        "isotopes": HOBBY_ISOTOPES,
        "samples_per_isotope": 30
    },
    "comprehensive": {
        "name": "Comprehensive (95+ isotopes)",
        "description": "All isotopes including fission products, transuranics",
        "isotopes": None,  # Use full database
        "samples_per_isotope": 15
    }
}

# =========================================================
# DETECTOR PROFILES (Phase 4: Multi-Detector Support)
# Different scintillator detectors have different resolutions
# =========================================================
DETECTOR_PROFILES = {
    'alphahound_csi': {
        'name': 'AlphaHound CsI(Tl)',
        'channels': 1024,
        'keV_per_channel': 3.0,
        'fwhm_662': 0.10,  # 10% FWHM - 1.1cm³ CsI(Tl) per RadView specs
        'description': 'AlphaHound AB+G with CsI(Tl) crystal (1.1cm³)'
    },
    'alphahound_bgo': {
        'name': 'AlphaHound BGO',
        'channels': 1024,
        'keV_per_channel': 3.0,
        'fwhm_662': 0.13,  # 13% FWHM - 0.6cm³ BGO per RadView specs
        'description': 'AlphaHound AB+G with BGO crystal (0.6cm³)'
    },
    'alphahound': {  # Alias for CsI (most common)
        'name': 'AlphaHound (Auto)',
        'channels': 1024,
        'keV_per_channel': 3.0,
        'fwhm_662': 0.10,  # Default to CsI specs
        'description': 'AlphaHound AB+G (defaults to CsI settings)'
    },
    'radiacode_103': {
        'name': 'Radiacode 103',
        'channels': 1024,
        'keV_per_channel': 2.93,
        'fwhm_662': 0.08,  # 8% FWHM - 1cm³ CsI(Tl)
        'description': 'Radiacode 103 pocket detector (1cm³ crystal)'
    },
    'radiacode_103g': {
        'name': 'Radiacode 103G',
        'channels': 1024,
        'keV_per_channel': 2.93,
        'fwhm_662': 0.07,  # 7% FWHM - GMI crystal, better resolution
        'description': 'Radiacode 103G with GMI crystal (1cm³)'
    },
    'radiacode_110': {
        'name': 'Radiacode 110',
        'channels': 1024,
        'keV_per_channel': 2.93,
        'fwhm_662': 0.08,  # 8% FWHM - same resolution as 103, larger crystal
        'description': 'Radiacode 110 (3cm³ crystal, higher sensitivity)'
    },
    'radiacode_102': {
        'name': 'Radiacode 102',
        'channels': 1024,
        'keV_per_channel': 2.93,
        'fwhm_662': 0.08,  # 8% FWHM
        'description': 'Radiacode 102 compact detector'
    },
    'generic_nai': {
        'name': 'Generic NaI(Tl)',
        'channels': 1024,
        'keV_per_channel': 3.0,
        'fwhm_662': 0.08,  # 8% typical for NaI
        'description': 'Generic NaI(Tl) scintillator'
    }
}


class MLIdentifier:
    """ML-based isotope identifier (scikit-learn MLP).
    
    Uses authoritative gamma-ray energies from IAEA NDS, NNDC/ENSDF databases
    to generate synthetic training spectra for comprehensive isotope identification.
    
    Supports multiple detector profiles:
    - alphahound: AlphaHound CsI(Tl) @ 10% FWHM
    - radiacode_103: Radiacode 103 @ 7% FWHM
    - radiacode_102: Radiacode 102 @ 8% FWHM
    - generic_nai: Generic NaI(Tl) @ 8% FWHM
    """
    
    def __init__(self, model_type: str = "hobby", detector: str = "alphahound"):
        """Initialize ML identifier with selectable model type and detector.
        
        Args:
            model_type: "hobby" for 35 common isotopes, "comprehensive" for 95+ isotopes
            detector: Detector profile name (see DETECTOR_PROFILES)
        """
        self.model = None
        self.classes_: List[str] = []
        self.is_trained = False
        self.model_type = model_type if model_type in ML_MODEL_TYPES else "hobby"
        
        # Get detector profile
        self.detector_name = detector if detector in DETECTOR_PROFILES else "alphahound"
        profile = DETECTOR_PROFILES[self.detector_name]
        
        self.n_channels = profile['channels']
        self.keV_per_channel = profile['keV_per_channel']
        self.reference_fwhm_fraction = profile['fwhm_662']
        self.reference_energy = 662.0  # keV (Cs-137 reference)
        
        logger.info(f"[ML] Model: {ML_MODEL_TYPES[self.model_type]['name']}, Detector: {profile['name']}")
        
        
    def energy_to_channel(self, energy_keV: float) -> int:
        """Convert gamma energy in keV to channel number."""
        channel = int(energy_keV / self.keV_per_channel)
        return max(0, min(channel, self.n_channels - 1))
    
    def get_fwhm_channels(self, energy_keV: float) -> int:
        """Calculate FWHM in channels for AlphaHound CsI(Tl) detector.
        
        Uses energy-dependent resolution model:
        FWHM(E) = FWHM_ref * sqrt(E_ref / E) for scintillators
        
        At 662 keV: FWHM = 10% = 66.2 keV = 22 channels
        At 186 keV: FWHM = 18.8% = 35 keV = 12 channels
        At 1461 keV: FWHM = 6.7% = 98 keV = 33 channels
        """
        # FWHM in keV using scintillator resolution scaling
        fwhm_keV = self.reference_fwhm_fraction * energy_keV * (self.reference_energy / energy_keV) ** 0.5
        fwhm_channels = max(3, int(fwhm_keV / self.keV_per_channel))
        return fwhm_channels
    
    def add_compton_continuum(self, spectrum: np.ndarray, peak_energy_keV: float, peak_intensity: float):
        """Add realistic Compton scattering continuum for a gamma-ray peak.
        
        Compton scattering creates a continuous distribution of energies from
        the Compton edge down to zero. The Compton edge energy is:
        E_edge = E_gamma / (1 + 2*E_gamma/(511 keV))
        
        For CsI(Tl), we add a simplified continuum shape that:
        1. Rises from the Compton edge toward lower energies
        2. Peaks around 1/3 of the way to zero
        3. Falls off gradually at very low energies
        """
        # Calculate Compton edge energy
        E_gamma = peak_energy_keV
        E_edge = E_gamma / (1 + 2 * E_gamma / 511.0)
        edge_channel = self.energy_to_channel(E_edge)
        
        # Compton continuum intensity is typically 30-50% of peak for CsI
        continuum_fraction = 0.35 * np.random.uniform(0.8, 1.2)
        total_continuum = int(peak_intensity * continuum_fraction)
        
        # Distribute counts from channel 0 to Compton edge
        if edge_channel > 5 and total_continuum > 0:
            # Create triangular-ish distribution (peak around 1/3 of edge)
            channels = np.arange(0, edge_channel)
            # Distribution rises then falls - peak around edge/3
            peak_pos = edge_channel // 3
            weights = np.where(channels < peak_pos, 
                              channels / (peak_pos + 1),
                              (edge_channel - channels) / (edge_channel - peak_pos + 1))
            weights = weights / (weights.sum() + 1e-10)  # Normalize
            
            # Add Poisson-distributed counts
            continuum_counts = np.random.multinomial(total_continuum, weights)
            spectrum[:edge_channel] += continuum_counts
        
        return spectrum
    
    def add_environmental_background(self, spectrum: np.ndarray, scale: float = 1.0):
        """Add realistic environmental background radiation to spectrum.
        
        Phase 2 of ML Improvement Plan: Train model to ignore background.
        
        Background includes:
        - K-40 at 1461 keV (potassium in soil/concrete)
        - Bi-214 at 609 keV (radon daughter)
        - Tl-208 at 2614 keV (thorium chain)
        - Low-energy continuum from cosmic rays
        """
        # Environmental background peaks with typical relative intensities
        BACKGROUND_PEAKS = [
            (1461, 0.30),  # K-40 - strongest environmental gamma
            (609, 0.15),   # Bi-214 from radon
            (352, 0.08),   # Pb-214 from radon
            (2614, 0.05),  # Tl-208 from thorium
            (583, 0.04),   # Tl-208 secondary
            (911, 0.03),   # Ac-228 from thorium
        ]
        
        # Randomize background intensity (0.5x to 2.0x scale)
        bg_scale = scale * np.random.uniform(0.5, 2.0)
        base_bg_intensity = 50  # Base counts for background peaks
        
        for energy_keV, rel_intensity in BACKGROUND_PEAKS:
            channel = self.energy_to_channel(energy_keV)
            if channel < 5 or channel >= self.n_channels - 5:
                continue
            
            peak_intensity = int(base_bg_intensity * rel_intensity * bg_scale)
            if peak_intensity < 1:
                continue
            
            # Add Gaussian-shaped background peak
            fwhm = self.get_fwhm_channels(energy_keV)
            half_width = max(2, fwhm // 2)
            start_ch = max(0, channel - half_width)
            end_ch = min(self.n_channels, channel + half_width + 1)
            width = end_ch - start_ch
            
            if width > 0:
                peak_counts = np.random.poisson(max(1, peak_intensity // width), width)
                spectrum[start_ch:end_ch] += peak_counts
        
        # Add low-energy continuum (cosmic/scattered)
        low_energy_continuum = np.exp(-np.arange(self.n_channels) / 100) * 3 * bg_scale
        spectrum += np.random.poisson(np.maximum(0.1, low_energy_continuum))
        
        return spectrum
    
    def energy_to_channel_with_jitter(self, energy_keV: float) -> int:
        """Convert energy to channel with calibration jitter.
        
        Phase 3 of ML Improvement Plan: Make model robust to calibration drift.
        
        Applies random ±10% gain variation and ±5 keV offset to simulate
        real-world detector calibration differences.
        """
        # Random calibration variation
        gain_jitter = np.random.uniform(0.9, 1.1)  # ±10% gain
        offset_jitter = np.random.uniform(-5, 5)    # ±5 keV offset
        
        effective_keV_per_ch = self.keV_per_channel * gain_jitter
        channel = int((energy_keV - offset_jitter) / effective_keV_per_ch)
        
        return max(0, min(channel, self.n_channels - 1))
        
    def lazy_train(self):
        """Train model on synthetic data using authoritative isotope database."""
        if not HAS_ML:
            raise ImportError("scikit-learn not installed")
            
        if self.is_trained:
            return
            
        model_config = ML_MODEL_TYPES[self.model_type]
        logger.info(f"[ML] Training classifier on synthetic data ({model_config['name']})...")
        
        # Build isotope list from authoritative database
        # Filter to isotopes with gamma emissions (non-empty energy lists)
        isotope_data = {}
        
        # Get allowed isotopes for this model type
        allowed_isotopes = model_config['isotopes']  # None = all isotopes
        
        if HAS_ISOTOPE_DB and ISOTOPE_DATABASE_ADVANCED:
            for isotope, energies in ISOTOPE_DATABASE_ADVANCED.items():
                if energies and len(energies) > 0:  # Has gamma emissions
                    # Filter by model type if specified
                    if allowed_isotopes is None or isotope in allowed_isotopes:
                        isotope_data[isotope] = energies
        
        # Add Background if not present
        if 'Background' not in isotope_data:
            isotope_data['Background'] = []
            
        isotopes = list(isotope_data.keys())
        base_samples = model_config['samples_per_isotope']  # Use model-specific sample count
        logger.info(f"[ML] Training on {len(isotopes)} isotopes with {base_samples} samples each")
        
        # =========================================================
        # ABUNDANCE-WEIGHTED SAMPLE GENERATION
        # Generate more samples for common isotopes, fewer for rare
        # =========================================================
        SAMPLE_WEIGHTS = {
            # U-238 chain - MOST COMMON in natural uranium (99.3%)
            "U-238": 5.0, "Bi-214": 5.0, "Pb-214": 5.0, "Ra-226": 5.0,
            "Pa-234m": 3.0, "Th-234": 3.0,
            # U-235 chain - RARE (0.72%) - heavily suppress
            "U-235": 0.2, "Th-231": 0.2, "Ra-223": 0.2, "Th-227": 0.2,
            # Th-232 chain - common in mantles
            "Th-232": 3.0, "Tl-208": 3.0, "Ac-228": 3.0, "Pb-212": 3.0,
            # Common isotopes
            "K-40": 3.0, "Cs-137": 2.0, "Co-60": 2.0,
            # Many-line artificial isotopes soak up noisy natural spectra: keep their prior low
            "Eu-152": 0.4, "Se-75": 0.4, "Ir-192": 0.4, "Ba-133": 0.6,
            # Default weight = 1.0
        }
        
        # Define realistic multi-isotope mixtures (common real-world sources)
        # CRITICAL: Natural uranium mixtures should NOT include U-235 prominently
        mixtures = {
            'UraniumGlass': {  # Uranium glass / Fiestaware - U-238 chain ONLY
                'isotopes': ['Bi-214', 'Pb-214', 'Ra-226', 'Pa-234m', 'Th-234'],
                'ratios': [10.0, 2.0, 1.0, 0.5, 0.4],  # Bi-214@609keV dominates
                'weight': 3.0  # More training samples for this common source
            },
            'UraniumGlassWeak': {  # Weaker uranium glass sample
                'isotopes': ['Bi-214', 'Pb-214', 'Ra-226', 'Th-234'],
                'ratios': [5.0, 1.5, 0.7, 0.3],
                'weight': 2.0
            },
            'UraniumMineral': {  # Pitchblende, autunite - U-238 chain
                'isotopes': ['Bi-214', 'Pb-214', 'Ra-226', 'Pa-234m', 'U-238'],
                'ratios': [8.0, 2.0, 1.5, 0.8, 0.3],
                'weight': 1.5
            },
            'RadiumDial': {  # Vintage watch dials - Ra-226 dominant
                'isotopes': ['Ra-226', 'Bi-214', 'Pb-214'],
                'ratios': [1.0, 5.0, 1.5],
                'weight': 1.5
            },
            'ThoriumMantle': {  # Th-232 series in secular equilibrium (mantles, thoriated lenses/glass/rods)
                'isotopes': ['Ac-228', 'Pb-212', 'Bi-212', 'Tl-208', 'Ra-224', 'Th-228', 'Th-232'],
                'ratios': [1.0, 1.0, 1.0, 0.36, 1.0, 1.0, 0.05],  # Tl-208 only 36% of Bi-212 decays
                'weight': 3.0
            },
            'ThoriumMantleAged': {  # Ra-228 / Ac-228 depleted (older purified thorium): Th-228 end dominates
                'isotopes': ['Ac-228', 'Pb-212', 'Bi-212', 'Tl-208', 'Ra-224', 'Th-228'],
                'ratios': [0.3, 1.0, 1.0, 0.36, 1.0, 1.0],
                'label': 'ThoriumMantle', 'weight': 2.0
            },
            'ThoriumMantleFresh': {  # Ac-228 enriched (fresh Ra-228 ingrowth)
                'isotopes': ['Ac-228', 'Pb-212', 'Bi-212', 'Tl-208', 'Ra-224', 'Th-228'],
                'ratios': [1.0, 0.6, 0.6, 0.22, 0.6, 0.6],
                'label': 'ThoriumMantle', 'weight': 1.5
            },
            'RadiumEquilibrium': {  # Ra-226 with radon retained: Pb-214 / Bi-214 at full strength
                'isotopes': ['Ra-226', 'Pb-214', 'Bi-214'],
                'ratios': [0.3, 1.0, 1.0],
                'label': 'RadiumDial', 'weight': 3.0
            },
            'MedicalWaste': {  # Hospital nuclear medicine waste
                'isotopes': ['Tc-99m', 'I-131', 'Mo-99'],
                'ratios': [1.0, 0.5, 0.3],
                'weight': 1.0
            },
            'IndustrialGauge': {  # Level/density gauges
                'isotopes': ['Cs-137', 'Co-60'],
                'ratios': [1.0, 0.8],
                'weight': 1.5
            },
            'CalibrationSource': {  # Multi-isotope check source
                'isotopes': ['Am-241', 'Ba-133', 'Cs-137', 'Co-60'],
                'ratios': [0.7, 1.0, 0.9, 0.8],
                'weight': 1.0
            },
            'NaturalBackground': {  # Typical background radiation
                'isotopes': ['K-40', 'Bi-214', 'Tl-208', 'Pb-214'],
                'ratios': [1.0, 0.3, 0.1, 0.2],
                'weight': 2.0
            }
        }
        
        rng = np.random.default_rng(12345)
        lines_for = {iso: self._lines(iso, isotope_data.get(iso, [])) for iso in isotopes}

        spectra, labels = [], []
        # Natural-series daughters never occur alone: they are only trained as part of the series
        # mixtures below (a thorium lens must not be explained as "just Pb-214").
        from source_templates import SERIES_MEMBERS
        series_daughters = {m for parent, members in SERIES_MEMBERS.items() for m in members if m != parent}
        for isotope in isotopes:
            if isotope in series_daughters:
                continue
            for _ in range(int(base_samples * SAMPLE_WEIGHTS.get(isotope, 1.0))):
                spectra.append(self.synthesize(lines_for[isotope] if isotope != 'Background' else [], rng,
                                               is_background=(isotope == 'Background')))
                labels.append(isotope)
        for name, mix in mixtures.items():
            def lines_by_nuclide(rng, mix=mix):
                out = []
                for iso, ratio in zip(mix['isotopes'], mix['ratios']):
                    energies = isotope_data.get(iso) or ISOTOPE_DATABASE_ADVANCED.get(iso) or []
                    k = ratio * float(np.exp(rng.normal(0, 0.35)))      # per-nuclide strength
                    out += [(e, w * k) for e, w in self._lines(iso, energies)]
                return out
            for _ in range(int(25 * mix.get('weight', 1.0))):
                # each constituent's strength varies per sample (disequilibrium, radon loss, ...)
                jittered = lines_by_nuclide(rng)
                spectra.append(self.synthesize(jittered, rng))
                labels.append(mix.get('label', name))
        spectra_matrix = np.array(spectra)
        logger.info(f"[ML] Synthesised {len(labels)} training spectra")

        # Labelled real spectra are opt-in: the loader labels by filename and resamples without
        # regard to calibration, so it can teach the model wrong things (and leaks benchmark files).
        if os.environ.get("ML_USE_REAL_DATA") == "1" and HAS_REAL_DATA_LOADER and load_real_training_data:
            try:
                real_x, real_labels = load_real_training_data(data_dir=None, target_channels=self.n_channels,
                                                              augment_count=10)
                if len(real_labels) > 0:
                    spectra_matrix = np.vstack([spectra_matrix, real_x])
                    labels.extend(real_labels)
                    logger.info(f"[ML] Added {len(real_labels)} augmented real spectra")
            except Exception as e:
                logger.warning(f"[ML] Real spectra loading failed (non-critical): {e}")

        unique_isotopes = sorted(set(labels))
        try:
            self.model = MLPClassifier(hidden_layer_sizes=(256, 128), max_iter=300, early_stopping=True,
                                       n_iter_no_change=10, random_state=0)
            # integer-encoded: scikit-learn's early-stopping scorer cannot handle string classes
            self.classes_ = unique_isotopes
            index = {name: i for i, name in enumerate(unique_isotopes)}
            self.model.fit(self.features(spectra_matrix), np.array([index[l] for l in labels]))
            self.is_trained = True
            logger.info(f"[ML] Training complete. Model ready with {len(unique_isotopes)} classes.")
        except Exception as e:
            logger.warning(f"[ML] Training failed: {e}")
            self.is_trained = False
            raise

    @staticmethod
    def _lines(isotope: str, energies) -> List[tuple]:
        """(energy keV, relative weight) for an isotope's gamma lines, weighted by IAEA intensity %."""
        gammas = {}
        if HAS_ISOTOPE_DB and IAEA_DATA and isotope in IAEA_DATA:
            gammas = {round(e, 1): i for e, i in IAEA_DATA[isotope].get('gammas', []) or []}
        out = []
        for e in energies:
            inten = next((i for ge, i in gammas.items() if abs(ge - e) < 2.0), 5.0)
            out.append((float(e), max(float(inten), 0.5)))
        return out

    # Typical environmental background lines (keV, relative weight)
    ENV_LINES = [(1461, 10.7), (609, 45.0 * 0.3), (352, 35.0 * 0.3), (2614, 36.0 * 0.15), (583, 30.0 * 0.15),
                 (911, 26.0 * 0.15), (1764, 15.0 * 0.3)]

    def synthesize(self, lines, rng, is_background: bool = False) -> np.ndarray:
        """One synthetic spectrum on this model's grid.

        Per sample (not per line): one gain/offset error, one resolution scale, one total-count level
        and one source-to-background mix. Lines get Gaussian photopeaks with energy-dependent FWHM,
        efficiency falling with energy, a Compton shelf, and low-energy continuum; Poisson noise last.
        """
        n, kpc = self.n_channels, self.keV_per_channel
        grid = np.arange(n) * kpc + kpc / 2                  # channel centre energies
        gain = rng.uniform(0.97, 1.03)
        offset = rng.uniform(-8.0, 8.0)
        res_scale = rng.uniform(0.85, 1.2)

        def shape(src_lines, peak_to_compton):
            spec = np.zeros(n)
            for energy, weight in src_lines:
                e = (energy - offset) / gain                  # where this line lands on the (mis)calibrated axis
                if e < 15 or e > grid[-1]:
                    continue
                area = weight * (max(energy, 30.0) / 100.0) ** -0.8
                fwhm = self.reference_fwhm_fraction * res_scale * 662.0 * np.sqrt(e / 662.0)
                sigma = max(fwhm / 2.355, kpc)
                spec += area * np.exp(-0.5 * ((grid - e) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi)) * kpc
                if energy > 120:
                    edge = e / (1 + 2 * e / 511.0)
                    shelf = np.where(grid < edge, 1.0, 0.0) * (0.35 + 0.65 * grid / max(edge, 1.0))
                    if shelf.sum() > 0:
                        spec += area * peak_to_compton * shelf / shelf.sum()
            return spec

        src = np.zeros(n) if (is_background or not lines) else shape(lines, rng.uniform(0.8, 3.0))
        bg = shape(self.ENV_LINES, 2.0)
        bg_lowE = np.exp(-grid / 250.0)
        bg = bg / max(bg.sum(), 1e-9) + 0.3 * bg_lowE / bg_lowE.sum()
        total = 10 ** rng.uniform(3.7, 6.3)                   # 5 k .. 2 M counts
        if is_background or src.sum() <= 0:
            mix = bg / bg.sum()
            total = 10 ** rng.uniform(3.3, 5.0)
        else:
            frac_bg = rng.uniform(0.02, 0.6) if rng.random() < 0.7 else 0.0
            mix = (1 - frac_bg) * src / src.sum() + frac_bg * bg / bg.sum()
        return rng.poisson(mix * total).astype(float)

    @staticmethod
    def features(spectra: np.ndarray) -> np.ndarray:
        """Square-root (Poisson variance-stabilising) then L2-normalise each spectrum."""
        x = np.sqrt(np.clip(np.atleast_2d(np.asarray(spectra, dtype=float)), 0, None))
        norm = np.linalg.norm(x, axis=1, keepdims=True)
        return x / np.where(norm > 0, norm, 1.0)

    def resample(self, counts, energies=None) -> np.ndarray:
        """Counts on this model's channel grid (channel i spans i*keV_per_channel upward).

        With energies (channel energies of the input spectrum) the counts are redistributed over the
        model's grid by interpolating the cumulative spectrum, which preserves the total and moves
        every line to the right channel whatever the input calibration. Without energies the input
        is assumed to already be on the model's grid (padded/truncated).
        """
        counts = np.asarray(counts, dtype=float)
        if energies is not None and len(energies) == len(counts) and len(counts) > 1:
            e = np.asarray(energies, dtype=float)
            if np.all(np.diff(e) > 0):
                step = np.median(np.diff(e))
                edges_in = np.concatenate([[e[0] - step / 2], (e[:-1] + e[1:]) / 2, [e[-1] + step / 2]])
                cum = np.concatenate([[0.0], np.cumsum(counts)])
                grid = np.arange(self.n_channels + 1) * self.keV_per_channel
                return np.diff(np.interp(grid, edges_in, cum))
        out = np.zeros(self.n_channels)
        n = min(len(counts), self.n_channels)
        out[:n] = counts[:n]
        return out

    def identify(self, counts: List[int], top_k: int = 5, energies: Optional[List[float]] = None) -> List[Dict]:
        """
        Identify isotopes using the ML model.

        Args:
            counts: Spectrum counts array
            top_k: Number of top predictions to return
            energies: Optional channel energies (keV) of the input, used to resample onto the model grid

        Returns:
            List of predictions with isotope name and confidence (percent)
        """
        if not HAS_ML:
            raise ImportError("scikit-learn not installed")
        if not self.is_trained:
            self.lazy_train()

        spectrum = self.resample(counts, energies)
        if spectrum.sum() <= 0:
            return []
        try:
            probas = self.model.predict_proba(self.features(spectrum))[0]
        except Exception as e:
            logger.error(f"[ML] Prediction error: {e}")
            return []
        results = [
            {'isotope': str(name), 'confidence': round(float(p) * 100, 2), 'method': 'ML (MLP)'}
            for name, p in zip((self.classes_[int(i)] for i in self.model.classes_), probas) if p * 100 > 1.0
        ]
        results.sort(key=lambda x: x['confidence'], reverse=True)
        return results[:top_k]

    def export_model(self, output_path: str, format: str = 'onnx') -> dict:
        """Export the trained model to ONNX (requires the optional skl2onnx package)."""
        if format.lower() != 'onnx':
            return {'success': False, 'error': f"Unsupported format: {format} (only 'onnx')"}
        if not self.is_trained:
            self.lazy_train()
        try:
            from skl2onnx import to_onnx
        except ImportError:
            return {'success': False, 'error': 'skl2onnx not installed. Run: pip install skl2onnx'}
        try:
            proto = to_onnx(self.model, np.zeros((1, self.n_channels), dtype=np.float32))
            if not output_path.endswith('.onnx'):
                output_path += '.onnx'
            with open(output_path, 'wb') as f:
                f.write(proto.SerializeToString())
            return {'success': True, 'format': 'onnx', 'path': output_path, 'input_shape': [self.n_channels],
                    'output_classes': list(self.classes_), 'model_type': self.model_type,
                    'note': 'Input is sqrt-then-L2-normalised counts on the model energy grid'}
        except Exception as e:
            return {'success': False, 'error': f'ONNX export failed: {e}'}


# Global instances (one per model type + detector combination)
_ml_identifiers = {}

def get_ml_identifier(model_type: str = "hobby", detector: str = "alphahound") -> Optional[MLIdentifier]:
    """Get or create ML identifier instance for specified model type and detector.
    
    Args:
        model_type: "hobby" for 35 common isotopes, "comprehensive" for 95+
        detector: Detector profile name ("alphahound", "radiacode_103", etc.)
        
    Returns:
        MLIdentifier instance (None if scikit-learn is not available)
    """
    global _ml_identifiers
    
    if not HAS_ML:
        return None
    
    # Normalize model type and detector
    if model_type not in ML_MODEL_TYPES:
        model_type = "hobby"
    if detector not in DETECTOR_PROFILES:
        detector = "alphahound"
    
    # Cache key is combination of model type and detector
    cache_key = f"{model_type}_{detector}"
    
    # Create instance for this combination if not exists
    if cache_key not in _ml_identifiers:
        _ml_identifiers[cache_key] = MLIdentifier(model_type=model_type, detector=detector)
    
    return _ml_identifiers[cache_key]


def get_available_detectors() -> dict:
    """Get available detector profiles for settings UI.
    
    Returns:
        Dict of detector_name -> {"name": str, "description": str, "fwhm": float}
    """
    return {
        k: {
            "name": v["name"], 
            "description": v["description"],
            "fwhm_662": v["fwhm_662"]
        }
        for k, v in DETECTOR_PROFILES.items()
    }


def get_available_ml_models() -> dict:
    """Get available ML model types for settings UI.
    
    Returns:
        Dict of model_type -> {"name": str, "description": str}
    """
    return {
        k: {"name": v["name"], "description": v["description"]}
        for k, v in ML_MODEL_TYPES.items()
    }


def hybrid_identify(counts: List[int], peak_isotopes: List[Dict], 
                    model_type: str = "hobby", 
                    ml_weight: float = 0.4) -> List[Dict]:
    """Combine ML and peak-matching for improved identification.
    
    Phase 5 of ML Improvement Plan: Hybrid ensemble scoring.
    
    Peak-matching is more reliable for known isotopes with clear signatures,
    while ML can identify complex mixtures and unusual patterns.
    
    Args:
        counts: Spectrum counts array
        peak_isotopes: Results from peak-matching algorithm
            Each dict: {'isotope': str, 'confidence': float, ...}
        model_type: ML model type ('hobby' or 'comprehensive')
        ml_weight: Weight for ML predictions (0.0-1.0), default 0.4
            Peak-matching gets (1 - ml_weight)
    
    Returns:
        Combined results sorted by hybrid confidence
    """
    peak_weight = 1.0 - ml_weight
    
    # Get ML predictions
    ml_results = []
    ml = get_ml_identifier(model_type)
    if ml is not None:
        try:
            ml_results = ml.identify(counts, top_k=10)
        except Exception as e:
            logger.warning(f"[Hybrid] ML failed, using peak-matching only: {e}")
    
    # Build combined score map
    combined = {}
    
    # Add peak-matching results
    for r in peak_isotopes:
        isotope = r.get('isotope', '')
        if not isotope:
            continue
        
        conf = r.get('confidence', 0)
        combined[isotope] = {
            'isotope': isotope,
            'peak_conf': conf,
            'ml_conf': 0.0,
            'matched_peaks': r.get('matched_peaks', []),
            'peak_method': r.get('method', 'Peak Matching')
        }
    
    # Add/merge ML results
    for r in ml_results:
        isotope = r.get('isotope', '')
        if not isotope:
            continue
        
        if isotope in combined:
            combined[isotope]['ml_conf'] = r.get('confidence', 0)
        else:
            combined[isotope] = {
                'isotope': isotope,
                'peak_conf': 0.0,
                'ml_conf': r.get('confidence', 0),
                'matched_peaks': [],
                'peak_method': None
            }
    
    # Calculate hybrid scores
    results = []
    for isotope, scores in combined.items():
        # Weighted combination
        hybrid_conf = (peak_weight * scores['peak_conf'] + 
                      ml_weight * scores['ml_conf'])
        
        # Determine primary method
        if scores['peak_conf'] > scores['ml_conf']:
            method = 'Hybrid (Peak+ML)'
        elif scores['ml_conf'] > scores['peak_conf']:
            method = 'Hybrid (ML+Peak)'
        else:
            method = 'Hybrid'
        
        results.append({
            'isotope': isotope,
            'confidence': round(hybrid_conf, 2),
            'peak_conf': round(scores['peak_conf'], 2),
            'ml_conf': round(scores['ml_conf'], 2),
            'method': method,
            'matched_peaks': scores['matched_peaks']
        })
    
    # Sort by hybrid confidence
    results.sort(key=lambda x: x['confidence'], reverse=True)
    
    return results
