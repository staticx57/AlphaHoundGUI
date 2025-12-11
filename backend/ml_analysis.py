"""
ML-based isotope identification using PyRIID.
Note: This module requires riid to be installed.
"""
import numpy as np
from typing import List, Dict, Optional

# Try to import riid with proper error handling
try:
    from riid.data.synthetic import get_dummy_seeds
    from riid.data.sampleset import SampleSet
    from riid.models import MLPClassifier
    HAS_RIID = True
    print("[ML] PyRIID successfully imported")
except ImportError as e:
    HAS_RIID = False
    print(f"[WARNING] PyRIID not available. ML identification disabled. Error: {e}")
except Exception as e:
    HAS_RIID = False
    print(f"[ERROR] Unexpected error importing PyRIID: {e}")

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
            
        print("[ML] Training classifier on dummy seed data...")
        
        # Use PyRIID's dummy seeds directly - they're already a SampleSet
        seeds = get_dummy_seeds()
        
        # Train a simple MLP classifier with defaults (simpler, more compatible)
        self.model = MLPClassifier()
        try:
            self.model.fit(seeds, epochs=5, verbose=False)
            self.is_trained = True
            print(f"[ML] Training complete. Model ready.")
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
        
        # Prepare input as a SampleSet
        import pandas as pd
        spectrum_array = np.array(counts, dtype=float)
        
        # Create a minimal SampleSet with the spectrum
        # SampleSet expects specific columns
        test_data = pd.DataFrame({
            'live_time': [300.0],  # Default live time in seconds
            'total_counts': [np.sum(spectrum_array)]
        })
        test_data['counts'] = [spectrum_array]
        
        test_ss = SampleSet()
        test_ss.spectra = test_data
        test_ss.n_samples = 1
        test_ss.n_channels = len(spectrum_array)
        
        # Get predictions
        try:
            predictions_ss = self.model.predict(test_ss)
            
            # Extract prediction probabilities
            # The predictions are in the SampleSet's prediction columns
            pred_df = predictions_ss.get_predictions()
            
            results = []
            if not pred_df.empty and len(pred_df) > 0:
                # Get all prediction columns (exclude metadata)
                pred_cols = [col for col in pred_df.columns if not col.startswith('_')]
                
                if pred_cols:
                    # Get the first row's predictions
                    probs = pred_df.iloc[0][pred_cols]
                    # Sort and get top K
                    top_preds = probs.nlargest(top_k)
                    
                    for isotope_name, confidence in top_preds.items():
                        conf_pct = float(confidence) * 100
                        if conf_pct > 1.0:  # Only return meaningful predictions
                            results.append({
                                'isotope': isotope_name,
                                'confidence': conf_pct,
                                'method': 'ML (PyRIID)'
                            })
            
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
