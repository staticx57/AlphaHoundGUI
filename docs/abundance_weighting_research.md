# Decay Chain Abundance Weighting - Authoritative Sources

## Research Summary

**Primary Sources:**
- Lawrence Berkeley National Laboratory (Earth's crust abundance data)
- Britannica Encyclopedia of Science
- Nuclear regulatory data (NRC, IAEA)

## Earth's Crust Abundances (from authoritative sources)

### Elements
- **Thorium**: 10.5 ppm (0.000105 or 1.05×10⁻⁵)
- **Uranium**: 2.8-3 ppm (0.000003 or 3.0×10⁻⁶)  
- **Potassium**: 2.0-2.6% of crust mass

### Isotopic Composition
**Natural Uranium:**
- U-238: 99.274% (±0.00001%)
- U-235: 0.720% (±0.00001%)
- U-234: 0.0054%

**Natural Thorium:**
- Th-232: ~100% (essentially monoisotopic)

**Natural Potassium:**
- K-40: 0.0117% of all potassium

## Calculated Weights for Detection

### For Natural Sample Detection

**Relative Expected Activity in Natural Samples:**

1. **U-238 Chain**: 
   - Abundance: 2.98 ppm × 0.99274 = 2.96 ppm
   - Weight: **1.00** (baseline, most common in U sources)

2. **Th-232 Chain**:
   - Abundance: 10.5 ppm
   - Relative to U-238: 10.5 / 2.96 = **3.55**
   - Weight: **3.55** (Th is 3.5× more abundant than U in crust)

3. **U-235 Chain**:
   - Abundance: 2.98 ppm × 0.00720 = 0.021 ppm
   - Relative to U-238: 0.021 / 2.96 = **0.0072**
   - Weight: **0.0072** (U-235 should be penalized heavily in U sources)

4. **K-40**:
   - Abundance: 2.3% (avg) × 0.000117 = 0.027%
   - Much higher than U/Th, but different context
   - Weight: **100** (background radiation, extremely common)

## Application Strategy

### For Uranium-Bearing Samples (glass, ceramics, minerals):
- U-238 should strongly dominate
- U-235 should be barely detectable
- Th-232 should only appear if thorium is present

### For Thorium-Bearing Samples (mantles, lenses):
- Th-232 should strongly dominate
- U chains should not appear

### For Background Radiation:
- K-40 should be ubiquitous
- U-238 chain weak but present
- Th-232 chain weak but present
- U-235 chain very weak

## Weighting Function Design

```python
# For natural samples (not enriched/pure sources):
weighted_confidence = base_confidence * (1.0 + (abundance_weight - 1.0) * scaling_factor)

# Where:
# - base_confidence = percentage of indicators found
# - abundance_weight = relative crustal/isotopic abundance
# - scaling_factor = 0.5 (moderate weighting, avoids over-correction)
```

This ensures:
- U-238 (weight=0.993) gets slight boost
- U-235 (weight=0.0072) gets strong penalty
- Th-232 (weight=1.0 or 3.55 depending on context) neutral or boosted
- K-40 (weight=100) strongly boosted for background
