# RadTrace Calibration & Accuracy Guide

## 📘 Overview

This guide covers energy calibration fundamentals, AlphaHound device calibration, and techniques to improve detection accuracy for both PyRIID machine learning and manual peak detection methods.

---

## 🎯 Energy Calibration Fundamentals

### What is Energy Calibration?

Gamma spectrometers measure photon energies indirectly. The detector outputs a signal proportional to energy, which is digitized into "channels." Energy calibration converts channel numbers to actual energy values (keV).

### Linear Calibration Model

Most gamma spectrometers use a linear calibration:

```
Energy (keV) = Slope × Channel + Intercept
```

For a 1024-channel spectrometer:
- **AlphaHound**: ~7.39 keV/channel, 15 keV offset → Range: 15-7572 keV
- **Typical NaI**: ~3.0 keV/channel, 0 keV offset → Range: 0-3069 keV

### Calibration Procedure

```mermaid
flowchart LR
    A[Collect Spectrum] --> B[Identify Known Peaks]
    B --> C[Record Channel Numbers]
    C --> D[Calculate Slope/Intercept]
    D --> E[Apply to All Channels]
```

#### Step-by-Step:

1. **Acquire spectrum** from a known source (e.g., Cs-137, Co-60)
2. **Find peak channels** in the raw spectrum
3. **Match to known energies**:
   - Cs-137: 661.7 keV
   - Co-60: 1173.2 keV, 1332.5 keV
4. **Calculate calibration**:
   ```python
   # Two-point calibration
   slope = (E2 - E1) / (Ch2 - Ch1)
   intercept = E1 - slope * Ch1
   ```

---

## 🔧 AlphaHound Device Calibration

### Current Device Calibration

> [!IMPORTANT]
> **Verified AlphaHound Calibration:**
> - Channels: 1024
> - Energy Range: 15 - 7572 keV
> - Slope: ~7.39 keV/channel
> - Crystal: CsI(Tl), 1.1 cm³
> - Resolution: ≤10% FWHM at 662 keV

### Calibration Verification Test

A 6-hour uranium glass spectrum (190,623 counts) was used to verify calibration:

| Calibration | Peak 1 | Peak 2 | Peak 3 | U-238 Detection | U-235 (False Positive) |
|-------------|--------|--------|--------|-----------------|------------------------|
| Device (7.4 keV/ch) | 108 keV | 78 keV | 42 keV | ✅ HIGH | ❌ Not detected |
| Wrong (3 keV/ch) | 165 keV | 111 keV | 48 keV | ✅ HIGH | ⚠️ 75% FALSE |

**Conclusion**: Device calibration is CORRECT. Do NOT use 3 keV/channel assumption.

### Detector Specifications

| Parameter | CsI(Tl) (Current) | BGO (Legacy) |
|-----------|-------------------|--------------|
| Volume | 1.1 cm³ | 0.6 cm³ |
| Sensitivity | 48 cps/μSv/h | 42 cps/μSv/h |
| Resolution @ 662 keV | ≤10% FWHM | ≤13% FWHM |
| Min Energy | ~20 keV | ~50 keV |

---

## 📊 Adding Reference Spectra for PyRIID

### Why Add More Training Spectra?

The ML model's accuracy depends on training data quality. Adding real detector spectra improves:
- Recognition of actual peak shapes
- Handling of detector-specific noise patterns
- Accuracy on weak sources

### Collecting Training Spectra

#### Required Information Per Spectrum:

1. **Source identification** (isotope or mixture)
2. **Acquisition time** (seconds)
3. **Total counts**
4. **Calibration parameters**

#### Recording Process:

```bash
# 1. Place known source near detector
# 2. Start acquisition (5-10 minutes recommended)
# 3. Save spectrum to CSV
# 4. Label with source type
```

### Adding Spectra to Training

Edit `backend/ml_analysis.py`:

