# ML Isotope Identification Improvement Plan

> **Status**: Planning  
> **Created**: 2024-12-22  
> **Goal**: Improve PyRIID ML model accuracy from WIP to production-ready

---

## Current State

| Component | Status | Notes |
|-----------|--------|-------|
| Peak Matching (Legacy) | ✅ Working | U-238 #2, U-235 suppressed, 20+ peaks detected |
| ML Identification | ❌ WIP | Wrong predictions (Sb-125), uranium not in top 10 |
| Training Data | Synthetic only | IAEA gamma energies, but no real spectra |
| Detector Support | AlphaHound | Radiacode not yet tuned |

---

## 📁 Public Gamma Spectra Datasets for Training

### 1. IAEA International Database (IDB) ⭐ RECOMMENDED
- **URL**: https://www-nds.iaea.org/ids/
- **Content**: Reference gamma spectra for uranium and plutonium isotopic composition
- **Format**: ZIP download (~105 MB), includes metadata
- **License**: CC BY 4.0 (free with attribution)
- **Use Case**: High-quality labeled U/Pu spectra for training
- **Download**: `IDB-v2024-01.zip`

### 2. OpenGammaProject Spectrum Database ⭐ RECOMMENDED
- **URL**: https://github.com/NuclearPhoenix/OpenGammaProject
- **Content**: Common gamma-ray emitting radioisotopes
- **Format**: SPE/N42 spectrum files
- **License**: Open source
- **Use Case**: Community-sourced hobby detector spectra (Cs-137, Co-60, Am-241, natural uranium)

### 3. RADAI Synthetic Urban Dataset
- **URL**: https://datadryad.org/stash/dataset/doi:10.5061/dryad.xgxd254h5
- **Content**: Simulated urban radiological environment spectra
- **Includes**: U-238 chain, Th-232 chain, Cs-137 background
- **Format**: HDF5 with labels
- **Size**: Training/validation/test splits included
- **Use Case**: Large-scale ML training with ground truth

### 4. JRC U/Pu Gamma Spectra (EU)
- **URL**: https://data.jrc.ec.europa.eu/
- **Content**: High-resolution certified reference spectra
- **Detector**: Portable HPGe and NaI
- **Use Case**: Validation/test set for uranium identification

### 5. Radiacode Isotope Library
- **URL**: https://radiacode.com/library
- **Content**: Reference spectra for 100+ isotopes
- **Format**: Radiacode native format (exportable)
- **Use Case**: Radiacode-specific training data

### Download Priority

| Dataset | Priority | Reason |
|---------|----------|--------|
| OpenGammaProject | 1️⃣ | Community spectra, similar detectors (NaI/CsI) |
| IAEA IDB | 2️⃣ | Authoritative U/Pu reference |
| RADAI Synthetic | 3️⃣ | Large scale, pre-labeled |
| JRC | 4️⃣ | Validation only (HPGe resolution differs) |



---

## Root Cause Analysis

### Why ML Underperforms

1. **Synthetic Training Gap**: Model learns idealized Gaussian peaks + Poisson noise, never sees real detector artifacts
2. **Missing Environmental Background**: Training has uniform background, real spectra have K-40/Radon peaks
3. **Simplified Compton**: Triangular approximation vs actual Klein-Nishina scattering
4. **No Calibration Drift**: All training at 3.0 keV/ch exactly; real detectors drift ±10%
5. **Limited Data Volume**: ~1800 samples insufficient for MLP generalization

---

## Improvement Phases

### Phase 1: Real Data Augmentation ⭐ HIGHEST IMPACT

**Goal**: Supplement synthetic training with real labeled spectra

**Data Sources Available**:
```
backend/data/acquisitions/     # 15+ real AlphaHound spectra (N42)
backend/data/community/        # Community-shared spectra
```

**Implementation**:

