"""
ML-based isotope identification using PyRIID.
Note: This module requires riid to be installed.

Uses isotope data from isotope_database.py which is sourced from:
- IAEA Nuclear Data Services (NDS)
- NNDC/ENSDF (National Nuclear Data Center)
- CapGam capture gamma-ray database

Tested working with PyRIID 2.2.0:
- Spectra must be 2D matrix (rows=samples, cols=channels)
- Sources must use 3-level MultiIndex: ('Category', 'Isotope', 'Seed')
- predict() modifies SampleSet in-place, doesn't return new object
"""
import numpy as np
from typing import List, Dict, Optional

# Try to import riid with proper error handling
try:
    from riid.data.sampleset import SampleSet
    from riid.models import MLPClassifier
    import pandas as pd
    HAS_RIID = True
    print("[ML] PyRIID successfully imported")
except ImportError as e:
    HAS_RIID = False
    SampleSet = None
    MLPClassifier = None
    pd = None
    print(f"[WARNING] PyRIID not available. ML identification disabled. Error: {e}")
except Exception as e:
    HAS_RIID = False
    SampleSet = None
    MLPClassifier = None
    pd = None
    print(f"[ERROR] Unexpected error importing PyRIID: {e}")

# Import the authoritative isotope database and IAEA intensity data
try:
    from isotope_database import ISOTOPE_DATABASE_ADVANCED, get_gamma_intensity, HAS_IAEA_DATA
    HAS_ISOTOPE_DB = True
    print(f"[ML] Loaded {len(ISOTOPE_DATABASE_ADVANCED)} isotopes from database")
except ImportError:
    HAS_ISOTOPE_DB = False
    HAS_IAEA_DATA = False
    ISOTOPE_DATABASE_ADVANCED = {}
    def get_gamma_intensity(isotope, energy): return 1.0
    print("[WARNING] Isotope database not found, using fallback isotopes")

# Import real spectrum loader for training data augmentation
try:
    from ml_data_loader import load_real_training_data
    HAS_REAL_DATA_LOADER = True
    print("[ML] Real spectrum loader available")