```python
def load_real_training_data(self):
    """Load user-provided training spectra from files."""
    training_dir = "data/training/"
    real_spectra = []
    real_labels = []
    
    for filename in os.listdir(training_dir):
        if filename.endswith('.csv'):
            # Parse filename for label: "Cs137_sample1.csv" -> "Cs-137"
            label = filename.split('_')[0].replace('137', '-137')
            
            # Load spectrum
            spectrum = load_spectrum_csv(os.path.join(training_dir, filename))
            real_spectra.append(spectrum)
            real_labels.append(label)
    
    return real_spectra, real_labels
```

### Training Data Directory Structure

```
backend/data/training/
├── Cs137_sample1.csv
├── Cs137_sample2.csv
├── Co60_sample1.csv
├── Am241_sample1.csv
├── UraniumGlass_sample1.csv
└── Background_sample1.csv
```

---

## ⚡ Adding Energy Points for Better Detection

### Expanding the Isotope Database

The isotope database directly affects detection accuracy. To add more reference energies:

#### 1. Find Authoritative Data

- **NNDC**: [https://www.nndc.bnl.gov/nudat3/](https://www.nndc.bnl.gov/nudat3/)
- **IAEA NDS**: [https://www-nds.iaea.org/](https://www-nds.iaea.org/)
- **LBNL**: [https://ie.lbl.gov/toi/](https://ie.lbl.gov/toi/)

#### 2. Add to Database

Edit `backend/isotope_database.py`:

```python
# Add more energy lines with intensity > ~5%
ISOTOPE_DATABASE_ADVANCED = {
    # Existing: Only main peaks
    "Bi-214": [609.3, 1120.3, 1764.5],
    
    # Improved: All significant peaks with intensity > 5%
    "Bi-214": [
        609.3,   # 46.1% - strongest
        1764.5,  # 15.4%
        1120.3,  # 15.0%
        1238.1,  # 5.8%
        768.4,   # 4.9%
        1377.7,  # 4.0%
        2204.2,  # 5.0%
        2448.0,  # 1.6%
    ],
}
```

### Key Isotopes to Enhance

#### U-238 Decay Chain (Most Important for Hobbyists)

| Isotope | Current Energies | Recommended Additions |
|---------|------------------|----------------------|
| **Th-234** | [92.5] | [63.3, 92.5] |
| **Pa-234m** | [1001.0] | [766.4, 1001.0] |
| **Ra-226** | [186.2] | [186.2] (gamma-poor) |
| **Pb-214** | [295.2, 351.9] | [241.9, 295.2, 351.9] |
| **Bi-214** | [609.3, 1120.3, 1764.5] | All 8 peaks above |

#### Th-232 Decay Chain

| Isotope | Current Energies | Recommended Additions |
|---------|------------------|----------------------|
| **Ac-228** | [911.2, 338.3, 968.9] | [209.3, 270.2, 338.3, 463.0, 794.9, 835.7, 911.2, 964.8, 968.9] |
| **Tl-208** | [583.2, 2614.5, 860.6] | [277.4, 510.8, 583.2, 860.6, 2614.5] |
| **Pb-212** | [238.6] | [238.6, 300.1] |

#### Common Calibration Sources

| Source | Energies (keV) | Notes |
|--------|----------------|-------|
| **Am-241** | 59.5 | Low energy calibration point |
| **Ba-133** | 81.0, 276.4, 302.9, 356.0, 383.8 | Multiple peaks |
| **Cs-137** | 661.7 | Standard reference |
| **Co-60** | 1173.2, 1332.5 | High energy pair |
| **K-40** | 1460.8 | Natural background |
| **Tl-208** | 2614.5 | Highest common gamma |

---

## 🎚️ Tuning Peak Detection Parameters

### Algorithm Parameters

The peak detection in `backend/peak_detection.py` can be tuned:

```python
def detect_peaks(energies, counts, prominence_factor=0.05, distance=10):
    """
    Detect peaks in spectrum data.
    
    Args:
        prominence_factor: Minimum prominence as fraction of max counts
        distance: Minimum distance between peaks (in indices/channels)
    """
```

### Tuning Guide

| Scenario | Prominence Factor | Distance | Notes |
|----------|-------------------|----------|-------|
| **Strong sources** | 0.05 (5%) | 10 | Default settings |
| **Weak sources** | 0.02 (2%) | 8 | More sensitive |
| **High-res detector** | 0.03 (3%) | 5 | NaI with good resolution |
| **CsI(Tl) @ low energy** | 0.04 (4%) | 15 | Broader peaks |
| **High background** | 0.08 (8%) | 12 | Reduce false peaks |

### Example: Weak Source Settings

```python
# For weak sources (< 1000 total counts)
WEAK_SOURCE_SETTINGS = {
    'prominence_factor': 0.02,  # 2% of max
    'distance': 8,              # Channels between peaks
    'height_factor': 0.005      # 0.5% of max
}
```

---

## 🧮 Energy Tolerance Adjustment

### What is Energy Tolerance?

When matching detected peaks to database energies, tolerance defines the acceptable difference:

```python
# Peak at 660 keV matches Cs-137 (661.7 keV) if tolerance ≥ 1.7 keV
match = abs(peak_energy - isotope_energy) <= tolerance
```

### Recommended Tolerances by Detector

| Detector Type | Resolution @ 662 keV | Recommended Tolerance |
|---------------|---------------------|----------------------|
| HPGe | 0.2% (1.3 keV) | 3-5 keV |
| NaI(Tl) 2×2" | 7% (46 keV) | 15-20 keV |
| CsI(Tl) AlphaHound | 10% (66 keV) | 20-30 keV |
| BGO | 13% (86 keV) | 30-40 keV |

### Dynamic Tolerance

For best results, tolerance should scale with energy:

```python
def get_tolerance(energy_keV, base_resolution=0.10):
    """
    Calculate energy-dependent tolerance based on detector resolution.
    
    Args:
        energy_keV: Peak energy
        base_resolution: Resolution at 662 keV (e.g., 0.10 for 10%)
    """
    # Scintillator resolution scales as sqrt(1/E)
    fwhm = base_resolution * energy_keV * (662 / energy_keV) ** 0.5
    
    # Tolerance = ~1.5 × FWHM is typical
    tolerance = fwhm * 1.5
    return tolerance
```

---

## 🎯 Improving PyRIID ML Accuracy

### Training Parameters

Edit `backend/ml_analysis.py`:

```python
class MLIdentifier:
    def lazy_train(self):
        # Increase samples for better coverage
        n_samples_per_single = 25   # Default: 15
        n_samples_per_mixture = 40  # Default: 25
        
        # More epochs for deeper learning
        self.model.fit(train_ss, epochs=50, ...)  # Default: 25
```

### Peak Shape Modeling

Adjust synthetic peak generation for your detector:

```python
def get_fwhm_channels(self, energy_keV: float) -> int:
    """
    Calculate FWHM for your specific detector.
    
    For CsI(Tl) AlphaHound: 10% @ 662 keV
    For NaI(Tl) 2×2": 7% @ 662 keV
    For BGO: 13% @ 662 keV
    """
    # Your detector's resolution at 662 keV
    resolution_at_662keV = 0.10  # 10% for CsI(Tl)
    
    # Energy-dependent scaling
    fwhm_keV = resolution_at_662keV * energy_keV * (662 / energy_keV) ** 0.5
    fwhm_channels = max(3, int(fwhm_keV / self.keV_per_channel))
    return fwhm_channels
```

### Adding Low-Count Scenarios

Train on weak source conditions:

```python
# In lazy_train(), after generating standard spectra:
for isotope in isotopes:
    for i in range(5):  # 5 weak source samples per isotope
        # Low background (1-2 counts/channel)
        spectrum = np.random.poisson(1.5, 1024)
        
        # Weak peaks (10-30 counts above background)
        for energy in isotope_energies:
            channel = self.energy_to_channel(energy)
            intensity = np.random.randint(10, 30)
            # Add Gaussian peak...
        
        spectra_list.append(spectrum)
        labels.append(isotope)
```

---

## 📋 Reference Energy Tables

### Natural Uranium (U-238 Chain)

| Isotope | Energy (keV) | Intensity | Notes |
|---------|--------------|-----------|-------|
| **Th-234** | 63.3 | 4.8% | X-ray |
| **Th-234** | 92.6 | 5.6% | Primary gamma |
| **Pa-234m** | 766.4 | 0.3% | Weak |
| **Pa-234m** | 1001.0 | 0.8% | Best Pa-234m peak |
| **Ra-226** | 186.2 | 3.6% | Often obscured by U-235 |
| **Pb-214** | 241.9 | 7.3% | |
| **Pb-214** | 295.2 | 18.4% | Strong |
| **Pb-214** | 351.9 | 35.6% | Strongest Pb-214 |
| **Bi-214** | 609.3 | 45.5% | **Strongest in chain** |
| **Bi-214** | 768.4 | 4.9% | |
| **Bi-214** | 1120.3 | 14.9% | |
| **Bi-214** | 1238.1 | 5.8% | |
| **Bi-214** | 1764.5 | 15.3% | High energy marker |
| **Bi-214** | 2204.1 | 4.9% | |

### Thorium (Th-232 Chain)

| Isotope | Energy (keV) | Intensity | Notes |
|---------|--------------|-----------|-------|
| **Ac-228** | 338.3 | 11.3% | |
| **Ac-228** | 463.0 | 4.4% | |
| **Ac-228** | 794.9 | 4.3% | |
| **Ac-228** | 911.2 | 25.8% | Strongest Ac-228 |
| **Ac-228** | 968.9 | 15.8% | |
| **Pb-212** | 238.6 | 43.6% | Strongest Pb-212 |
| **Bi-212** | 727.3 | 6.7% | |
| **Tl-208** | 277.4 | 2.3% | |
| **Tl-208** | 510.8 | 8.1% | Annihilation overlap |
| **Tl-208** | 583.2 | 30.6% | Strong |
| **Tl-208** | 860.6 | 4.5% | |
| **Tl-208** | 2614.5 | 35.8% | **Highest gamma** |

### Common Calibration Sources

| Isotope | Energy (keV) | Intensity | Half-Life |
|---------|--------------|-----------|-----------|
| **Am-241** | 59.5 | 35.9% | 432 years |
| **Ba-133** | 81.0 | 32.9% | 10.5 years |
| **Ba-133** | 276.4 | 7.2% | |
| **Ba-133** | 302.9 | 18.3% | |
| **Ba-133** | 356.0 | 62.1% | Strongest |
| **Ba-133** | 383.8 | 8.9% | |
| **Cs-137** | 661.7 | 85.1% | 30.2 years |
| **Co-60** | 1173.2 | 99.9% | 5.3 years |
| **Co-60** | 1332.5 | 100.0% | |
| **Na-22** | 511.0 | 180.7% | 2.6 years |
| **Na-22** | 1274.5 | 99.9% | |

### Natural Background

| Source | Energy (keV) | Origin |
|--------|--------------|--------|
| **K-40** | 1460.8 | Potassium in rocks/soil |
| **Bi-214** | 609.3, 1764.5 | Radon daughters |
| **Tl-208** | 2614.5 | Thorium in soil |

---

## ✅ Calibration Checklist

### Before Acquisition

- [ ] Verify detector connection and dose rate display
- [ ] Check device calibration hasn't drifted
- [ ] Ensure proper source placement
- [ ] Set appropriate acquisition time (5+ minutes for weak sources)

### Calibration Verification

- [ ] Acquire spectrum from known source (Cs-137 recommended)
- [ ] Check peak appears at expected energy (661.7 keV for Cs-137)
- [ ] Verify FWHM matches detector specs
- [ ] Record calibration parameters if drifted

### Accuracy Optimization

- [ ] Adjust energy tolerance for your detector type
- [ ] Add missing isotope energies to database
- [ ] Consider adding training spectra for PyRIID
- [ ] Tune peak detection parameters for source strength

---

## 📚 Related Documentation

- [Theory of Operation](THEORY_OF_OPERATION.md) - System architecture
- [PyRIID Guide](PYRIID_GUIDE.md) - ML integration details
- [Modularity Guide](MODULARITY_GUIDE.md) - Extending the application
- [README](README.md) - Quick start guide

---

*Last Updated: 2024-12-14*
*RadTrace Calibration & Accuracy Guide v1.0*