```python
# New file: backend/ml_data_loader.py

def load_real_spectra(directory: str) -> List[Tuple[np.ndarray, str]]:
    """Load real N42 spectra with auto-labeling from isotope identifications."""
    labeled_data = []
    for n42_file in Path(directory).glob("*.n42"):
        tree = ET.parse(n42_file)
        # Extract counts from ChannelData
        counts = parse_channel_data(tree)
        # Extract primary isotope from IsotopeIdentification
        isotope = get_top_isotope(tree)
        if isotope:
            labeled_data.append((counts, isotope))
    return labeled_data
```

**Training Integration**:
```python
# In ml_analysis.py lazy_train()
real_spectra = load_real_spectra("data/acquisitions")
# Weight real data 10x compared to synthetic
for counts, label in real_spectra:
    for _ in range(10):  # Replicate with noise variations
        augmented = add_poisson_noise(counts, factor=0.05)
        spectra_matrix[sample_idx] = augmented
        labels.append(label)
```

**Files to Modify**:
- `backend/ml_data_loader.py` (NEW)
- `backend/ml_analysis.py` (modify `lazy_train()`)

---

### Phase 2: Background Variation Training

**Goal**: Train model to ignore environmental radiation

**Implementation**:
```python
# Add realistic background to training spectra

BACKGROUND_TEMPLATE = {
    'K-40': {'channel': 487, 'intensity': 0.3},    # 1461 keV
    'Bi-214': {'channel': 203, 'intensity': 0.15}, # 609 keV (radon)
    'Tl-208': {'channel': 872, 'intensity': 0.05}  # 2614 keV
}

def add_background_variation(spectrum: np.ndarray) -> np.ndarray:
    """Add randomized environmental background."""
    bg_scale = np.random.uniform(0.5, 2.0)
    for isotope, params in BACKGROUND_TEMPLATE.items():
        peak = generate_peak(params['channel'], 
                            params['intensity'] * bg_scale)
        spectrum += peak
    return spectrum
```

**Expected Improvement**: Reduces false positives from background peaks

---

### Phase 3: Calibration Jitter

**Goal**: Make model robust to detector drift

**Implementation**:
```python
# In generate_training_spectrum()

def energy_to_channel_with_jitter(energy_keV: float, jitter: float = 0.1):
    """Convert energy with calibration variation."""
    keV_per_ch = 3.0 * np.random.uniform(1-jitter, 1+jitter)
    offset = np.random.uniform(-5, 5)  # keV
    return int((energy_keV - offset) / keV_per_ch)
```

**Expected Improvement**: Model generalizes across calibration differences

---

### Phase 4: Multi-Detector Support

**Goal**: Train separate models for AlphaHound vs Radiacode

**Detector Profiles**:
```python
DETECTOR_PROFILES = {
    'alphahound_csi': {
        'channels': 1024,
        'keV_per_channel': 3.0,
        'fwhm_662': 0.10,  # 10% at 662 keV
        'name': 'AlphaHound CsI(Tl)'
    },
    'radiacode_103': {
        'channels': 1024,
        'keV_per_channel': 2.93,
        'fwhm_662': 0.07,  # 7% - better CsI resolution
        'name': 'Radiacode 103'
    },
    'radiacode_103g': {
        'channels': 1024,
        'keV_per_channel': 2.93,
        'fwhm_662': 0.08,  # 8% - GMI crystal
        'name': 'Radiacode 103G'
    }
}
```

**Files to Modify**:
- `backend/ml_analysis.py` - Add detector_profile parameter
- `backend/routers/analysis.py` - Pass detector type from frontend

---

### Phase 5: Ensemble Hybrid Scoring

**Goal**: Combine ML + peak-matching for best results

