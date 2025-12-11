"""
Machine Learning Isotope Identification using PyRIID
"""
import numpy as np
from typing import List, Dict, Optional
import logging

# Try importing PyRIID with proper error handling
try:
    from riid.data.synthetic import SeedMixer, GammaSpectrum
    from riid.data import get_dummy_seeds
    from riid.models import MLPClassifier as RIIDMLPClassifier
    HAS_RIID = True
    logging.info("[ML] PyRIID successfully imported")
except ImportError as e:
    HAS_RIID = False
    logging.warning(f"[ML] PyRIID not available: {e}")


class MLIdentifier:
    """ML-based isotope identifier using PyRIID."""
    
    def __init__(self):
        self.model = None
        self.is_trained = False
        self.labels = []
        
    def lazy_train(self):
        """Train model on synthetic data (lazy initialization)."""
        if not HAS_RIID:
            raise ImportError("PyRIID not installed. Please install with: pip install git+https://github.com/sandialabs/pyriid.git@main")
            
        if self.is_trained:
            return
            
        logging.info("[ML] Training PyRIID classifier...")
        
        try:
            # Get dummy seeds (pre-configured isotope templates)
            seeds = get_dummy_seeds()
            
            # Extract seed names for labels
            self.labels = list(seeds.keys())
            logging.info(f"[ML] Training on {len(self.labels)} isotopes: {', '.join(self.labels[:5])}...")
            
            # Create synthetic data mixer
            mixer = SeedMixer(
                seeds=seeds,
                bg_cps=300,  # Background counts per second
                live_time=600  # Simulated acquisition time
            )
            
            # Generate training samples (100 samples per isotope)
            n_samples = len(self.labels) * 100
            logging.info(f"[ML] Generating {n_samples} synthetic spectra...")
            
            spectra_list, labels_list = [], []
            for _ in range(n_samples):
                spec, label = mixer.generate(1)
                spectra_list.append(spec[0])
                labels_list.append(label[0])
            
            spectra = np.array(spectra_list)
            labels = np.array(labels_list)
            
            # Train MLP classifier
            self.model = RIIDMLPClassifier(hidden_layers=(128, 64))
            logging.info("[ML] Training model...")
            self.model.fit(spectra, labels)
            
            self.is_trained = True
            logging.info("[ML] Training complete!")
            
        except Exception as e:
            logging.error(f"[ML] Training failed: {e}")
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
            
        # Lazy training
        if not self.is_trained:
            self.lazy_train()
        
        # Prepare input
        spectrum = np.array(counts, dtype=float).reshape(1, -1)
        
        # Normalize if needed (PyRIID expects specific format)
        if spectrum.sum() > 0:
            spectrum = spectrum / spectrum.sum() * 10000  # Normalize to 10k counts
        
        # Get predictions
        predictions = self.model.predict_proba(spectrum)[0]
        
        # Get top K results
        top_indices = np.argsort(predictions)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            confidence = float(predictions[idx]) * 100
            
            if confidence > 0.1:  # Only meaningful predictions
                results.append({
                    'isotope': self.labels[idx] if idx < len(self.labels) else f"Unknown_{idx}",
                    'confidence': confidence,
                    'method': 'ML (PyRIID)'
                })
        
        return results


# Global singleton instance
_ml_identifier = None


def get_ml_identifier() -> Optional[MLIdentifier]:
    """Get or create the global ML identifier instance."""
    global _ml_identifier
    
    if not HAS_RIID:
        return None
        
    if _ml_identifier is None:
        _ml_identifier = MLIdentifier()
    
    return _ml_identifier
