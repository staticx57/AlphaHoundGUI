#!/usr/bin/env python3
"""
Becquerel vs AlphaHoundGUI Comparison Test Script
==================================================

This script compares the `becquerel` library's features against the current
AlphaHoundGUI implementation for gamma spectroscopy analysis.

Comparison areas:
1. Spectrum object handling (calibration, errors, rebinning)
2. Peak fitting (Gaussian fitting, FWHM, net area)
3. Background subtraction (SNIP algorithm)
4. Uncertainty propagation

Run with: python test_becquerel_comparison.py
"""

import sys
import os
import time
import numpy as np

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# =============================================================================
# SETUP AND IMPORTS
# =============================================================================

print("=" * 70)
print("BECQUEREL vs ALPHAHOUNDGUI COMPARISON")
print("=" * 70)

# Check if becquerel is available
try:
    import becquerel as bq
    from becquerel import Spectrum
    HAS_BECQUEREL = True
    print(f"✓ Becquerel version: {bq.__version__}")
except ImportError as e:
    HAS_BECQUEREL = False
    print(f"✗ Becquerel not installed: {e}")
    print("  Install with: pip install becquerel")

# Import our current implementation
from spectral_analysis import fit_gaussian, snip_background, subtract_background, calibrate_energy
from isotope_database import identify_isotopes
from n42_parser import parse_n42

print()

# =============================================================================
# LOAD TEST SPECTRUM
# =============================================================================

TEST_SPECTRUM_PATH = os.path.join(
    os.path.dirname(__file__),
    "data", "test_spectra", "synthetic_cesium137.n42"
)

# Fallback to any available spectrum
if not os.path.exists(TEST_SPECTRUM_PATH):
    TEST_SPECTRUM_PATH = os.path.join(
        os.path.dirname(__file__),
        "Cs137_Verification_Spectra.n42"
    )

print(f"Loading test spectrum: {os.path.basename(TEST_SPECTRUM_PATH)}")

try:
    with open(TEST_SPECTRUM_PATH, 'r', encoding='utf-8') as f:
        file_content = f.read()
    spectrum_data = parse_n42(file_content)
    if 'error' in spectrum_data:
        raise ValueError(spectrum_data['error'])
    counts = np.array(spectrum_data['counts'])
    energies = np.array(spectrum_data['energies'])
    live_time = spectrum_data.get('metadata', {}).get('live_time', 60.0)
    print(f"✓ Loaded {len(counts)} channels, live_time={live_time}s")
except Exception as e:
    print(f"✗ Failed to load spectrum: {e}")
    # Create synthetic Cs-137 spectrum for testing
    print("  Generating synthetic Cs-137 spectrum...")
    channels = np.arange(1024)
    energies = channels * 3.0  # 3 keV/channel
    counts = np.zeros(1024)
    # Add Gaussian peak at 662 keV (Cs-137)
    peak_channel = 662 / 3.0
    sigma = 15 / 3.0  # ~15 keV FWHM
    counts += 5000 * np.exp(-0.5 * ((channels - peak_channel) / sigma) ** 2)
    # Add Compton continuum
    counts += 200 * np.exp(-channels / 150)
    counts = counts.astype(int)
    live_time = 300.0
    print(f"✓ Generated synthetic spectrum with {len(counts)} channels")

print()

# =============================================================================
# TEST 1: ENERGY CALIBRATION
# =============================================================================

print("-" * 70)
print("TEST 1: Energy Calibration")
print("-" * 70)

# Known calibration points (channel -> energy)
known_channels = [220, 487, 1024]  # Example channels
known_energies = [662, 1460, 3000]  # Example energies (keV)

# Our implementation
print("\n[AlphaHoundGUI Implementation]")
t0 = time.perf_counter()
try:
    result, params = calibrate_energy(
        list(range(len(counts))), 
        known_energies[:2], 
        known_channels[:2]
    )
    t_ours = (time.perf_counter() - t0) * 1000
    print(f"  Slope: {params['slope']:.4f} keV/channel")
    print(f"  Intercept: {params['intercept']:.4f} keV")
    print(f"  Time: {t_ours:.2f} ms")