**Algorithm**:
```python
def hybrid_identify(counts, peaks, detected_isotopes):
    """Combine ML and peak-matching confidence."""
    ml_results = ml_identifier.identify(counts)
    peak_results = detected_isotopes  # From existing pipeline
    
    combined = {}
    for r in ml_results:
        combined[r['isotope']] = {
            'ml_conf': r['confidence'],
            'peak_conf': 0
        }
    
    for r in peak_results:
        if r['isotope'] in combined:
            combined[r['isotope']]['peak_conf'] = r['confidence']
        else:
            combined[r['isotope']] = {
                'ml_conf': 0,
                'peak_conf': r['confidence']
            }
    
    # Weighted combination (peak-matching more reliable for known isotopes)
    final = []
    for isotope, scores in combined.items():
        final_score = 0.6 * scores['peak_conf'] + 0.4 * scores['ml_conf']
        final.append({
            'isotope': isotope,
            'confidence': final_score,
            'ml_conf': scores['ml_conf'],
            'peak_conf': scores['peak_conf'],
            'method': 'Hybrid (ML + Peak)'
        })
    
    return sorted(final, key=lambda x: x['confidence'], reverse=True)
```

---

### Phase 6: Model Architecture Improvements

**Current**: MLPClassifier with (128, 64) hidden layers

**Options**:

| Architecture | Pros | Cons |
|--------------|------|------|
| Deeper MLP (256, 128, 64) | More capacity | Slower training |
| 1D CNN | Feature position invariant | More complex |
| Attention-based | Peaks as tokens | Overkill for this problem |
| **Recommended: Regularized MLP** | Simple, fast | Needs tuning |

**Implementation**:
```python
self.model = MLPClassifier(
    hidden_layers=(256, 128, 64),
    dropout=0.3,
    learning_rate=1e-3
)
self.model.fit(train_ss, epochs=50, target_level='Isotope')
```

---

## Validation Strategy

### Test Dataset

Create holdout test set from real acquisitions:
```
data/acquisitions/test/  # 20% of real spectra, never used in training
```

### Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Top-1 Accuracy | >70% | ~20% |
| Top-3 Accuracy | >90% | ~50% |
| Uranium Detection Rate | >95% | ~60% |
| False Positive Rate (medical) | <5% | Unknown |

### Test Script

```bash
python test_ml_accuracy.py --model hobby --test-dir data/acquisitions/test
```

---

## Implementation Priority

| Phase | Effort | Impact | Priority | Status |
|-------|--------|--------|----------|--------|
| 1. Real Data Augmentation | Medium | ⭐⭐⭐⭐⭐ | **Highest** | ✅ Complete |
| 2. Background Variation | Low | ⭐⭐⭐ | High | ✅ Complete |
| 3. Calibration Jitter | Low | ⭐⭐⭐ | High | ✅ Complete |
| 4. Multi-Detector | Medium | ⭐⭐ | Medium | Planned |
| 5. Hybrid Scoring | Low | ⭐⭐⭐⭐ | High | ✅ Complete |
| 6. Architecture | High | ⭐⭐ | Low | Planned |

---

## Quick Wins (Can Implement Today)

1. **Increase training samples**: Change `samples_per_isotope: 30` → `100`
2. **More epochs**: Change `epochs=25` → `epochs=50`
3. **Add dropout**: Prevent overfitting on synthetic patterns
4. **Lower confidence threshold**: Show predictions >0.5% instead of >1%

---

## Files Reference

| File | Purpose |
|------|---------|
| `backend/ml_analysis.py` | Main ML training and prediction |
| `backend/ml_identifier.py` | Legacy ML wrapper (unused) |
| `backend/isotope_database.py` | IAEA gamma energies + intensities |
| `backend/iaea_parser.py` | IAEA CSV data parser |
| `backend/data/idb/isotopes/` | 49 isotope CSV files from IAEA |
| `backend/data/acquisitions/` | Real AlphaHound spectra (N42) |

---

## Success Criteria

- [ ] Top-1 accuracy >70% on uranium glass spectra
- [ ] Correctly identifies Bi-214/Pb-214 as primary peaks
- [ ] Does not misidentify as Sb-125, Ta-182, or Pu-239
- [ ] Works for both AlphaHound and Radiacode spectra
- [ ] Training time <60 seconds on first run
