# PyRIID Integration Guide

## 📘 Overview

This guide explains how **PyRIID** (Python Radioisotope Identification Dataset) is integrated into RadTrace for machine learning-based isotope identification. PyRIID is developed by **Sandia National Laboratories** and provides neural network classifiers optimized for gamma spectroscopy.

---

## 🤖 What is PyRIID?

**PyRIID** is an open-source Python library for machine learning-based radioisotope identification:

- **Author**: Sandia National Laboratories
- **Repository**: [github.com/sandialabs/PyRIID](https://github.com/sandialabs/PyRIID)
- **License**: BSD-3-Clause
- **Version Used**: 2.2.0

### Key Components

| Component | Description |
|-----------|-------------|
| `SampleSet` | Container for gamma spectra with metadata |
| `MLPClassifier` | Multi-layer perceptron neural network classifier |
| `spectra` | 2D DataFrame (samples × channels) |
| `sources` | One-hot encoded isotope labels with MultiIndex |
| `prediction_probas` | Classification probabilities after prediction |

---

## 🎯 AlphaHound Detector Tuning

The ML integration is **specifically tuned** for the AlphaHound AB+G detector:

### Detector Parameters Used

| Parameter | Value | Source |
|-----------|-------|--------|
| **Channels** | 1024 | AlphaHound standard |
| **Energy Range** | 0-3069 keV | 3 keV/channel |
| **Crystal Type** | CsI(Tl) | Current production model |
| **Resolution (FWHM)** | 10% @ 662 keV | Official spec |
| **Sensitivity** | 48 cps/µSv/h | Official spec |

### Energy-Dependent Resolution Model

The ML training uses a **scintillator resolution model** that matches CsI(Tl) physics:

```
FWHM(E) = 0.10 × E × √(662/E)
```

| Energy (keV) | FWHM (keV) | FWHM (channels) | Resolution |
|--------------|------------|-----------------|------------|
| 186 | ~35 | ~12 | 18.8% |
| 662 | 66.2 | ~22 | 10.0% |
| 1461 | ~98 | ~33 | 6.7% |

This creates **realistic peak shapes** during training that match actual AlphaHound spectra.

### Code Implementation

```python
# In MLIdentifier class
def get_fwhm_channels(self, energy_keV: float) -> int:
    """Calculate FWHM in channels for AlphaHound CsI(Tl)."""
    # FWHM in keV using scintillator resolution scaling
    fwhm_keV = 0.10 * energy_keV * (662 / energy_keV) ** 0.5
    fwhm_channels = max(3, int(fwhm_keV / 3.0))  # 3 keV/channel
    return fwhm_channels
```

---

## 🔧 How the Integration Works

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     RadTrace Frontend                        │
│  ┌─────────────────┐    ┌─────────────────────────────────┐ │
│  │ "🤖 AI Identify"│───▶│   POST /analyze/ml-identify     │ │
│  │     Button      │    │   (backend/routers/analysis.py) │ │
│  └─────────────────┘    └─────────────────────────────────┘ │
└──────────────────────────────────────┬──────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  backend/ml_analysis.py                      │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                   MLIdentifier Class                      ││
│  │  ┌───────────────┐  ┌──────────────┐  ┌───────────────┐ ││
│  │  │  lazy_train() │  │  identify()  │  │ get_ml_ident  │ ││
│  │  │  (First Run)  │  │ (Prediction) │  │ ifier()       │ ││
│  │  └───────┬───────┘  └──────┬───────┘  └───────────────┘ ││
│  └──────────┼─────────────────┼────────────────────────────┘│
└─────────────┼─────────────────┼─────────────────────────────┘
              │                 │
              ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│                    PyRIID Library                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │    SampleSet    │  │  MLPClassifier  │  │ TensorFlow   │ │
│  │   (Data Store)  │  │ (Neural Net)    │  │ (Backend)    │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Training Pipeline

The model trains **lazily** (on first prediction request) using synthetic spectra:

```python
# Step 1: Import authoritative isotope database
from isotope_database import ISOTOPE_DATABASE_ADVANCED
# Contains 100+ isotopes with gamma-ray energies from IAEA/NNDC

# Step 2: Generate synthetic training spectra
# - 15 samples per single isotope (90+ isotopes)
# - 25 samples per mixture (7 mixture types)
# - Total: ~1,500 training samples

# Step 3: Create SampleSet for PyRIID
train_ss = SampleSet()
train_ss.spectra = pd.DataFrame(spectra_matrix)  # 2D: samples × channels
train_ss.spectra_type = 3   # Gross spectrum
train_ss.spectra_state = 1  # Raw counts

# Step 4: Create one-hot encoded source labels
# PyRIID requires 3-level MultiIndex: ('Category', 'Isotope', 'Seed')
sources_df.columns = pd.MultiIndex.from_tuples(
    [('Radionuclide', isotope_name, '') for isotope_name in isotopes],
    names=SampleSet.SOURCES_MULTI_INDEX_NAMES
)
train_ss.sources = sources_df

# Step 5: Train MLPClassifier
model = MLPClassifier()
model.fit(train_ss, epochs=25, target_level='Isotope', verbose=False)
```

### Prediction Pipeline

```python
# Step 1: Prepare input spectrum
test_ss = SampleSet()
test_ss.spectra = pd.DataFrame(spectrum_array.reshape(1, -1))  # 1 sample
test_ss.spectra_type = 3   # Gross
test_ss.spectra_state = 1  # Counts

# Step 2: Run prediction (modifies SampleSet in-place)
model.predict(test_ss)

# Step 3: Extract probabilities
probas = test_ss.prediction_probas
# Returns DataFrame with isotope columns and probability values
```

---

## 📊 Training Data

### Single Isotopes

The model trains on **90+ isotopes** from authoritative sources:

| Source | Description |
|--------|-------------|
| IAEA NDS | Nuclear Data Services database |
| NNDC ENSDF | Evaluated Nuclear Structure Data File |
| CapGam | Capture gamma-ray database |
| LBNL | Lawrence Berkeley National Lab isotope data |

Each isotope has characteristic gamma-ray energies. For example:
- **Cs-137**: 661.7 keV
- **Co-60**: 1173.2 keV, 1332.5 keV
- **Am-241**: 59.5 keV
- **Bi-214**: 609.3 keV, 1120.3 keV, 1764.5 keV

### Multi-Isotope Mixtures

The model also recognizes **7 realistic source mixtures**:

| Mixture | Isotopes | Description |
|---------|----------|-------------|
| **UraniumGlass** | Bi-214, Pb-214, Ra-226, Th-234, U-238 | Uranium glass / Fiestaware |
| **UraniumGlassWeak** | Same as above, lower intensity | Weaker uranium sample |
| **ThoriumMantle** | Th-232, Ac-228, Tl-208, Pb-212 | Gas lantern mantles |
| **MedicalWaste** | Tc-99m, I-131, Mo-99 | Hospital nuclear medicine |
| **IndustrialGauge** | Cs-137, Co-60 | Level/density gauges |
| **CalibrationSource** | Am-241, Ba-133, Cs-137, Co-60 | Multi-isotope check source |
| **NaturalBackground** | K-40, Bi-214, Tl-208 | Typical environmental background |

### Synthetic Spectrum Generation

Each training sample is generated with realistic characteristics:

```python
# 1. Start with Poisson-distributed background noise
spectra = np.random.poisson(5, (n_samples, 1024))

# 2. Add Gaussian peaks at characteristic gamma energies
for energy_keV in isotope_energies:
    channel = int(energy_keV / 3.0)  # 3 keV/channel calibration
    
    # Intensity decreases with energy (typical detector response)
    intensity = max(50, 300 - energy_keV / 10)
    
    # Add Gaussian peak (FWHM ~3 channels for NaI/CsI detectors)
    half_width = 3
    peak_counts = np.random.poisson(intensity, width)
    spectra[sample, channel-hw:channel+hw] += peak_counts
```

---

## 🎯 Using ML Identification in RadTrace

### Prerequisites

1. **Full Installation Mode** (includes PyRIID):
   ```bash
   install.bat
   # or
   pip install git+https://github.com/sandialabs/pyriid.git@main
   ```

2. **Verify Installation** (check startup logs):
   ```
   [ML] PyRIID successfully imported
   [ML] Loaded 100 isotopes from database
   ```

### Step-by-Step Usage

1. **Load a Spectrum**
   - Upload N42/CSV file, or
   - Acquire from AlphaHound device

2. **Click "🤖 AI Identify"**
   - First run: ~30-60 seconds (training)
   - Subsequent runs: ~1-2 seconds

3. **View Results**
   - Results appear in "AI Identification (ML)" panel
   - Purple gradient confidence bars
   - Sorted by confidence (highest first)

### API Endpoint

```http
POST /analyze/ml-identify
Content-Type: application/json

{
  "counts": [10, 12, 15, 8, 9, ...]  // 1024-element array
}
```

**Response:**
```json
{
  "predictions": [
    {"isotope": "UraniumGlass", "confidence": 87.3, "method": "ML (PyRIID)"},
    {"isotope": "Bi-214", "confidence": 8.2, "method": "ML (PyRIID)"},
    {"isotope": "Ra-226", "confidence": 2.1, "method": "ML (PyRIID)"}
  ],
  "ml_available": true
}
```

---

## ⚠️ Limitations & Best Practices

### When ML Works Best

✅ **Real Detector Data**: Spectra with Poisson noise statistics
✅ **Known Source Types**: Matches trained mixtures (uranium glass, thorium, etc.)
✅ **Strong Signals**: Spectra with clear peaks above background
✅ **Standard Calibration**: ~3 keV/channel energy calibration

### When ML May Struggle

❌ **Synthetic Demo Files**: Constant background, no noise → Pattern mismatch
❌ **Very Weak Sources**: Low count rates may confuse classifier
❌ **Unknown Mixtures**: Novel isotope combinations not in training data
❌ **Uncalibrated Spectra**: Channel-only data without energy calibration

### Interpretation Tips

| Confidence | Interpretation |
|------------|----------------|
| >80% | **Strong match** - High confidence identification |
| 50-80% | **Possible match** - Verify with Peak Matching |
| 20-50% | **Weak suggestion** - Use as starting point |
| <20% | **Uncertain** - May be background or unknown |

### Comparison: ML vs Peak Matching

| Method | Strengths | Weaknesses |
|--------|-----------|------------|
| **Peak Matching** | Precise energy identification, Works on any data | Requires clear peaks, Sensitive to energy tolerance |
| **ML (PyRIID)** | Pattern recognition, Identifies mixtures, Fast | Needs training data match, Black-box confidence |

**Best Practice**: Use both methods together!
- Peak Matching for precise isotope identification
- ML for mixture recognition and confirmation

---

## 🔬 Technical Details

### PyRIID 2.2.0 API Requirements

The integration handles several PyRIID-specific requirements:

```python
# 1. Spectra must be 2D DataFrame (rows=samples, cols=channels)
train_ss.spectra = pd.DataFrame(matrix_2d)

# 2. Sources require 3-level MultiIndex
# Format: ('Category', 'Isotope', 'Seed')
columns = pd.MultiIndex.from_tuples(
    [('Radionuclide', name, '') for name in isotopes],
    names=['Category', 'Isotope', 'Seed']
)

# 3. Required metadata
train_ss.spectra_type = 3   # Gross (vs. Background-subtracted)
train_ss.spectra_state = 1  # Counts (vs. Rate)

# 4. predict() modifies SampleSet in-place
model.predict(test_ss)  # No return value!
probas = test_ss.prediction_probas  # Results stored here
```

### Spectrum Handling

```python
# Energy-to-channel conversion
keV_per_channel = 3.0
n_channels = 1024

def energy_to_channel(energy_keV):
    return int(energy_keV / keV_per_channel)

# Spectrum resizing (if input doesn't match training)
if len(spectrum) < 1024:
    spectrum = np.pad(spectrum, (0, 1024 - len(spectrum)))
elif len(spectrum) > 1024:
    spectrum = spectrum[:1024]
```

### Model Caching

The model is cached as a global singleton to avoid retraining:

```python
_ml_identifier = None

def get_ml_identifier():
    global _ml_identifier
    if _ml_identifier is None:
        _ml_identifier = MLIdentifier()  # Lazy training on first use
    return _ml_identifier
```

---

## 📚 Further Resources

### PyRIID Documentation
- **Repository**: [github.com/sandialabs/PyRIID](https://github.com/sandialabs/PyRIID)
- **Paper**: Holland et al. (2024) "PyRIID: Machine Learning-based Radioisotope Identification"
- **Citation**:
  ```
  @software{pyriid,
    author = {Darren Holland et al.},
    title = {PyRIID: Machine Learning-based Radioisotope Identification},
    year = {2024},
    publisher = {Sandia National Laboratories},
    url = {https://github.com/sandialabs/PyRIID}
  }
  ```

### Related Files in This Project

| File | Description |
|------|-------------|
| `backend/ml_analysis.py` | ML integration module |
| `backend/isotope_database.py` | Authoritative gamma-ray energy database |
| `backend/routers/analysis.py` | `/analyze/ml-identify` endpoint |
| `backend/static/js/main.js` | Frontend ML button handler |

---

## 🛠️ Extending & Enhancing the ML Integration

Users can customize and enhance the ML functionality in several ways:

### 1. Adding Custom Isotopes to Training

Add new isotopes to `backend/isotope_database.py`:

```python
# In ISOTOPE_DATABASE_ADVANCED dictionary:
'My-Custom-Isotope': [123.4, 456.7, 789.0],  # Gamma energies in keV
```

Then restart the server. The ML model will automatically include your custom isotopes in training.

### 2. Creating New Mixture Types

Edit the `mixtures` dictionary in `backend/ml_analysis.py`:

```python
mixtures = {
    # Add your custom mixture:
    'MyCustomMixture': {
        'isotopes': ['Cs-137', 'Co-60', 'Am-241'],
        'ratios': [1.0, 0.8, 0.5]  # Relative peak intensities
    },
    # ... existing mixtures
}
```

**Ratio Guidelines:**
- `1.0` = Primary/dominant isotope
- `0.5-0.8` = Secondary isotopes
- `0.1-0.3` = Minor contributors

### 3. Tuning Training Parameters

Modify `lazy_train()` in `backend/ml_analysis.py`:

```python
# Increase training samples for better accuracy
n_samples_per_single = 25   # Default: 15
n_samples_per_mixture = 40  # Default: 25

# Adjust training epochs (more = better but slower)
self.model.fit(train_ss, epochs=50, ...)  # Default: 25

# Modify peak shape (detector-specific)
half_width = 5  # Wider peaks for NaI, narrower for HPGe
```

### 4. Adjusting Energy Calibration

If your detector uses different calibration:

```python
# In MLIdentifier.__init__():
self.keV_per_channel = 2.5  # Default: 3.0 keV/channel
self.n_channels = 2048       # Default: 1024
```

### 5. Changing Confidence Thresholds

Edit `identify()` in `backend/ml_analysis.py`:

```python
# Lower threshold shows more predictions
if conf_pct > 0.5:  # Default: 1.0 (show anything >1%)
    results.append(...)

# Or add high-confidence filtering
if conf_pct > 50.0:  # Only high-confidence results
    results.append(...)
```

### 6. Using Real Training Data

Replace synthetic training with your own recorded spectra:

```python
def train_on_real_data(self, spectra_files):
    """Train on user-provided real spectra."""
    train_ss = SampleSet()
    
    # Load your labeled spectra
    spectra_list = []
    labels = []
    for file_path, isotope_label in spectra_files:
        data = load_spectrum(file_path)  # Your loading function
        spectra_list.append(data['counts'])
        labels.append(isotope_label)
    
    train_ss.spectra = pd.DataFrame(spectra_list)
    # ... continue with existing training code
```

### 7. Adding New ML Models

PyRIID supports multiple classifier types:

```python
from riid.models import MLPClassifier, LabelProportionEstimator

# Switch classifier type
self.model = LabelProportionEstimator()  # Alternative to MLP

# Or use ensemble
models = [MLPClassifier(), MLPClassifier()]
# Train each model and combine predictions
```

### 8. Improving Mixture Detection

Add mixture-specific post-processing:

```python
def identify(self, counts, top_k=5):
    results = self._base_identify(counts)
    
    # Add mixture component breakdown
    for result in results:
        if result['isotope'] in self.mixture_definitions:
            result['components'] = self.mixture_definitions[result['isotope']]['isotopes']
            result['is_mixture'] = True
    
    return results
```

### 9. Caching Trained Models to Disk

Save training time by persisting the model:

```python
import pickle

def save_model(self, path='model.pkl'):
    with open(path, 'wb') as f:
        pickle.dump(self.model, f)

def load_model(self, path='model.pkl'):
    with open(path, 'rb') as f:
        self.model = pickle.load(f)
        self.is_trained = True
```

### 10. Contributing Improvements

If you develop improvements, consider contributing:

1. **Fork the repository** on GitHub
2. **Create a feature branch**: `git checkout -b feature/my-enhancement`
3. **Test thoroughly** with real detector data
4. **Submit a Pull Request** with description of changes

**High-value contributions:**
- New mixture definitions for common sources
- Improved synthetic spectrum generation
- Real detector training datasets
- Alternative classifier architectures

---

## ✅ Summary

| Aspect | Details |
|--------|---------|
| **Library** | PyRIID 2.2.0 by Sandia National Labs |
| **Model** | MLPClassifier (Multi-layer Perceptron) |
| **Training** | 90+ isotopes + 7 mixtures (~1500 samples) |
| **Data Source** | IAEA NDS, NNDC/ENSDF, CapGam |
| **Training Time** | ~30-60s on first run (cached) |
| **Prediction Time** | ~1-2 seconds |
| **Confidence Range** | 0-100% |
| **Best For** | Mixture identification, Real detector data |

---

*Last Updated: 2025-12-12*
*RadTrace v2.x - PyRIID Integration Guide*