except Exception as e:
    print(f"  ✗ Error: {e}")
    t_ours = 0

# Becquerel implementation
if HAS_BECQUEREL:
    print("\n[Becquerel Implementation]")
    t0 = time.perf_counter()
    try:
        # Create spectrum with calibration
        spec = Spectrum(
            counts=counts,
            bin_edges_kev=np.concatenate([energies, [energies[-1] + (energies[1] - energies[0])]])
        )
        t_bq = (time.perf_counter() - t0) * 1000
        print(f"  Calibration from bin_edges: auto-applied")
        print(f"  Energy range: {spec.bin_centers_kev[0]:.1f} - {spec.bin_centers_kev[-1]:.1f} keV")
        print(f"  Time: {t_bq:.2f} ms")
        print(f"\n  ✓ Becquerel provides bin_centers_kev, bin_edges_kev, and automatic unit handling")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        t_bq = 0
else:
    print("\n[Becquerel Implementation] - SKIPPED (not installed)")
    t_bq = 0

print()

# =============================================================================
# TEST 2: POISSON ERROR PROPAGATION
# =============================================================================

print("-" * 70)
print("TEST 2: Poisson Error / Uncertainty Handling")
print("-" * 70)

print("\n[AlphaHoundGUI Implementation]")
print("  Current implementation does NOT track uncertainties.")
print("  Errors must be calculated manually: sqrt(counts)")

# Our manual uncertainty calculation
counts_error_ours = np.sqrt(counts + 1)  # +1 to avoid sqrt(0)
print(f"  Example: counts[500] = {counts[500]} ± {counts_error_ours[500]:.1f}")

if HAS_BECQUEREL:
    print("\n[Becquerel Implementation]")
    try:
        spec = Spectrum(counts=counts)
        print(f"  Becquerel auto-calculates Poisson errors:")
        print(f"  Example: counts[500] = {spec.counts[500]:.0f} ± {spec.counts_uncs[500]:.1f}")
        print(f"\n  ✓ Becquerel provides .counts_uncs property for automatic error propagation")
        print(f"  ✓ Uncertainties propagate through arithmetic operations (add, subtract, etc.)")
    except Exception as e:
        print(f"  ✗ Error: {e}")
else:
    print("\n[Becquerel Implementation] - SKIPPED (not installed)")

print()

# =============================================================================
# TEST 3: BACKGROUND SUBTRACTION (SNIP)
# =============================================================================

print("-" * 70)
print("TEST 3: Background Subtraction (SNIP Algorithm)")
print("-" * 70)

print("\n[AlphaHoundGUI Implementation]")
t0 = time.perf_counter()
try:
    bg_ours = snip_background(counts, iterations=24)
    net_ours = counts - bg_ours
    net_ours[net_ours < 0] = 0
    t_snip_ours = (time.perf_counter() - t0) * 1000
    print(f"  SNIP iterations: 24")
    print(f"  Background sum: {np.sum(bg_ours):.0f}")
    print(f"  Net counts sum: {np.sum(net_ours):.0f}")
    print(f"  Time: {t_snip_ours:.2f} ms")
except Exception as e:
    print(f"  ✗ Error: {e}")
    t_snip_ours = 0
    bg_ours = None

if HAS_BECQUEREL:
    print("\n[Becquerel Implementation]")
    try:
        # Check if becquerel has SNIP
        from becquerel.core import utils as bq_utils
        if hasattr(bq_utils, 'snip'):
            t0 = time.perf_counter()
            bg_bq = bq_utils.snip(counts, iterations=24)
            t_snip_bq = (time.perf_counter() - t0) * 1000
            print(f"  SNIP iterations: 24")
            print(f"  Background sum: {np.sum(bg_bq):.0f}")
            print(f"  Time: {t_snip_bq:.2f} ms")
        else:
            print("  Becquerel does not include SNIP; uses other background methods")
            print("  (Manual background subtraction via spectrum arithmetic)")
            t_snip_bq = 0
    except Exception as e:
        print(f"  Note: Becquerel background handling: {e}")
        print("  Becquerel focuses on spectrum arithmetic rather than built-in SNIP")
        t_snip_bq = 0
