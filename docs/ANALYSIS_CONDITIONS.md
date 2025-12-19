# Analysis Pipeline Conditions

This document describes when and how various analysis enhancements are applied.

## SNIP Background Removal

**Location:** `peak_detection_enhanced.py` → `detect_peaks_enhanced()`

**When Applied:**
- `apply_snip=True` (default) AND
- Max peak counts > 10,000

**What It Does:**
- Removes Compton continuum using SNIP (Sensitive Nonlinear Iterative Peak) algorithm
- Makes true gamma peaks stand out at their correct energies
- Applied BEFORE CWT peak detection

**Skipped For:**
- Quick acquisitions (low counts)
- When `apply_snip=False` passed by caller

---

## Dynamic Energy Tolerance

**Location:** `chain_detection_enhanced.py` → `match_peaks_to_chain()`

**When Applied:**
- High-count spectra: max peak counts > 10,000 → uses **60 keV** tolerance
- Normal spectra: uses default **15-30 keV** tolerance (from settings)

**Why:**
- Scintillator detectors (CsI, NaI) have ~8-15% energy resolution
- At 600 keV, this is ~50-90 keV FWHM
- High-count spectra have overlapping peaks that shift detected positions
- Wider tolerance compensates for peak position uncertainty

---

## Thresholds Summary

| Condition | Threshold | Effect |
|-----------|-----------|--------|
| SNIP applied | max counts > 10,000 | Background removal before peak finding |
| Wide tolerance | max counts > 10,000 | 60 keV chain matching tolerance |
| Chain detection | min 1-2 isotopes | Required for chain to appear |
| Isotope confidence | ≥ 30% | Below this, isotope filtered out |
| Chain confidence | ≥ 1% (uploads) | Minimum for chain to show |

---

## Files Modified

- `peak_detection_enhanced.py` - SNIP integration
- `chain_detection_enhanced.py` - Dynamic tolerance
- `core.py` - Settings thresholds
