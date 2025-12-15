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


class MLIdentifier:
    """ML-based isotope identifier using PyRIID MLPClassifier.
    
    Uses authoritative gamma-ray energies from IAEA NDS, NNDC/ENSDF databases
    to generate synthetic training spectra for comprehensive isotope identification.
    
    TUNED FOR ALPHAHOUND AB+G DETECTOR:
    - 1024 channels @ 3 keV/channel (0-3069 keV range)
    - CsI(Tl) crystal: 10% FWHM at 662 keV
    - Energy-dependent resolution: FWHM = 0.10 * sqrt(662/E) * E
    """
    
    def __init__(self):
        self.model = None
        self.is_trained = False
        self.n_channels = 1024  # AlphaHound standard channel count
        self.keV_per_channel = 7.4  # AlphaHound actual calibration: ~7.4 keV/channel
        # AlphaHound CsI(Tl) resolution: 10% FWHM at 662 keV
        self.reference_fwhm_fraction = 0.10  # 10% at 662 keV
        self.reference_energy = 662.0  # keV
        
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
        
    def lazy_train(self):
        """Train model on synthetic data using authoritative isotope database."""
        if not HAS_RIID:
            raise ImportError("PyRIID not installed")
            
        if self.is_trained:
            return
            
        print("[ML] Training classifier on synthetic data (IAEA/NNDC energies)...")
        
        # Build isotope list from authoritative database
        # Filter to isotopes with gamma emissions (non-empty energy lists)
        isotope_data = {}
        
        if HAS_ISOTOPE_DB and ISOTOPE_DATABASE_ADVANCED:
            for isotope, energies in ISOTOPE_DATABASE_ADVANCED.items():
                if energies and len(energies) > 0:  # Has gamma emissions
                    isotope_data[isotope] = energies
        
        # Add Background if not present
        if 'Background' not in isotope_data:
            isotope_data['Background'] = []
            
        isotopes = list(isotope_data.keys())
        print(f"[ML] Training on {len(isotopes)} single isotopes from authoritative sources")
        
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
        base_samples = 15  # Base samples per isotope
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
                for energy_keV in energies:
                    channel = self.energy_to_channel(energy_keV)
                    
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
                        channel = self.energy_to_channel(energy_keV)
                        
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
                
                sample_idx += 1
        
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
        
        # Train model
        try:
            self.model = MLPClassifier()
            self.model.fit(train_ss, epochs=25, target_level='Isotope', verbose=False)
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

# Global instance (singleton pattern)
_ml_identifier = None

def get_ml_identifier() -> Optional[MLIdentifier]:
    """Get or create the global ML identifier instance."""
    global _ml_identifier
    
    if not HAS_RIID:
        return None
        
    if _ml_identifier is None:
        _ml_identifier = MLIdentifier()
    
    return _ml_identifier