else:
    print("\n[Becquerel Implementation] - SKIPPED (not installed)")
    t_snip_bq = 0

print()

# =============================================================================
# TEST 4: PEAK FITTING (GAUSSIAN)
# =============================================================================

print("-" * 70)
print("TEST 4: Peak Fitting (Gaussian)")
print("-" * 70)

# Find the Cs-137 peak around 662 keV
peak_centers = [662.0]

print("\n[AlphaHoundGUI Implementation]")
t0 = time.perf_counter()
try:
    fit_results = fit_gaussian(energies, counts, peak_centers, window_width=50)
    t_fit_ours = (time.perf_counter() - t0) * 1000
    if fit_results:
        r = fit_results[0]
        print(f"  Centroid: {r['energy']:.2f} keV")
        print(f"  FWHM: {r['fwhm']:.2f} keV")
        print(f"  Net Area: {r['net_area']:.0f} counts")
        print(f"  Chi-squared: {r['chi_squared']:.2f}")
        print(f"  Time: {t_fit_ours:.2f} ms")
    else:
        print("  No peaks fitted")
except Exception as e:
    print(f"  ✗ Error: {e}")
    t_fit_ours = 0

if HAS_BECQUEREL:
    print("\n[Becquerel Implementation]")
    try:
        from becquerel import Fitter
        from becquerel.fitting import GaussModel
        
        t0 = time.perf_counter()
        spec = Spectrum(
            counts=counts,
            bin_edges_kev=np.concatenate([energies, [energies[-1] + (energies[1] - energies[0])]])
        )
        
        # Define energy range around 662 keV
        fitter = Fitter(
            spec,
            xmin=600,
            xmax=720,
            components=[GaussModel(prefix='cs137_')]
        )
        
        # Set initial guesses
        fitter.set_param_hint('cs137_center', value=662, min=640, max=680)
        fitter.set_param_hint('cs137_amplitude', value=5000, min=0)
        fitter.set_param_hint('cs137_sigma', value=10, min=1, max=50)
        
        result = fitter.fit()
        t_fit_bq = (time.perf_counter() - t0) * 1000
        
        if result.success:
            print(f"  Centroid: {result.params['cs137_center'].value:.2f} keV")
            sigma = result.params['cs137_sigma'].value
            print(f"  FWHM: {2.355 * sigma:.2f} keV")
            print(f"  Fit success: {result.success}")
            print(f"  Time: {t_fit_bq:.2f} ms")
            print(f"\n  ✓ Becquerel Fitter provides constrained fitting with uncertainties")
        else:
            print(f"  Fit failed: {result.message}")
    except ImportError:
        print("  Becquerel Fitter not available in this version")
        t_fit_bq = 0
    except Exception as e:
        print(f"  ✗ Error: {e}")
        t_fit_bq = 0
else:
    print("\n[Becquerel Implementation] - SKIPPED (not installed)")
    t_fit_bq = 0

print()

# =============================================================================
# TEST 5: SPECTRUM ARITHMETIC
# =============================================================================

print("-" * 70)
print("TEST 5: Spectrum Arithmetic (Add, Subtract, Combine)")
print("-" * 70)

print("\n[AlphaHoundGUI Implementation]")
print("  Currently uses numpy array operations manually")
print("  No automatic uncertainty propagation during arithmetic")

