"""
ML-based isotope identification using PyRIID.
Note: This module requires riid to be installed.
"""
import numpy as np
from typing import List, Dict, Optional

# Try to import riid with proper error handling
try:
    from riid.data.synthetic import SeedMixer, GrossCountPlus Spectrum, get_dummy_seeds
    from riid.models import MLPClassifier
    HAS_RIID = True
except ImportError:
    HAS_RIID = False
    print("[WARNING] PyRIID not available. ML identification disabled.")

class MLIdentifier:
    """Simple ML-based identifier using PyRIID."""
    
    def __init__(self):
        self.model = None
        self.is_trained = False
        
    def lazy_train(self):
        """Train a simple model on synthetic data if not already trained."""
        if not HAS_RIID:
            raise ImportError("PyRIID not installed")
            
        if self.is_trained:
            return
            
        print("[ML] Training classifier on synthetic data...")
        
        # Use PyRIID's built-in synthetic data generation
        # This creates realistic spectra with Poisson noise
        seeds = get_dummy_seeds()
        mixer = SeedMixer(seeds=seeds, bg_cps=300, long_bg_live_time=600)
        
        # Generate training samples (simplified for speed)
        n_samples = 100
        spectra, labels = mixer.generate(n_samples)
        
        # Train a simple MLP classifier
        self.model = MLPClassifier(hidden_layers=(128,))
        self.model.fit(spectra, labels)
        self.is_trained = True
        
        print(f"[ML] Training complete. Model ready.")
    
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
        
        # Prepare input (PyRIID expects specific format)
        spectrum = np.array(counts, dtype=float).reshape(1, -1)
        
        # Get predictions
        predictions = self.model.predict_proba(spectrum)[0]
        
        # Get top K isotopes
        top_indices = np.argsort(predictions)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            isotope_name = self.model.get_labels()[idx]
            confidence = float(predictions[idx]) * 100
            
            if confidence > 1.0:  # Only return meaningful predictions
                results.append({
                    'isotope': isotope_name,
                    'confidence': confidence,
                    'method': 'ML (PyRIID)'
                })
        
        return results

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