except ImportError:
    HAS_REAL_DATA_LOADER = False
    load_real_training_data = None
    print("[WARNING] Real spectrum loader not available")


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
    """ML-based isotope identifier using PyRIID MLPClassifier.
    
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
        self.is_trained = False
        self.model_type = model_type if model_type in ML_MODEL_TYPES else "hobby"
        
        # Get detector profile
        self.detector_name = detector if detector in DETECTOR_PROFILES else "alphahound"
        profile = DETECTOR_PROFILES[self.detector_name]
        
        self.n_channels = profile['channels']
        self.keV_per_channel = profile['keV_per_channel']
        self.reference_fwhm_fraction = profile['fwhm_662']
        self.reference_energy = 662.0  # keV (Cs-137 reference)
        
        print(f"[ML] Model: {ML_MODEL_TYPES[self.model_type]['name']}, Detector: {profile['name']}")
        
        
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
        if not HAS_RIID:
            raise ImportError("PyRIID not installed")
            
        if self.is_trained:
            return
            
        model_config = ML_MODEL_TYPES[self.model_type]
        print(f"[ML] Training classifier on synthetic data ({model_config['name']})...")
        
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
        print(f"[ML] Training on {len(isotopes)} isotopes with {base_samples} samples each")
        
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
            'ThoriumMantle': {  # Gas lantern mantles - Th-232 chain
                'isotopes': ['Tl-208', 'Ac-228', 'Pb-212', 'Th-232'],
                'ratios': [1.0, 0.6, 0.4, 0.1],  # Tl-208 diagnostic at 2614 keV
                'weight': 2.0
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
        
        # Calculate total samples with abundance weighting
        # base_samples already set from model_config above
        n_single_samples = sum(
            int(base_samples * SAMPLE_WEIGHTS.get(iso, 1.0)) 
            for iso in isotopes
        )
        
        base_mixture_samples = 25
        n_mixture_samples = sum(
            int(base_mixture_samples * m['weight']) 
            for m in mixtures.values()
        )
        n_samples = n_single_samples + n_mixture_samples
        
        print(f"[ML] Training samples: {n_single_samples} single + {n_mixture_samples} mixtures = {n_samples} total")
        
        # Create spectra as 2D matrix (rows=samples, cols=channels)
        spectra_matrix = np.random.poisson(5, (n_samples, self.n_channels)).astype(float)
        labels = []
        
        sample_idx = 0
        
        # Generate single-isotope training data with abundance weighting
        for isotope in isotopes:
            energies = isotope_data.get(isotope, [])
            
            # Get weighted sample count for this isotope
            n_samples_for_isotope = int(base_samples * SAMPLE_WEIGHTS.get(isotope, 1.0))
            
            for i in range(n_samples_for_isotope):
                labels.append(isotope)
                
                # Add characteristic peaks at each gamma energy
                # Phase 3: Use calibration jitter for robustness
                for energy_keV in energies:
                    channel = self.energy_to_channel_with_jitter(energy_keV)
                    
                    # Skip if outside detector range
                    if channel < 5 or channel >= self.n_channels - 5:
                        continue
                    
                    # Use IAEA intensity data for realistic peak heights
                    # Strong gamma lines (e.g., Bi-214 @ 609 keV = 45%) get taller peaks
                    iaea_intensity = get_gamma_intensity(isotope, energy_keV)
                    base_intensity = max(50, 500 * iaea_intensity)  # Scale by IAEA intensity
                    peak_intensity = int(np.random.poisson(base_intensity) * (0.7 + np.random.random() * 0.6))
                    
                    # Add Gaussian-like peak with AlphaHound CsI(Tl) FWHM
                    # Uses energy-dependent resolution (10% at 662 keV)
                    fwhm = self.get_fwhm_channels(energy_keV)
                    half_width = max(2, fwhm // 2)
                    start_ch = max(0, channel - half_width)
                    end_ch = min(self.n_channels, channel + half_width + 1)
                    width = end_ch - start_ch
                    
                    if width > 0:
                        peak_counts = np.random.poisson(max(1, peak_intensity // width), width)
                        spectra_matrix[sample_idx, start_ch:end_ch] += peak_counts
                        
                        # Add Compton continuum for realistic CsI(Tl) response
                        self.add_compton_continuum(spectra_matrix[sample_idx], energy_keV, peak_intensity)
                
                # Phase 2: Add environmental background (50% of samples)
                if np.random.random() > 0.5:
                    self.add_environmental_background(spectra_matrix[sample_idx])
                
                sample_idx += 1
        
        # Generate multi-isotope mixture training data with weighted sample counts
        for mixture_name, mixture_info in mixtures.items():
            mix_isotopes = mixture_info['isotopes']
            mix_ratios = mixture_info['ratios']
            mixture_weight = mixture_info.get('weight', 1.0)
            n_samples_for_mixture = int(base_mixture_samples * mixture_weight)
            
            for i in range(n_samples_for_mixture):
                # Label is the mixture name
                labels.append(mixture_name)
                
                # Add peaks from all isotopes in the mixture with their relative intensities
                for iso_idx, isotope in enumerate(mix_isotopes):
                    if isotope not in isotope_data:
                        continue
                        
                    energies = isotope_data[isotope]
                    relative_strength = mix_ratios[iso_idx]
                    
                    for energy_keV in energies:
                        # Phase 3: Use calibration jitter
                        channel = self.energy_to_channel_with_jitter(energy_keV)
                        
                        if channel < 5 or channel >= self.n_channels - 5:
                            continue
                        
                        # Scale intensity by IAEA data and mixture ratio
                        iaea_intensity = get_gamma_intensity(isotope, energy_keV)
                        base_intensity = max(50, 500 * iaea_intensity) * relative_strength
                        peak_intensity = int(np.random.poisson(base_intensity) * (0.7 + np.random.random() * 0.6))
                        
                        # Use AlphaHound energy-dependent FWHM
                        fwhm = self.get_fwhm_channels(energy_keV)
                        half_width = max(2, fwhm // 2)
                        start_ch = max(0, channel - half_width)
                        end_ch = min(self.n_channels, channel + half_width + 1)
                        width = end_ch - start_ch
                        
                        if width > 0:
                            peak_counts = np.random.poisson(max(1, peak_intensity // width), width)
                            spectra_matrix[sample_idx, start_ch:end_ch] += peak_counts
                
                # Phase 2: Add environmental background (50% of mixtures)
                if np.random.random() > 0.5:
                    self.add_environmental_background(spectra_matrix[sample_idx])
                
                sample_idx += 1
        
        # =========================================================
        # REAL SPECTRA AUGMENTATION (Phase 1 of ML Improvement Plan)
        # Load real labeled spectra from data/acquisitions for training
        # Real data is weighted 10x compared to synthetic for better learning
        # =========================================================
        real_spectra_matrix = None
        real_labels = []
        
        if HAS_REAL_DATA_LOADER and load_real_training_data:
            try:
                print("[ML] Loading real spectra for training augmentation...")
                real_spectra_matrix, real_labels = load_real_training_data(
                    data_dir=None,  # Uses default data directory
                    target_channels=self.n_channels,
                    augment_count=10  # Each real spectrum creates 10 training samples
                )
                
                if len(real_labels) > 0:
                    print(f"[ML] Loaded {len(real_labels)} augmented samples from real spectra")
                    print(f"[ML] Real labels: {set(real_labels)}")
            except Exception as e:
                print(f"[ML] Real spectra loading failed (non-critical): {e}")
                real_spectra_matrix = None
                real_labels = []
        
        # Combine synthetic and real spectra
        if real_spectra_matrix is not None and len(real_labels) > 0:
            # Append real spectra to synthetic
            spectra_matrix = np.vstack([spectra_matrix[:sample_idx], real_spectra_matrix])
            labels.extend(real_labels)
            print(f"[ML] Combined training set: {sample_idx} synthetic + {len(real_labels)} real = {len(labels)} total")
        else:
            # Trim synthetic matrix to actual size
            spectra_matrix = spectra_matrix[:sample_idx]
        
        # Create SampleSet with 2D matrix spectra
        train_ss = SampleSet()
        train_ss.spectra = pd.DataFrame(spectra_matrix)
        train_ss.spectra_type = 3  # Gross (supported by MLPClassifier)
        train_ss.spectra_state = 1  # Counts
        
        # Create sources with 3-level MultiIndex: ('Category', 'Isotope', 'Seed')
        unique_isotopes = list(set(labels))
        sources_data = {}
        for iso in unique_isotopes:
            # One-hot encoding
            col_key = ('Radionuclide', iso, '')
            sources_data[col_key] = [1.0 if label == iso else 0.0 for label in labels]
        
        sources_df = pd.DataFrame(sources_data)
        sources_df.columns = pd.MultiIndex.from_tuples(
            sources_df.columns,
            names=SampleSet.SOURCES_MULTI_INDEX_NAMES
        )
        train_ss.sources = sources_df
        
        # Train model with increased epochs for better convergence
        try:
            self.model = MLPClassifier()
            # Increased epochs from 25 to 50 for better training with real data
            self.model.fit(train_ss, epochs=50, target_level='Isotope', verbose=False)
            self.is_trained = True
            print(f"[ML] Training complete. Model ready with {len(unique_isotopes)} isotopes.")
        except Exception as e:
            print(f"[ML] Training failed: {e}")
            self.is_trained = False
            raise
    
    def identify(self, counts: List[int], top_k: int = 5) -> List[Dict]:
        """
        Identify isotopes using ML model.
        
        Args:
            counts: Spectrum counts array
            top_k: Number of top predictions to return
            
        Returns:
            List of predictions with isotope name and confidence
        """
        if not HAS_RIID:
            raise ImportError("PyRIID not installed")
            
        # Lazy load model
        if not self.is_trained:
            self.lazy_train()
        
        # Prepare spectrum array
        spectrum_array = np.array(counts, dtype=float)
        
        # Resize spectrum to match training data if needed
        if len(spectrum_array) != self.n_channels:
            if len(spectrum_array) < self.n_channels:
                padded = np.zeros(self.n_channels)
                padded[:len(spectrum_array)] = spectrum_array
                spectrum_array = padded
            else:
                spectrum_array = spectrum_array[:self.n_channels]
        
        # Create test SampleSet with 2D matrix format (1 sample x n_channels)
        test_ss = SampleSet()
        test_ss.spectra = pd.DataFrame(spectrum_array.reshape(1, -1))
        test_ss.spectra_type = 3  # Gross
        test_ss.spectra_state = 1  # Counts
        
        # Get predictions (predict modifies in-place)
        try:
            self.model.predict(test_ss)
            
            # Use prediction_probas for probability values
            probas = test_ss.prediction_probas
            
            results = []
            if probas is not None and not probas.empty:
                for col in probas.columns:
                    # Extract isotope name from multi-index column
                    if isinstance(col, tuple):
                        isotope_name = col[1] if len(col) > 1 else str(col)
                    else:
                        isotope_name = str(col)
                    
                    prob = float(probas[col].iloc[0])
                    conf_pct = round(prob * 100, 2)
                    
                    if conf_pct > 1.0:  # Only return meaningful predictions
                        results.append({
                            'isotope': isotope_name,
                            'confidence': conf_pct,
                            'method': 'ML (PyRIID)'
                        })
                
                # Sort by confidence and take top_k
                results.sort(key=lambda x: x['confidence'], reverse=True)
                results = results[:top_k]
            
            return results
        except Exception as e:
            print(f"[ML] Prediction error: {e}")
            return []
    
    def export_model(self, output_path: str, format: str = 'onnx') -> dict:
        """
        Export trained model to ONNX or TFLite format for deployment.
        
        Args:
            output_path: Path to save the exported model
            format: 'onnx' or 'tflite'
        
        Returns:
            dict with export status and metadata
        """
        if not self.is_trained:
            self.lazy_train()
        
        if self.model is None:
            return {'success': False, 'error': 'Model not trained'}
        
        try:
            if format.lower() == 'onnx':
                return self._export_onnx(output_path)
            elif format.lower() == 'tflite':
                return self._export_tflite(output_path)
            else:
                return {'success': False, 'error': f'Unknown format: {format}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _export_onnx(self, output_path: str) -> dict:
        """Export to ONNX format."""
        try:
            import tf2onnx
            import tensorflow as tf
            
            # Get the underlying Keras model from PyRIID
            keras_model = self.model.model
            
            # Convert to ONNX
            spec = (tf.TensorSpec((None, self.n_channels), tf.float32, name="input"),)
            model_proto, _ = tf2onnx.convert.from_keras(keras_model, input_signature=spec)
            
            # Save
            if not output_path.endswith('.onnx'):
                output_path += '.onnx'
            
            with open(output_path, 'wb') as f:
                f.write(model_proto.SerializeToString())
            
            return {
                'success': True,
                'format': 'onnx',
                'path': output_path,
                'input_shape': [self.n_channels],
                'output_classes': list(self.model.model.output_names) if hasattr(self.model.model, 'output_names') else [],
                'model_type': self.model_type
            }
        except ImportError:
            return {'success': False, 'error': 'tf2onnx not installed. Run: pip install tf2onnx'}
        except Exception as e:
            return {'success': False, 'error': f'ONNX export failed: {e}'}
    
    def _export_tflite(self, output_path: str) -> dict:
        """Export to TensorFlow Lite format."""
        try:
            import tensorflow as tf
            
            # Get the underlying Keras model
            keras_model = self.model.model
            
            # Convert to TFLite
            converter = tf.lite.TFLiteConverter.from_keras_model(keras_model)
            converter.optimizations = [tf.lite.Optimize.DEFAULT]
            tflite_model = converter.convert()
            
            # Save
            if not output_path.endswith('.tflite'):
                output_path += '.tflite'
            
            with open(output_path, 'wb') as f:
                f.write(tflite_model)
            
            return {
                'success': True,
                'format': 'tflite',
                'path': output_path,
                'input_shape': [self.n_channels],
                'size_bytes': len(tflite_model),
                'model_type': self.model_type
            }
        except Exception as e:
            return {'success': False, 'error': f'TFLite export failed: {e}'}

# Global instances (one per model type + detector combination)
_ml_identifiers = {}

def get_ml_identifier(model_type: str = "hobby", detector: str = "alphahound") -> Optional[MLIdentifier]:
    """Get or create ML identifier instance for specified model type and detector.
    
    Args:
        model_type: "hobby" for 35 common isotopes, "comprehensive" for 95+
        detector: Detector profile name ("alphahound", "radiacode_103", etc.)
        
    Returns:
        MLIdentifier instance (trained or None if PyRIID not available)
    """
    global _ml_identifiers
    
    if not HAS_RIID:
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
            print(f"[Hybrid] ML failed, using peak-matching only: {e}")
    
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
