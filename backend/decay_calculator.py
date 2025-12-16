
"""
Decay Calculator with Custom Bateman Solver
"""
import math
import numpy as np
from typing import List, Dict, Tuple, Optional

# === NUCLEAR DATA ===
# Half-lives in seconds
d = 86400
y = 365.25 * d
m = 60 * 1000000000 # dummy if needed? No, standard time units.
h = 3600
min = 60

HALF_LIVES = {
    # U-238 Chain
    "U-238": 4.468e9 * y,
    "Th-234": 24.10 * d,
    "Pa-234m": 1.17 * min,
    "U-234": 2.455e5 * y,
    "Th-230": 7.538e4 * y,
    "Ra-226": 1600 * y,
    "Rn-222": 3.8235 * d,
    "Po-218": 3.10 * min,
    "Pb-214": 26.8 * min,
    "Bi-214": 19.9 * min,
    "Po-214": 164.3e-6,
    "Pb-210": 22.3 * y,
    
    # Th-232 Chain
    "Th-232": 1.405e10 * y,
    "Ra-228": 5.75 * y,
    "Ac-228": 6.15 * h,
    "Th-228": 1.9116 * y,
    "Ra-224": 3.6319 * d,
    "Rn-220": 55.6 * 1, # seconds
    "Po-216": 0.145 * 1, # seconds
    "Pb-212": 10.64 * h,
    "Bi-212": 60.55 * min,
    "Tl-208": 3.053 * min,
    
    # Simple pairs
    "Cs-137": 30.17 * y,
    "Ba-137m": 2.55 * min,
}

# Simplified Linear Chains (Parent -> Child -> Grandchild)
# Ignoring minor branches for MVP visualization
CHAINS = {
    "U-238 Sequence": ["U-238", "Th-234", "Pa-234m", "U-234", "Th-230", "Ra-226", "Rn-222", "Po-218", "Pb-214", "Bi-214", "Pb-210"],
    "Th-232 Sequence": ["Th-232", "Ra-228", "Ac-228", "Th-228", "Ra-224", "Rn-220", "Po-216", "Pb-212", "Bi-212", "Tl-208"]
}

# Try to import curie
try:
    import curie
    HAS_CURIE = True
except ImportError:
    HAS_CURIE = False

def get_decay_constant(isotope: str) -> float:
    """Return decay constant lambda = ln(2) / half_life."""
    if HAS_CURIE:
        try:
            # Curie uses simple strings like 'U-238'
            iso = curie.Isotope(isotope)
            if iso.half_life > 0:
                return math.log(2) / iso.half_life
        except:
            pass
            
    # Fallback to internal DB
    hl = HALF_LIVES.get(isotope)
    if not hl:
        return 0.0
    return math.log(2) / hl


def bateman_solution(
    chain_isotopes: List[str], 
    initial_activity: float, 
    time_points_s: List[float]
) -> Dict[str, List[float]]:
    """
    Solve Bateman equations for a linear decay chain A -> B -> C -> ...
    Returns activity of each isotope at given time points.
    
    Assumes N_1(0) based on initial_activity, and N_i(0) = 0 for i > 1.
    """
    n_iso = len(chain_isotopes)
    lambdas = [get_decay_constant(iso) for iso in chain_isotopes]
    
    # If starting activity A_1(0) is given:
    # A = lambda * N  => N_1(0) = A_1(0) / lambda_1
    if lambdas[0] == 0:
        return {} # Stable parent?
        
    N0 = initial_activity / lambdas[0]
    
    results = {iso: [] for iso in chain_isotopes}
    
    for t in time_points_s:
        # Calculate N_k(t) for each isotope k
        for k in range(n_iso):
            lambda_k = lambdas[k]
            
            # Summation term for N_k(t)
            sum_val = 0.0
            for i in range(k + 1):
                lambda_i = lambdas[i]
                
                # Product term (coefficients)
                numerator = 1.0
                for j in range(k + 1):
                    numerator *= lambdas[j] # Product of all lambdas up to k (actually only n-1 usually? Bateman is N1(0) * Prod(lambda_1..n-1))
                    
                # Standard Bateman coefficient formulation:
                # N_n = N_1(0) * (Prod_{i=1}^{n-1} lambda_i) * Sum_{i=1}^n ( e^{-lambda_i t} / Prod_{j=1, j!=i}^n (lambda_j - lambda_i) )
                
                # Calculate denominator product
                denominator = 1.0
                for j in range(k + 1):
                    if i != j:
                        # Handle very close half-lives (singularity) roughly
                        diff = lambdas[j] - lambdas[i]
                        if abs(diff) < 1e-20: diff = 1e-20 
                        denominator *= diff
                
                term = math.exp(-lambda_i * t) / denominator
                sum_val += term
            
            # The pre-factor: N1(0) * Prod(lambda_0 ... lambda_{k-1})
            # Note: Indices 0 to k-1
            pre_factor = N0
            for j in range(k):
                pre_factor *= lambdas[j]
                
            N_k = pre_factor * sum_val
            
            # Activity A_k = lambda_k * N_k
            A_k = lambda_k * N_k
            
            # Store result (handle potential precision errors near zero)
            results[chain_isotopes[k]].append(max(0, A_k))
            
    return results

def predict_decay_chain(
    parent_isotope: str,
    initial_activity_bq: float,
    duration_days: float,
    steps: int = 50
) -> Optional[Dict]:
    """
    Predict activity evolution for a standard chain.
    """
    # Find matching chain
    chain = None
    if parent_isotope in ["U-238", "Uranium"]:
        chain = CHAINS["U-238 Sequence"]
    elif parent_isotope in ["Th-232", "Thorium"]:
        chain = CHAINS["Th-232 Sequence"]
    else:
        # Check if user passed a known chain member and back-track? 
        # For now only support starting from parent
        return None
        
    duration_s = duration_days * 86400
    times = np.linspace(0, duration_s, steps).tolist()
    
    activities = bateman_solution(chain, initial_activity_bq, times)
    
    return {
        "isotopes": chain,
        "time_points_days": [t/86400 for t in times],
        "activities": activities
    }