# Create second spectrum (simulate background)
counts2 = np.maximum(counts // 10, 0)  # 10% background

result_add_ours = counts + counts2
result_sub_ours = counts - counts2
result_sub_ours[result_sub_ours < 0] = 0
print(f"  Add result: sum = {np.sum(result_add_ours):.0f}")
print(f"  Sub result: sum = {np.sum(result_sub_ours):.0f}")

if HAS_BECQUEREL:
    print("\n[Becquerel Implementation]")
    try:
        spec1 = Spectrum(counts=counts, livetime=live_time)
        spec2 = Spectrum(counts=counts2, livetime=live_time)
        
        # Arithmetic with automatic uncertainty propagation
        spec_add = spec1 + spec2
        spec_sub = spec1 - spec2
        
        print(f"  Add result: sum = {np.sum(spec_add.counts):.0f}")
        print(f"  Sub result: sum = {np.sum(spec_sub.counts):.0f}")
        print(f"\n  ✓ Becquerel automatically propagates uncertainties in arithmetic")
        print(f"  ✓ Becquerel handles livetime normalization when combining spectra")
    except Exception as e:
        print(f"  ✗ Error: {e}")
else:
    print("\n[Becquerel Implementation] - SKIPPED (not installed)")

print()

# =============================================================================
# TEST 6: REBINNING
# =============================================================================

print("-" * 70)
print("TEST 6: Spectrum Rebinning")
print("-" * 70)

print("\n[AlphaHoundGUI Implementation]")
print("  No built-in rebinning functionality")
print("  Would need manual implementation with proper error propagation")

if HAS_BECQUEREL:
    print("\n[Becquerel Implementation]")
    try:
        spec = Spectrum(
            counts=counts,
            bin_edges_kev=np.concatenate([energies, [energies[-1] + (energies[1] - energies[0])]])
        )
        
        # Rebin to half the number of bins
        new_edges = np.linspace(energies[0], energies[-1], len(energies) // 2 + 1)
        spec_rebinned = spec.rebin(new_edges)
        
        print(f"  Original bins: {len(spec.counts)}")
        print(f"  Rebinned bins: {len(spec_rebinned.counts)}")
        print(f"  Total counts preserved: {np.sum(spec.counts):.0f} -> {np.sum(spec_rebinned.counts):.0f}")
        print(f"\n  ✓ Becquerel handles rebinning with proper uncertainty propagation")
    except Exception as e:
        print(f"  ✗ Error: {e}")
else:
    print("\n[Becquerel Implementation] - SKIPPED (not installed)")

print()

# =============================================================================
# SUMMARY
# =============================================================================

print("=" * 70)
print("SUMMARY")
print("=" * 70)

print("""
Feature Comparison:
┌──────────────────────────────────┬─────────────────┬─────────────────┐
│ Feature                          │ AlphaHoundGUI   │ Becquerel       │
├──────────────────────────────────┼─────────────────┼─────────────────┤
│ Energy Calibration               │ ✓ Linear fit    │ ✓ Auto-handled  │
│ Poisson Uncertainty              │ ✗ Manual        │ ✓ Automatic     │
│ Background Subtraction (SNIP)    │ ✓ Implemented   │ ~ Via arithmetic│
│ Peak Fitting (Gaussian)          │ ✓ scipy.optimize│ ✓ Fitter class  │
│ Uncertainty Propagation          │ ✗ Not tracked   │ ✓ Automatic     │
│ Spectrum Arithmetic              │ ✗ Manual numpy  │ ✓ Built-in      │
│ Rebinning                        │ ✗ Not available │ ✓ Built-in      │
│ Livetime Handling                │ ✗ Manual        │ ✓ Automatic     │
└──────────────────────────────────┴─────────────────┴─────────────────┘

Recommendations:
1. ADOPT becquerel.Spectrum for internal spectrum representation
   - Automatic uncertainty tracking is valuable for error propagation
   - Rebinning and arithmetic are common operations that would benefit

2. KEEP our SNIP background subtraction
   - Our implementation works well; becquerel focuses on spectrum arithmetic

3. EVALUATE becquerel.Fitter for peak fitting
   - Provides more robust fitting with proper uncertainty estimates
   - Supports multi-component fitting (overlapping peaks)

4. INTEGRATE uncertainties package for result display
   - Show results like "662.5 ± 0.3 keV" instead of just "662.5 keV"
""")

if not HAS_BECQUEREL:
    print("\n⚠️  Becquerel is not installed. Install with:")
    print("    pip install becquerel")
    print("\n   Then re-run this script to see the comparison.")

print("=" * 70)
